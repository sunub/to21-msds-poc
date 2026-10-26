"""15항 국내 규제 판정 시험 (설계서 4단계)."""
from msds.compliance.knowledge import EmptyProvider
from msds.compliance.sec15 import compare_sec15

CAS = "7664-93-9"


class FakeProvider(EmptyProvider):
    def __init__(self, rows):
        self.rows = rows

    def get_regulation(self, cas_no, as_of):
        return {**super().get_regulation(cas_no, as_of), "knowledge_version": "test-1",
                "rows": [{**r, "source": "시험 기준"} for r in self.rows.get(cas_no, [])]}


def _ref(item, value=None, op=">=", law="OSH"):
    return {"law": law, "item_code": item, "threshold_op": op if value is not None else None,
            "threshold_value": value, "threshold_unit": "%" if value is not None else None}


def _sup(item, applicable, comp_ref="1", law="OSH", cas=CAS):
    return {"law": law, "item_code": item, "comp_ref": comp_ref, "applicable": applicable, "cas_no": cas}


def _inputs(regs, content=None, cas=CAS):
    q = content or {"lower_op": ">=", "lower": 93, "upper_op": "<=", "upper": 98, "unit": "%"}
    return {"as_of_date": "2022-06-29", "components": [{"seq": 1, "cas_no": cas, "content": q}],
            "regulations": regs}


def _verdicts(rows):
    return {(r["law"], r["item_code"], r["comp_ref"]): r["verdict"] for r in rows}


def test_applicable_above_threshold_matches():
    rows = compare_sec15(_inputs([_sup("OSH_MEASURE", "해당")]), FakeProvider({CAS: [_ref("OSH_MEASURE", 1)]}))

    assert _verdicts(rows) == {("OSH", "OSH_MEASURE", "1"): "일치"}
    assert rows[0]["expected"] == "해당" and rows[0]["source"] == ["시험 기준"]


def test_regulation_without_threshold_applies_at_any_content():
    rows = compare_sec15(_inputs([_sup("OSH_EXPOSURE_STD", "해당")]),
                         FakeProvider({CAS: [_ref("OSH_EXPOSURE_STD")]}))

    assert _verdicts(rows) == {("OSH", "OSH_EXPOSURE_STD", "1"): "일치"}


def test_supplier_not_stating_applicable_regulation_mismatches():
    p = FakeProvider({CAS: [_ref("OSH_MEASURE", 1), _ref("OSH_MANAGED", 1), _ref("CCA_ACCIDENT", 10, law="CCA")]})
    rows = compare_sec15(_inputs([_sup("OSH_MEASURE", "비해당"), _sup("OSH_MANAGED", "미기재")]), p)

    assert _verdicts(rows) == {("OSH", "OSH_MEASURE", "1"): "불일치", ("OSH", "OSH_MANAGED", "1"): "불일치",
                               ("CCA", "CCA_ACCIDENT", "1"): "불일치"}


def test_below_threshold_is_not_applicable():
    low = {"lower_op": ">=", "lower": 2, "upper_op": "<=", "upper": 7, "unit": "%"}
    p = FakeProvider({CAS: [_ref("CCA_ACCIDENT", 10, law="CCA")]})

    assert _verdicts(compare_sec15(_inputs([_sup("CCA_ACCIDENT", "비해당", law="CCA")], low), p)) == {
        ("CCA", "CCA_ACCIDENT", "1"): "일치"}
    assert _verdicts(compare_sec15(_inputs([_sup("CCA_ACCIDENT", "해당", law="CCA")], low), p)) == {
        ("CCA", "CCA_ACCIDENT", "1"): "불일치"}


def test_content_range_across_threshold_is_borderline():
    q = {"lower_op": ">=", "lower": 0.5, "upper_op": "<=", "upper": 3, "unit": "%"}
    rows = compare_sec15(_inputs([_sup("OSH_MEASURE", "해당")], q), FakeProvider({CAS: [_ref("OSH_MEASURE", 1)]}))

    assert _verdicts(rows) == {("OSH", "OSH_MEASURE", "1"): "경계"}


def test_strict_bounds_at_the_threshold():
    below = {"upper_op": "<", "upper": 1, "unit": "%"}       # 1% 미만
    above = {"lower_op": ">", "lower": 1, "unit": "%"}       # 1% 초과
    p = FakeProvider({CAS: [_ref("OSH_MEASURE", 1, op=">")]})

    assert compare_sec15(_inputs([], below), p)[0]["expected"] == "비해당"
    assert compare_sec15(_inputs([], above), p)[0]["expected"] == "해당"


def test_no_reference_row_and_supplier_not_applicable_matches():
    rows = compare_sec15(_inputs([_sup("KREACH_REG", "비해당", law="KREACH")]), FakeProvider({}))

    assert _verdicts(rows) == {("KREACH", "KREACH_REG", "1"): "일치"}


def test_no_reference_row_and_supplier_applicable_is_insufficient_evidence():
    rows = compare_sec15(_inputs([_sup("KREACH_REG", "해당", law="KREACH")]), FakeProvider({}))

    assert _verdicts(rows) == {("KREACH", "KREACH_REG", "1"): "근거부족"}


def test_international_rows_are_excluded():
    rows = compare_sec15(_inputs([_sup("INTL_EU", "해당", law="INTL")]),
                         FakeProvider({CAS: [_ref("INTL_US", law="INTL")]}))

    assert rows == []


def test_mixture_wide_row_is_insufficient_evidence():
    rows = compare_sec15(_inputs([_sup("OSH_PSM", "해당", comp_ref="MIX", cas=None)]), FakeProvider({}))

    assert _verdicts(rows) == {("OSH", "OSH_PSM", "MIX"): "근거부족"}


def test_no_knowledge_cas_or_content_is_insufficient_evidence():
    sup = [_sup("OSH_MEASURE", "해당")]
    p = FakeProvider({CAS: [_ref("OSH_MEASURE", 1)]})

    assert _verdicts(compare_sec15(_inputs(sup), EmptyProvider())) == {("OSH", "OSH_MEASURE", "1"): "근거부족"}
    assert _verdicts(compare_sec15(_inputs([_sup("OSH_MEASURE", "해당", cas=None)], cas=None), p)) == {
        ("OSH", "OSH_MEASURE", "1"): "근거부족"}
    assert _verdicts(compare_sec15(_inputs(sup, {"unit": "%"}), p)) == {("OSH", "OSH_MEASURE", "1"): "근거부족"}
