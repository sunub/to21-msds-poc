"""설명 생성: 약속 ③ finding → 요청 → 모델(또는 문장틀) → 검사. 문장틀과 환각 검사는 compliance/explain.py 를 그대로 쓴다.

판정·구분은 모델 응답에서 받지 않는다. 검사에 두 번 걸리거나 모델이 없으면 문장틀로 대체하고 by=template 로 남긴다.
"""
import hashlib
import json
import os
import re
import threading
from contextlib import contextmanager

from msds.compliance import explain as engine

_KIND = {"mixture_calc": "mixture", "reference_lookup": "reference", "label_check": "label",
         "regulation_check": "regulation", "dg_check": "regulation"}
EXPLAIN_MODEL_DEFAULT = "qwen36_35b_runpod"


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256(obj) -> str:
    return hashlib.sha256(canonical(obj)).hexdigest()


def build_request(f: dict, trace: dict | None) -> dict:
    msds, exp = f["msds"], f["expected"]
    if f["section"] == "15":
        finding = {"item": f["item"], "item_name": f["label"], "component": (f["comp"] or {}).get("comp_ref", "MIX"),
                   "msds": {"applicable": msds.get("applicable"), "threshold": msds.get("threshold")},
                   "expected": {"applicable": exp.get("applicable"), "threshold": exp.get("threshold")}}
    elif f["kind"] == "label":
        finding = {"item": f["item"], "item_name": f["label"], "msds": {"code": msds.get("code")},
                   "expected": {"code": exp.get("code")}}
    else:
        finding = {"item": f["item"], "item_name": f["label"],
                   "msds": {"category": msds.get("category"), "route_form": msds.get("route_form")},
                   "expected": {"low": exp.get("low"), "high": exp.get("high"), "route_form": exp.get("route_form")}}
    causes = (trace or {}).get("cause_texts") or [{"code": c, "text": f["reason"]} for c in f["causes"]]
    # 원인이 있으면 엔진 표기인 reason 은 보내지 않는다. 같은 내용을 causes 가 읽는 말로 담는다 (우진 설명 측정 4~6차)
    finding = {"id": f["id"], "section": f["section"], "kind": f["kind"], **finding, "verdict": f["verdict"], "type": f["type"],
               "severity": f["severity"], "reason": None if causes else f["reason"]}
    # compact_trace 는 엔진의 trace 이름을 읽는다
    compact = engine.compact_trace({**trace, "kind": _KIND.get(trace["kind"], trace["kind"])}) if trace else None
    if compact and any(c["code"] == "CONDITION_CHECK" for c in causes):
        compact.pop("db_text", None)  # 조문의 제품 형태를 이 제품으로 읽는 일이 있어 뺀다 (우진 측정 3차)
    evidence = [{"page": e.get("page"), "text": (e.get("source_text") or "")[:200], "field": e.get("field")}
                for e in msds.get("evidence") or []]
    return {"task": "explain_finding", "lang": "ko", "finding": engine._short(finding),
            "causes": causes, "trace": compact, "evidence": evidence}


_SAID_VERDICT = re.compile(r"판정(?:\s*결과)?[은는이가:\s]*(불일치|일치|경계|근거부족)|(불일치|일치|경계|근거부족)(?:으로|로)\s*판정")
_SAID_EXPECTED = re.compile(r"(?:계산|검증)\s*결과[^.]{0,12}구분\s*(\d[A-C]?)|(?:계산|검증)\s*결과[은는:\s]*(\d[A-C]?)입니다")
_SAID_MSDS = re.compile(r"MSDS[^.,]{0,12}구분\s*(\d[A-C]?)")


def _categories(*values) -> set[str]:
    return {x.split(":")[0] for v in values if v for x in str(v).split("·")}


def claim_problems(resp: dict, req: dict) -> list[str]:
    """엔진과 다른 결론을 말하는 설명을 막는다 (개요 4절). 숫자 검사는 값이 요청 어딘가에 있으면 통과하므로 따로 본다.

    shortcut: 흔한 문장 모양만 본다. 실제 모델 응답을 모은 뒤 걸러지지 않는 표현이 있으면 패턴을 늘린다.
    """
    f = req["finding"]
    text = " ".join([str(resp.get("summary") or "")] + [str(x) for x in (resp.get("reasons") or []) + (resp.get("basis") or [])])
    said = [a or b for a, b in _SAID_VERDICT.findall(text)]
    out = [f"판정을 '{w}'(으)로 말함. 엔진 판정은 '{f['verdict']}'" for w in said if w != f["verdict"]]
    exp, msds = f.get("expected") or {}, f.get("msds") or {}
    if f.get("kind") == "class":  # 값이 없는 칸은 요청에서 빠지므로 칸 유무로 판단하면 검사를 건너뛴다
        allowed = _categories(exp.get("low"), exp.get("high"))
        out += [f"계산 결과를 구분 {a or b}(으)로 말함" for a, b in _SAID_EXPECTED.findall(text) if (a or b) not in allowed]
        allowed = _categories(msds.get("category"))
        out += [f"MSDS를 구분 {c}(으)로 말함" for c in _SAID_MSDS.findall(text) if c not in allowed]
    return out


def generate(req: dict, llm=None, retries: int = 1) -> dict:
    """요청 → 저장할 설명. compliance.explain.explain_finding 과 같은 흐름에 claim_problems 만 더한다.

    llm(system, user) → (응답 dict | None, 기록 dict).
    """
    failures: list[str] = []
    meta: dict = {}
    fixed_summary = (req.get("finding") or {}).get("type") in engine._DIRECTION_TYPES
    if llm is not None:
        problems = None
        for _ in range(retries + 1):
            try:
                resp, meta = llm(engine.SYSTEM, engine._user(req, problems))
            except Exception as e:  # 모델 서버 장애로 설명이 '작성 중'에 멈추면 안 된다
                resp, meta = None, {"errors": [f"{type(e).__name__}: {e}"[:200]]}
            if fixed_summary and isinstance(resp, dict):  # 과소·과대의 한 줄 요약은 문장틀로 고정 (우진 측정 7차)
                resp = {**resp, "llm_summary": resp.get("summary"), "summary": engine._summary(req)}
            problems = engine.check(resp, req) + claim_problems(resp, req) if resp is not None else ["모델 응답 없음: " + "; ".join(meta.get("errors") or [])]
            if not problems:
                return _stored(engine._out("llm", resp, req, meta, failures), "llm", meta.get("model") or "llm", failures)
            failures += problems
    return _stored(engine._out("template", engine.template(req), req, meta, failures), "template", "template", failures)


def _stored(out: dict, by: str, model: str, failures: list[str]) -> dict:
    return {"by": by, "checked": out["checked"], "summary": out["summary"], "reasons": out["reasons"], "basis": out["basis"],
            "model": model, "check_failures": list(dict.fromkeys(failures))}


def make_llm():
    """모델 서버 주소가 설정돼 있을 때만 모델을 쓴다. 없으면 None(문장틀)."""
    tag = os.environ.get("MSDS_EXPLAIN_MODEL", EXPLAIN_MODEL_DEFAULT)
    try:
        from msds.extract.client import load_model_config
        cfg = load_model_config(tag)
        if not os.environ.get(cfg.get("base_url_env") or ""):
            return None
        return engine.ChatExplainer(tag, cfg=cfg)
    except Exception as e:  # 설정 오류로 저장 흐름을 막지 않는다. 문장틀로 가고 시작 기록에 남긴다
        print(f"설명 모델을 쓰지 않음: {e}")
        return None


class _SemaphoreGate:
    """약속 ④ 대역. shortcut: A1의 common/model_gate 가 들어오기 전까지 동시 수만 막고 추출 우선 순서는 없다."""

    def __init__(self, limit: int | None = None):
        self._sem = threading.Semaphore(limit or int(os.environ.get("MSDS_MODEL_MAX_INFLIGHT", "4")))

    @contextmanager
    def slot_sync(self, kind):
        with self._sem:
            yield


def default_gate():
    try:
        from msds.common.model_gate import gate
        return gate
    except ImportError:
        return _SemaphoreGate()
