"""판정 설명 — 설계서 13장(설명 요청·응답과 안전장치), 40장(불일치 상세 화면), 44장(explanation), 8장(설명 대상).

방식(11/02 F 결정 13): 근거 검색(RAG)은 쓰지 않는다. 판정 줄 하나의 근거 묶음 — 차이 원인 코드(causes), 계산 근거(trace) 요약,
MSDS 원문 조각(evidence) — 을 설계서 13장 요청 모양으로 만들어 프롬프트에 그대로 넣는다. 근거는 trace_id 로 이미 정해져 있어
검색할 것이 없고, 검색은 다른 물질·항목의 글을 끌어올 위험이 있다.

    build_request → LLM(JSON: summary·reasons·basis·used_numbers) → check(숫자·코드·구분 검사)
    → 실패하면 문제를 알려 한 번 다시 요청 → 그래도 실패하거나 LLM이 없으면 원인 코드 문장틀(template)로 대체하고 표시

판정·유형·심각도·구분은 LLM이 바꿀 수 없다. 응답에서 설명 글만 받고 판정은 엔진 값을 그대로 둔다.
설명은 일치가 아닌 줄(불일치·경계·근거부족)에만 붙인다.
"""
import csv
import json
import re
from functools import lru_cache

from .mixture.params import RULES_DIR
from .trace import cat_text

SYSTEM = """너는 MSDS(물질안전보건자료) 정합성 검증 결과를 검토자에게 설명하는 도우미다.
규칙:
1. 판정(verdict)·유형(type)·심각도(severity)·구분은 검증 엔진이 이미 정했다. 바꾸거나 다른 결론을 내지 않는다.
2. 요청 JSON에 있는 숫자·코드·성분 이름·쪽 번호만 쓴다. 새로 계산하거나 값을 추정하지 않는다.
3. causes(차이 원인)를 앞에서부터 근거로 삼는다. 원인 코드 이름(CAT_LOWER 등)은 문장에 쓰지 않는다.
4. summary는 한 문장, reasons는 2~4개, basis는 판단 근거(적용 규칙·고시·MSDS 쪽)를 1~3개. 한국어 합니다체로 쓴다.
5. used_numbers에는 글에 쓴 숫자를 모두 적는다(구분 번호와 'N항'의 N은 빼도 된다)."""

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "reasons": {"type": "array", "items": {"type": "string"}},
        "basis": {"type": "array", "items": {"type": "string"}},
        "used_numbers": {"type": "array", "items": {"type": "number"}},
    },
    "required": ["summary", "reasons", "basis", "used_numbers"],
    "additionalProperties": False,
}
EXPLAIN_ASSUMPTIONS = [
    "설명은 일치가 아닌 줄에만 붙임(설계서 8장). LLM에는 그 줄의 원인 코드·trace 요약·MSDS 원문 조각만 보냄(설계서 13장, F 결정 13: 검색 없음)",
    "LLM 설명은 숫자·코드(H·P·GHS·CAS·UN)·구분이 요청에 모두 있어야 통과. 실패하면 한 번 다시 요청하고, 그래도 실패하면 원인 코드 문장틀로 대체(by=template)",
]
_LABEL_NAME = {"LABEL_H_CODES": "표시 요소(H코드)", "LABEL_PICTOGRAMS": "표시 요소(그림문자)", "LABEL_SIGNAL_WORD": "표시 요소(신호어)"}
_LABEL_EVIDENCE = {"LABEL_H_CODES": "hazard.h_statements", "LABEL_PICTOGRAMS": "hazard.pictograms", "LABEL_SIGNAL_WORD": "hazard.signal_word"}
_GROUP = {"DG_HAZMAT": "위험물", "WASTE_DESIG": "폐기물", "KREACH_ETC": "기타 대상 여부"}
_ENDPOINT = {"HH_ACUTE_ORAL": "TX_ORAL", "HH_ACUTE_DERMAL": "TX_DERMAL", "HH_ACUTE_INHAL": "TX_INHAL"}
_MAX_EVIDENCE, _MAX_TEXT = 4, 200


# ── 이름표 ────────────────────────────────────────────────────────────

def _rows(name):
    with open(RULES_DIR / name, encoding="utf-8") as f:
        return list(csv.DictReader(line for line in f if not line.startswith("#")))


@lru_cache
def item_names() -> dict:
    """class_code → 국문 항목 이름(class_map.csv db_div_name), item_code → '법 세부규제'(reg_map.csv)."""
    out = {}
    for r in _rows("class_map.csv"):
        out.setdefault(r["class_code"], re.sub(r"\(흡입:[^)]*\)", "(흡입)", r["db_div_name"]))
    regs = {}
    for r in _rows("reg_map.csv"):
        if r["item_code"]:
            regs.setdefault(r["item_code"], []).append((r["law"], r["db_item_name"]))
    for code, rows in regs.items():  # 세부규제 여럿이 한 항목으로 묶이면(위험물 제1~6류 등) 법 이름과 묶음 이름으로
        laws = list(dict.fromkeys(law for law, _ in rows))
        out.setdefault(code, f"{rows[0][0]} {rows[0][1]}" if len(rows) == 1 else f"{'·'.join(laws)} {_GROUP.get(code, code)}")
    out.update(_LABEL_NAME)
    return out


_cat = cat_text
_DIGIT_RO = {"0": "으로", "3": "으로", "6": "으로"}  # 영·삼·육은 받침이 있어 '으로', 나머지 숫자는 '로'


def ro(word: str) -> str:
    """word + 조사 (으)로. 받침이 없거나 ㄹ 받침이면 '로', 그 밖의 받침이면 '으로'."""
    w = str(word).rstrip(" )")
    last = w[-1] if w else ""
    if last.isdigit():
        return f"{word}{_DIGIT_RO.get(last, '로')}"
    if last.isascii() and last.isalpha():  # 1A·1B·2A: 에이·비·씨처럼 받침 없이 읽는다(M·N은 받침이 있어 '으로')
        return f"{word}{'으로' if last.upper() in 'MN' else '로'}"
    if "가" <= last <= "힣":
        jong = (ord(last) - 0xAC00) % 28
        return f"{word}{'로' if jong in (0, 8) else '으로'}"
    return f"{word}(으)로"


# ── 요청 (설계서 13장) ─────────────────────────────────────────────────

def _g(x):
    return float(f"{x:.4g}") if isinstance(x, float) else x


def _short(v):
    if isinstance(v, float):
        return _g(v)
    if isinstance(v, str):
        return v[:_MAX_TEXT]
    if isinstance(v, list):
        return [_short(x) for x in v[:8]]
    if isinstance(v, dict):
        return {k: _short(x) for k, x in v.items() if x not in (None, [], {}, "")}
    return v


def _compact_input(i):
    keep = ("role", "name", "cas", "content", "used_as", "excluded", "ate_used", "source", "step", "share", "un_no",
            "hazard_class", "sub_risk", "packing_group", "category", "form", "effect")
    out = {k: i[k] for k in keep if k in i}
    for k in ("flash_point", "boiling"):  # 9항 물성 행은 원문만
        if i.get(k):
            out[k] = [q.get("raw") for q in i[k] if isinstance(q, dict)]
    return _short(out)


def compact_trace(t):
    """trace → LLM에 보낼 요약. 설계서 41장 필드 중 설명에 쓰는 것만 남기고 긴 목록은 줄인다."""
    if not t:
        return None
    kind = t.get("kind")
    out = {"kind": kind, "rule": _short({k: (t.get("rule") or {}).get(k) for k in ("id", "basis", "formula")}),
           "result": _short(t.get("result"))}
    if kind == "mixture":
        out["inputs"] = [_compact_input(i) for i in t.get("inputs") or []][:8]
        calc = dict(t.get("calc") or {})
        values = calc.pop("values", None)
        out["calc"] = _short({k: v for k, v in calc.items() if k != "ref_cat5"})
        if values:  # 조건식에 쓴 합계값(하한·상한)
            out["calc"]["values"] = _short(values)
        th = t.get("thresholds") or []
        fired = [x for x in th if x.get("result") is True]
        out["thresholds"] = _short(fired or th[:4])
        out["assumptions"] = _short([a for a in t.get("assumptions") or []][:6])
    elif kind == "regulation":
        out.update(_short({k: t.get(k) for k in ("law", "item_code", "expected", "db_threshold", "msds_value",
                                                  "msds_threshold", "source")}))
        out["inputs"] = _short(t.get("inputs"))
        out["db_text"] = [s[:300] for s in (t.get("db_text") or [])[:2]]
    elif kind == "reference":
        out["inputs"] = _short(t.get("inputs"))
        out["all_sources"] = _short(t.get("all_sources"))
        if t.get("reason"):
            out["reason"] = t["reason"]
    elif kind == "label":
        out.update(_short({k: t.get(k) for k in ("derived", "msds", "missing", "extra", "from_classes")}))
    out["knowledge_version"] = t.get("knowledge_version")
    return out


def _ev(e):
    return {"page": e.get("page"), "text": (e.get("source_text") or "")[:_MAX_TEXT], "field": e.get("field")}


def msds_evidence(f, item) -> list[dict]:
    """판정 줄과 관계된 MSDS 원문 조각(추출 JSON evidence: 쪽·원문). 화면 '원문 근거'와 LLM 요청에 함께 쓴다."""
    item = item or {}
    by_field = {e.get("field"): e for e in item.get("evidence") or []}
    fields = []
    code = f.get("class_code")
    if f.get("section") == "2" and code in _LABEL_EVIDENCE:
        pre = _LABEL_EVIDENCE[code]
        fields = [k for k in by_field if k == pre or k.startswith(pre + "[")]
    elif f.get("section") == "2":
        for i, c in enumerate((item.get("hazard") or {}).get("classes") or []):
            if c.get("class_code") == code and (c.get("route_form") or None) in (f.get("msds_form"), f.get("form"), None):
                fields.append(f"hazard.classes[{i}]")
        if any(x.get("code") == "ATE_VALUE_DIFF" for x in f.get("causes") or []):
            for i, t in enumerate(item.get("toxicity") or []):
                if str(t.get("comp_ref")) == "MIX" and str(t.get("endpoint") or "").startswith(_ENDPOINT.get(code, "-")):
                    fields.append(f"toxicity[{i}]")
    else:
        for i, r in enumerate(item.get("regulations") or []):
            if str(r.get("comp_ref")) == str(f.get("comp_ref")) and r.get("item_code") == f.get("item_code"):
                fields.append(f"regulations[{i}]")
        for i, c in enumerate(item.get("components") or []):
            if str(c.get("seq")) == str(f.get("comp_ref")):
                fields.append(f"components[{i}]")
    return [_ev(by_field[k]) for k in dict.fromkeys(fields) if k in by_field][:_MAX_EVIDENCE]


def build_request(f, trace, item=None) -> dict:
    names = item_names()
    if f.get("section") == "15":
        code = f.get("item_code")
        finding = {"item": code, "item_name": names.get(code, code), "component": f.get("comp_ref"),
                   "msds": {"applicable": f.get("msds_value"), "threshold": f.get("msds_threshold")},
                   "expected": {"applicable": f.get("expected"), "threshold": f.get("db_threshold")}}
    else:
        code = f.get("class_code")
        finding = {"item": code, "item_name": names.get(code, code),
                   "msds": {"category": f.get("msds_value"), "route_form": f.get("msds_form")},
                   "expected": {**(f.get("our_value") or {}), "route_form": f.get("form")}}
    finding = {"id": f.get("id"), "section": f.get("section"), **finding, "verdict": f.get("verdict"),
               "type": f.get("type"), "severity": f.get("severity"), "reason": f.get("reason")}
    return {"task": "explain_finding", "lang": "ko", "finding": _short(finding),
            "causes": [{"code": c["code"], "text": c["text"]} for c in f.get("causes") or []],
            "trace": compact_trace(trace), "evidence": msds_evidence(f, item)}


# ── 검사 (설계서 13장 '숫자 환각 검사') ──────────────────────────────────

_CODE = re.compile(r"\b(?:EUH\d{3}|H\d{3}|P\d{3}|GHS0\d)\b")
_CAS = re.compile(r"\b\d{2,7}-\d{2}-\d\b")
_UN = re.compile(r"\bUN\s?\d{4}\b")
_CATEGORY = re.compile(r"구분\s*(\d[A-C]?)")
_SECTION = re.compile(r"\d{1,2}\s*항")
_TERM = re.compile(r"\b(?:L[CD]50|E[rby]?C\d{2}|EL50|IC50|NOEC|LOEC|ATE(?:mix)?|PM10|PM2\.5)\b|mg/m3|㎎/㎥|m3\b")  # 숫자가 든 용어·단위
_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _walk(v):
    if isinstance(v, dict):
        for x in v.values():
            yield from _walk(x)
    elif isinstance(v, list):
        for x in v:
            yield from _walk(x)
    else:
        yield v


def allowed(req) -> dict:
    nums, codes, cats = set(), set(), set()
    for v in _walk(req):
        if isinstance(v, bool) or v is None:
            continue
        if isinstance(v, (int, float)):
            nums.add(float(v))
            continue
        s = str(v)
        codes |= set(_CODE.findall(s)) | set(_CAS.findall(s)) | {u.replace(" ", "") for u in _UN.findall(s)}
        cats |= set(_CATEGORY.findall(s))
        if re.fullmatch(r"\d[A-C]?(:.*)?", s):  # 구분 값 자체('2', '1A', '3:마취')
            cats.add(s.split(":")[0])
        nums |= {float(n.replace(",", "")) for n in _NUM.findall(s)}
    shares = [i.get("share") for i in ((req.get("trace") or {}).get("inputs") or []) if isinstance(i, dict)]
    nums |= {round(s * 100, 6) for s in shares if isinstance(s, (int, float))}
    return {"nums": nums, "codes": codes, "cats": cats}


def _num_ok(x, dec, nums):
    return any(round(a, dec) == round(x, dec) or abs(a - x) <= 0.005 * max(abs(a), 1e-12) for a in nums)


def check(resp, req) -> list[str]:
    """설명 글의 숫자·코드·구분이 요청(근거)에 모두 있는지. 문제 목록(빈 목록이면 통과)."""
    if not isinstance(resp, dict) or not isinstance(resp.get("summary"), str) or not resp["summary"].strip():
        return ["응답 형식이 맞지 않음(summary 없음)"]
    ok = allowed(req)
    text = " ".join([resp["summary"]] + [str(x) for x in (resp.get("reasons") or []) + (resp.get("basis") or [])])
    problems = []
    for code in _CODE.findall(text) + _CAS.findall(text):
        if code not in ok["codes"]:
            problems.append(f"근거에 없는 코드 {code}")
    for un in _UN.findall(text):
        if un.replace(" ", "") not in ok["codes"]:
            problems.append(f"근거에 없는 UN번호 {un}")
    for c in _CATEGORY.findall(text):
        if c not in ok["cats"]:
            problems.append(f"근거에 없는 구분 {c}")
    rest = _TERM.sub(" ", _SECTION.sub(" ", _CATEGORY.sub(" ", _UN.sub(" ", _CAS.sub(" ", _CODE.sub(" ", text))))))
    for n in _NUM.findall(rest):
        dec = len(n.split(".")[1]) if "." in n else 0
        if not _num_ok(float(n.replace(",", "")), dec, ok["nums"]):
            problems.append(f"근거에 없는 숫자 {n}")
    for x in resp.get("used_numbers") or []:
        if isinstance(x, (int, float)) and not _num_ok(float(x), 6, ok["nums"]) and not _num_ok(float(x), 2, ok["nums"]):
            problems.append(f"used_numbers에 근거에 없는 숫자 {x:g}")
    return list(dict.fromkeys(problems))


# ── 문장틀 (LLM이 없거나 검사에 실패했을 때) ───────────────────────────

def _summary(req) -> str:
    f = req["finding"]
    name, verdict, t = f.get("item_name") or f.get("item"), f.get("verdict"), f.get("type")
    if f.get("section") == "15":
        m, e = f.get("msds") or {}, f.get("expected") or {}
        comp = next((i.get("name") for i in (req.get("trace") or {}).get("inputs") or [] if isinstance(i, dict)), None)
        who = f"{comp}(성분 {f.get('component')}) {name}" if comp else f"성분 {f.get('component')} {name}" \
            if f.get("component") not in (None, "MIX") else f"제품 {name}"
        if t == "규제 누락":
            if not m.get("applicable"):
                return f"{who}: 함량상 해당인데 MSDS 15항에 이 항목이 없습니다."
            return f"{who}: 함량상 해당인데 MSDS는 {ro(m['applicable'])} 적었습니다."
        if t == "기준 불일치":
            return f"{who}: 둘 다 해당이지만 기준 농도 표기가 다릅니다(MSDS {m.get('threshold')}, 지식DB {e.get('threshold')})."
        if t == "과기재":
            return f"{who}: 함량상 비해당인데 MSDS는 해당으로 적었습니다."
        if verdict == "경계":
            return f"{who}: 사람 확인이 필요합니다."
        return f"{who}: 기준을 확인하지 못해 판정하지 못했습니다."
    ex, ms = f.get("expected") or {}, f.get("msds") or {}
    ours = _cat(ex.get("low")) if ex.get("low") == ex.get("high") else f"{_cat(ex.get('low'))}~{_cat(ex.get('high'))}"
    msds = _cat(ms.get("category"))
    if t == "과소분류":
        return f"{name}: 계산 결과는 {ours}인데 MSDS는 {ro(msds)} 더 약하게 적었습니다."
    if t == "과대분류":
        return f"{name}: 계산 결과는 {ours}인데 MSDS는 {ro(msds)} 더 강하게 적었습니다."
    if t == "형태·세부 표기" and ms.get("route_form") and ms.get("route_form") != ex.get("route_form"):
        return (f"{name}: 구분은 같지만 흡입 형태가 다릅니다"
                f"(MSDS {ms['route_form']} {msds}, 계산 {ex.get('route_form')} {ours}).")
    if t == "형태·세부 표기":
        return f"{name}: 구분 순위는 같지만 세부 표기가 다릅니다(MSDS {msds}, 계산 {ours})."
    if t == "표시 요소 불일치":
        return f"{name}: MSDS 2항 분류에서 도출한 값과 MSDS 기재가 다릅니다."
    if verdict == "경계":
        return f"{name}: 계산 결과가 {ours}로 갈려 사람 확인이 필요합니다."
    return f"{name}: 기준정보나 입력값이 없어 판정하지 못했습니다."


def template(req) -> dict:
    f, t = req["finding"], req.get("trace") or {}
    reasons = [c["text"] for c in req.get("causes") or []] or [f.get("reason") or ""]
    rule = t.get("rule") or {}
    basis = [x for x in (f"적용 규칙 {rule['id']}" + (f" ({rule['basis']})" if rule.get("basis") else "") if rule.get("id") else None,
                         f"지식 버전 {t['knowledge_version']}" if t.get("knowledge_version") else None) if x]
    basis += [f"MSDS {e['page']}쪽: {e['text']}" for e in (req.get("evidence") or [])[:2] if e.get("page")]
    return {"summary": _summary(req), "reasons": reasons[:4], "basis": basis[:3], "used_numbers": []}


# ── 실행 ──────────────────────────────────────────────────────────────

# 외부 중계(MonoRouter: 교육원 키로 GPT·Claude 호출)로 가는 모델은 설명에 쓰지 않는다. 요청에 HTODB 값·조문이 들어가
# 외부로 나가면 안 되고(D-47), 과제 조건도 '외부 API 사용 불가·오픈소스 LLM 직접 서빙'이다.
EXTERNAL_BASE_URL_ENVS = {"LLM_BASE_URL"}


class ChatExplainer:
    """configs/models.yaml 의 모델로 설명을 받는다(extract/client.ChatClient 재사용, OpenAI 호환 — vLLM·furiosa-llm).

    호출: explainer(system, user) → (응답 dict 또는 None, 기록 dict). 시험에서는 같은 모양의 함수를 대신 넘긴다.
    """

    def __init__(self, tag: str | None = None, client=None, max_tokens: int = 1500, cfg: dict | None = None):
        if client is None:
            if cfg is None:
                from ..extract.client import load_model_config
                cfg = load_model_config(tag)
            if cfg.get("base_url_env") in EXTERNAL_BASE_URL_ENVS:
                raise ValueError(f"'{tag}'는 외부 중계 모델이라 설명에 쓸 수 없음(D-47). 온프레미스 태그(vLLM·RNGD)를 쓰세요.")
            from ..extract.client import ChatClient
            client = ChatClient(cfg)
        self.client, self.max_tokens = client, max_tokens
        self.model = getattr(client, "model", tag)

    def __call__(self, system: str, user: str):
        r = self.client.call(system, [{"type": "text", "text": user}], RESPONSE_SCHEMA, "explain_finding",
                             max_tokens=self.max_tokens)
        meta = {"model": getattr(r, "model", self.model), "seconds": round(getattr(r, "seconds", 0) or 0, 2),
                "errors": list(getattr(r, "errors", []) or [])[:3]}
        return (r.parsed if getattr(r, "ok", False) else None), meta


def _user(req, problems=None):
    text = "아래 판정을 설명하세요. 판정은 바꾸지 마세요.\n" + json.dumps(req, ensure_ascii=False)
    if problems:
        text += ("\n\n앞 응답이 검사에 걸렸습니다: " + "; ".join(problems[:6])
                 + "\n요청에 있는 숫자·코드·구분만 써서 다시 쓰세요.")
    return text


def explain_finding(f, trace, item=None, llm=None, retries: int = 1) -> dict:
    req = build_request(f, trace, item)
    tried, meta = [], {}
    if llm is not None:
        problems = None
        for _ in range(retries + 1):
            resp, meta = llm(SYSTEM, _user(req, problems))
            problems = check(resp, req) if resp is not None else ["LLM 응답 없음: " + "; ".join(meta.get("errors") or [])]
            if not problems:
                return _out("llm", resp, req, meta, tried)  # 다시 요청해 통과했으면 앞 문제를 남긴다
            tried += problems
    return _out("template", template(req), req, meta, tried)


def _out(by, resp, req, meta, problems):
    reasons = [str(x) for x in resp.get("reasons") or []]
    return {"by": by, "checked": not check(resp, req), "summary": resp["summary"], "reasons": reasons,
            "basis": [str(x) for x in resp.get("basis") or []], "text": " ".join([resp["summary"]] + reasons),
            "used_numbers": resp.get("used_numbers") or [], "model": meta.get("model") if by == "llm" else None,
            "seconds": meta.get("seconds") if by == "llm" else None,
            "llm_problems": list(dict.fromkeys(problems)), "evidence": req["evidence"]}


def explain_consistency(result: dict, item: dict | None = None, llm=None, *, ids=None) -> dict:
    """run_consistency 결과에 explanation 을 붙인다(일치가 아닌 줄만). ids 를 주면 그 판정 줄만, 이미 설명이 있는 줄은 건너뛴다.
    반환: 집계."""
    c = result["consistency"]
    stats = {"설명": 0, "llm": 0, "template": 0, "검사 통과": 0, "대체": 0}
    for f in c["findings"]:
        if f["verdict"] == "일치" or (ids is not None and f["id"] not in ids) or "explanation" in f:
            continue
        e = explain_finding(f, c.get("traces", {}).get(f.get("trace_id")), item, llm)
        f["explanation"] = e
        stats["설명"] += 1
        stats[e["by"]] += 1
        stats["검사 통과"] += e["checked"]
        stats["대체"] += bool(llm is not None and e["by"] == "template")
    c["assumptions"] = list(c.get("assumptions") or []) + [a for a in EXPLAIN_ASSUMPTIONS if a not in (c.get("assumptions") or [])]
    return stats
