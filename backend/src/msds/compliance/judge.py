"""약속 ③ judge(): 판정 엔진(run_consistency) 결과를 계약 consistency 모양으로 옮긴다.

판정·유형·심각도는 엔진 값을 그대로 쓴다. 여기서 정하는 것은 항목 ID, 칸 이름, 화면 글뿐이다.
예외는 추출 실패 항 하나다(handoff.checks.failed_sections → 근거부족).
계약: docs/superpowers/specs/contracts/3-consistency.schema.json, ID 규칙: contracts/README.md 3절.
"""
import hashlib
import json
import re
from functools import lru_cache

import psycopg

from .classifier import effective_components
from .consistency import ENGINE_VERSION, _reassign_gas, run_consistency
from .mixture.acute import value_to_category
from .mixture.build_components import _state
from .explain import item_names
from .htodb.reference import ReferenceProvider
from .mixture.params import RULES_DIR
from .mixture.rules_loader import load_mixture_rules
from .mixture.units import to_target
from .trace import cat_text

CONTRACT = "consistency/2"
# shortcut: ghsclass ClassificationLogic 끼움 자리 없이 로직 id만 기록한다. TO21 로직 API가 생기면 slot으로 바꾼다.
LOGIC_ID = "to21_v6@6"

LAW_LABEL = {"OSH": "산안법", "CCA": "화관법", "KREACH": "화평법", "DG": "위험물법", "WASTE": "폐기물법",
             "POPS": "POPs법", "KR_ETC": "기타 국내", "INTL": "해외"}
SCOPE_NOTE = "8항 노출기준 값, 브리징, 화합물군 합산은 PoC 검증 범위 밖이라 판정하지 않음 (설계서 v0.4 검증 범위, D-10)"
_OUT_OF_SCOPE = {"해당 없음": "해당 없음", "대조": "대조만", "구버전": "구버전 제외"}
_LABEL_KEY = {"LABEL_H_CODES": ("H", "H코드"), "LABEL_PICTOGRAMS": ("PIC", "그림문자"), "LABEL_SIGNAL_WORD": ("SIGNAL", "신호어")}
_ENDPOINT = {"HH_ACUTE_ORAL": "TX_ORAL", "HH_ACUTE_DERMAL": "TX_DERMAL", "HH_ACUTE_INHAL": "TX_INHAL"}
_ACTIVE = ("일치", "불일치", "경계", "경고")
_NEEDS_EXPLANATION = ("불일치", "경계", "근거부족")
_FAILED_SECTION = {
    2: lambda f: f["kind"] in ("class", "label"),
    3: lambda f: True,
    9: lambda f: f["item"].startswith("PH_") or f["kind"] == "dangerous_goods",
    11: lambda f: f["item"].startswith("HH_"),
    12: lambda f: f["item"].startswith("ENV_"),
    14: lambda f: f["item"].startswith("PH_"),
    15: lambda f: f["kind"] in ("regulation", "dangerous_goods"),
}


def is_connection_error(e: Exception) -> bool:
    """값이나 코드가 아니라 연결 문제인가. 복구되면 같은 입력으로 성공한다. 쿼리 제한 시간 초과 등 서버가 답한 다른 오류는 뺀다."""
    if isinstance(e, psycopg.OperationalError):  # 연결 전 실패는 sqlstate 가 없다. 08 연결, 53 자원 부족, 57P 서버 종료
        return e.sqlstate is None or e.sqlstate[:2] in ("08", "53") or e.sqlstate[:3] == "57P"
    return isinstance(e, (ConnectionError, TimeoutError))


class KnowledgeUnavailable(RuntimeError):
    """지식DB가 판정할 수 없는 상태 (적재 중 등). 글은 화면에 그대로 나가므로 접속 정보를 넣지 않는다."""


class _WatchedRepo:
    """엔진의 지식 조회는 오류를 삼키고 '근거부족'으로 이어 간다. 오류를 적어 두어 judge()가 판정 대신 예외를 내게 한다."""

    def __init__(self, repo):
        self._repo, self.errors, self.connection_error = repo, [], None

    def __getattr__(self, name):
        attr = getattr(self._repo, name)
        if not callable(attr):
            return attr

        def call(*args, **kw):
            try:
                return attr(*args, **kw)
            except Exception as e:
                self.errors.append(f"{name}: {type(e).__name__}: {e}")
                if is_connection_error(e):
                    self.connection_error = e
                raise

        return call


def _open_repo(provider):
    if provider is not None:
        return _WatchedRepo(provider)
    from .mixture.class_lookup_db import _DbRepo
    return _WatchedRepo(_DbRepo())


def rules_digest(folder=RULES_DIR) -> str:
    """규칙 파일 전체의 해시. mixture_rules 의 버전 글자만 쓰면 다른 규칙표를 고쳐도 옛 판정을 재사용한다."""
    h = hashlib.sha256()
    for path in sorted(p for p in folder.rglob("*") if p.is_file() and p.suffix in (".csv", ".yaml", ".yml")):
        h.update(path.relative_to(folder).as_posix().encode())
        h.update(path.read_bytes())
    return h.hexdigest()[:12]


@lru_cache(maxsize=1)
def _loaded_rules_digest() -> str:
    # shortcut: 엔진이 규칙을 메모리에 고정하므로 해시도 함께 고정한다. 규칙 파일을 고치면 서버를 다시 켜야 반영된다
    return rules_digest()


def current_versions(provider=None) -> dict:
    """판정 키에 쓰는 버전들. 지식DB에 붙지 못하면 예외를 낸다(장애를 '근거부족' 판정으로 저장하지 않게)."""
    if provider is None:
        from .mixture.class_lookup_db import _DbRepo
        version = _DbRepo().version()
        if not version:
            raise KnowledgeUnavailable("지식DB 적재 차수가 하나로 정해지지 않음 (htodb.load_log 확인). 해결되면 자동으로 다시 판정함")
    else:
        version = provider.version() if hasattr(provider, "version") else "unknown"
    return {"engine_version": ENGINE_VERSION,
            "knowledge": {"provider": "reference", "version": version,
                          "rules": f"{load_mixture_rules()['meta']['version']}+{_loaded_rules_digest()}", "logic": LOGIC_ID}}


def _has_value(v) -> bool:
    """MSDS 내용이 있는가. 문서 정보·원문 조각·순번만 있으면 판정할 내용이 없다."""
    if isinstance(v, dict):
        return any(_has_value(x) for k, x in v.items() if k not in ("meta", "evidence", "seq"))
    if isinstance(v, list):
        return any(map(_has_value, v))
    return bool(v.strip()) if isinstance(v, str) else bool(v)  # false·0 은 추출 기본값일 수 있어 내용으로 치지 않는다


def judge(extraction: dict, as_of: str, provider=None, failed_sections=()) -> dict:
    """추출 JSON 한 건 → consistency/2. provider None = 로컬 HTODB, CsvRepo() = 샘플.

    failed_sections: 넘김 기록의 checks.failed_sections. 그 항에 기대는 판정은 근거부족(추출 실패)으로 낸다.
    as_of 는 기록용이다. HTODB에 시행일이 없어(D-09) 지금은 판정 값에 영향을 주지 않는다.
    """
    versions = current_versions(provider)
    repo = _open_repo(provider)
    items = extraction.get("msds") or [{}]
    results = []
    for i, item in enumerate(items):
        failed = [s for s in failed_sections if s["msds_index"] == i]
        if not _has_value(item):  # 양쪽 다 비어 '일치'로 나오면 안 된다. 3항 실패는 모든 줄에 걸린다
            failed = [*failed, {"msds_index": i, "section": 3, "error": "추출값이 비어 있음"}]
        results.append(_result(extraction, i, item, as_of, repo, versions["knowledge"]["version"], failed))
    if repo.connection_error:
        raise repo.connection_error
    if repo.errors:
        raise RuntimeError(f"지식DB 조회 실패 {len(repo.errors)}건: {repo.errors[0]}"[:500])
    out = {"contract": CONTRACT, "doc_id": (extraction.get("doc") or {}).get("doc_id"), "as_of": as_of,
           **versions, "results": results}
    return json.loads(json.dumps(out, ensure_ascii=False, allow_nan=False))


# ── msds 한 건 ────────────────────────────────────────────────────────

def _result(doc, i, item, as_of, provider, kv, failed) -> dict:
    c = run_consistency(doc, provider, i)["consistency"]
    ctx = {"i": i, "item": item, "kv": kv, "traces": c["traces"], "doc_assumptions": c["assumptions"],
           "comps": {str(x.get("seq")): x for x in item.get("components") or []}}
    built = [_type_finding(i, c, ctx)]
    for row in c["findings"]:
        if row["section"] == "15":
            built.append(_regulation(row, ctx))
        elif row["class_code"] not in _LABEL_KEY:
            built.append(_class(row, ctx))
    built += _labels(c, ctx)
    if c["product_type"]["value"] == "단일물질":
        built += _cross_checks(i, item, ctx)
    for row in c["excluded"]:
        if row.get("class_code") not in _LABEL_KEY:
            built += _excluded(row, ctx)
    built += _international(ctx)
    _apply_failed(built, failed)

    built.sort(key=lambda x: (x[0]["id"], _duplicate_order(x[0])))
    seen: dict[str, int] = {}
    for f, _ in built:  # 같은 키가 또 나오면 #2, #3 (README 3절). 성분 순번이 아니라 내용 순서로 번호를 준다
        seen[f["id"]] = seen.get(f["id"], 0) + 1
        if seen[f["id"]] > 1:
            f["id"] += f"#{seen[f['id']]}"
    built.sort(key=lambda x: x[0]["id"])
    findings, traces = [], {}
    for n, (f, t) in enumerate(built, 1):
        if t is not None:
            f["trace_id"] = f"T-{n:04d}"
            traces[f["trace_id"]] = t
        findings.append(f)

    summary = {k: 0 for k in ("일치", "불일치", "경계", "근거부족", "경고", "참고", "범위 외")}
    for f in findings:
        summary[f["verdict"]] += 1
    meta = item.get("meta") or {}
    return {"msds_index": i, "msds_revision_date": meta.get("last_revision_date") or meta.get("first_issue_date"),
            "product_type": {"value": _type_value(c), "basis": c["product_type"]["basis"]},
            "summary": summary, "findings": findings, "traces": traces,
            "components": _components(item, findings, traces, provider, as_of, c["gaps"]),
            "limitations": _limitations(findings, c) + [{"finding_id": None, "text": SCOPE_NOTE}]}


def _duplicate_order(f):
    return json.dumps([f["expected"].get("content"), (f["comp"] or {}).get("name"), f["msds"].get("applicable"), f["msds"].get("category"),
                       f["msds"].get("threshold"), f["expected"].get("threshold")], sort_keys=True, ensure_ascii=False)


def _type_value(c):
    v = c["product_type"]["value"]
    return "불명확" if v == "판단불가" else v


def _type_finding(i, c, ctx):
    v, basis = _type_value(c), c["product_type"]["basis"]
    stated = "표기 없음" not in basis and v != "불명확"
    verdict = "일치" if stated else "근거부족" if v == "불명확" else "참고"
    evidence = _evidence({"kind": "product_type"}, ctx)
    f = _base(i, "FPT:TYPE", "2", "product_type", "TYPE", "단일·혼합 판별",
              {"present": stated, "product_type": v if stated else None, "evidence": evidence},
              {"present": v != "불명확", "product_type": None if v == "불명확" else v,
               "status": "근거부족" if v == "불명확" else "확정"},
              verdict, basis, rule="FPT-1", method="3항 표기·성분 수")
    return f, None


def _base(i, key, section, kind, item, label, msds, expected, verdict, reason, *, rule=None, type_=None, severity=None,
          causes=(), comp=None, law=None, method="비교 제외", oos=None):
    return {"id": f"m{i}/{key}", "section": section, "kind": kind, "item": item, "label": label, "law_label": law,
            "comp": comp, "msds": msds, "expected": expected, "verdict": verdict, "type": type_, "severity": severity,
            "rule": rule, "causes": list(dict.fromkeys(x["code"] for x in causes)), "trace_id": None,
            "needs_explanation": verdict in _NEEDS_EXPLANATION, "method": method, "reason": reason or "",
            "out_of_scope_reason": oos}


# ── 2항 유해성 분류 ────────────────────────────────────────────────────

def _class(row, ctx):
    cc, form = row["class_code"], row.get("form")
    raw = ctx["traces"].get(row.get("trace_id"))
    msds_vals = row.get("msds_value")
    present = msds_vals not in (None, [], "")
    our = row.get("our_value") or {}
    low, high = our.get("low"), our.get("high")
    status = _class_status(row, raw)
    evidence = _evidence(row, ctx)
    basis, calc = _lines(row, raw, ctx["kv"])
    f = _base(ctx["i"], f"F2:{_key(cc)}:{_key(form or '-')}", "2", "class", cc, _name(cc),
              {"present": present, "category": _one(msds_vals), "route_form": row.get("msds_form"), "evidence": evidence},
              {"present": low is not None, "category": low if low == high else None, "route_form": form, "low": low,
               "high": high, "status": status, "source": _sources(raw)},
              row["verdict"], row.get("reason"), rule=_rule_text(row.get("rule_id")), type_=row.get("type"),
              severity=row.get("severity"), causes=row.get("causes") or (), method=_method(cc, raw))
    # 문서 전체에 걸린 가정도 계산 근거에 남긴다 (파트 B 설계 3절)
    with_doc = {**row, "assumptions": list(row.get("assumptions") or []) + list(ctx["doc_assumptions"])}
    return f, _trace(raw, with_doc, ctx["kv"], cc, form, low, high, status, basis, calc)


# ── 11·12항 수치 교차 확인 (설계서 19장, 단일물질) ─────────────────────

_CROSS_ROUTE = {"HH_ACUTE_ORAL": ("TX_ORAL", "oral"), "HH_ACUTE_DERMAL": ("TX_DERMAL", "dermal"), "HH_ACUTE_INHAL": ("TX_INHAL", "inhal")}
_FORM_EN = {"가스": "gas", "증기": "vapour", "분진·미스트": "mist"}
_ROUTE_KO = {"oral": "경구", "dermal": "경피", "inhal": "흡입"}
_AQ_DESCRIPTORS = ("LC50", "EC50", "ERC50", "EBC50", "LL50", "EL50", "LEC50", "IC50")
_AQ_UNIT_TO_MG_L = {"mg/l": 1.0, "㎎/ℓ": 1.0, "㎎/l": 1.0, "mg/ℓ": 1.0, "ug/l": 0.001, "µg/l": 0.001, "μg/l": 0.001}
_AQ_ENDPOINTS = ("ECO_FISH", "ECO_DAPHNIA", "ECO_CRUST", "ECO_ALGA", "ECO_AQUATIC")
_AQ_CAT1_MAX = 1.0  # mg/L


def _own_values(rows, refs):
    """이 물질의 단일 수치 행. 범위·부등호는 구분을 하나로 정할 수 없어 뺀다."""
    return [r for r in rows if str(r.get("comp_ref")) in refs and (r.get("q") or {}).get("value") is not None]


def _exposure_hours(row):
    """시험 시간(시간). 시간이 없으면 None(4시간으로 본다), 단위를 모르면 0(환산표에 없어 건너뛰게 된다)."""
    unit, value = str(row.get("duration_unit") or "").lower(), row.get("duration_value")
    if value is None:
        return None
    for words, hours in ((("min", "분"), 1 / 60), (("h", "시"), 1), (("d", "일"), 24), (("w", "주"), 168)):
        if unit.startswith(words):
            return value * hours
    return 0


def _cross_finding(i, cc, form, stated, low, reason, ctx):
    msds = {"present": bool(stated), "category": _one(stated), "route_form": form, "evidence": _evidence({"class_code": cc}, ctx)}
    expected = {"present": True, "low": low, "high": low, "route_form": form, "status": "확정"}
    f = _base(i, f"F2:CROSS:{cc}:{form or '-'}", "2", "class", cc, f"11·12항 수치 교차 확인: {item_names().get(cc, cc)}", msds, expected, "경고", reason,
              rule="CROSS-1", type_="내부 불일치", severity="낮음", method="MSDS 11·12항 수치")
    return f, None


def _cross_checks(i, item, ctx):
    """11항 LD50·LC50과 12항 L(E)C50으로 정한 구분이 MSDS 2항과 다르면 내부 불일치 경고. 2항 판정과 별도다.

    shortcut: 분자량·밀도가 있어야 하는 단위(증기 ppm, mmol/kg, mL/kg)와 표에 없는 노출시간은 건너뛴다. 실버에 그런 단일물질 값이 없다.
    """
    stated: dict = {}
    for c in (item.get("hazard") or {}).get("classes") or []:
        stated.setdefault(c.get("class_code"), []).append(c)
    main = effective_components(item.get("components"))
    refs = {"MIX", *(str(c.get("seq")) for c in main[:1])}
    state = _state(item, [])
    default_form = {"액체": "증기", "고체": "분진·미스트", "가스": "가스", "기체": "가스"}.get(state)  # D-06
    out = []
    for cc, (endpoint, route) in _CROSS_ROUTE.items():
        rows = [r for r in _own_values(item.get("toxicity") or [], refs)
                if str(r.get("endpoint")).startswith(endpoint) and r.get("descriptor") in ("LD50", "LC50")]
        found: dict = {}
        estimated: set = set()
        for r in rows:
            q = r["q"]
            form = None
            if route == "inhal":
                forms = {c.get("route_form") for c in stated.get(cc, [])} - {None}
                form = r.get("physical_form") if r.get("physical_form") in _FORM_EN else next(iter(forms)) if len(forms) == 1 else default_form
                if form not in _FORM_EN:
                    continue
                if r.get("physical_form") not in _FORM_EN and not forms:
                    estimated.add(form)
            t = to_target(q["value"], q.get("unit"), route, _FORM_EN.get(form), hours=_exposure_hours(r))
            if t and "미환산" not in t["note"] and (form not in found or t["value"] < found[form]):
                found[form] = t["value"]
        for form, value in found.items():
            cat = value_to_category(_ROUTE_KO[route], form, value) or "분류안됨"
            rows_2 = stated.get(cc, [])
            if route == "inhal" and rows_2 and all(c.get("route_form") not in (form, None) for c in rows_2):
                continue  # 2항이 다른 형태로 적었으면 형태 차이는 2항 판정이 본다
            cats = [c.get("category") for c in rows_2 if route != "inhal" or c.get("route_form") in (form, None)]
            if "5" in cats and cat == "분류안됨":  # 구분5는 고시 밖이라 참고로만 둔다 (D-18)
                continue
            if (cats or ["분류안됨"]) != [cat] and cat not in cats:
                out.append(_cross_finding(i, cc, form, cats, cat, f"내부 불일치: 11항 값 {value:g}이면 {cat}인데 2항은 {_one(cats) or '기재 없음'}" + (f" (흡입 형태는 성상으로 추정한 {form})" if form in estimated else ""), ctx))
    aq = [r["q"]["value"] * _AQ_UNIT_TO_MG_L[str(r["q"].get("unit")).lower()] for r in _own_values(item.get("ecotox") or [], refs)
          if str(r.get("endpoint")).startswith(_AQ_ENDPOINTS) and str(r.get("descriptor")).upper().replace("(", "").replace(")", "") in _AQ_DESCRIPTORS and str(r["q"].get("unit")).lower() in _AQ_UNIT_TO_MG_L]
    if aq:
        value, cats = min(aq), [c.get("category") for c in stated.get("ENV_AQ_ACUTE", [])]
        if (value <= _AQ_CAT1_MAX) != ("1" in cats):
            out.append(_cross_finding(i, "ENV_AQ_ACUTE", None, cats, "1" if value <= _AQ_CAT1_MAX else None,
                                      f"내부 불일치: 12항 값 {value:g} mg/L와 2항 수생 급성({_one(cats) or '기재 없음'})의 구분1 기준(1 mg/L 이하)이 맞지 않음", ctx))
    return out


def _class_status(row, raw):
    if raw and (raw.get("result") or {}).get("status") in ("확정", "경계", "근거부족") and row["verdict"] not in ("경계", "근거부족"):
        return raw["result"]["status"]
    return row["verdict"] if row["verdict"] in ("경계", "근거부족") else "확정"


def _one(v):
    if isinstance(v, list):
        return "·".join(str(x) for x in v) if v else None
    return None if v is None else str(v)


def _method(cc, raw):
    if not raw:
        return "MSDS 기재만"
    if raw.get("kind") == "reference":
        return "기준 분류 비교"
    if cc in _ENDPOINT:
        return "ATEmix 계산"
    if cc.startswith("ENV_AQ"):
        return "M-factor 가산"
    if cc.startswith("PH_"):
        return "9항 시험값·UN 정보"
    return "가산·한계농도 계산"


def _sources(raw):
    vals = [i.get("source") for i in (raw or {}).get("inputs") or [] if i.get("source")]
    return "; ".join(dict.fromkeys(vals)) or None


# ── 2항 표시 요소: 엔진은 종류별 한 줄, 계약은 코드별 한 줄 ─────────────────

def _labels(c, ctx):
    """엔진은 종류별로(H코드 불일치가 빠짐·더함 두 줄일 수 있음), 생략 허용은 excluded 로 낸다. 코드 하나당 한 줄로 합친다."""
    out = []
    for code, (kind, name) in _LABEL_KEY.items():
        rows = [r for r in c["findings"] if r.get("class_code") == code]
        omitted = [r for r in c["excluded"] if r.get("class_code") == code]
        if not rows and not omitted:
            continue
        if kind == "SIGNAL":
            r = rows[0]
            out.append(_label_one(r, ctx, "F2L:SIGNAL", "SIGNAL", "표시 요소(신호어)", (r.get("our_value") or {}).get("low"),
                                  r.get("msds_value"), r["verdict"], r.get("reason"), r.get("causes") or [],
                                  r.get("type"), r.get("severity")))
            continue
        derived = next(((r.get("our_value") or {}).get("low") for r in rows if r.get("our_value")), None)
        if derived is None:
            derived = next((r.get("our_value") for r in omitted), None) or []
        msds = next((r.get("msds_value") for r in rows + omitted if r.get("msds_value")), None) or []
        for x in sorted(set(derived) | set(msds)):
            bad = next((r for r in rows if r["verdict"] == "불일치" and x in (r.get("missing") or []) + (r.get("extra") or [])), None)
            lack = next((r for r in rows if r["verdict"] == "근거부족"), None)
            if bad:
                # 분류에 없는 H코드를 더 적은 경우는 규칙표 CMP-2의 경고. 엔진은 판정 4종에 맞춰 불일치로 낸다
                row, verdict = bad, "경고" if x in (bad.get("extra") or []) and bad.get("severity") == "낮음" else "불일치"
                reason = (f"{name} {x}: 분류로 보면 있어야 하는데 MSDS에 없음" if x in (bad.get("missing") or [])
                          else f"{name} {x}: 분류에 없는데 MSDS가 더 적음")
                causes = [y for y in bad.get("causes") or [] if y.get("item", x) == x]
            elif omitted and x in derived and x not in msds:
                row, verdict, reason, causes = omitted[0], "참고", omitted[0].get("reason"), []
            elif lack:
                row, verdict, reason, causes = lack, "근거부족", lack.get("reason"), lack.get("causes") or []
            else:
                row, verdict, causes = (rows or omitted)[0], "일치", []
                reason = f"{name} {x} 같음" + (" (그림문자 4개 표시 규칙으로 생략 허용)" if x in derived and x not in msds else "")
            out.append(_label_one(row, ctx, f"F2L:{kind}:{_key(x)}", x, f"표시 요소({name}) {x}", x if x in derived else None,
                                  x if x in msds else None, verdict, reason, causes,
                                  row.get("type") if bad else None, row.get("severity") if bad else None))
    return out


def _label_one(row, ctx, key, item, label, derived, msds, verdict, reason, causes, type_, severity):
    raw = ctx["traces"].get(row.get("trace_id"))
    status = "근거부족" if verdict == "근거부족" else "확정"
    evidence = _evidence(row, ctx)
    basis, calc = _lines({**row, "reason": reason}, raw, ctx["kv"])
    f = _base(ctx["i"], key, "2", "label", item, label,
              {"present": msds not in (None, ""), "code": msds, "evidence": evidence},
              {"present": derived not in (None, ""), "code": derived, "status": status,
               "source": "MSDS 2항 분류 → 고시 별표2"},
              verdict, reason, rule=row.get("rule_id"), type_=type_, severity=severity, causes=causes, method="별표2 매핑")
    return f, _trace(raw, row, ctx["kv"], None, None, derived, derived, status, basis, calc, causes=causes)


# ── 15항 ──────────────────────────────────────────────────────────────

def _regulation(row, ctx):
    raw = ctx["traces"].get(row.get("trace_id"))
    ref, law, code = str(row.get("comp_ref")), row.get("law"), row.get("item_code")
    dg = code == "DG_HAZMAT"
    comp = ctx["comps"].get(ref) or {}
    verdict, exp = row["verdict"], row.get("expected")
    status = verdict if verdict in ("경계", "근거부족") else "확정"
    evidence = _evidence(row, ctx)
    basis, calc = _lines(row, raw, ctx["kv"])
    msds_thr, db_thr = row.get("msds_threshold"), row.get("db_threshold")
    msds = {"present": row.get("msds_value") is not None, "applicable": row.get("msds_value"),
            "threshold": _threshold_q(msds_thr), "evidence": evidence}
    expected = {"present": exp is not None, "applicable": exp, "threshold": None if dg else _threshold_q(db_thr),
                "content": comp.get("content"), "status": status, "source": "; ".join(row.get("source") or []) or None}
    if dg:
        expected["dg"] = {"item": db_thr}
    key = "F15DG:MIX" if dg else f"F15:{_comp_key(ref, comp)}:{law or '-'}.{code or '-'}"
    f = _base(ctx["i"], key, "15", "dangerous_goods" if dg else "regulation", "DG" if dg else f"{law}.{code}",
              "위험물" if dg else _reg_name(code), msds, expected, verdict, row.get("reason"), rule=row.get("rule_id"),
              type_=row.get("type"), severity=row.get("severity"), causes=row.get("causes") or (),
              comp=_comp(ref, comp), law=LAW_LABEL.get(law, law), method="인화점 판정" if dg else "규제DB 대조")
    return f, _trace(raw, row, ctx["kv"], None, None, exp, exp, status, basis, calc,
                     kind="dg_check" if dg else "regulation_check")


def _threshold_q(text):
    """엔진의 기준 표기('>= 10%')를 계약의 TO21 Q 구조로."""
    if not text:
        return None
    m = re.fullmatch(r"(>=|>|<=|<)\s*([\d.]+(?:[eE][-+]?\d+)?)\s*(\S*)", str(text).strip())
    if not m:  # '기준 농도 없음(함유하면 해당)'. 판단 근거 줄에 남는다
        return None
    side = "lower" if m[1].startswith(">") else "upper"
    return {"raw": str(text), f"{side}_op": m[1], side: float(m[2]), "unit": m[3] or None, "status": "값있음"}


def _reg_name(code):
    if not code:
        return "법 단위 기재"
    # item_names 는 '<법 이름> <항목>' 모양이다. 법은 law_label 칸에 따로 있다
    return re.sub(r"^\S*법(·\S*법)*\s+", "", item_names().get(code, code))


def _comp(ref, comp):
    return None if ref == "MIX" else {"comp_ref": ref, "cas": comp.get("cas_no"), "name": comp.get("name")}


def _comp_key(ref, comp):
    if ref == "MIX":
        return "MIX"
    if comp.get("cas_no"):
        return _key(comp["cas_no"])
    return f"name:{_key(comp['name'])}" if comp.get("name") else f"seq:{_key(ref)}"


# ── 비교 제외 줄 ───────────────────────────────────────────────────────

def _excluded(row, ctx):
    status = row["status"]
    verdict = "참고" if status == "참고" else "범위 외"
    oos = None if verdict == "참고" else _OUT_OF_SCOPE.get(status, "해당 없음")
    evidence = _evidence(row, ctx)
    if row["section"] == "15":
        ref, law, code = str(row.get("comp_ref")), row.get("law"), row.get("item_code")
        comp = ctx["comps"].get(ref) or {}
        key = f"F15:{_comp_key(ref, comp)}:{law or '-'}.{code or '-'}"
        f = _base(ctx["i"], key, "15", "regulation", f"{law or '-'}.{code or '-'}", _reg_name(code),
                  {"present": row.get("msds_value") is not None, "applicable": row.get("msds_value"), "evidence": evidence},
                  {"present": False, "status": "근거부족", "content": comp.get("content"), "source": "; ".join(row.get("source") or []) or None},
                  verdict, row.get("reason"), comp=_comp(ref, comp), law=LAW_LABEL.get(law, law) if law else None, oos=oos)
        return [(f, None)]
    cc = row.get("class_code")
    if cc is None:  # 단일·혼합을 판별하지 못한 줄은 FPT 판정과 limitations 로 보인다
        return []
    form, our = row.get("form"), row.get("our_value")
    f = _base(ctx["i"], f"F2:{_key(cc)}:{_key(form or '-')}", "2", "class", cc, _name(cc),
              {"present": row.get("msds_value") not in (None, [], ""), "category": _one(row.get("msds_value")),
               "route_form": None, "evidence": evidence},
              {"present": our is not None, "category": our if isinstance(our, str) else None, "route_form": form,
               "status": "확정" if our is not None else "근거부족"},
              verdict, row.get("reason"), oos=oos)
    return [(f, None)]


def _international(ctx):
    """해외 규제는 판정하지 않지만 MSDS에 적힌 행을 '범위 외'로 보인다 (설계서 v0.4 검증 범위). 엔진은 이 행을 버린다."""
    out = []
    for i, r in enumerate(ctx["item"].get("regulations") or []):
        if r.get("law") != "INTL":
            continue
        ref, code = str(r.get("comp_ref") or "MIX"), r.get("item_code") or "-"
        comp = ctx["comps"].get(ref) or {}
        evidence = _evidence({"section": "15", "comp_ref": ref, "item_code": r.get("item_code")}, ctx)
        reason = "해외 규제는 PoC 검증 범위 밖"
        out.append((_base(ctx["i"], f"F15:{_comp_key(ref, comp)}:INTL.{_key(code)}", "15", "regulation", f"INTL.{code}",
                          r.get("item_raw") or "해외 규제",
                          {"present": True, "applicable": r.get("applicable"), "evidence": evidence},
                          {"present": False, "status": "근거부족", "content": comp.get("content"), "source": None}, "범위 외", reason,
                          comp=_comp(ref, comp), law=LAW_LABEL["INTL"], oos="해외 규제"), None))
    return out


# ── 추출 실패 항 ───────────────────────────────────────────────────────

def _apply_failed(built, failed):
    for s in failed:
        hit = _FAILED_SECTION.get(s["section"])
        if hit is None:
            continue
        for f, t in built:
            if f["verdict"] not in (*_ACTIVE, "근거부족") or not hit(f):  # 이미 근거부족이어도 진짜 이유로 바꾼다
                continue
            text = f"{s['section']}항 추출 실패로 판정할 수 없음: {s.get('error') or '이유 없음'}"
            f.update(verdict="근거부족", type=None, severity=None, needs_explanation=True, reason=text, causes=["NO_BASIS"])
            f["expected"]["status"] = "근거부족"
            if t is not None:
                t["cause_texts"] = [{"code": "NO_BASIS", "text": text}]
                t["basis_lines"].insert(0, text)


# ── 성분별 요약 ───────────────────────────────────────────────────────

_ROUTE = {"HH_ACUTE_ORAL": ("oral", "mg/kg"), "HH_ACUTE_DERMAL": ("dermal", "mg/kg"), "HH_ACUTE_INHAL": ("inhal", None)}
_INHAL_UNIT = {"가스": "ppm", "증기": "mg/L", "분진·미스트": "mg/L"}


def _components(item, findings, traces, provider, as_of, gaps):
    ref_provider = ReferenceProvider(provider)
    out = []
    for c in item.get("components") or []:
        ref, cas, name = str(c.get("seq")), c.get("cas_no"), c.get("name")
        know = ref_provider.get_reference(cas, as_of) if cas else {}
        ate = []
        for f in findings:
            if f["item"] not in _ENDPOINT or not f["trace_id"]:
                continue
            route, unit = _ROUTE[f["item"]]
            form = f["expected"].get("route_form")
            for i in traces[f["trace_id"]]["inputs"]:
                if (cas and i.get("cas") == cas) or (not cas and i.get("name") == name):
                    ate.append({"route": route, "value": i.get("ate_used"), "unit": unit or _INHAL_UNIT.get(form), "form": form,
                                "source": i.get("source"), "step": i.get("step"), "excluded": i.get("excluded")})
        # 판정과 같은 형태를 보인다 (D-22)
        classes = _reassign_gas(know.get("classes") or [], ref_provider.class_rows(cas), _state(item, [])) if cas else []
        out.append({"comp_ref": ref, "name": name, "cas": cas, "content": c.get("content"),
                    "reference_classes": [{"class_code": r["class_code"], "category": str(r.get("category") or ""),
                                           "route_form": r.get("route_form"), "source": str(r.get("source") or "")} for r in classes],
                    "ate": ate,
                    "regulation_hits": sum(1 for f in findings if f["kind"] == "regulation" and f["comp"]
                                           and f["comp"]["comp_ref"] == ref and f["expected"].get("applicable") == "해당"),
                    "reliability": _reliability(ate, classes),
                    "notes": [g["reason"] for g in gaps if f"[{name}]" in str(g.get("field"))]})
    return out


def _reliability(ate, classes):
    """1·2·5단계 높음, 3·4단계 보통, 6단계(자료 없음) 낮음 (설계서 21장). ATE 판정이 없으면 기준 분류 유무로 본다."""
    steps = {a["step"] for a in ate if a["step"] is not None}
    if not steps:
        return "높음" if classes else "낮음"
    if 6 in steps:
        return "낮음"
    return "보통" if steps & {3, 4} else "높음"


def _limitations(findings, c):
    out = [{"finding_id": f["id"], "text": f"{f['label']}: {f['reason']}"} for f in findings if f["verdict"] in ("경계", "근거부족")]
    texts = [g["reason"] for g in c["gaps"]] + [f"입력에 없음: {m}" for m in c.get("missing") or []]
    texts += [e["reason"] for e in c["excluded"] if e.get("class_code") is None and e.get("section") == "2" and e.get("status") == "참고"]
    return out + [{"finding_id": None, "text": t} for t in dict.fromkeys(texts)]


# ── 공통 ──────────────────────────────────────────────────────────────

def _key(s):
    return re.sub(r"\s+", "_", str(s))


def _name(code):
    return item_names().get(code, code)


_LABEL_FIELD = {"LABEL_H_CODES": "hazard.h_statements", "LABEL_PICTOGRAMS": "hazard.pictograms", "LABEL_SIGNAL_WORD": "hazard.signal_word"}
_MAX_EVIDENCE = 6
_PH_PROPS = {"APPEARANCE_STATE", "FLASH_POINT", "BOILING", "AUTOIGNITION", "LEL", "UEL", "VISCOSITY_40", "PH"}


def _evidence_targets(row, item):
    code = row.get("class_code")
    if row.get("section") == "15":
        out = [f"regulations[{i}]" for i, r in enumerate(item.get("regulations") or [])
               if str(r.get("comp_ref")) == str(row.get("comp_ref")) and r.get("item_code") == row.get("item_code")]
        return out + [f"components[{i}]" for i, c in enumerate(item.get("components") or [])
                      if str(c.get("seq")) == str(row.get("comp_ref"))]
    if code in _LABEL_FIELD:
        return [_LABEL_FIELD[code]]
    if row.get("kind") == "product_type":
        return ["composition"] + [f"components[{i}]" for i in range(len(item.get("components") or []))]
    out = [f"hazard.classes[{i}]" for i, c in enumerate((item.get("hazard") or {}).get("classes") or [])
           if c.get("class_code") == code]
    if code in _ENDPOINT:  # 계산에 쓴 11항도 원문 탭에 보인다
        out += [f"toxicity[{i}]" for i, t in enumerate(item.get("toxicity") or [])
                if str(t.get("endpoint") or "").startswith(_ENDPOINT[code])]
    elif str(code).startswith("PH_"):  # 물리적 위험성은 9항 물성과 14항 운송 정보로 판정한다
        out += [f"physchem[{i}]" for i, r in enumerate(item.get("physchem") or []) if r.get("prop_code") in _PH_PROPS]
        out += [f"transport[{i}]" for i in range(len(item.get("transport") or []))]
    elif str(code).startswith("ENV_"):
        out += [f"ecotox[{i}]" for i in range(len(item.get("ecotox") or []))]
    return out


def _evidence(row, ctx):
    """칸의 원문 근거. 추출본마다 근거를 적은 깊이가 달라(hazard.classes / hazard.classes[0] / …[0].category) 위아래 경로를 모두 찾는다."""
    out, seen = [], set()
    for target in _evidence_targets(row, ctx["item"]):
        parent = target.split("[")[0]
        for e in ctx["item"].get("evidence") or []:
            field = e.get("field") or ""
            if field in seen or not (field in (target, parent) or field.startswith((target + ".", target + "["))):
                continue
            seen.add(field)
            out.append({"field": field, "page": e.get("page"), "source_text": e.get("source_text")})
    return out[:_MAX_EVIDENCE]


def _g(x):
    return f"{x:.4g}" if isinstance(x, (int, float)) and not isinstance(x, bool) else str(x)


def _rule_text(v):
    """함량 하한·상한에 다른 규칙이 걸리면 엔진은 {'low': …, 'high': …}로 준다. 계약은 글자 하나다."""
    if isinstance(v, dict):
        return " ~ ".join(dict.fromkeys(str(x) for x in (v.get("low"), v.get("high")) if x)) or None
    return v


def _lines(row, raw, kv):
    basis = [row["reason"]] if row.get("reason") else []
    raw = raw or {}
    rule = raw.get("rule") or {}
    rule_id, rule_basis = _rule_text(rule.get("id")), _rule_text(rule.get("basis"))
    if rule_id:
        basis.append(f"적용 규칙 {rule_id}" + (f" ({rule_basis})" if rule_basis else ""))
    for t in raw.get("thresholds") or []:
        if t.get("range"):
            basis.append(f"{cat_text(t.get('category'))}: {t['range']}")
    basis += [f"규제DB: {s}" for s in row.get("source") or []]
    basis += [f"조문: {s}" for s in (row.get("db_text") or [])[:1]]
    if raw:
        basis.append(f"지식 버전 {kv}")
    return basis, _calc_lines(raw)


def _calc_lines(raw):
    out = []
    for i in raw.get("inputs") or []:
        if not i.get("name") and not i.get("cas"):
            continue
        content = i.get("content") or {}
        amount = f" {_g(content.get('low'))}~{_g(content.get('high'))}%" if content.get("low") is not None else ""
        head = f"{i.get('name') or i.get('cas')}{amount}"
        if i.get("excluded"):
            out.append(f"{head}: 제외 ({i['excluded']})")
        elif i.get("ate_used") is not None:
            step = f" · {i['step']}단계" if i.get("step") else ""
            out.append(f"{head}: ATE {_g(i['ate_used'])} · {i.get('source') or '출처 없음'}{step}")
        elif i.get("used_as"):
            out.append(f"{head}: {', '.join(str(x) for x in i['used_as'])}에 포함")
    calc = raw.get("calc") or {}
    if calc.get("ate_mix_low") is not None or calc.get("ate_mix_high") is not None:
        out.append(f"함량 하한 기준 ATEmix {_g(calc.get('ate_mix_low'))}, 함량 상한 기준 ATEmix {_g(calc.get('ate_mix_high'))}")
    if calc.get("unknown_pct"):
        out.append(f"독성값을 모르는 성분 {_g(calc['unknown_pct'])}%")
    return out


_KIND = {"mixture": "mixture_calc", "reference": "reference_lookup", "label": "label_check", "regulation": "regulation_check"}


def _trace(raw, row, kv, class_code, form, low, high, status, basis, calc, kind=None, causes=None):
    if raw is None:
        return None
    rule = raw.get("rule") or {}
    assumptions = list(dict.fromkeys(list(row.get("assumptions") or []) + list(raw.get("assumptions") or [])))
    return {**raw, "kind": kind or _KIND.get(raw.get("kind"), raw.get("kind")), "class_code": class_code, "form": form,
            "result": {"low": low, "high": high, "status": status},
            "rule": {"id": _rule_text(rule.get("id")) or _rule_text(row.get("rule_id")) or "-",
                     "basis": _rule_text(rule.get("basis")) or "", "formula": _rule_text(rule.get("formula"))},
            "inputs": raw.get("inputs") or [], "thresholds": raw.get("thresholds") or [],
            "assumptions": [{"id": _decision_id(a), "text": a} for a in assumptions],
            "knowledge_version": kv, "steps": [{"step": s} for s in basis + calc], "basis_lines": basis, "calc_lines": calc,
            "cause_texts": [{"code": x["code"], "text": x["text"]} for x in (row.get("causes") or [] if causes is None else causes)]}


def _decision_id(text):
    m = re.search(r"\bD-\d+\b", text)
    return m.group(0) if m else "-"
