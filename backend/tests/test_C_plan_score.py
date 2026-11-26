"""기획서 기준 채점(plan_score) 시험. 실제 데이터 없이 돈다."""
from msds.evaluate import plan_score as ps


def item(**kw):
    base = {"meta": {"msds_no": None, "first_issue_date": None, "last_revision_date": None},
            "product": {"name": "질소"}, "components": [], "hazard": {"signal_word": None, "classes": []},
            "regulations": [], "narratives": [], "evidence": [{"field": "x", "page": 1}], "extras": []}
    for k, v in kw.items():
        base[k] = v
    return base


def doc(*items):
    return {"doc": {}, "msds": list(items)}


def test_scope_follows_plan_sections():
    assert ps.scope_of("meta.msds_no") == "범위"
    assert ps.scope_of("meta.last_revision_date") == "16항 참고"        # D-1: 16항 개정 정보는 범위 밖
    assert ps.scope_of("narratives[k=S8_ENG].item_code") == "범위"
    assert ps.scope_of("narratives[k=S7_HANDLING].item_code") == "범위 밖"  # 7항은 추출하지 않는다
    assert ps.scope_of("toxicity[k=MIX|TX_ORAL|LD50|RAT].q") == "범위"
    assert ps.scope_of("regulations[k=MIX|OSH|OSH_MANAGED|].applicable") == "범위"
    assert ps.scope_of("regulations[k=71-43-2|INTL|INTL_US|US|미국관리정보].applicable") == "15항 해외·기타"   # D-2
    assert ps.scope_of("regulations[k=MIX|KR_ETC|||기타법령].applicable") == "15항 해외·기타"


def test_engine_cells_are_what_judgment_reads():
    assert ps.is_engine_cell("components[k=7727-37-9].cas_no")
    assert not ps.is_engine_cell("components[k=7727-37-9].ec_no")
    assert ps.is_engine_cell("hazard.classes[k=FLAM_GAS|1|].category")
    assert ps.is_engine_cell("regulations[k=MIX|OSH|OSH_MANAGED|].applicable")
    assert not ps.is_engine_cell("regulations[k=MIX|INTL|INTL_US|US|TSCA].applicable")   # D-2: 해외 규제
    assert not ps.is_engine_cell("exposure_limits[k=MIX|KR|TWA].q")                    # D-2: 8항 값은 판정 안 함


def test_cells_skip_bookkeeping():
    c = ps.cells(item())
    assert not any(p.startswith(("evidence", "extras")) for p in c)


def test_compare_doc_counts_results():
    g = doc(item(product={"name": "질소"}, hazard={"signal_word": "경고", "classes": []},
                 meta={"msds_no": "AA00001-0000000001", "first_issue_date": "2010-06-21", "last_revision_date": None}))
    p = doc(item(product={"name": "질소가스"}, hazard={"signal_word": None, "classes": []},
                 meta={"msds_no": "AA00001-0000000001", "first_issue_date": None, "last_revision_date": "2020-01-01"},
                 regulations=[{"comp_ref": "MIX", "law": "OSH", "item_code": "OSH_MANAGED", "applicable": "비해당"}]))
    rows = ps.compare_doc(g, p)["cells"]
    by = {r["path"]: r["result"] for r in rows}
    assert by["meta.msds_no"] == "맞음"
    assert by["product.name"] == "틀림"
    assert by["hazard.signal_word"] == "빠뜨림"
    assert by["regulations[k=MIX|OSH|OSH_MANAGED|].applicable"] == "지어냄"
    inside = ps.tally([r for r in rows if r["scope"] == "범위"])
    assert (inside["correct"], inside["wrong"], inside["missing"]) == (1, 1, 1)
    assert inside["accuracy"] == 1 / 3
    assert inside["to_fix"] == inside["wrong"] + inside["missing"] + inside["extra"]
    ref = ps.tally([r for r in rows if r["scope"] == "16항 참고"])      # 날짜 두 칸은 범위 밖으로 따로 센다
    assert (ref["missing"], ref["extra"]) == (1, 1)


def test_unreviewed_cells_left_out_of_accuracy():
    g = doc(item(product={"name": "질소"}))
    p = doc(item(product={"name": "질소가스"}))
    rows = ps.compare_doc(g, p, unreviewed={"msds[0].product.name"})["cells"]
    t = ps.tally(rows)
    assert t["unreviewed"] == 1 and t["wrong"] == 0 and t["accuracy"] is None


def test_extra_msds_counts_as_extra_cells():
    g = doc(item())
    p = doc(item(), item(product={"name": "아르곤"}))
    rows = ps.compare_doc(g, p)["cells"]
    assert any(r["msds"] == 1 and r["result"] == "지어냄" for r in rows)


def test_cell_agreement_only_in_scope():
    a = doc(item(product={"name": "질소"}, meta={"msds_no": None, "first_issue_date": "2010-01-01",
                                                "last_revision_date": None}))
    b = doc(item(product={"name": "질소가스"}, meta={"msds_no": None, "first_issue_date": None,
                                                  "last_revision_date": None}))
    got = ps.cell_agreement(a, b)
    assert got["total"] == 1 and got["same"] == 0          # 16항 날짜는 재현성 계산에서 뺀다
    assert ps.cell_agreement(a, a)["rate"] == 1.0


def test_empty_forms_are_the_same_value():
    assert ps.canon({"value": "자료없음", "refs": [], "cond": None, "key": ""}) == {"value": "자료없음"}
    assert ps.canon([]) is None and ps.canon("") is None and ps.canon({"a": None}) is None
    assert ps.canon("자료 없음") == "자료 없음"          # 글자 표기는 그대로 둔다


def test_q_compared_on_seven_elements_only():
    g = {"raw": "해당 없음", "status": "해당없음", "value": None, "dp": 1, "approx": True, "note": "추정치"}
    p = {"raw": "해당없음", "status": "해당없음", "value": None}
    assert ps.canon(ps.q_only("toxicity[k=x].q", g)) == ps.canon(ps.q_only("toxicity[k=x].q", p))
    assert ps.q_only("narratives[k=S8_ENG].statements[k=1]", {"raw": "x", "value": 1}) == {"raw": "x", "value": 1}
    assert ps.canon(ps.q_only("components[k=x].content", {"value": 5, "unit": "%"})) != \
        ps.canon(ps.q_only("components[k=x].content", {"value": 5, "unit": "wt%"}))
