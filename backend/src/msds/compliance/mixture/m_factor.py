"""수생환경 유해성 곱셈계수(M)를 지식DB 수생독성 값으로 정한다 (설계서 36·56장, D-07).

  급성 M : GHS0311~0314(어류·갑각류·조류·기타) L(E)C50 중 쓸 수 있는 값의 최솟값 → rules/m_factor.yaml acute 표
  만성 M : GHS0325~0328 NOEC(또는 EC10)의 최솟값 + GHS0331 생분해성 → chronic 표(빠르게 분해되는지에 따라 다름)
           NOEC 가 없으면 급성 L(E)C50 표로 정한다(TO21 로직 v6 33쪽)
  쓸 값이 없거나 값이 표 밖이면 M 을 정하지 않고(None) 이유를 남긴다. 그 성분이 구분 1이면 evaluate_item.build_m 이
  규칙표 m_factor_default(1)를 쓰고 '가정'으로 표시한다.

문장 파싱은 htodb.parsers 와 같은 규칙(부등호·범위 최솟값, D-12·D-21)에 두 가지를 더했다.
  - ㎍/L 값은 1/1000 해서 mg/L 로 쓴다(parsers 는 mg/L 만 읽음 — 독성이 아주 강한 물질은 ㎍/L 로 적힌 경우가 많다).
  - 한 문장에 값이 여럿이면 모두 읽어 최솟값을 쓴다(parsers.parse_lc50 은 첫 값만 읽음).
"""
from decimal import Decimal
from functools import lru_cache
import re

from ..htodb.parsers import AQUATIC_ACUTE_DIVS, AQUATIC_CHRONIC_DIVS, NOEC_GAP, NUM, RAPID_DIV, SIGNS, parse_rapid
from .params import RULES_DIR

ITEMS = ("ENV_AQ_ACUTE", "ENV_AQ_CHRONIC")
BASIS = "rules/m_factor.yaml (고시 제2026-26호 별표1 4.2 다, TO21 로직 v6 30·33쪽)"

_MG = r"㎎/ℓ|㎎/L|mg/l|mg/L"
_UG = r"㎍/ℓ|㎍/L|µg/L|μg/L|ug/L|µg/l|μg/l|ug/l"
_UNIT = rf"({_MG}|{_UG})"
_LC50 = re.compile(r"(?:LC50|EC50|ErC50|EbC50|EyC50|EL50)\s*[:=]?\s*([＞＜><≥≤≧≦]?)\s*" + NUM
                   + r"\s*(?:~\s*" + NUM + r")?\s*" + _UNIT)
_NOEC = re.compile(r"(?:NOEC|ErC10|EbC10|EC10)(?!\d+\s*[=<>＞≥≤])" + NOEC_GAP + r"([=<>＞＜≥≤]?)\s*" + NUM
                   + r"\s*" + _UNIT)


@lru_cache
def load_m_rules() -> dict:
    import yaml
    with open(RULES_DIR / "m_factor.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _mg(value: str, unit: str) -> float:
    v = float(value.replace(",", ""))
    return v / 1000 if re.fullmatch(_UG, unit) else v


def _values(rx, text):
    """문장 → [(부등호, mg/L 값)]. 범위(a ~ b)는 최솟값 a."""
    out = []
    for m in rx.finditer(text or ""):
        unit = m.groups()[-1]
        out.append((SIGNS.get(m.group(1), "="), _mg(m.group(2), unit)))
    return out


def aquatic_values(db_rows) -> dict:
    """tb_eng_chem_toxicity_test_info 행 → {"lc50", "noec", "rapid", "unused"}.

    lc50·noec 는 쓸 수 있는 값 중 최솟값 {"value", "div_code", "text"} 또는 None. rapid 는 True/False/None.
    unused 는 수생 행인데 값을 못 쓴 이유 목록(부등호 >·<, 단위·형식 불명).
    """
    use = set(load_m_rules()["use_signs"])
    best = {"lc50": None, "noec": None}
    rapid, unused = [], []
    for r in db_rows or []:
        div, text = r.get("div_code"), r.get("primary_value_text") or ""
        if div in AQUATIC_ACUTE_DIVS or div in AQUATIC_CHRONIC_DIVS:
            key, rx = ("lc50", _LC50) if div in AQUATIC_ACUTE_DIVS else ("noec", _NOEC)
            vals = _values(rx, text)
            ok = [v for s, v in vals if s in use]
            if not ok:
                unused.append(f"{div} '{text[:60]}' — " + ("부등호 >·< 값만 있음(D-12)" if vals else "값·단위를 읽지 못함"))
                continue
            v = min(ok)
            if best[key] is None or v < best[key]["value"]:
                best[key] = {"value": v, "div_code": div, "text": text}
        elif div == RAPID_DIV:
            rd = parse_rapid(text)
            if rd is not None:
                rapid.append(rd)
    # 생분해성 행이 서로 다르면 '빠르게 분해되지 않음'을 택한다(M 이 더 큰 쪽, 보수적)
    rd = None if not rapid else (False if False in rapid else True)
    return {**best, "rapid": rd, "unused": unused}


def m_from(value: float, spec: dict):
    """표에서 M. 값이 upper 보다 크면 표 밖(None). 마지막 줄보다 작으면 10배씩 계속(고시 표 주석)."""
    if value <= 0 or value > spec["upper"]:   # 0 이하는 잘못 읽은 값
        return None
    for lower, m in spec["table"]:
        if value > lower:
            return m
    lower, m = Decimal(str(spec["table"][-1][0])), spec["table"][-1][1]
    while Decimal(str(value)) <= lower:
        lower, m = lower / 10, m * 10
    return m


def _fmt(x):
    return f"{x:g}"


def m_factors(vals: dict) -> dict:
    """aquatic_values 결과 → {ENV_AQ_ACUTE: {"m", "basis"}, ENV_AQ_CHRONIC: {"m", "basis"}}. m 이 None 이면 basis 가 이유."""
    rules = load_m_rules()
    lc50, noec = vals.get("lc50"), vals.get("noec")

    def acute():
        if lc50 is None:
            return None, "지식DB 급성 L(E)C50(GHS0311~0314) 쓸 값 없음"
        m = m_from(lc50["value"], rules["acute"])
        where = f"L(E)C50 {_fmt(lc50['value'])} mg/L ({lc50['div_code']})"
        return (m, f"{where} → M={m}") if m else (None, f"{where} — M 표 밖(> {_fmt(rules['acute']['upper'])} mg/L)")

    out = {"ENV_AQ_ACUTE": dict(zip(("m", "basis"), acute()))}
    if noec is not None:
        rd = vals.get("rapid")
        kind = "rapid" if rd else "not_rapid"
        spec = rules["chronic"][kind]
        how = ("빠르게 분해됨" if rd else "빠르게 분해되지 않음" if rd is False
               else "생분해성 자료 없음 → 빠르게 분해되지 않는 것으로 봄")
        m = m_from(noec["value"], spec)
        where = f"NOEC {_fmt(noec['value'])} mg/L ({noec['div_code']}), {how}"
        out["ENV_AQ_CHRONIC"] = ({"m": m, "basis": f"{where} → M={m}"} if m else
                                 {"m": None, "basis": f"{where} — M 표 밖(> {_fmt(spec['upper'])} mg/L)"})
    else:
        m, why = acute()
        out["ENV_AQ_CHRONIC"] = {"m": m, "basis": f"NOEC 없음 → 급성 값으로 정함(TO21 로직 v6 33쪽): {why}"}
    return out
