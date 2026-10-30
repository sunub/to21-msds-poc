"""검수 화면의 문장 카드: 검수표 칸 값을 사람 말로 바꾼다. review_app을 가져오지 않는다(순환 방지) — 표는 인자로 받는다."""
import json
import re
from decimal import Decimal

from msds.common.align import generic
from msds.common.jsonpath import from_cell
from msds.review.build_gold import TAGS, _decide, _items, _under

GLOSSARY = {   # 도메인 용어 한 줄 풀이 (어떤 문서에도 같음)
    "LD50": "시험 동물의 절반이 죽는 투여량 (작을수록 독함)",
    "LC50": "시험 동물의 절반이 죽는 공기·물 속 농도 (작을수록 독함)",
    "EC50": "시험 생물의 절반에 영향이 나타나는 농도",
    "NOEC": "영향이 나타나지 않은 가장 높은 농도",
    "TWA": "8시간 일하는 동안의 평균 노출 허용 농도",
    "STEL": "15분 동안 넘으면 안 되는 단시간 노출 허용 농도",
    "BEI": "몸속(소변·혈액)에서 재는 생물학적 노출 지표",
    "BCF": "생물 몸속에 쌓이는 정도 (클수록 잘 쌓임)",
    "NOAEL": "해로운 영향이 나타나지 않은 가장 많은 양", "LOAEL": "해로운 영향이 처음 나타난 가장 적은 양",
    "ATE": "급성 독성 추정값 (작을수록 독함)",
    "경구": "입으로 먹었을 때", "경피": "피부에 묻었을 때", "흡입": "숨으로 들이마셨을 때",
    "피부 호칭": "피부로 흡수될 수 있다는 표시 (피부 자극이 아님)", "피부 표기": "피부로 흡수될 수 있다는 표시 (피부 자극이 아님)",
    "Skin": "피부로 흡수될 수 있다는 표시 (피부 자극이 아님)",
    "영업비밀": "회사가 성분 이름·함량을 가린 것",
    "KSSTDG": "국내 위험물 운송 규정 이름 (육상)", "ADR": "유럽 위험물 운송 규정 이름 (육상)", "RID": "유럽 철도 운송 규정 이름 (육상)",
    "IMDG": "국제 해상 위험물 운송 규정 이름 (해상)", "IATA": "국제 항공 위험물 운송 규정 이름 (항공)", "ICAO": "국제 항공 위험물 운송 규정 이름 (항공)",
    "결과기술": "수치 없이 시험 결과를 글로 적은 것",
}
_TERM = {k: re.compile(r"(?<![A-Za-z0-9])" + re.escape(k) + r"(?![A-Za-z0-9])", re.I) for k in GLOSSARY}   # 칩 글자·원문 속 용어 찾기
YES, NO = ("예", "yes", "해당됨", "해당"), ("아니오", "아니요", "no", "해당없음", "해당 없음", "비해당")   # 원문의 예·아니오 낱말 (한 글자 o·x는 'o-Xylene'·'4 x 5L'에 걸려 뺀다)
SPECIES = {   # 흔한 시험 생물 이름 짝 (어떤 문서에도 같음). 긴 이름부터 찾는다
    "rat": "쥐", "mouse": "생쥐", "rabbit": "토끼", "guinea pig": "기니피그", "dog": "개", "monkey": "원숭이",
    "hamster": "햄스터", "fish": "물고기", "랫드": "쥐", "마우스": "생쥐",
    "daphnia magna": "물벼룩", "daphnia": "물벼룩", "algae": "조류(물풀)", "oncorhynchus mykiss": "무지개송어",
    "pimephales promelas": "팻헤드미노(물고기)", "danio rerio": "제브라피시(물고기)", "lepomis macrochirus": "블루길(물고기)",
    "cyprinus carpio": "잉어", "oryzias latipes": "송사리", "poecilia reticulata": "구피(물고기)",
    "raphidocelis subcapitata": "녹조류", "pseudokirchneriella subcapitata": "녹조류", "selenastrum capricornutum": "녹조류",
}
_SPECIES = re.compile(r"(?<![a-z가-힣])(" + "|".join(map(re.escape, sorted(SPECIES, key=len, reverse=True))) + r")(?![a-z가-힣])", re.I)
SIGNS = "(> = 초과, ≥ = 이상, < = 미만, ≤ = 이하)"
APPLICABLE = "해당 = 이 규제에 걸림 · 비해당/해당없음 = 걸리지 않음"
APPLICABLE_FIELDS = {"applicable", "value_raw", "designated", "marine_pollutant"}   # 규제 해당 여부 칸만 (상태·분류·용기등급의 '해당 없음'은 뜻이 다르다)
STATUS_TIP = {"값있음": "적혀 있음 = 원문에 이 값이 적혀 있음", "자료없음": "자료 없음 = 원문에 ‘자료 없음’·‘정보 없음’처럼 적힘",
              "해당없음": "해당 없음 = 이 제품에는 맞지 않는 항목", "미기재": "적혀 있지 않음 = 원문의 이 칸이 비었거나 ‘-’",
              "판독불가": "판독불가 = 원문 글자를 읽을 수 없음", "마스킹": "마스킹 = 원문 값이 가려져 있음"}   # 상태 칸 풀이
FIELD_TIP = {   # 명세 설명이 기술 말뿐인 칸의 쉬운 풀이 (칸 종류마다 같음, 문서 무관)
    "regulations[].country": "규제한 나라·지역 약자 (US = 미국, EU = 유럽연합, JP = 일본 등). 국내 규제면 비어요",
    "hazard.h_statements[].code": "유해·위험 문구 번호 (H로 시작). 원문의 번호와 같은지 보세요",
    "hazard.h_statements[].text": "이 번호의 원문 문장 그대로", "hazard.p_statements[].text": "이 번호의 원문 문장 그대로",
}
_STATUS = {"값있음": "적혀 있음", "자료없음": "자료 없음", "해당없음": "해당 없음", "미기재": "적혀 있지 않음"}
_LOWER = {">": "초과", ">=": "이상"}
_UPPER = {"<": "미만", "<=": "이하"}
_COND = [("temp", "온도", "temp_unit"), ("pressure", "압력", "pressure_unit"), ("method", "방법", None),
         ("reference", "기준", None), ("conc_value", "농도", "conc_unit")]   # 화면 condText와 같은 순서


def card_key(path: str) -> str:
    """화면 gkey(p)와 같은 규칙: 마지막 ']'까지, 그것이 msds[n]이면 msds[n].<첫 이름>."""
    g = path[:path.rfind("]") + 1]
    return ".".join(path.split(".")[:2]) if g.startswith("msds[") and g.endswith("]") and "." not in g else g


def _num(x) -> str:
    """2000.0 → '2000', 1e-05 → '0.00001' (끝 .0·지수 꼴 없이)."""
    return format(Decimal(repr(x)).normalize(), "f") if isinstance(x, float) else str(x)


def _q_status(o: dict):
    """Q의 상태. 상태가 비었으면 수가 있을 때만 값있음."""
    return o.get("status") or ("값있음" if any(o.get(k) is not None for k in ("value", "lower", "upper")) else None)


def _quantity(o: dict) -> str:
    unit, raw, st = f" {o['unit']}" if o.get("unit") else "", str(o.get("raw") or ""), _q_status(o)
    if st is None:
        return raw or "비움"
    if st != "값있음":
        word = _STATUS.get(st, st)
        return word if not raw or raw.replace(" ", "") == word.replace(" ", "") else f"{word} ({raw})"
    lo, up = o.get("lower") is not None, o.get("upper") is not None
    pre, a, b = "약 " if o.get("approx") else "", _num(o.get("lower")), _num(o.get("upper"))
    if lo and up:                         # 닫힌 범위만 '~', 열린 끝이 있으면 말로 (부등호를 빠뜨리지 않는다)
        if o.get("lower_op") in (">=", None) and o.get("upper_op") in ("<=", None):
            return f"{pre}{a}~{b}{unit}"
        return f"{pre}{a} {_LOWER.get(o.get('lower_op'), '이상')} {b}{unit} {_UPPER.get(o.get('upper_op'), '이하')}"
    if lo:
        return f"{pre}{a}{unit} {_LOWER.get(o.get('lower_op'), '초과')}"
    if up:
        return f"{pre}{b}{unit} {_UPPER.get(o.get('upper_op'), '미만')}"
    if o.get("value") is not None:
        return f"{pre}{_num(o['value'])}{unit}"
    return raw or "비움"


def _comp(path: str, s: str, comps: dict):
    """성분 번호 → 성분명. comps 키는 'MSDS 순번|성분 순번'(여러 MSDS 문서) 또는 성분 순번만."""
    m = re.match(r"msds\[(\d+)\]", path)
    return (comps.get(f"{m.group(1)}|{s}") if m else None) or comps.get(s)


def _text(v, path: str, names: dict, comps: dict) -> str:
    if v is None or v == "":
        return "비움"
    if isinstance(v, bool):
        return "예" if v else "아니요"
    if isinstance(v, list):
        return " · ".join(_text(x, path, names, comps) for x in v) or "비움"
    if isinstance(v, dict):
        if "raw" in v:
            return _quantity(v)
        if "text" in v or "value" in v:   # 문장 목록 항목
            key, val = v.get("key"), v.get("value")
            return f"{key}: {val}" if key and val not in (None, "") else str(key or val or v.get("text") or "비움")
        if any(k in v for k, _, _ in _COND):
            return ", ".join(f"{n} {_num(v[k])}{' ' + v[u] if u and v.get(u) else ''}" for k, n, u in _COND if v.get(k) is not None) or "조건 없음"
        return json.dumps(v, ensure_ascii=False)
    s = _num(v)
    if path.rsplit(".", 1)[-1] in ("comp_ref", "parent_seq"):
        return _comp(path, s, comps) or s
    return (names.get(s) or [_STATUS.get(s, s)])[0]


def human(path: str, cell: str, names: dict, comps: dict) -> dict:
    """검수표 칸 글 → {"text": 사람 말, "code": 원래 TO21 코드(코드 값일 때만)}."""
    v = from_cell(cell)
    code = v if isinstance(v, str) and v in names else None
    return {"text": _text(v, path, names, comps), "code": code}


# 문장 틀: 목록 종류(번호 지운 경로) → 조각 차례. 조각 안의 {칸}이 하나라도 없으면 그 조각을 뺀다. {a|b}: a가 없으면 b.
# 틀에 없는 칸·틀 없는 목록은 문장 뒤에 '이름: 값' 칩으로 붙는다(빠지는 줄 없음). 문서 무관.
_TOX = ["{comp_ref}을 ", "{endpoint} ", "{species} 실험에서 ", "{descriptor}은 ", "{q|status}"]
_TOX_NOSP = ["{comp_ref}의 ", "{endpoint} ", "{descriptor}: ", "{q|status}"]   # 시험종이 없으면 '을 … 실험에서'가 매달리지 않게
TEMPLATES: dict[str, list[str]] = {
    "toxicity[]": _TOX, "ecotox[]": _TOX,
    "exposure_limits[]": ["{comp_ref}의 ", "{standard} ", "{limit_type} ", "기준값은 {q}"],
    "physchem[]": ["{comp_ref}의 ", "{prop_code}은 ", "{q} ", "{text_value}"],
    "regulations[]": ["{comp_ref}은 ", "{law} ", "{item_code|item_raw}에 ", "{applicable}"],
    "cmr[]": ["{comp_ref}의 ", "{hazard}: ", "{agency} 분류 ", "{class|status}"],
    "components[]": ["{name}", " (CAS {cas_no})", " 함유량 {content}"],
    "hazard.classes[]": ["{class_code} ", "구분 {category}"],
    "hazard.h_statements[]": ["{code} ", "{text}"], "hazard.p_statements[]": ["{code} ", "{text}"],
    "hazard.pictograms[]": ["{code}"],
    "transport[]": ["{mode} 운송: ", "유엔번호 {un_no}, ", "위험성 등급 {hazard_class}, ", "용기등급 {packing_group}"],
    "companies[]": ["{role} ", "{name}"], "companies[].contacts[]": ["{type} ", "{value}"],
    "extras[]": ["표에 자리가 없어 따로 모아 둔 내용: ‘{title_raw}’"],
    "narratives[]": ["{item_code}"],                 # 문장은 각자 카드
}
ALT = {"toxicity[]": ("species", _TOX_NOSP), "ecotox[]": ("species", _TOX_NOSP)}   # 목록 → (이 칸이 없으면, 이 틀)
AUTO = {"seq", "page", "page_start", "page_end", "section_no"}   # 사람이 판단할 수 없어 숨기고 자동 확인 (이름 규칙)
DERIVED = {"hazard.p_statements[].type", "hazard.h_statements[].system", "hazard.classes[].group"}   # 코드에서 정해지는 칸
META = {"after_item", "reason", "suggested_code", "match_score", "detection"}   # 모델이 정한 정보: 판단 안 함, 작게 보임
QUESTIONS = {"no_hazardous_component": "유해 성분이 없다", "regulated": "운송 규제 대상이다",
             "trade_secret": "영업비밀이라 성분을 가렸다", "classified": "유해성 분류 대상이다"}
QLABEL = {"no_hazardous_component": "유해 성분 없음", "regulated": "운송 규제 대상",   # 섞인 카드의 예·아니오 칩 이름
          "trade_secret": "영업비밀로 가림", "classified": "유해성 분류 대상"}
HINT_KREACH = ("화평법 줄에 번호·표시(KE-…, 321, CMR)가 있으면 ‘해당’, ‘해당없음·비해당·N/A’면 ‘비해당’, "
               "‘공급자에게 문의’ 같은 안내문이면 비워 둡니다(팀 규칙 A-1)")
HINT_PACKING = "운송 비대상 행의 용기등급 표기(비움/해당없음)는 팀에서 아직 정하지 않았어요. 메모에 남겨 주세요"
_P_TYPE = {"1": "일반", "2": "예방", "3": "대응", "4": "저장", "5": "폐기"}   # GHS P 코드 첫 자리
_GROUP = {"PH": "물리적", "HH": "건강", "EN": "환경"}                        # 분류 코드 머리
_JOSA = {"을": "를", "은": "는", "이": "가", "과": "와"}
_NOJOSA = {"을": " —", "은": ":", "이": ":", "과": " ·"}   # 받침을 모를 때(영문 끝): 조사 없이 잇는다 ('Benzene — 급성 독성')


def _batchim(word: str):
    """끝 글자 받침이 있나. 한글·숫자가 아니면 None (정할 수 없음)."""
    ch = word.rstrip(" )]’'\"")[-1:]
    if "가" <= ch <= "힣":
        return (ord(ch) - 0xAC00) % 28 > 0
    return ch in "013678" if ch.isdigit() else None   # 영·일·삼·육·칠·팔


def _josa(word: str, piece: str) -> str:
    """칩 바로 뒤 조사를 앞 글자 받침으로 고른다. 정할 수 없으면 조사 없이 ' — '·':'로 잇는다."""
    j = piece[:1]
    if j not in _JOSA or piece[1:2] not in ("", " ", ",", ":"):
        return piece
    has = _batchim(word)
    return (_NOJOSA[j] if has is None else j if has else _JOSA[j]) + piece[1:]


def dropped(rows: list[dict], model: str) -> dict[str, list[str]]:
    """골드에서 통째로 빠지는 목록 항목 → 그렇게 만든 줄들. 골드(build_gold._assemble)와 같은 규칙·같은 함수(_decide):
    항목 안 줄 하나라도 '삭제' 결정(삭제, 값이 없는 모델 채택)이거나, 항목 자체인 한 칸(문장 등)이 빈 값.
    model: 그 문서 골드의 기본값 모델 (build_gold.default_model). 빠뜨리면 오류 (기본값을 두지 않는다)."""
    out = {}
    for r in rows:
        m = re.fullmatch(r"(msds\[\d+\]\.)(.+)", r["경로"])
        its = _items(m.group(2)) if m else []
        if not its:
            continue
        try:
            k = _decide(r, TAGS[model])
        except ValueError:                # 엑셀에 적힌 엉뚱한 결과: 골드 만들기가 막는다
            continue
        if k[0] == "del" or (k[0] == "set" and k[1] is None and its[-1] == m.group(2)):
            out.setdefault(m.group(1) + its[-1], []).append(r["경로"])
    return out


def gone_by(path: str, drop: dict) -> str:
    """이 경로를 품은, 골드에서 빠지는 항목 (없으면 '')."""
    return next((d for d in drop if _under(path, [d])), "")


def comps_from_rows(rows: list[dict], drop: dict) -> dict[str, str]:
    """성분 번호 → 성분명 표 (MSDS 건마다): 'MSDS 순번|성분 순번' 키와 MIX. 성분명이 비면 순번.
    골드에서 빠지는 성분(drop)은 이름 대신 ''(카드가 '가리키는 성분이 골드에서 빠져요'로 알린다)."""
    out = {"MIX": "제품 전체"}
    cur = {r["경로"]: from_cell(_cell_now(r)) for r in rows}
    for p, v in cur.items():
        if (m := re.fullmatch(r"msds\[(\d+)\]\.components\[k=[^\]]*\]\.seq", p)) and v not in (None, ""):
            name = cur.get(p[:-4] + ".name")
            key = f"{m.group(1)}|{_num(v)}"
            if gone_by(p, drop):
                out.setdefault(key, "")
            else:
                out[key] = _num(name) if name not in (None, "") else _num(v)
    return out


def _snip(r: dict) -> str:
    """지금 값의 근거 줄: 고친 줄(수정·누락 추가)은 수정 원문 조각, 나머지는 AI 원문 조각."""
    fixed = r.get("검수 결과") in ("수정", "누락 추가") and r.get("수정값")
    return (r.get("수정 원문 조각") if fixed else "") or r.get("Claude 원문 조각") or r.get("GPT 원문 조각") or ""


def _cell_now(r: dict) -> str:
    """줄의 지금 값(골드와 같은 규칙): 수정·누락 추가 줄은 수정값, 나머지(채택·삭제·미검수)는 AI 값. 엑셀에 남은 수정값은 값이 아니다."""
    return (r.get("검수 결과") in ("수정", "누락 추가") and r.get("수정값")) or r.get("Claude 값") or r.get("GPT 값") or ""


FIX_ASK = "‘다른 칩이 있어요’를 누르고 이 칩을 눌러 맞는 값을 적어 주세요"


def _odd(r: dict) -> str:
    """엑셀에서만 생기는, 화면 값과 골드가 갈리는 판단 → ⚠ 글 (화면은 이런 칸을 '확인함'으로 세지 않는다. 화면 rowOdd와 같은 규칙).
    '수정'·'누락 추가'인데 맞는 값이 빔 → 골드 빈칸. 값이 없는 모델을 채택 → 골드에서 삭제(목록 항목이면 항목째, build_gold._assemble)."""
    res = r.get("검수 결과") or ""
    if res in ("수정", "누락 추가") and not r.get("수정값"):
        return f"이 칸은 고친 값이 비어 있어 골드에서 {'이 항목이 빠져요' if r['경로'].endswith(']') else '빈칸이 돼요'}. {FIX_ASK}"   # 항목 자체인 한 칸(문장)은 항목째
    if res.endswith(" 채택") and not r.get(res[:-3] + " 값"):
        where = "이 항목이 통째로 빠져요" if "[" in r["경로"].split(".", 1)[-1] else "이 칸이 비어요"
        return f"이 칸은 고른 값이 없어 골드에서 {where}. {FIX_ASK}"
    return ""


def _check(name: str, gfield: str, v, vals: dict, ex: str, pages: int) -> tuple[bool, str]:
    """숨긴 칸 자동 확인 → (통과, 까닭)."""
    s = "" if v is None else _num(v)
    if name == "seq":                     # review_app._explain의 순번 확인 결과를 따른다
        ok = bool(s) and "확인 필요" not in ex and ("자동 확인" in ex or not ex)
        return ok, ex or ("순번" if s else "순번이 비어 있어요")
    if name in ("page", "page_start", "page_end"):
        ok = s.isdigit() and 1 <= int(s) <= pages
        return ok, f"PDF {pages}쪽 안" if ok else f"쪽 번호({s or '비움'})가 PDF 쪽수({pages}쪽) 밖이에요"
    if name == "section_no":
        ok = s.isdigit() and 0 <= int(s) <= 16      # TO21 명세: 0(머리글)~16
        return ok, "MSDS 0~16항 안 (0 = 머리글)" if ok else f"항 번호({s or '비움'})가 0~16항 밖이에요"
    if name == "status":
        q = vals.get("q")
        want = _q_status(q) if isinstance(q, dict) else None
        return s == want, f"수치의 상태({want})와 같음" if s == want else f"행 상태({s or '비움'})와 수치의 상태({want or '비움'})가 달라요"
    code = str(vals.get("class_code" if gfield.endswith("group") else "code") or "")
    if gfield.endswith("p_statements[].type"):
        want = _P_TYPE.get(code[1:2]) if code.startswith("P") else None
    elif gfield.endswith("h_statements[].system"):
        want = "EUH" if code.startswith("EUH") else "GHS" if re.match(r"H\d", code) else "R" if re.match(r"R\d", code) else None
    else:
        want = _GROUP.get(code[:2], "기타") if code else None
    if want is None:
        return False, "코드가 없어 자동으로 확인할 수 없어요"
    return s == want, f"코드 {code} → {want}"


# 처음 보는 사람에게 안 맞는 풀이: 스키마·추출 규칙 말(정규식, 밑줄 이름, seq/Q/null, 'MIX'·'1A' 같은 따옴표 속 영문·숫자 보기, C5·R12 같은 표 번호, 재생성·추출기)
_TECH = re.compile(r"[_\\^$\[\]{}]|\b(?:seq|null|true|false|Q|value|unit|lower|upper|item|[CR]\d+)\b|['‘][A-Za-z0-9]|['’] →|재생성|추출기|분리|분해|쪼갬|YYYY")   # 마지막 줄: 추출 규칙 말
TIP_MAX = 120
CODE_TIP = "정해진 이름이에요{}. 원문의 어느 말인지 확인해 주세요"


def _plain(s: str) -> str:
    """명세 설명·값 풀이 → 쉬운 한 줄. 기술 말이 섞였으면 버린다."""
    s = re.split(r" — | \(TO21 명세서", s or "")[0].strip()
    s = re.sub(r"\s*\(R\d+\)$", "", s)                           # 끝의 규칙 번호
    if len(s) > TIP_MAX:
        s = re.sub(r" \(.*\)$", "", s)                            # 긴 풀이는 끝 괄호 설명을 뗀다
    s = re.sub(r"^TO21이 이 칸에 정한 값\((.*)\) 중 하나$", r"고를 수 있는 값: \1", s)
    if re.match(r"^\S+ = ", s) or _TECH.search(s):                  # 'TX_ORAL = …', 'false = …' (칩 글자·코드 줄과 겹침)
        return ""
    return s


def _pair(name: str, v) -> str:
    """짝 풀이(문서 무관): 수치는 원문 표기와 부호 뜻, 해당 여부, 시험종 영어 이름, 여러 값 목록."""
    if isinstance(v, dict) and v.get("raw"):
        raw = str(v["raw"])
        return f"원문 ‘{raw}’" + (f" {SIGNS}" if re.search(r"[<>≤≥]", raw) else "")
    if name == "status" and v in STATUS_TIP:
        return STATUS_TIP[v]
    if name in APPLICABLE_FIELDS and v in ("해당", "비해당", "해당없음"):
        return APPLICABLE
    if name == "species" and isinstance(v, str):
        found = dict.fromkeys(m.group(0) for m in _SPECIES.finditer(v))
        return " · ".join(f"{w} = {SPECIES[w.lower()]}" for w in found)
    if isinstance(v, list) and len(v) > 1:
        return "원문의 여러 값을 ‘ · ’로 나눠 적었어요"
    return ""


_squash = lambda x: re.sub(r"\s+", "", str(x)).lower()


def _terms(text: str, skip: str = "") -> list[str]:
    """칩 글자 속 용어('급성 독성(경피)'의 경피, '한국 OELs: 피부 호칭')의 풀이. 짧은 글자에만 (긴 문장은 칩 자체가 원문)."""
    if len(text) > 40:
        return []
    return [f"{k} = {g}" for k, g in GLOSSARY.items() if k != skip and _TERM[k].search(text)][:2]


def _why(text: str, snippet: str) -> str:
    """원문에 칩 글자가 그대로 없을 때 왜 그 값인지: 원문의 규정 이름(‘KSSTDG’ = … (육상)), 예·아니오 낱말(‘예’ → 해당)."""
    for k, g in GLOSSARY.items():
        if f"({text})" in g and _TERM[k].search(snippet):
            return f"원문 ‘{_TERM[k].search(snippet).group(0)}’ = {g}"
    for k in GLOSSARY:                    # 칩 글자 속 용어가 원문에 있으면 그 말을 옮긴 값 ('경피' → 급성 독성(경피))
        if _TERM[k].search(text) and (m := _TERM[k].search(snippet)):
            return f"원문 ‘{m.group(0)}’ → {text}"
    words = YES if text in ("해당", "예") else NO if text in ("비해당", "해당 없음", "아니요") else ()
    for w in words:
        if m := re.search(r"(?<![가-힣A-Za-z])" + re.escape(w) + r"(?![가-힣A-Za-z])", snippet, re.I):
            return f"원문 ‘{m.group(0)}’ → {text}"
    return ""


def _tip(path: str, label: str, h: dict, v, own: str, snippet: str, tips: dict, explain: dict, names: dict) -> str:
    """칩 풀이(한두 줄): 용어 풀이 → 짝 풀이 → 값 풀이(성분명 등) → 쉬운 칸 풀이 → 쉬운 명세 풀이 → 코드 이름 풀이 가운데 하나,
    칩 글자 속 용어 풀이, 코드면 원문의 가장 긴 표기 = 이름 (own: 원문에서 이 코드의 표기). 원문에 칩 글자가 그대로 없으면 왜 그 값인지.
    근거를 못 찾은 정해진 값의 '어떤 말을 옮긴 값인지'는 화면이 점선 칩에만 붙인다."""
    name = path.rsplit(".", 1)[-1]
    base = (GLOSSARY.get(str(v)) or _pair(name, v) or _plain(explain.get(path, ""))
            or FIELD_TIP.get(generic(path).removeprefix("msds[].")) or _plain(tips.get(path, "")))
    if base in (h["text"], label) or base.startswith(h["text"] + "("):    # '제품 전체(MIX)'처럼 칩 글자·칸 이름 되풀이는 뺀다
        base = ""
    code = own and h["code"] and _squash(own) != _squash(h["text"]) and f"원문 ‘{own}’ = {h['text']}"   # '원문 ‘증기압’ = 증기압' 되풀이는 뺀다
    why = ""
    if (isinstance(v, (str, int, float)) and not isinstance(v, bool) and snippet and not own and name not in ("comp_ref", "parent_seq")
            and _squash(h["text"]) not in _squash(snippet) and not (h["code"] and _squash(h["code"]) in _squash(snippet))):
        why = _why(h["text"], snippet)
    if not base and h["code"] and not own and not why:                    # 코드: 원문에서 근거를 못 찾음. 흔한 원문 표기를 보이고 확인을 부탁한다
        syn = list(dict.fromkeys(n for n in (names.get(h["code"]) or [])[1:] if n and _squash(n) != _squash(h["text"])))[:3]
        base = CODE_TIP.format(f" (원문 표기 예: {', '.join(syn)})" if syn else "")
    s = " · ".join(x for x in [base, *_terms(h["text"], str(v)), code, why] if x)
    return s if len(s) <= TIP_MAX else s[:TIP_MAX - 1] + "…"


def _own_form(code: str, snippet: str, names: dict) -> tuple[str, str, str]:
    """code_match가 없을 때(시험): 원문에서 이 코드 이름 중 가장 긴 것. 다른 코드는 보지 않는다."""
    low = snippet.lower()
    return max((n for n in names.get(code) or [] if n and n.lower() in low), key=len, default=""), "", ""


def build_cards(rows: list[dict], *, names: dict, comps: dict[str, str], labels: dict[str, str], tips: dict[str, str],
                pages: int, explain: dict[str, str], drop: dict, code_match=None) -> dict[str, dict]:
    """검수표 줄 → 카드(목록 항목 하나 = 문장 하나). 모든 줄은 칩·auto·meta 중 정확히 한 곳에 들어간다.
    code_match(코드, 원문 조각) → (이 코드의 원문 표기, 원문이 실은 다른 코드면 그 코드, 그 표기) (review_app._code_match)."""
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(card_key(r["경로"]), []).append(r)
    cm = code_match or (lambda c, s: _own_form(c, s, names))
    # drop: 문서 전체로 구한 골드에서 빠지는 항목 (카드 몇 장만 다시 만들 때도 같게)
    out = {key: _card(key, rs, names, comps, labels, tips, pages, explain, cm) for key, rs in groups.items()}
    for key, c in out.items():           # 골드에서 통째로 빠지는 항목의 카드: 그렇게 만든 줄(이 카드 밖 상위 항목 줄일 수도)과 '카드 전체 삭제'인지
        d = gone_by(key, drop)
        c["drop"] = {"by": drop[d], "all": all(r.get("검수 결과") == "삭제" for r in groups[key])} if d else None
    return out


def _overlap(prev: str, piece: str) -> str:
    """칩 글이 이음말 첫 낱말로 끝나면 그 낱말을 뺀다 ('… CMR 분류' + ' 분류 ' → ' ')."""
    w = piece.split()[0] if piece.strip() else ""
    if len(w) >= 2 and re.search(r"(?:^|[\s·])" + re.escape(w) + "$", prev):
        return piece.replace(w, "", 1).replace("  ", " ")
    return piece


def _lead(prev: str, text: str) -> str:
    """바로 앞 칩의 끝 낱말로 시작하는 칩 글은 그 낱말을 뗀다 ('위험물안전관리법' [위험물안전관리법 위험물] → [위험물])."""
    w = re.split(r"[\s·]", prev)[-1]
    rest = text[len(w):].strip() if len(w) >= 2 and text.startswith(w) and text[len(w):len(w) + 1] in (" ", "(") else ""
    return (rest[1:-1] if rest[:1] == "(" and rest[-1:] == ")" else rest) or text


def _trim(parts: list):
    """문장 끝 이음말의 ', '·' '·':'와 뒤가 없는 조사('LD50은')를 뗀다 (뒤 칸이 빠진 틀)."""
    if parts and parts[-1]["t"] == "text":
        parts[-1]["s"] = re.sub(r"^(은|는|을|를|이|가|과|와|의)$", "", parts[-1]["s"].rstrip(" ,:"))
        if not parts[-1]["s"]:
            parts.pop()


def _card(key, rs, names, comps, labels, tips, pages, explain, code_match) -> dict:
    tkey = generic(key).removeprefix("msds[].")
    field = lambda r: r["경로"][len(key) + 1:]          # 카드 안 칸 이름 (카드 자체인 줄은 '')
    vals = {field(r): from_cell(_cell_now(r)) for r in rs}
    parts, auto, meta, late, qs, cand = [], [], [], [], [], []
    label = lambda r: labels.get(r["경로"]) or field(r).rsplit(".", 1)[-1] or r["경로"]
    isq = lambda r: field(r).rsplit(".", 1)[-1] in QUESTIONS or isinstance(vals[field(r)], bool)   # 예·아니오 칸

    def chip(r, warn=""):                # 칩 글·풀이·⚠는 지금 값 기준 (고친 줄은 수정값과 그 근거 줄. 저장하면 화면이 이 카드를 다시 받는다)
        cell = _cell_now(r)
        h, v, name = human(r["경로"], cell, names, comps), from_cell(cell), field(r).rsplit(".", 1)[-1]
        snip = _snip(r)
        if name in ("comp_ref", "parent_seq") and not _comp(r["경로"], "" if v is None else _num(v), comps):
            mi = re.match(r"msds\[(\d+)\]", r["경로"])
            gone = mi and comps.get(f"{mi.group(1)}|{'' if v is None else _num(v)}") == ""   # 표에 있지만 골드에서 빠지는 성분
            warn = warn or ("가리키는 성분이 골드에서 빠져요. 성분 카드를 되살리거나 맞는 성분으로 고쳐 주세요" if gone else "성분표에 없는 성분 번호예요")
        own, other, form = code_match(h["code"], snip) if h["code"] else ("", "", "")
        if other and not other.startswith(h["code"] + "_"):     # 원문 표기가 실은 다른 코드의 것 ('특별관리대상물질' 속 '관리대상물질'). 하위 코드는 맞는 관계
            b = _batchim(form)
            warn = warn or f"원문 ‘{form}’{'은(는)' if b is None else '은' if b else '는'} ‘{(names.get(other) or [other])[0]}’ 표기예요. 맞는지 확인해 주세요"
        lb = QLABEL.get(name, label(r)) if isq(r) else label(r)
        if isq(r):                                             # 예·아니오: 무엇을 보고 정했는지
            say = f"‘{QUESTIONS[name]}’는 뜻의 말" if name in QUESTIONS else f"‘{lb}’ 표시"
            say += "이" if _batchim(say) else "가"                     # '말이', '표시가'
            tip = " · ".join(_terms(lb) + [f"원문에 {say} 없어서 ‘아니요’예요. 있으면 틀린 칩이에요" if v is False else
                                           f"원문에 {say} 있으면 예, 없으면 아니요"])
        else:
            tip = _tip(r["경로"], lb, h, v, own, "" if other else snip, tips, explain, names)   # ⚠가 이유를 말하면 '어떤 말을 옮긴 값인지'는 뺀다
        return {"t": "chip", "path": r["경로"], "label": lb, "text": h["text"], "code": h["code"], "tip": tip, "warn": warn}

    for r in rs:
        f = field(r)
        name, gfield = f.rsplit(".", 1)[-1], f"{tkey}.{generic(f)}"
        if odd := _odd(r):                                     # 숨길 칸이어도 칩으로 드러낸다
            late.append(chip(r, odd))
        elif r.get("검수 결과") == "누락 추가" and (name in META or name == "seq"):   # 사람이 넣은 줄의 순번·사유는 화면이 정한 값 (쪽·항 번호는 사람이 적어 아래 자동 확인으로)
            auto.append({"path": r["경로"], "label": label(r), "text": human(r["경로"], _cell_now(r), names, comps)["text"], "ok": True,
                         "why": "빠진 값 넣기로 화면이 정한 값"})
        elif name in META:
            meta.append({"path": r["경로"], "label": label(r), "text": human(r["경로"], _cell_now(r), names, comps)["text"]})
        elif name in AUTO or gfield in DERIVED or (name == "status" and "q" in vals):
            ok, why = _check(name, gfield, vals[f], vals, explain.get(r["경로"], ""), pages)
            if ok:
                auto.append({"path": r["경로"], "label": label(r), "text": human(r["경로"], _cell_now(r), names, comps)["text"], "ok": True, "why": why})
            else:
                late.append(chip(r, why))
        else:
            if isq(r):
                qs.append(f"이 문서에 ‘{QUESTIONS[name]}’는 말이 적혀 있나요?" if name in QUESTIONS else f"이 문서에 ‘{label(r)}’ 표시가 있나요?")
            cand.append(r)

    by = {field(r): r for r in cand}
    used = set()
    alt = ALT.get(tkey)
    for g in alt[1] if alt and alt[0] not in by else TEMPLATES.get(tkey, []):
        picks = [next((f for f in alt.split("|") if f in by and f not in used), None) for alt in re.findall(r"\{([^}]+)\}", g)]
        if None in picks:
            continue
        for i, piece in enumerate(re.split(r"\{[^}]+\}", g)):
            if piece:
                prev = parts[-1]["text"] if parts and parts[-1]["t"] == "chip" else None
                parts.append({"t": "text", "s": piece if prev is None else _overlap(prev, _josa(prev, piece))})
            if i < len(picks):
                used.add(picks[i])
                c = chip(by[picks[i]])
                if (c["code"] and len(parts) > 1 and parts[-1]["t"] == "text" and not parts[-1]["s"].strip()
                        and parts[-2]["t"] == "chip" and parts[-2]["code"] and (t := _lead(parts[-2]["text"], c["text"])) != c["text"]):
                    seen = _squash(t) in _squash(_snip(by[picks[i]]))      # 뗀 이름이 원문에 있으면 '어느 말인지' 부탁만 뺀다 (용어 풀이는 둔다)
                    tip = " · ".join(x for x in c["tip"].split(" · ") if not (seen and x.startswith(CODE_TIP[:8])))
                    c["tip"] = " · ".join(x for x in [f"전체 이름: {c['text']}", tip] if x)   # 코드 칩끼리 같은 낱말 되풀이만 뗀다 (자유 글은 그대로)
                    c["text"] = t
                parts.append(c)
    _trim(parts)
    rest = [(chip(r), isq(r)) for r in cand if field(r) not in used] + [(c, False) for c in late]   # 틀 밖 칸, 실패한 자동 확인은 끝에
    pure = bool(qs) and len(qs) == len(cand) and not late    # 질문 카드는 판단할 칸이 모두 예·아니오일 때만 (섞이면 질문 없이 '이름: [예]' 칩)
    nbool = sum(q for _, q in rest)
    for c, q in rest:
        parts += ([{"t": "text", "s": " · "}] if parts else []) + [{"t": "text", "s": "AI의 답: " if q and nbool == 1 and pure else f"{c['label']}: "}, c]
    _trim(parts)
    if not qs and not any(p["t"] == "chip" for p in parts):   # 판단할 칸이 하나도 없으면 숨긴 줄을 칩으로 (빈 문장 막기)
        for x in auto + meta:
            r = next(r for r in rs if r["경로"] == x["path"])
            parts += ([{"t": "text", "s": " · "}] if parts else []) + [{"t": "text", "s": f"{x['label']}: "}, chip(r)]
        auto, meta = [], []

    hint = None
    if tkey == "regulations[]" and vals.get("law") == "KREACH":
        hint = HINT_KREACH
    elif tkey == "transport[]" and vals.get("regulated") is False and "packing_group" in vals:
        hint = HINT_PACKING
    title = (rs[0].get("칸 이름") or "").split(" · ")[0] or key
    return {"type": "question" if pure else "sentence", "title": title, "parts": parts, "question": " ".join(qs) if pure else None,
            "auto": auto, "meta": meta, "hint": hint}


# 같은 원문 줄이 TO21 표 두 곳에 들어간 카드 (문서 무관). (표A, 표B, 맞는 쪽 "a"|"b"|"ignore", 근거). 표 = (표 이름, 코드 접두어들 | None). 위에서 먼저 맞는 것. 규칙 없는 쌍은 안내만
OVERLAP_RULES = [
    (("regulations", ("DG",)), ("dangerous_goods", None), "b", "명세서 5-6 DG_HAZMAT, 예제 25"),
    (("regulations", ("WASTE",)), ("waste", None), "b", "명세서 5-6 WASTE_DESIG, 예제 25"),
    (("toxicity", ("TX_CARC", "TX_MUTA", "TX_REPRO")), ("cmr", None), "b", "예제 25: 기관 분류는 cmr"),
    (("ecotox", None), ("narratives", None), "a", "예제 25: 12항은 ecotox"),
    (("intl_class", None), ("regulations", ("INTL",)), "a", "예제 25: EU·국제 분류는 intl_class"),
    (("toxicity", None), ("narratives", None), "b", "예제 25: 11항 서술은 narratives"),
    (("extras", None), ("*", None), "b", "명세서 R24: 맞는 부분은 정식 칸, 나머지만 extras"),
    (("components", None), ("composition", None), "ignore", ""),    # 서로 다른 칸을 같은 줄에서 읽음
    (("ecotox", None), ("toxicity", None), "ignore", ""),           # 같은 글이 다른 줄('- 이소부텐 : 자료없음')
]
_KEY = re.compile(r"msds\[(\d+)\]\.(\w+)(?:\[(?:k=)?([^\]]*)\])?")


def _overlap_rule(ka: str, kb: str):
    """두 카드 키 → (맞는 쪽 "a"|"b"|"ignore"|None, 근거). 규칙이 없으면 (None, "")."""
    def fits(k, spec):
        m = _KEY.match(k)
        name, codes = spec
        return bool(m) and (name == "*" and m[2] != "extras" or m[2] == name) and (
            codes is None or any(((m[3] or "").split("|") + [""])[1].startswith(c) for c in codes))
    for a, b, keep, why in OVERLAP_RULES:
        if fits(ka, a) and fits(kb, b):
            return keep, why
        if fits(kb, a) and fits(ka, b):
            return {"a": "b", "b": "a"}.get(keep, keep), why
    return None, ""


def overlaps_src(r: dict | None):
    """겹침 판정에 쓰는 줄 상태: (삭제인가, 쪽, 근거 줄). 이게 바뀌면 겹친 카드도 다시 만든다."""
    return None if r is None else (r.get("검수 결과") == "삭제", _row_page(r), _squash(_snip(r)))


def _row_page(r: dict) -> str:
    fixed = r.get("검수 결과") in ("수정", "누락 추가") and r.get("수정값")
    return str(r.get("수정 쪽") if fixed else r.get("Claude 쪽") or r.get("GPT 쪽") or "").strip()


def overlaps(rows: list[dict], count, drop: dict | None = None) -> dict[str, list[dict]]:
    """같은 원문 줄(같은 MSDS·같은 쪽·공백 뺀 조각이 같고 6글자 이상, 그 쪽 글자층에 한 번만)이 서로 다른 표 카드에 들어간 것.
    count(쪽, 조각) → 그 쪽 글자층에서 조각이 나오는 횟수. 삭제한 줄·골드에서 빠지는 항목은 뺀다.
    → 카드 키 → [{other_key, other_title, page, keep: "this"|"other"|None, why}]"""
    drop, at, title = drop or {}, {}, {}
    for r in rows:
        k, res = card_key(r["경로"]), r.get("검수 결과")
        pg, s = _row_page(r), _squash(_snip(r))
        title.setdefault(k, (r.get("칸 이름") or "").split(" · ")[0] or k)
        if res != "삭제" and pg.isdigit() and len(s) >= 6 and not gone_by(r["경로"], drop):
            at.setdefault((k.split(".")[0], int(pg), s), set()).add(k)
    out: dict[str, dict] = {}
    for (_, pg, s), ks in at.items():
        if len(ks) > 1 and count(pg, s) == 1:
            for a in ks:
                for b in ks - {a}:
                    keep, why = _overlap_rule(a, b)
                    if keep != "ignore" and a.split(".")[1].split("[")[0] != b.split(".")[1].split("[")[0]:      # 같은 표의 다른 항목은 겹침이 아님
                        out.setdefault(a, {})[b] = {"other_key": b, "other_title": title[b], "page": pg, "why": why,
                                                    "keep": None if keep is None else "other" if keep == "b" else "this"}
    return {k: sorted(v.values(), key=lambda o: o["other_key"]) for k, v in out.items()}
