"""역할 F 보조 도구: 성적표 묶음(score_set), 결과 비교(compare), 검수 진도(progress)."""
import copy
import json

from openpyxl import Workbook

from msds.common import paths
from msds.evaluate import compare as cp
from msds.evaluate import progress as pg
from msds.evaluate import score as sc
from msds.review.sheet_spec import COLUMNS, INFO_FIELDS, SHEET_INFO, SHEET_MAIN


def _bad_cas(gold):
    bad = copy.deepcopy(gold)
    bad["msds"][0]["components"][0]["cas_no"] = "7664-93-8"
    return bad


def test_score_set_average_and_details(gold25, tmp_path):
    res = sc.score_set([("T21-A", gold25, gold25), ("T21-B", gold25, _bad_cas(gold25))])
    comp = next(i for i in res["items"] if i["name"].startswith("구성성분(CAS"))
    assert 0 < comp["score"] < 1 and comp["docs_failed"] == 1      # 두 문서 평균
    assert not res["must_pass"] and not res["passed"]
    assert res["docs"]["T21-A"]["passed"] and not res["docs"]["T21-B"]["passed"]
    assert any(d["doc_id"] == "T21-B" for d in res["details"])        # 필수 항목 오류 상세
    assert comp["빠뜨림"] + comp["지어냄"] + comp["틀림"] > 0
    out = sc.write_report(res, tmp_path / "r", "시험")
    for f in ("report.md", "items.csv", "docs.csv", "details.csv", "result.json"):
        assert (tmp_path / "r" / f).exists()
    assert "불합격" in out.read_text(encoding="utf-8")


def test_unreviewed_marks_ref(gold25, tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "GOLD", tmp_path)
    (tmp_path / "T21-A.unreviewed.json").write_text(
        json.dumps(["msds[0].hazard.h_statements[k=H314].text", "msds[0].regulations[k=x].applicable"]),
        encoding="utf-8")
    res = sc.score_set([("T21-A", gold25, gold25)])
    ref = {i["name"] for i in res["items"] if i["ref"]}
    assert "H 코드" in ref and any(n.startswith("15항") for n in ref)
    assert not any(n.startswith("구성성분") for n in ref)


def test_compare(gold25, tmp_path):
    a = sc.score_set([("T21-A", gold25, gold25)])
    b = sc.score_set([("T21-A", gold25, _bad_cas(gold25))])
    for name, r in (("a", a), ("b", b)):
        sc.write_report(r, tmp_path / name, name)
    cmp = cp.compare([("기준선", cp.load_result(tmp_path / "b")), ("GPT실버", cp.load_result(tmp_path / "a"))])
    assert cmp["labels"] == ["기준선", "GPT실버"] and len(cmp["rows"]) == 23
    out = cp.write_compare(cmp, tmp_path / "c", "시험", ["GPT실버"])
    text = out.read_text(encoding="utf-8")
    assert "GPT실버 (참고)" in text and "미달" in text and (tmp_path / "c" / "compare.csv").exists()


def _sheet(path, rows, info):
    wb = Workbook()
    ws = wb.active
    ws.title = SHEET_MAIN
    ws.append(COLUMNS)
    for r in rows:
        ws.append([r.get(c, "") for c in COLUMNS])
    wi = wb.create_sheet(SHEET_INFO)
    for k in INFO_FIELDS:
        wi.append([k, info.get(k, "")])
    wb.save(path)


def _no_manifest(*_a, **_k):
    raise FileNotFoundError("data/manifest.csv")


def test_progress(tmp_path, monkeypatch):
    monkeypatch.setattr(pg.manifest, "load", _no_manifest)   # manifest가 없는 브랜치에서도 돈다
    rows = [{"경로": "a", "우선순위": 1, "검수 결과": "GPT 채택", "교차 확인자": "B"},
            {"경로": "b", "우선순위": 1, "검수 결과": "수정"},
            {"경로": "c", "우선순위": 2, "검수 결과": ""},
            {"경로": "d", "우선순위": 3, "검수 결과": ""},
            {"경로": "e", "우선순위": "", "검수 결과": "누락 추가"}]
    _sheet(tmp_path / "T21-X999.xlsx", rows,
           {"검수자": "F", "교차 확인자": "B", "검수 시작": "2026-10-26 10:00", "검수 끝": "2026-10-26 12:30"})
    p = pg.read_sheet(tmp_path / "T21-X999.xlsx")
    assert p["total"] == {"1": 2, "2": 1, "3": 1, pg.EXTRA: 1} and p["done"] == {"1": 2, pg.EXTRA: 1}
    assert p["cross"] == (1, 2) and p["minutes"] == 150 and p["results"]["수정"] == 1
    assert pg.status(p, gold=False) == "1순위 완료"
    items = pg.collect(purpose="기타", review_dir=tmp_path)
    md = pg.to_markdown(items)
    assert "T21-X999" in md and "2/2" in md and "150분" in md
