"""묶음별 프롬프트를 TO21 명세서에서 만든다 (D-35, D-43).

프롬프트 = 공통 지시(system.md) + 묶음 안내(아래 GUIDES) + 명세서에서 꺼낸
  [필드 정의] [규칙] [공통 구조] [코드표] [동의어]
명세서를 직접 옮겨 넣기 때문에, TO21이 명세서를 고치면 다시 만들기만 하면 된다.

만들어진 파일: src/msds/extract/prompts/b1.md ~ b5.md (사람이 읽고 검토하는 대상)
다시 만들기: python scripts/build_prompts.py

원칙 (D-43)
- 평가용 문서(25번 정답 예제 포함)의 내용을 예시로 넣지 않는다. 명세서의 '예시(가상)' 값만 쓴다.
- 1주차 프롬프트는 예시 문서 없이 규칙만으로 쓴다.
"""
from __future__ import annotations

import json
import re
from datetime import date

import openpyxl

from ..common.bundles import load_bundles
from ..common.paths import PROMPTS, to21_file

PROMPT_VERSION = "p2"   # 프롬프트 내용을 고치면 올린다 (p2, p3 ...). 실행 기록에 남는다

# 묶음별 안내: 명세서에 없는, 읽는 순서와 자주 틀리는 점
GUIDES = {
    "b1": """- 한 파일에 MSDS가 여러 건이면(키트, A/B제 등) msds를 건마다 나누고 meta.page_start / page_end에 쪽 범위를 적는다(R16). 대부분은 1건이다.
- 관리정보: MSDS 번호(제출번호)와 회사 내부 문서번호를 구분한다. 회사 내부 번호는 msds_no가 아니다. 날짜는 R01.
- 회사(companies): 역할(제조자·수입자·공급자 등)마다 한 항목. 전화·팩스·이메일은 contacts로 나누고, 긴급 연락처는 type="긴급". 전화번호는 R12.
- 유해성 분류(hazard.classes): 분류마다 한 항목. 구분(category)은 '구분' 글자를 뺀다(R07). 급성독성(흡입) 등 노출 형태가 적혀 있으면 route_form에 원문대로(가스 / 증기 / 분진·미스트).
- 분류 코드표에 없는 유해성 표기(예: 단순질식제)는 hazard.classes에 넣지 않고 hazard.other_hazards에 원문 문장으로 둔다.
- 신호어·그림문자: 문서에 보이는 것만. 그림문자는 이미지에서 실제로 보이는 그림의 코드를 적고 detection="이미지판독". 그림이 보이지 않으면 넣지 않는다.
- H·P 코드: R05, R21. P코드의 type은 첫 자리로 정한다(P1 일반, P2 예방, P3 대응, P4 저장, P5 폐기).
- 성분(components): 성분표의 행마다 한 항목, seq는 1부터. CAS와 KE 번호를 나눈다(R02, R03). 함유량은 Q로 나눈다(R04, R06, R19). 원문은 raw에 그대로 둔다. 영업비밀은 R13·R23, 하위 성분은 R22, 가려진 값은 R20.""",
    "b2": """- 8항 노출기준(exposure_limits): 성분 × 기준 출처(국내·ACGIH 등) × 기준 종류(TWA·STEL·C)마다 한 행이다. TWA와 STEL을 한 행에 합치지 않는다. 값은 q(Q)로 나눈다.
- 생물학적 노출기준도 행으로 남긴다(standard="생물학적").
- 9항 물리화학적 특성(physchem): 특성마다 한 행(prop_code). 숫자 값은 q, 글자 값은 text_value. 괄호 속 측정 조건은 cond(COND)로 나눈다.
- 숫자 특성이라도 원문 값이 말로 적혀 있으면 q는 null로 두고 text_value에만 적는다.
- 성분마다 값이 따로 적혀 있으면 [성분 목록]의 comp_ref로 구분하고, 제품 전체 값은 comp_ref="MIX"(R10).
- 특성 이름의 표기가 달라도 [동의어]로 코드를 정한다(R25).""",
    "b3": """- 11항 독성(toxicity): 성분 × 독성 항목(endpoint) × 지표(LD50·LC50·ATE 등) × 시험 동물마다 한 행이다.
- 급성독성(경구·경피·흡입) 값은 필수 칸이다. 흡입은 노출 형태(physical_form: 가스 / 증기 / 분진·미스트)와 노출 시간(duration)을 원문대로 적는다.
- "자료없음"으로 적힌 항목도 행으로 남기고 status로 표시한다.
- 발암성·생식세포변이원성·생식독성의 기관별 분류는 cmr에 기관(agency)마다 한 행.
- 12항 생태독성(ecotox): 성분 × 항목 × 지표 × 생물종마다 한 행. 값은 q.
- comp_ref는 [성분 목록]의 번호, 제품 전체 값은 "MIX"(R10).""",
    "b4": """- 14항 운송(transport): 운송 방식(mode)마다 한 행. UN번호는 R09. 규제 대상이 아니면 regulated=false.
- 15항 국내 규제(regulations): 성분 × 법령(law) × 규제 항목(item_code)마다 한 행이다. 해당 / 비해당 / 자료없음 모두 원문에 적힌 대로 행으로 남긴다. "해당없음" 행을 빠뜨리지 않는다.
- 규제 기준 농도(예: "1% 이상 함유한 황산")는 threshold(Q)로 나눈다.
- 위험물안전관리법은 dangerous_goods(류·품명·수용성·등급·지정수량), 폐기물관리법의 지정폐기물 여부는 waste.
- 해외 규제와 해외 분류(EU CLP 등)는 law="INTL" 행 또는 intl_class에 둔다.
- 규제 항목 이름의 표기가 달라도 [동의어]로 코드를 정한다(R25). 2025 개정 고시의 화평법 항목이 문서에 없으면 미기재(R18).""",
    "b5": """- 4·5·6·7·8·10·11·12·13·14·16항의 서술 내용을 항목 코드(item_code)마다 나누고, 그 안을 문장·불릿 단위 statements로 나눈다(R14).
- '키 : 값' 형태는 key / value로 나누고, '[성분명] : 값'은 refs에 [성분 목록]의 번호를 넣는다.
- 쪽 머리글·바닥글(회사명, 쪽 번호 등)은 넣지 않고, 쪽을 넘어가는 문장은 이어 붙인다.
- statements의 text에는 나누기 전 원문 한 줄을 그대로 둔다(재생성 확인용).
- 문서 전체에서 스키마에 맞는 칸이 없는 항목은 버리지 말고 extras에 담는다(R24). 억지로 비슷한 칸에 넣지 않는다.
- 16항 끝의 각주(상표 ™·® 설명 등)는 extras가 아니라 narratives의 S16_OTHER(기타 참고사항)에 넣고 title_raw를 채운다.""",
}

_BASE_RULES = {"R15", "R17"}
_BUNDLE_RULES = {
    "b1": {"R01", "R02", "R03", "R04", "R05", "R06", "R07", "R11", "R12", "R13", "R16", "R19", "R20", "R21", "R22", "R23"},
    "b2": {"R04", "R06", "R08", "R10", "R25"},
    "b3": {"R04", "R06", "R08", "R10"},
    "b4": {"R04", "R06", "R09", "R10", "R18", "R25"},
    "b5": {"R10", "R14", "R24", "R25"},
}


def _rows(ws):
    return [tuple("" if c is None else str(c).replace("\n", " / ").strip() for c in r)
            for r in ws.iter_rows(values_only=True)]


def _field_rows(wb, keys: list[str], doc_keys: list[str]) -> list[str]:
    out = []
    for r in _rows(wb["1_항목정의"])[4:]:
        if not r[0] or not r[3]:
            continue
        path = r[3]
        top = path.split(".")[1].split("[")[0] if path.startswith("msds[]") else None
        is_doc = path.startswith("doc.") and path.split(".")[1] in (doc_keys or [])
        if top in keys or is_doc:
            p = path.replace("msds[].", "")
            extra = " ".join(x for x in [r[8], f"[참조 {r[9]}]" if r[9] else "", f"예: {r[10]}" if r[10] else "",
                                         f"({r[11]})" if r[11] else ""] if x)
            out.append(f"- `{p}` {r[4]} — {r[5]}, {r[7]}. {extra}".rstrip())
    return out


def _rules(wb, codes: set[str]) -> list[str]:
    out = []
    for r in _rows(wb["3_정규화규칙"])[3:]:
        if r[0] in codes:
            line = f"- {r[0]} {r[1]}: {r[2]}"
            if r[3]:
                line += f" 원문 예: {r[3]} → 저장 예: {r[4]}"
            if r[5]:
                line += f" ({r[5]})"
            out.append(line)
    return out


def _common_structure(wb) -> list[str]:
    return [" | ".join(x for x in r if x) for r in _rows(wb["2_공통구조"])[1:] if any(r)]


def _code_table(wb, name: str) -> list[str]:
    rows = _rows(wb[name])
    out = [f"### {rows[0][0]}"]
    if rows[1][0]:
        out.append(rows[1][0])
    out += [" | ".join(x for x in r if x) for r in rows[3:] if any(r)]
    return out


def _referenced_rules(field_lines: list[str]) -> set[str]:
    return set(re.findall(r"R\d{2}", "\n".join(field_lines)))


def build_bundle_prompt(bundle_id: str) -> str:
    b = load_bundles()[bundle_id]
    wb = openpyxl.load_workbook(to21_file("spec"), read_only=True, data_only=True)
    with open(to21_file("dictionary"), encoding="utf-8") as f:
        dic = json.load(f)

    fields = _field_rows(wb, b.keys, b.doc_keys)
    rule_codes = _BASE_RULES | _BUNDLE_RULES.get(bundle_id, set()) | _referenced_rules(fields)
    parts = [
        f"<!-- 프롬프트 {PROMPT_VERSION} / {bundle_id} / 명세서 v0.5에서 생성 ({date.today().isoformat()}). "
        f"직접 고치지 말고 prompt_builder.py를 고친 뒤 다시 만든다 -->",
        f"# 이번 묶음: {b.name}",
        f"읽을 곳: {b.sections}",
        "뽑을 칸: " + ", ".join(([f"doc.{k}" for k in b.doc_keys] if b.doc_keys else []) + [f"msds[].{k}" for k in b.keys]),
        "",
        "## 묶음 안내",
        GUIDES[bundle_id],
        "",
        "## [필드 정의] (TO21 명세서 1_항목정의)",
        "형식: `경로` 이름 — 타입, 중요도. 형식·분해 규칙 [참조] 예(가상 값)",
        *fields,
        "",
        "## [규칙] (TO21 명세서 3_정규화규칙)",
        *_rules(wb, rule_codes),
        "",
        "## [공통 구조] 숫자(Q)·측정 조건(COND)·서술 문장(STMT) (TO21 명세서 2_공통구조)",
        *_common_structure(wb),
        "",
        "## [코드표]",
    ]
    for name in b.code_tables:
        parts += _code_table(wb, name) + [""]
    parts.append("## [동의어] 표기가 달라도 같은 코드로 본다 (공백·구두점·가운뎃점은 무시)")
    for k in list(b.dictionary) + ["status"]:
        entry = dic.get(k)
        parts.append(f"### {k}")
        if isinstance(entry, dict):
            for code, names in entry.items():
                parts.append(f"- {code}: " + " / ".join(names))
        elif isinstance(entry, list):
            parts.append("- 자주 나오는 소제목(값이 아니라 제목이다): " + " / ".join(entry))
    return "\n".join(parts).strip() + "\n"


def build_all() -> list[str]:
    written = []
    for bid in load_bundles():
        p = PROMPTS / f"{bid}.md"
        p.write_text(build_bundle_prompt(bid), encoding="utf-8")
        written.append(str(p))
    return written


def load_prompt(bundle_id: str, mode: str) -> tuple[str, str]:
    """(system 프롬프트, 묶음 프롬프트). mode: silver | baseline"""
    system = (PROMPTS / "system.md").read_text(encoding="utf-8")
    output = (PROMPTS / f"output_{mode}.md").read_text(encoding="utf-8")
    bundle = (PROMPTS / f"{bundle_id}.md").read_text(encoding="utf-8")
    return system + "\n" + output, bundle
