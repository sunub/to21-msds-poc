"""추출 결과의 코드를 화면에 보일 우리말 이름으로 (추출값 확인 화면 2.2).

이름은 TO21 추출명세서 v0.6의 코드표(5-1 유해성 분류, 5-4 물리화학, 5-5 독성·생태, 5-6 법규제)를 따른다.
표에 없는 코드는 None이다. 부르는 쪽이 원래 값을 그대로 보인다.
"""
from __future__ import annotations

PHYSCHEM = {
    "APPEARANCE_STATE": "외관-성상", "APPEARANCE_COLOR": "외관-색상", "ODOR": "냄새", "ODOR_THRESHOLD": "냄새 역치",
    "PH": "pH", "MELT_FREEZE": "녹는점/어는점", "BOILING": "초기 끓는점과 끓는점 범위", "FLASH_POINT": "인화점",
    "EVAP_RATE": "증발 속도", "FLAMMABILITY": "인화성(고체, 기체)", "UEL": "폭발 범위 상한", "LEL": "폭발 범위 하한",
    "VAPOR_PRESSURE": "증기압", "SOLUBILITY": "용해도", "VAPOR_DENSITY": "증기밀도", "RELATIVE_DENSITY": "비중(상대밀도)",
    "LOG_KOW": "n-옥탄올/물 분배계수", "AUTOIGNITION": "자연발화온도", "DECOMPOSITION": "분해온도", "VISCOSITY": "점도",
    "VISCOSITY_KIN": "동점도", "MOL_WEIGHT": "분자량",
}

ENDPOINT = {
    "TX_ORAL": "급성 독성(경구)", "TX_DERMAL": "급성 독성(경피)", "TX_INHAL": "급성 독성(흡입)",
    "TX_SKIN": "피부 부식성/자극성", "TX_EYE": "심한 눈 손상/자극성", "TX_RESP_SENS": "호흡기 과민성",
    "TX_SKIN_SENS": "피부 과민성", "TX_CARC": "발암성", "TX_MUTA": "생식세포 변이원성", "TX_REPRO": "생식독성",
    "TX_STOT_SE": "특정표적장기 독성(1회)", "TX_STOT_RE": "특정표적장기 독성(반복)", "TX_ASP": "흡인 유해성",
    "ECO_FISH": "생태독성-어류", "ECO_CRUST": "생태독성-갑각류", "ECO_ALGAE": "생태독성-조류",
    "ECO_OTHER": "생태독성-기타", "ECO_PERSIST": "잔류성 및 분해성", "ECO_BIOACC": "생물농축성",
    "ECO_SOIL": "토양이동성", "ECO_OZONE": "오존층 유해성",
}

HAZARD_CLASS = {
    "PH_EXPLOSIVE": "폭발성 물질", "PH_FLAM_GAS": "인화성 가스", "PH_AEROSOL": "에어로졸", "PH_OXID_GAS": "산화성 가스",
    "PH_PRESS_GAS": "고압가스", "PH_FLAM_LIQ": "인화성 액체", "PH_FLAM_SOL": "인화성 고체", "PH_SELF_REACT": "자기반응성 물질",
    "PH_PYRO_LIQ": "자연발화성 액체", "PH_PYRO_SOL": "자연발화성 고체", "PH_SELF_HEAT": "자기발열성 물질",
    "PH_WATER_REACT": "물반응성 물질", "PH_OXID_LIQ": "산화성 액체", "PH_OXID_SOL": "산화성 고체",
    "PH_ORG_PEROX": "유기과산화물", "PH_METAL_CORR": "금속부식성 물질", "PH_DESENS_EXPL": "둔감화된 폭발성 물질",
    "HH_ACUTE_ORAL": "급성 독성(경구)", "HH_ACUTE_DERMAL": "급성 독성(경피)", "HH_ACUTE_INHAL": "급성 독성(흡입)",
    "HH_SKIN_CORR": "피부 부식성/피부 자극성", "HH_EYE_DMG": "심한 눈 손상성/눈 자극성", "HH_RESP_SENS": "호흡기 과민성",
    "HH_SKIN_SENS": "피부 과민성", "HH_MUTAGEN": "생식세포 변이원성", "HH_CARCINOGEN": "발암성", "HH_REPRO": "생식독성",
    "HH_STOT_SE": "특정표적장기 독성(1회 노출)", "HH_STOT_RE": "특정표적장기 독성(반복 노출)",
    "HH_ASPIRATION": "흡인 유해성", "ENV_AQ_ACUTE": "수생환경 유해성(급성)", "ENV_AQ_CHRONIC": "수생환경 유해성(만성)",
    "ENV_OZONE": "오존층 유해성",
}

LAW = {
    "OSH": "산업안전보건법", "KREACH": "화학물질의 등록 및 평가 등에 관한 법률", "CCA": "화학물질관리법",
    "DG": "위험물안전관리법", "WASTE": "폐기물관리법", "POPS": "잔류성오염물질 관리법", "KR_ETC": "기타 국내법",
    "INTL": "외국법·국제협약",
}

REGULATION = {
    "OSH_PROHIBIT": "제조 등 금지물질", "OSH_PERMIT": "허가대상물질", "OSH_MANAGED": "관리대상유해물질",
    "OSH_SPECIAL": "특별관리물질", "OSH_MEASURE": "작업환경측정 대상물질", "OSH_HEALTH_EXAM": "특수건강진단 대상물질",
    "OSH_EXPOSURE_STD": "노출기준 설정물질", "OSH_PERMISSIBLE": "허용기준 설정물질", "OSH_PSM": "공정안전보고서(PSM) 제출대상",
    "KREACH_EXIST": "기존화학물질", "KREACH_REG": "등록대상화학물질", "KREACH_PRIORITY": "중점관리물질",
    "KREACH_CMR": "CMR 및 CMR 우려물질", "KREACH_ETC": "기타 화평법 항목", "CCA_TOXIC": "유독물질",
    "CCA_ACUTE": "인체급성유해성물질", "CCA_CHRONIC": "인체만성유해성물질", "CCA_ECO": "생태유해성물질",
    "CCA_PERMIT": "허가물질", "CCA_RESTRICT": "제한물질", "CCA_PROHIBIT": "금지물질", "CCA_ACCIDENT": "사고대비물질",
    "CCA_PRTR": "배출량조사 대상화학물질", "CCA_HALLUC": "환각물질", "DG_HAZMAT": "위험물안전관리법 위험물",
    "WASTE_DESIG": "지정폐기물", "POPS": "잔류성오염물질", "KR_ETC": "기타 국내법", "INTL_EU": "EU 규제",
    "INTL_US": "미국 규제", "INTL_TREATY": "국제협약", "INTL_JP": "일본 규제", "INTL_ETC": "기타 외국법",
}

TEMP_UNIT = {"C": "℃", "F": "℉", "K": "K"}

# 칸 이름(마지막 키) → 그 칸 값의 코드표
_BY_FIELD = {"prop_code": PHYSCHEM, "endpoint": ENDPOINT, "class_code": HAZARD_CLASS, "law": LAW,
             "item_code": REGULATION, "temp_unit": TEMP_UNIT}


def code_name(code) -> str | None:
    """어느 코드표에든 있으면 그 이름 (묶음 제목용)."""
    if not isinstance(code, str):
        return None
    for table in (PHYSCHEM, ENDPOINT, HAZARD_CLASS, REGULATION):
        if code in table:
            return table[code]
    return None


def display_value(field: str, value) -> str | None:
    """화면에 보일 값. 원래 값을 그대로 보이면 되는 칸은 None. 참·거짓은 예·아니오로."""
    if isinstance(value, bool):
        return "예" if value else "아니오"
    table = _BY_FIELD.get(field)
    return table.get(value) if table and isinstance(value, str) else None
