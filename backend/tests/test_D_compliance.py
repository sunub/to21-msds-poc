"""역할 D 완료 기준: 이 파일의 시험이 모두 passed (skipped 0)."""
from conftest import todo
from msds.compliance.classifier import product_type
from msds.compliance.loader import load_inputs


def test_loader(gold25):
    x = todo(load_inputs, gold25)
    assert any(c.get("cas_no") == "7664-93-9" for c in x["components"])
    assert x["as_of_date"]


def test_classifier(gold25):
    x = todo(load_inputs, gold25)
    r = todo(product_type, x)
    assert r["type"] in ("단일물질", "혼합물", "판단불가") and r["basis"]
