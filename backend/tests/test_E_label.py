from msds.compliance.label import derive_label


def test_황산_25번():
    r = derive_label([("PH_METAL_CORR", "1"), ("HH_ACUTE_INHAL", "2"), ("HH_SKIN_CORR", "1"),
                      ("HH_EYE_DMG", "1"), ("HH_CARCINOGEN", "1A"), ("HH_STOT_SE", "1"), ("ENV_AQ_CHRONIC", "3")])
    assert r["pictograms"] == ["GHS05", "GHS06", "GHS08"]
    assert r["signal_word"] == "위험"
    assert r["h_codes"] == ["H290", "H314", "H318", "H330", "H350", "H370", "H412"]


def test_해골이면_감탄부호_생략():
    assert derive_label([("HH_ACUTE_ORAL", "3"), ("HH_ACUTE_DERMAL", "4")])["pictograms"] == ["GHS06"]


def test_부식성이면_자극성_감탄부호_생략_급성4의_감탄부호는_유지():
    assert derive_label([("HH_SKIN_CORR", "1A"), ("HH_EYE_DMG", "2")])["pictograms"] == ["GHS05"]
    assert derive_label([("HH_SKIN_CORR", "1A"), ("HH_ACUTE_ORAL", "4")])["pictograms"] == ["GHS05", "GHS07"]


def test_호흡기과민성이면_피부과민성_생략():
    assert derive_label([("HH_RESP_SENS", "1"), ("HH_SKIN_SENS", "1")])["pictograms"] == ["GHS08"]


def test_신호어_위험이_경고보다_우선():
    assert derive_label([("HH_SKIN_CORR", "2"), ("HH_EYE_DMG", "1")])["signal_word"] == "위험"
    assert derive_label([("HH_SKIN_CORR", "2")])["signal_word"] == "경고"


def test_구분5와_빈_입력은_표시_없음():
    assert derive_label([("HH_ACUTE_ORAL", "5")]) == {"pictograms": [], "signal_word": None, "h_codes": []}
