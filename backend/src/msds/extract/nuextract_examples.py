"""NuExtract 예시: 직접 만든 가짜 MSDS 한 건과 항별 예시 출력 (B, ADR-011).

NuExtract 2.0 대화 틀은 chat_template_kwargs.examples의 {"input", "output"}을 '# Examples:' 아래에 넣는다.
틀에는 칸 설명을 넣을 수 없어, 예시로 줄 번호 칸(line, start, end, lines)에 p1:L3 같은 번호를 쓰는 법을 보인다.
- 입력은 실제 요청과 같은 모양(build_user)이고 문서 전체가 들어간다. 출력은 그 항의 값만 담는다.
- 가짜 문서의 이름·CAS·값은 지어냈다. 실제 MSDS나 평가용 문서의 내용을 쓰지 않는다 (D-43, D-47).
"""
from __future__ import annotations

import json

from msds.extract.inputs import Line
from msds.extract.nuextract import coerce
from msds.extract.section_prompts import build_user
from msds.extract.section_specs import response_schema

_PAGES = {
    1: """\
물질안전보건자료
1. 화학제품과 회사에 관한 정보
가. 제품명 : 가상 세척제 A
나. 권고 용도 : 금속 표면 세척
다. 공급자 정보 : 가상화학(주) | 주소 : 가상시 가상구 가상로 12
긴급전화번호 : 02-0000-0000
MSDS 번호 : AA00000-2026000001
2. 유해성·위험성
가. 유해성·위험성 분류
인화성 액체 : 구분 3
심한 눈 손상성/눈 자극성 : 구분 2
나. 경고표지 항목 - 신호어 : 경고
H226 인화성 액체 및 증기
P210 열·스파크·화염·고열로부터 멀리하시오.
다. 그 밖의 경고표지 : 빈 용기에도 증기가 남을 수 있음
3. 구성성분의 명칭 및 함유량
물질 구분 : 혼합물
화학물질명 | CAS 번호 / KE 번호 | 함유량(%)
가상물질 갑 | 1234-56-6 / KE-12345 | 10 ~ 20
가상물질 을 | 2345-67-7 / KE-23456 | 1 미만
4. 응급조치 요령
가. 눈에 들어갔을 때
- 즉시 다량의 물로 15분 이상 씻어내시오.
나. 피부에 접촉했을 때
- 오염된 옷을 벗고 비누와 물로 씻으시오.
5. 폭발·화재 시 대처방법
가. 적절한 소화제 : 이산화탄소, 분말 소화약제
6. 누출 사고 시 대처방법
가. 인체를 보호하기 위해 필요한 조치 사항 및 보호구 : 보호구를 착용하시오.
나. 정화 또는 제거 방법 : 흡수제로 흡수하여 밀폐 용기에 담으시오.
7. 취급 및 저장방법
가. 안전취급요령 : 환기가 잘 되는 곳에서만 취급하시오.
나. 안전한 저장방법 : 서늘한 곳에 밀폐하여 저장하시오.
""",
    2: """\
8. 노출방지 및 개인보호구
가. 화학물질의 노출기준
가상물질 갑 (1234-56-6) | 국내규정 TWA 50 ppm | ACGIH TWA 20 ppm
나. 적절한 공학적 관리 : 국소배기장치를 설치하시오.
9. 물리화학적 특성
가. 외관 : 액체
나. 인화점 : 약 45 ℃ (밀폐식)
다. 증기압 : 1.2 kPa (20 ℃)
10. 안정성 및 반응성
가. 화학적 안정성 및 유해 반응의 가능성 : 정상 조건에서 안정함
나. 피해야 할 물질 : 강산화제
11. 독성에 관한 정보
가. 가능성이 높은 노출 경로에 관한 정보 : 흡입, 피부 접촉
나. 건강 유해성 정보
급성독성(경구) : 가상물질 갑 LD50 2,500 mg/kg (랫드)
발암성 : 가상물질 갑 IARC Group 3
12. 환경에 미치는 영향
가. 생태독성(어류) : 가상물질 갑 LC50 12 mg/L 96hr (송사리)
나. 기타 유해 영향 : 물 표면에 막을 만들 수 있음
13. 폐기 시 주의사항
가. 폐기방법 : 지정폐기물로 위탁 처리하시오.
나. 폐기 시 주의사항 : 빈 용기를 재사용하지 마시오.
14. 운송에 필요한 정보
구분 | 유엔번호 | 적정선적명 | 위험성 등급 | 용기등급
육상(국내) | UN1993 | 인화성 액체, N.O.S. | 3 | III
해상(IMDG) | UN1993 | FLAMMABLE LIQUID, N.O.S. | 3 | III
특별한 안전대책 : 화기를 멀리하시오.
15. 법적 규제현황
가. 산업안전보건법에 의한 규제 : 가상물질 갑 - 작업환경측정대상물질
나. 위험물안전관리법에 의한 규제 : 제4류 제2석유류(비수용성) 지정수량 1,000 L
다. 폐기물관리법에 의한 규제 : 지정폐기물(폐유기용제)
라. 기타 국내 및 외국법에 의한 규제 : 사용 전 관련 법규를 확인하시오.
16. 그 밖의 참고사항
가. 자료의 출처 : 가상화학(주) 자체 시험 자료
나. 최초 작성일자 : 2024.03.15
다. 개정횟수 및 최종 개정일자 : 2회, 2025.11.20
""",
}

FAKE_LINES: list[Line] = [Line(f"p{page}:L{no}", page, no, text)
                          for page, body in _PAGES.items()
                          for no, text in enumerate(body.splitlines(), 1)]


def _narr(code: str, title: str, start: str, end: str | None = None) -> dict:
    return {"item_code": code, "title_raw": title, "start": start, "end": end or start}


# 항 번호 → 손으로 쓴 일부 값. 빠진 칸은 coerce가 null·[]로 채운다. 줄 번호는 위 가짜 문서의 것이다.
_VALUES: dict[int, dict] = {
    1: {
        "meta": {"msds_no": "AA00000-2026000001", "lines": {"msds_no": "p1:L7"}},
        "product": {"name": "가상 세척제 A", "uses": ["금속 표면 세척"],
                    "lines": {"name": "p1:L3", "uses": "p1:L4"}},
        "companies": [{"role": "공급자", "name": "가상화학(주)", "address": "가상시 가상구 가상로 12",
                       "contacts": [{"type": "긴급", "value": "02-0000-0000", "line": "p1:L6"}],
                       "line": "p1:L5"}],
    },
    2: {
        "hazard": {
            "classified": True,
            "classes": [
                {"group": "물리적", "class_code": "PH_FLAM_LIQ", "category": "3",
                 "raw": "인화성 액체 : 구분 3", "line": "p1:L10"},
                {"group": "건강", "class_code": "HH_EYE_DMG", "category": "2",
                 "raw": "심한 눈 손상성/눈 자극성 : 구분 2", "line": "p1:L11"},
            ],
            "signal_word": "경고",
            "h_statements": [{"code": "H226", "system": "GHS", "text": "인화성 액체 및 증기", "line": "p1:L13"}],
            "p_statements": [{"code": "P210", "type": "예방", "text": "열·스파크·화염·고열로부터 멀리하시오.",
                              "line": "p1:L14"}],
            "lines": {"classified": "p1:L9", "signal_word": "p1:L12"},
        },
        "narratives": [_narr("S2_LABEL_NOTE", "다. 그 밖의 경고표지", "p1:L15")],
    },
    3: {
        "composition": {"type": "혼합물", "lines": {"type": "p1:L17"}},
        "components": [
            {"name": "가상물질 갑", "cas_no": "1234-56-6", "ke_no": "KE-12345",
             "content": {"raw": "10 ~ 20", "lower_op": ">=", "lower": 10, "upper_op": "<=", "upper": 20,
                         "unit": "%"},
             "line": "p1:L19"},
            {"name": "가상물질 을", "cas_no": "2345-67-7", "ke_no": "KE-23456",
             "content": {"raw": "1 미만", "upper_op": "<", "upper": 1, "unit": "%"},
             "line": "p1:L20"},
        ],
    },
    4: {"narratives": [_narr("S4_EYE", "가. 눈에 들어갔을 때", "p1:L22", "p1:L23"),
                       _narr("S4_SKIN", "나. 피부에 접촉했을 때", "p1:L24", "p1:L25")]},
    5: {"narratives": [_narr("S5_MEDIA", "가. 적절한 소화제", "p1:L27")]},
    6: {"narratives": [_narr("S6_PERSONAL", "가. 인체를 보호하기 위해 필요한 조치 사항 및 보호구", "p1:L29"),
                       _narr("S6_CLEANUP", "나. 정화 또는 제거 방법", "p1:L30")]},
    7: {"narratives": [_narr("S7_HANDLING", "가. 안전취급요령", "p1:L32"),
                       _narr("S7_STORAGE", "나. 안전한 저장방법", "p1:L33")]},
    8: {
        "exposure_limits": [
            {"comp_name": "가상물질 갑", "comp_cas": "1234-56-6", "standard": "국내", "limit_type": "TWA",
             "q": {"raw": "50 ppm", "value": 50, "unit": "ppm"}, "line": "p2:L3"},
            {"comp_name": "가상물질 갑", "comp_cas": "1234-56-6", "standard": "ACGIH", "limit_type": "TWA",
             "q": {"raw": "20 ppm", "value": 20, "unit": "ppm"}, "line": "p2:L3"},
        ],
        "narratives": [_narr("S8_ENG", "나. 적절한 공학적 관리", "p2:L4")],
    },
    9: {
        "physchem": [
            {"prop_code": "APPEARANCE_STATE", "text_value": "액체", "line": "p2:L6"},
            {"prop_code": "FLASH_POINT", "q": {"raw": "약 45 ℃", "value": 45, "approx": True, "unit": "C"},
             "cond": {"method": "밀폐식"}, "line": "p2:L7"},
            {"prop_code": "VAPOR_PRESSURE", "q": {"raw": "1.2 kPa", "value": 1.2, "unit": "kPa"},
             "cond": {"temp": 20, "temp_unit": "C"}, "line": "p2:L8"},
        ],
    },
    10: {"narratives": [_narr("S10_STABILITY", "가. 화학적 안정성 및 유해 반응의 가능성", "p2:L10"),
                        _narr("S10_INCOMPAT", "나. 피해야 할 물질", "p2:L11")]},
    11: {
        "toxicity": [{"comp_name": "가상물질 갑", "endpoint": "TX_ORAL", "descriptor": "LD50",
                      "q": {"raw": "2,500 mg/kg", "value": 2500, "unit": "mg/kg"}, "species": "랫드",
                      "status": "값있음", "line": "p2:L15"}],
        "cmr": [{"comp_name": "가상물질 갑", "hazard": "발암성", "agency": "IARC", "class": "Group 3",
                 "status": "값있음", "line": "p2:L16"}],
        "narratives": [_narr("S11_ROUTE", "가. 가능성이 높은 노출 경로에 관한 정보", "p2:L13")],
    },
    12: {
        "ecotox": [{"comp_name": "가상물질 갑", "endpoint": "ECO_FISH", "descriptor": "LC50",
                    "q": {"raw": "12 mg/L", "value": 12, "unit": "mg/L"}, "species": "송사리",
                    "duration_value": 96, "duration_unit": "hr", "status": "값있음", "line": "p2:L18"}],
        "narratives": [_narr("S12_OTHER", "나. 기타 유해 영향", "p2:L19")],
    },
    13: {"narratives": [_narr("S13_METHOD", "가. 폐기방법", "p2:L21"),
                        _narr("S13_CAUTION", "나. 폐기 시 주의사항", "p2:L22")]},
    14: {
        "transport": [
            {"mode": "육상", "un_no": "1993", "shipping_name": "인화성 액체, N.O.S.", "hazard_class": "3",
             "packing_group": "III", "line": "p2:L25"},
            {"mode": "해상", "basis_raw": "IMDG", "un_no": "1993", "shipping_name": "FLAMMABLE LIQUID, N.O.S.",
             "hazard_class": "3", "packing_group": "III", "line": "p2:L26"},
        ],
        "narratives": [_narr("S14_SPECIAL", "특별한 안전대책", "p2:L27")],
    },
    15: {
        "regulations": [{"law": "OSH", "item_code": "OSH_MEASURE", "item_raw": "작업환경측정대상물질",
                         "comp_name": "가상물질 갑", "applicable": "해당", "line": "p2:L29"}],
        "dangerous_goods": [{"class": "제4류", "item": "제2석유류", "water_soluble": "비수용성",
                             "designated_qty": {"raw": "1,000 L", "value": 1000, "unit": "L"}, "line": "p2:L30"}],
        "waste": [{"designated": "해당", "waste_type": "폐유기용제", "line": "p2:L31"}],
        "narratives": [_narr("S15_OTHER", "라. 기타 국내 및 외국법에 의한 규제", "p2:L32")],
    },
    16: {
        "narratives": [_narr("S16_SOURCE", "가. 자료의 출처", "p2:L34")],
        "meta_revision": {"first_issue_date": "2024-03-15", "revision_no": 2, "last_revision_date": "2025-11-20",
                          "lines": {"first_issue_date": "p2:L35", "revision_no": "p2:L36",
                                    "last_revision_date": "p2:L36"}},
    },
}


def example(no: int) -> dict:
    """항 no의 NuExtract 예시 {"input": str, "output": str}."""
    out = coerce({**_VALUES[no], "extras": []}, response_schema(no))
    return {"input": build_user(no, FAKE_LINES)[0]["text"], "output": json.dumps(out, ensure_ascii=False)}
