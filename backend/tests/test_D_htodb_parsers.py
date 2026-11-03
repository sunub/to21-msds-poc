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


def test_문장_첫머리가_부등호면_숫자_칸이_있어도_부등호로_읽는다():
    # 지식DB에 LD50 <200 인데 primary_value 200 인 행이 있다. = 로 읽으면 부등호를 계산에 넣게 된다 (D-12)
    r = p.parse_acute("LD50 <200 ㎎/㎏   실험종 : Rabbit (LD100 : 200mg/kg)", "200", "GHS0202")
    assert (r["sign"], r["value"], r["basis"]) == ("<=", 200.0, "PRIMARY_VALUE")  # 맹독 성분이 계산에서 빠지지 않게 상한으로 계산
    assert p.parse_acute("LD50 ≤15000 ㎎/㎏   실험종 : Guinea pig", "15000", "GHS0202")["sign"] == "<="
    assert p.parse_acute("LC50 >3.24 ㎎/ℓ  4 hr 실험종 : Rat", "495", "GHS0204")["sign"] == ">"


def test_괄호_속_다른_시험의_부등호는_대표값을_바꾸지_않는다():
    r = p.parse_acute("LD50 700 ㎎/㎏ 실험종 : Rat (계산값, 랫드 approx. LD50 > 6400 mg/kg bw)", "700", "GHS0201")
    assert (r["sign"], r["value"]) == ("=", 700.0)
    assert p.parse_acute("구분4", "500", "GHS0201")["sign"] == "="


def test_천_단위_쉼표_값은_문장에서_같은_값을_읽는다():
    r = p.parse_acute("LD50 1,720 ㎎/㎏ 실험종 : Rabbit", "1,720", "GHS0202")
    assert (r["sign"], r["value"]) == ("=", 1720.0)


def test_문장이_범위면_숫자_칸이_상한이어도_최솟값을_쓴다():
    r = p.parse_acute("LD50 50 ~ 300 ㎎/㎏  실험종 : Rat", "300", "GHS0201")  # 범위 771행 중 735행이 상한값 (D-12)
    assert (r["value"], r["value_max"]) == (50.0, 300.0)


def test_숫자_칸이_문장_값_그대로고_단위가_다르면_환산한다():
    r = p.parse_acute("LC50 454 ~ 507 ㎎/㎥ 실험종 : Rat", "507", "GHS0205")
    assert (r["sign"], r["value"], r["unit"]) == ("=", 0.454, "mg/L")
    assert p.parse_acute("LC50 463 ppm 실험종 : Rat", "463", "GHS0204", mw=100.0)["value"] == pytest.approx(463 * 100 / 24450)
    assert p.parse_acute("LC50 463 ppm 실험종 : Rat", "463", "GHS0204")["sign"] == "?"  # 분자량이 없으면 계산에서 뺀다


def test_DB가_환산한_숫자_칸은_그대로_쓴다():
    assert p.parse_acute("LC50 5.319 ㎎/ℓ 4 hr 실험종 : Rat", "1364.56", "GHS0203")["value"] == 1364.56


# ── 재검증(전 행 대조)에서 나온 입력 ──────────────────────────────
@pytest.mark.parametrize("text,pv,div,want", [
    ("LD50 7.34 ~ 7.46 ㎖/㎏ 실험종 : Rat (분류되지 않음)", "7400", "GHS0201", 7400.0),   # 모르는 단위: 숫자 칸 유지
    ("LC50 0.65 ~ 0.78 ㎎/ℓ 1 hr 실험종 : Rat", "0.39", "GHS0204", 0.325),               # 칸이 상한의 시간 환산: 하한에도
    ("LD50 0.7 ~ 0.30 ㎎/ℓ 실험종 : Rat", "0.30", "GHS0205", 0.30),                      # 역순 범위: 최솟값이 칸 값
    ("LC50 2165 ~ 3617 ppm 1 hr 실험종 : Rat", "6.829", "GHS0204", 6.829),                # 분자량 없이 환산된 칸: 유지
    ("LD50 1201 ~ 1842", "1521.5", "GHS0201", 1521.5),                                     # 알 수 없는 배율: 유지
])
def test_범위_문장의_숫자_칸(text, pv, div, want):
    r = p.parse_acute(text, pv, div)
    assert r["sign"] == "=" and r["value"] == pytest.approx(want)


def test_흡입_칸의_LC50_mg_kg은_단위_오타로_보고_LD50은_뺀다():
    assert (p.parse_acute("LC50 6.5 ㎎/㎏ 4 hr (노동부 구분 3)", "6.5", "GHS0205")["sign"]) == "="
    assert p.parse_acute("LD50 101 ㎎/㎏ 실험종 : Rabbit", "101", "GHS0205")["sign"] == "?"


def test_단위가_다른_범위는_숫자_칸의_시간_환산과_단위를_함께_맞춘다():
    # 말로노니트릴: 'LD50 200 ~ 300 ㎎/㎥ 2 hr', 숫자 칸 212.13 = 300/√2 (시간만 환산, 단위는 그대로)
    r = p.parse_acute("LD50 200 ~ 300 ㎎/㎥ 2 hr 실험종 : Rat", "212.13", "GHS0204")
    assert r["value"] == pytest.approx(200 / 2 ** 0.5 / 1000, rel=1e-3)
