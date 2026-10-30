from msds.common.conventions import apply

NONE_Q = {"raw": "해당없음", "value": None, "unit": None, "status": "해당없음"}


def test_no_value_rows_follow_to21_example():
    item = {
        "exposure_limits": [
            {"comp_ref": "2", "standard": "국내", "limit_type": "기타", "q": NONE_Q},
            {"comp_ref": "2", "standard": "생물학적", "limit_type": None, "q": NONE_Q},
            {"comp_ref": "2", "standard": "OSHA", "limit_type": None, "q": NONE_Q},       # 근거 없는 기준은 그대로
            {"comp_ref": "1", "standard": "국내", "limit_type": "기타", "q": {"value": 0.2, "status": "값있음"}},
            {"comp_ref": "1", "standard": "국내", "limit_type": None, "q": None},
        ],
        "toxicity": [
            {"endpoint": "TX_DERMAL", "descriptor": None, "status": "자료없음"},
            {"endpoint": "TX_DERMAL", "descriptor": "ATE", "status": "자료없음"},
            {"endpoint": "TX_ORAL", "descriptor": None, "status": "값있음"},
            {"comp_ref": "MIX", "endpoint": "TX_DERMAL", "descriptor": None, "status": "자료없음"},
            {"endpoint": "ECO_PERSIST", "descriptor": None, "status": "자료없음"},   # 독성 표에는 생태 지표를 쓰지 않는다
        ],
        "ecotox": [{"comp_ref": "1", "endpoint": e, "descriptor": None, "status": "자료없음"}
                   for e in ("ECO_FISH", "ECO_PERSIST", "ECO_BIOACC", "ECO_BIOACC", "ECO_BIOACC")],
        "cmr": [{"agency": "IARC", "class": "분류되지않음", "status": "자료없음"}],
    }
    out = apply(item)
    assert [r["limit_type"] for r in out["exposure_limits"]] == ["TWA", "BEI", None, "기타", None]
    assert [r["descriptor"] for r in out["toxicity"]] == ["결과기술", "ATE", None, "ATE", "결과기술"]
    assert [r["descriptor"] for r in out["ecotox"]] == ["결과기술", "분해율", "BCF", "분해율", "결과기술"]   # 행은 지우지 않는다
    assert out["cmr"][0]["class"] is None
    assert item["toxicity"][0]["descriptor"] is None                                    # 입력은 바꾸지 않는다


def test_no_value_rows_get_status_only_q():
    item = {"toxicity": [{"endpoint": "TX_ORAL", "descriptor": "LD50", "status": "자료없음", "q": None},
                         {"endpoint": "TX_ORAL", "descriptor": "LD50", "status": "값있음", "q": None, "classification": "분류되지않음"}],
            "ecotox": [{"endpoint": "ECO_FISH", "descriptor": "LC50", "status": "미기재", "q": None},
                       {"endpoint": "ECO_FISH", "descriptor": "LC50", "status": "해당없음", "q": {"raw": "해당 없음", "status": "해당없음"}}]}
    out = apply(item)
    assert out["toxicity"][0]["q"]["raw"] == "자료없음" and out["toxicity"][0]["q"]["status"] == "자료없음"
    assert out["toxicity"][1]["q"] is None                                              # 값있음 행은 그대로
    assert out["ecotox"][0]["q"]["raw"] == "" and out["ecotox"][0]["q"]["status"] == "미기재"
    assert out["ecotox"][1]["q"] == {"raw": "해당 없음", "status": "해당없음"}           # 이미 있는 q는 그대로


def test_missing_tables_are_fine():
    assert apply({"meta": {}}) == {"meta": {}}


def test_existing_bcf_row_is_not_duplicated():
    eco = [{"comp_ref": "1", "endpoint": "ECO_BIOACC", "descriptor": "BCF", "status": "값있음"},
           {"comp_ref": "1", "endpoint": "ECO_BIOACC", "descriptor": None, "status": "자료없음"}]
    assert apply({"ecotox": eco})["ecotox"][1]["descriptor"] == "분해율"
