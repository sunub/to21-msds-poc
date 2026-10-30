"""지식DB 텍스트 값 파싱 규칙(htodb/parsers.py). DB 없이 동작한다.

TO21 자료의 값은 시험 코드에 적지 않는다(D-47). 문장과 숫자는 모두 지어낸 것이다.
"""
import pytest

from msds.compliance.htodb import parsers as p


def test_acute_prefers_primary_value():
    r = p.parse_acute("LC50 1234 ppm 4 hr 실험종 : Rat", "12.5", "GHS0204")
    assert (r["sign"], r["value"], r["unit"], r["species"], r["basis"]) == ("=", 12.5, "mg/L", "Rat", "PRIMARY_VALUE")


def test_acute_text_sign_range_and_unit():
    r = p.parse_acute("LD50 ＞1,000~2,000 ㎎/㎏ 실험종 : Mouse", "", "GHS0201")
    assert (r["sign"], r["value"], r["value_max"], r["unit"]) == (">", 1000.0, 2000.0, "mg/kg")
    assert "범위값" in r["basis"]
    assert p.parse_acute("자료없음", None, "GHS0201") is None


def test_acute_ppm_to_mgl_and_unit_mismatch():
    r = p.parse_acute("LC50 2445 ppm", "", "GHS0204", mw=100.0)
    assert r["unit"] == "mg/L" and r["value"] == pytest.approx(10.0)
    bad = p.parse_acute("LD50 10 mg/L", "", "GHS0201")
    assert bad["sign"] == "?" and "계산 제외" in bad["basis"]


def test_acute_non_numeric_primary_value_falls_back_to_text():
    assert p.parse_acute("LD50 300 mg/kg", "N/A", "GHS0201")["basis"].startswith("PRIMARY_VALUE_TEXT")


def test_aquatic_and_rapid():
    assert p.parse_lc50("96hr LC50 < 3.3 mg/l") == ("<", 3.3)
    assert p.parse_noec("NOEC = 0.7 mg/L, NOEC 0.2 mg/L, NOEC > 0.01 mg/L") == 0.2
    assert p.parse_noec("NOEC > 1 mg/L") is None
    assert p.parse_rapid("이분해성") is True and p.parse_rapid("난분해성") is False
    assert p.parse_rapid("71 % 28 day") is True and p.parse_rapid("모름") is None


def test_noec_with_duration_between():
    assert p.parse_noec("조류 NOEC(72h)=1.5 ㎎/ℓ") == 1.5
    assert p.parse_noec("어류, NOEC, 30d, = 8.2  mg/L, 갑각류, NOEC, 21d, =0.4 mg/L") == 0.4
    assert p.parse_noec("NOEC 21d 0.9 mg/L") == 0.9
    assert p.parse_noec("갑각류: 21d-NOECDaphnia magna=0.7 mg/L") == 0.7                 # 종 이름이 사이에 낀 형태
    assert p.parse_noec("NOEC, Daphnia magna, ≥ 10 mg/L") is None                     # '≥'를 '='로 읽지 않음
    assert p.parse_noec("NOEC, LOEC = 5 mg/L") is None
    assert p.parse_noec("96hr NOEC50=2 mg/l") is None                                 # NOEC50은 NOEC가 아님
    assert p.parse_noec("NOEC21d=3 mg/L") == 3.0                                      # 기간이 NOEC에 붙은 형태
    assert p.parse_noec("NOEC(21d) > 1 mg/L") is None                 # '>' 값은 여전히 제외
    assert p.parse_noec("NOEC(21d) >= 1 mg/L") is None
    assert p.parse_noec("NOEC, 14d, = 600ug/L") is None               # ug/L 환산은 하지 않음
    assert p.parse_noec("NOEC, 21d, LC50 = 3 mg/L") is None           # 다른 종말점 값을 가져오지 않음


def test_viscosity_requires_40c_temperature():
    assert p.parse_phys("G0918000000", "6 cSt (40 °C)") == 6.0
    assert p.parse_phys("G0918000000", "40 cSt (@ 20 ℃)") is None
    assert p.parse_phys("G0918000000", "20-40 cSt (at 25℃)") is None
    assert p.parse_phys("G0918000000", "140 cSt (38도)") is None
    assert p.parse_phys("G0918000000", "1,400 cST(25℃)") is None


def test_phys():
    assert p.parse_phys("G0901000001", "무색 가스") == "기체"
    assert p.parse_phys("G0907000000", "A 12℃ / B -4℃") == -4.0
    assert p.parse_phys("G0907000000", "불연성") is None
    assert p.parse_phys("G0918000000", "3.1 mPa·s (40℃)") is None
    assert p.parse_phys("G0918000000", "7.5 mm2/s (40℃)") == 7.5


def test_row_dispatch():
    assert p.parse_toxicity_row({"div_code": "GHS9999", "primary_value_text": "LD50 1 mg/kg"}) is None
    assert p.parse_toxicity_row({"div_code": "GHS0201", "primary_value_text": "정보 없음", "primary_value": None}) == \
        {"rule": "acute", "result": None}
    assert p.parse_toxicity_row({"div_code": "GHS0312", "primary_value_text": "EC50 4 mg/L"}) == \
        {"rule": "aquatic_acute", "result": {"sign": "=", "value": 4.0, "unit": "mg/L"}}
    assert p.parse_toxicity_row({"div_code": "GHS0331", "primary_value_text": "이분해성"})["result"] == {"rapidly_degradable": True}
    assert p.parse_property_row({"property_id": "G0000000000", "primary_value_text": "5"}) is None
    assert p.parse_property_row({"property_id": "G0904000000", "primary_value_text": "pH 6.5"}) == \
        {"rule": "PH", "result": {"value": 6.5}}
