"""단일물질 2항 판정 시험 (설계서 3단계)."""
from msds.compliance.knowledge import EmptyProvider
from msds.compliance.single import compare_single

CAS = "64-17-5"


class FakeProvider(EmptyProvider):
    def __init__(self, classes):
        self.classes = classes

    def get_reference(self, cas_no, as_of):
        return {**super().get_reference(cas_no, as_of), "knowledge_version": "test-1",
                "classes": [{**c, "source": "시험 기준"} for c in self.classes]}


def _inputs(classes, cas=CAS):
    return {"as_of_date": "2024-01-01", "components": [{"cas_no": cas}], "hazard": {"classes": classes}}


def _cls(code, cat, route=None):
    return {"class_code": code, "category": cat, "route_form": route}


def _verdicts(rows):
    return {(r["class_code"], r["route_form"]): r["verdict"] for r in rows}


def test_same_category_matches():
    rows = compare_single(_inputs([_cls("PH_FLAM_LIQ", "2")]), FakeProvider([_cls("PH_FLAM_LIQ", "2")]))

    assert _verdicts(rows) == {("PH_FLAM_LIQ", None): "일치"}
    assert rows[0]["knowledge_version"] == "test-1"
    assert rows[0]["source"] == ["시험 기준"]


def test_missing_subcategory_matches_both_ways():
    p = FakeProvider([_cls("HH_SKIN_CORR", "1B"), _cls("HH_EYE_DMG", "2")])
    rows = compare_single(_inputs([_cls("HH_SKIN_CORR", "1"), _cls("HH_EYE_DMG", "2A")]), p)

    assert set(_verdicts(rows).values()) == {"일치"}
    assert all("세부구분" in r["basis"] for r in rows)


def test_different_subcategories_mismatch():
    rows = compare_single(_inputs([_cls("HH_SKIN_CORR", "1A")]), FakeProvider([_cls("HH_SKIN_CORR", "1B")]))

    assert _verdicts(rows) == {("HH_SKIN_CORR", None): "불일치"}


def test_reference_class_left_out_by_supplier_mismatches():
    rows = compare_single(_inputs([]), FakeProvider([_cls("HH_CARCINOGEN", "1A")]))

    assert _verdicts(rows) == {("HH_CARCINOGEN", None): "불일치"}


def test_class_only_supplier_lists_is_insufficient_evidence():
    rows = compare_single(_inputs([_cls("ENV_AQ_CHRONIC", "3")]), FakeProvider([]))

    assert _verdicts(rows) == {("ENV_AQ_CHRONIC", None): "근거부족"}


def test_extra_category_in_known_class_is_insufficient_evidence():
    p = FakeProvider([_cls("HH_STOT_SE", "1")])
    rows = compare_single(_inputs([_cls("HH_STOT_SE", "1"), _cls("HH_STOT_SE", "3(호흡기계자극)")]), p)

    assert _verdicts(rows) == {("HH_STOT_SE", None): "근거부족"}


def test_several_categories_of_one_class_match():
    both = [_cls("HH_STOT_SE", "1"), _cls("HH_STOT_SE", "3(호흡기계자극)")]
    rows = compare_single(_inputs(both), FakeProvider(both))

    assert _verdicts(rows) == {("HH_STOT_SE", None): "일치"}


def test_inhalation_route_is_part_of_the_class():
    p = FakeProvider([_cls("HH_ACUTE_INHAL", "2", "증기")])
    rows = compare_single(_inputs([_cls("HH_ACUTE_INHAL", "2", "가스")]), p)

    assert _verdicts(rows) == {("HH_ACUTE_INHAL", "증기"): "불일치", ("HH_ACUTE_INHAL", "가스"): "근거부족"}


def test_no_knowledge_or_no_cas_is_insufficient_evidence():
    sup = [_cls("PH_FLAM_LIQ", "2")]

    assert _verdicts(compare_single(_inputs(sup), EmptyProvider())) == {("PH_FLAM_LIQ", None): "근거부족"}
    assert _verdicts(compare_single(_inputs(sup, cas=None), FakeProvider(sup))) == {("PH_FLAM_LIQ", None): "근거부족"}
