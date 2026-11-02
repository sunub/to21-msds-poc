"""표시 요소 보완 시험 (설계서 31장, 11/02 F).

실제 HTODB로 silver 27개를 돌리자 표시 요소 불일치가 38줄 나왔는데, 대부분 표와 규칙의 빈틈이었다.
- 물리적 위험성(인화성·고압가스 등) H코드·그림문자 행이 표에 없었다 → HTODB TB_GHS_HCODE_PHRASE에서 옮김
- 표적장기 1회 구분3에서 효과와 상관없이 H335·H336을 둘 다 도출했다 → 효과로 고름
- 해골(GHS06)이 있으면 느낌표(GHS07)를 모두 뺐다 → 설계서 31장대로 '급성독성용' 느낌표만 뺌
- MSDS의 묶음 H코드(H302+H332), 신호어 '없음'을 다르게 읽었다 → 정리 후 비교
"""
from msds.compliance.consistency import _label
from msds.compliance.label import derive_label


def test_물리적_위험성도_표시_요소를_도출한다():
    d = derive_label([("PH_FLAM_LIQ", "2"), ("PH_PRESS_GAS", "냉동액화가스"), ("PH_OXID_GAS", "1")])
    assert d["h_codes"] == ["H225", "H270", "H281"]
    assert d["pictograms"] == ["GHS02", "GHS03", "GHS04"] and d["signal_word"] == "위험"  # SYM03·04 → GHS04·03
    assert derive_label([("PH_FLAM_LIQ", "4")]) == {"pictograms": [], "signal_word": "경고", "h_codes": ["H227"]}


def test_표적장기_구분3은_효과로_H코드를_고른다():
    assert derive_label([("HH_STOT_SE", "3", "마취")])["h_codes"] == ["H336"]
    assert derive_label([("HH_STOT_SE", "3", "호흡기계 자극")])["h_codes"] == ["H335"]
    assert derive_label([("HH_STOT_SE", "3")])["h_codes"] == ["H335", "H336"]  # 효과를 모르면 둘 다


def test_해골이_있으면_급성독성용_느낌표만_뺀다():
    d = derive_label([("HH_ACUTE_ORAL", "3"), ("HH_ACUTE_DERMAL", "4"), ("HH_STOT_SE", "3", "호흡기")])
    assert d["pictograms"] == ["GHS06", "GHS07"]  # 표적장기 구분3의 느낌표는 남는다(설계서 31장)
    assert derive_label([("HH_ACUTE_ORAL", "3"), ("HH_ACUTE_DERMAL", "4")])["pictograms"] == ["GHS06"]


def item(classes, pictos, signal, h):
    return {"hazard": {"classes": [{"class_code": c, "category": k, "effect": e} for c, k, e in classes],
                       "pictograms": [{"code": p} for p in pictos], "signal_word": signal,
                       "h_statements": [{"code": x} for x in h]}}


def test_MSDS_값을_정리해서_비교한다():
    rows, _ = _label(item([("HH_ACUTE_ORAL", "4", None), ("HH_ACUTE_INHAL", "4", None)], ["GHS07"], "경고", ["H302+H332"]))
    assert all(r["verdict"] == "일치" for r in rows), rows  # 묶음 H코드를 나눠 봄
    rows, _ = _label(item([("ENV_AQ_CHRONIC", "3", None)], [], "없음", ["H412"]))
    assert {r["class_code"]: r["verdict"] for r in rows}["LABEL_SIGNAL_WORD"] == "일치"  # 신호어 '없음' = 없음
    rows, _ = _label(item([("HH_STOT_SE", "3", None)], ["GHS07"], "경고", ["H336"]))
    assert all(r["verdict"] == "일치" for r in rows)  # 효과가 비면 MSDS H코드로 짐작
