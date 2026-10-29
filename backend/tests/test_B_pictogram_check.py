"""extract/pictogram_check.py 시험: H코드로 추론한 그림문자와 모델이 읽은 그림문자 대조 (ADR-019).

매핑표는 tmp_path에 만든 가짜 CSV이고 H코드 값도 가짜다. E의 매핑표 값을 시험에 적지 않는다.
실제 configs/hazard_label_map.csv는 열 이름과 그림문자 칸의 모양만 본다.
"""
import csv
import re

from msds.common.paths import CONFIGS
from msds.extract import pictogram_check as pc

COLUMNS = ["h_code", "class_code", "category", "pictogram", "signal_word", "source", "note"]
FAKE_ROWS = [
    ("H900", "FAKE_A", "1", "GHS02", "위험", "가짜 출처", ""),
    ("H900", "FAKE_A", "2", "GHS02", "경고", "가짜 출처", ""),
    ("H901", "FAKE_B", "1", "GHS05", "위험", "가짜 출처", ""),
    ("H901", "FAKE_B", "2", "GHS07", "경고", "가짜 출처", ""),
    ("H902", "FAKE_C", "5", "", "경고", "가짜 출처", "그림문자 없음"),
]


def fake_map(tmp_path):
    path = tmp_path / "hazard_label_map.csv"
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        w.writerows(FAKE_ROWS)
    return path


def item(h_codes, pictograms):
    """TO21 msds 항목 중 대조에 쓰는 칸만 있는 가짜."""
    return {"hazard": {"h_statements": [{"code": c} for c in h_codes],
                       "pictograms": [{"code": c, "detection": None} for c in pictograms]}}


# ── load_hazard_map ────────────────────────────────────

def test_load_hazard_map(tmp_path):
    assert pc.load_hazard_map(fake_map(tmp_path)) == {"H900": {"GHS02"}, "H901": {"GHS05", "GHS07"}}


def test_load_hazard_map_missing_file(tmp_path):
    assert pc.load_hazard_map(tmp_path / "없음.csv") is None


def test_load_hazard_map_default_path(tmp_path, monkeypatch):
    monkeypatch.setattr(pc, "HAZARD_MAP", fake_map(tmp_path))
    assert pc.load_hazard_map() == {"H900": {"GHS02"}, "H901": {"GHS05", "GHS07"}}
    monkeypatch.setattr(pc, "HAZARD_MAP", tmp_path / "없음.csv")
    assert pc.load_hazard_map() is None


def test_default_path_is_configs_copy():
    assert pc.HAZARD_MAP == CONFIGS / "hazard_label_map.csv"


# ── infer_pictograms ───────────────────────────────────

def test_infer_pictograms(tmp_path):
    hmap = pc.load_hazard_map(fake_map(tmp_path))
    assert pc.infer_pictograms(["H900"], hmap) == {"GHS02"}
    assert pc.infer_pictograms(["H900", "H901"], hmap) == {"GHS02", "GHS05", "GHS07"}
    assert pc.infer_pictograms(["H902", "H999"], hmap) == set()     # 그림문자 없는 구분, 표에 없는 코드
    assert pc.infer_pictograms([], hmap) == set()


def test_infer_pictograms_combined_and_suffix_codes(tmp_path):
    """결합 코드(+)는 나눠 보고, 접미 문자는 떼고 찾는다. EUH 코드는 그림문자가 없다."""
    hmap = pc.load_hazard_map(fake_map(tmp_path))
    assert pc.infer_pictograms(["H900+H901"], hmap) == {"GHS02", "GHS05", "GHS07"}
    assert pc.infer_pictograms(["H900FD"], hmap) == {"GHS02"}
    assert pc.infer_pictograms(["EUH900", None], hmap) == set()


# ── compare ────────────────────────────────────────────

def test_compare_same():
    assert pc.compare(["GHS07", "GHS02"], {"GHS02", "GHS07"}) == {
        "model": ["GHS02", "GHS07"], "inferred": ["GHS02", "GHS07"], "missing": [], "extra": [], "ok": True}


def test_compare_mismatch():
    assert pc.compare(["GHS07", "GHS09"], {"GHS02", "GHS09"}) == {
        "model": ["GHS07", "GHS09"], "inferred": ["GHS02", "GHS09"], "missing": ["GHS02"], "extra": ["GHS07"],
        "ok": False}


def test_compare_empty_and_none_codes():
    assert pc.compare([], set())["ok"] is True
    assert pc.compare([None, "GHS02", "GHS02"], {"GHS02"}) == {
        "model": ["GHS02"], "inferred": ["GHS02"], "missing": [], "extra": [], "ok": True}


# ── check_msds ─────────────────────────────────────────

def test_check_msds(tmp_path):
    hmap = pc.load_hazard_map(fake_map(tmp_path))
    assert pc.check_msds(item(["H900"], ["GHS07"]), hmap) == {
        "model": ["GHS07"], "inferred": ["GHS02"], "missing": ["GHS02"], "extra": ["GHS07"], "ok": False}
    assert pc.check_msds(item(["H900"], ["GHS02"]), hmap)["ok"] is True


def test_check_msds_without_map_is_skipped():
    assert pc.check_msds(item(["H900"], ["GHS07"]), None) == {"skipped": "hazard_label_map.csv 없음"}


def test_check_msds_empty_hazard(tmp_path):
    hmap = pc.load_hazard_map(fake_map(tmp_path))
    assert pc.check_msds({"hazard": {"h_statements": [], "pictograms": []}}, hmap)["ok"] is True


# ── 실제 사본 (값은 적지 않는다) ───────────────────────

def test_configs_copy_columns_and_pictogram_shape():
    path = CONFIGS / "hazard_label_map.csv"
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == COLUMNS
        rows = list(reader)
    assert rows
    assert all(re.fullmatch(r"GHS0\d", r["pictogram"]) or r["pictogram"] == "" for r in rows)


def test_configs_copy_source_note():
    text = (CONFIGS / "hazard_label_map.SOURCE.txt").read_text(encoding="utf-8").strip()
    assert len(text.splitlines()) == 1
    assert "e/classify" in text and "9b53d21" in text and "2026-10-29" in text
