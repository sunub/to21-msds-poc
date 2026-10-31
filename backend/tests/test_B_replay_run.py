"""scripts/replay_run.py 시험 (ADR-029).

쪽 글자·항목 분할·manifest·실행 폴더·정답은 모두 tmp_path에 만든 가짜 MSDS다 (D-43).
가짜 문서와 항별 응답은 test_B_section_runner의 것을 쓴다. 저장소의 runs/, data/는 읽거나 쓰지 않는다.
모델 서버를 부르지 않는다.
"""
import copy
import importlib
import json
import re
from pathlib import Path

import pytest
import yaml

from msds.common import manifest, paths
from msds.evaluate.score import WEIGHTS, score_set
from msds.extract.expand import to_to21
from msds.extract.inputs import load_document
from msds.extract.rows import parse_rows
from test_B_section_runner import PAGE1, page2, responses, rows11, spans

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
DOC, EVAL, NOGOLD = "T21-X01", "T21-X02", "T21-X03"
ROWS = [
    {"doc_id": DOC, "source_file": "가상 세정액 B.pdf", "purpose": "개발", "pages": "2",
     "text_layer": "정상", "language": "ko"},
    {"doc_id": EVAL, "source_file": "가상 평가 문서.pdf", "purpose": "평가", "pages": "2",
     "text_layer": "정상", "language": "ko"},
    {"doc_id": NOGOLD, "source_file": "가상 개발 문서.pdf", "purpose": "개발", "pages": "2",
     "text_layer": "정상", "language": "ko"},
]
ROWS_SECTION = 11
SUMMARY_KEYS = {"run", "docs", "weighted", "must_pass", "must_total", "items", "doc_weighted"}


@pytest.fixture
def rr(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    return importlib.import_module("replay_run")


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def env(tmp_path, monkeypatch):
    """가짜 쪽 글자(pages/), 항목 분할(sections/), manifest, 실행 폴더 위치(runs/)를 tmp_path에 둔다."""
    for d in (DOC, EVAL, NOGOLD):
        pages = tmp_path / "pages" / d
        pages.mkdir(parents=True)
        (pages / "p001.txt").write_text(PAGE1, encoding="utf-8")
        (pages / "p002.txt").write_text(page2(), encoding="utf-8")
        write_json(tmp_path / "sections" / f"{d}.json", {"msds": [{"pages": [1, 2], "sections": spans()}]})
    path = tmp_path / "manifest.csv"
    manifest.save(ROWS, path)
    orig = manifest.load
    monkeypatch.setattr(manifest, "load", lambda p=path: orig(p))
    monkeypatch.setattr(paths, "DATA", tmp_path)            # sections/, codes/ 위치
    monkeypatch.setattr(paths, "ROOT", tmp_path)            # run_info의 pages_dir 기준
    monkeypatch.setattr(paths, "run_dir", lambda name: tmp_path / "runs" / name)
    return tmp_path


def raw_record(no: int, *, ok: bool = True, parsed="default", mode: str = "json_schema",
               raw_text: str | None = None) -> dict:
    parsed = copy.deepcopy(responses()[no]) if parsed == "default" else parsed
    return {"doc_id": DOC, "msds_index": 0, "section": no, "reextracted": False, "ok": ok, "parsed": parsed,
            "raw_text": raw_text if raw_text is not None else json.dumps(parsed, ensure_ascii=False),
            "mode": mode, "finish_reason": "stop", "usage": {}, "attempts": 1, "errors": [], "requests": []}


def make_run(root: Path, name: str = "r1", docs=(DOC,), pages: str = "pages", override: dict | None = None,
             skip: set[int] = frozenset()) -> Path:
    """가짜 실행 폴더. 11항은 행 형식이고 저장된 parsed가 비어 있다(옛 파서가 못 읽은 꼴).
    override[항] = raw 기록으로 그 항을 바꾸고, skip에 든 항은 raw 파일을 쓰지 않는다."""
    run = root / "runs" / name
    info = {"model_tag": "가상태그", "model": "가상/모델", "prompt_version": "s7", "pages_dir": pages}
    run.mkdir(parents=True)
    (run / "run_info.yaml").write_text(yaml.safe_dump(info, allow_unicode=True), encoding="utf-8")
    for d in docs:
        write_json(run / "outputs" / f"{d}.json", {"doc": {"doc_id": d}, "msds": []})
        for no in range(1, 17):
            if no in skip:
                continue
            if no == ROWS_SECTION:
                rec = raw_record(no, ok=False, parsed=None, mode="rows", raw_text=rows11())
            else:
                rec = raw_record(no)
            rec = {**rec, **(override or {}).get(no, {}), "doc_id": d}
            write_json(run / "raw" / f"{d}_m0_s{no:02d}.json", rec)
    return run


def gold_doc(root: Path, doc_id: str = DOC) -> dict:
    """정답: 가짜 응답 전부를 지금 코드로 펼친 문서."""
    doc = load_document(doc_id, root / "pages", root / "sections", root / "codes")
    parts = [responses()]
    parts[0][ROWS_SECTION] = parse_rows(rows11(), ROWS_SECTION)[0]
    out, _ = to_to21(manifest.get(doc_id), parts, doc.lines, "정답")
    return out


def make_gold(root: Path, docs=(DOC,)) -> Path:
    gold = root / "gold"
    for d in docs:
        write_json(gold / f"{d}.json", gold_doc(root, d))
    return gold


def files(folder: Path) -> list[str]:
    return sorted(str(p.relative_to(folder)) for p in folder.rglob("*"))


def replay_doc(rr, env: Path, run: Path) -> dict:
    return rr.replay_document(run, DOC, env / "pages", manifest.get(DOC), "가상엔진")


# ── replay_document ────────────────────────────────────

def test_rows_section_reparsed_from_raw_text(rr, env):
    """저장된 parsed가 비고 ok가 거짓이어도 raw_text의 행을 지금 파서로 다시 읽는다."""
    out = replay_doc(rr, env, make_run(env))
    m = out["msds"][0]
    assert len(m["toxicity"]) == 1 and m["toxicity"][0]["q"]["lower"] == 2000
    assert len(m["cmr"]) == 1 and m["cmr"][0]["status"] == "해당없음"


def test_rows_section_unreadable_text_is_none(rr, env):
    """행 글에 표 머리글이 없어 다시 읽은 결과가 빈 dict면 그 항은 None(응답 없음)이다."""
    bad = {ROWS_SECTION: {"raw_text": "표 없음"}}
    m = replay_doc(rr, env, make_run(env, override=bad))["msds"][0]
    assert m["toxicity"] == [] and m["cmr"] == []


def test_json_section_not_ok_is_dropped(rr, env):
    """JSON 항은 ok가 참일 때만 저장된 parsed를 쓴다."""
    ok = replay_doc(rr, env, make_run(env, "ok"))["msds"][0]
    assert len(ok["components"]) == 1 and ok["product"]["name"] == "가상 세정액 B"
    failed = {3: {"ok": False}, 1: {"ok": False}}
    m = replay_doc(rr, env, make_run(env, "failed", override=failed))["msds"][0]
    assert m["components"] == []
    assert m["product"]["name"] is None


def test_missing_raw_file_is_skipped(rr, env):
    """raw 파일이 없는 항은 넘기지 않는다. 다른 항은 그대로 펼친다."""
    m = replay_doc(rr, env, make_run(env, skip={1}))["msds"][0]
    assert m["product"]["name"] is None
    assert len(m["components"]) == 1


def test_engine_written_to_doc(rr, env):
    out = replay_doc(rr, env, make_run(env))
    assert out["doc"]["doc_id"] == DOC and out["doc"]["extraction"]["engine"] == "가상엔진"


# ── replay_run ─────────────────────────────────────────

def test_replay_run_summary(rr, env):
    run = make_run(env, docs=(DOC, NOGOLD))
    gold = make_gold(env)                                   # NOGOLD는 정답이 없어 채점하지 않는다
    s = rr.replay_run("r1", gold_dir=gold)
    assert set(s) == SUMMARY_KEYS
    assert s["run"] == "r1" and s["docs"] == 1

    pred = replay_doc(rr, env, run)
    want = score_set([(DOC, json.loads((gold / f"{DOC}.json").read_text(encoding="utf-8")), pred)])
    assert s["weighted"] == round(want["weighted"], 1)
    assert (s["must_pass"], s["must_total"]) == (want["must_passed_count"], want["must_total"])
    assert s["items"] == {i["name"]: round(i["score"] * 100, 1) for i in want["items"]}
    assert all(0 <= v <= 100 for v in s["items"].values())
    assert s["doc_weighted"] == {DOC: round(want["docs"][DOC]["weighted"], 1)}


def test_replay_run_accepts_folder_path(rr, env):
    run = make_run(env)
    s = rr.replay_run(run, gold_dir=make_gold(env))
    assert s["run"] == "r1" and s["docs"] == 1


def test_replay_run_writes_only_to_out_dir(rr, env):
    run = make_run(env)
    gold = make_gold(env)
    before = files(run)
    out = env / "replay_out"
    rr.replay_run("r1", gold_dir=gold, out_dir=out)
    assert files(run) == before
    assert files(out) == ["outputs", f"outputs/{DOC}.json"]
    doc = json.loads((out / "outputs" / f"{DOC}.json").read_text(encoding="utf-8"))
    assert doc["doc"]["extraction"]["engine"] == "가상태그:가상/모델 (replay)"
    assert len(doc["msds"][0]["toxicity"]) == 1


def test_replay_run_no_out_dir_writes_nothing(rr, env):
    make_run(env)
    gold = make_gold(env)
    before = files(env)
    rr.replay_run("r1", gold_dir=gold)
    assert files(env) == before


def test_eval_doc_refused(rr, env):
    make_run(env, docs=(DOC, EVAL))
    gold = make_gold(env, (DOC, EVAL))
    with pytest.raises(ValueError, match="평가"):
        rr.replay_run("r1", gold_dir=gold)


def test_eval_doc_refused_even_without_gold(rr, env):
    """정답이 없어도 실행 결과에 평가용 문서가 있으면 멈춘다."""
    make_run(env, docs=(DOC, EVAL))
    with pytest.raises(ValueError, match="평가"):
        rr.replay_run("r1", gold_dir=make_gold(env))


def test_pages_dir_from_run_info(rr, env):
    """--pages-dir가 없으면 run_info의 pages_dir(저장소 루트 기준)를 쓴다."""
    make_run(env, pages="pages")
    s = rr.replay_run("r1", gold_dir=make_gold(env))
    assert s["docs"] == 1


def test_pages_dir_missing_asks_for_option(rr, env):
    make_run(env, pages="data/pages/version9")              # 옮겨져서 없는 폴더
    with pytest.raises(ValueError, match="--pages-dir"):
        rr.replay_run("r1", gold_dir=make_gold(env))
    s = rr.replay_run("r1", pages_dir=env / "pages", gold_dir=make_gold(env))
    assert s["docs"] == 1


def test_no_doc_with_gold_is_error(rr, env):
    make_run(env, docs=(NOGOLD,))
    with pytest.raises(ValueError, match="채점할 문서"):
        rr.replay_run("r1", gold_dir=make_gold(env))


# ── 명령줄 ─────────────────────────────────────────────

def test_main_json_prints_only_summary(rr, env, capsys):
    make_run(env)
    gold = make_gold(env)
    rr.main(["r1", "--pages-dir", str(env / "pages"), "--gold-dir", str(gold), "--json"])
    out = capsys.readouterr().out
    s = json.loads(out)
    assert set(s) == SUMMARY_KEYS and s["docs"] == 1


def test_main_text_lists_losses(rr, env, capsys):
    run = make_run(env, override={3: {"ok": False}})
    gold = make_gold(env)
    rr.main(["r1", "--gold-dir", str(gold)])
    lines = capsys.readouterr().out.splitlines()
    pred = replay_doc(rr, env, run)
    want = score_set([(DOC, json.loads((gold / f"{DOC}.json").read_text(encoding="utf-8")), pred)])
    assert lines[0] == (f"가중 종합 {want['weighted']:.1f} · 필수 통과 "
                        f"{want['must_passed_count']}/{want['must_total']}")
    body = lines[1:]
    assert len(body) == len(want["items"])
    total = sum(WEIGHTS[i["level"]] for i in want["items"])
    losses = []
    for line in body:
        m = re.match(r"^(필수|중요|일반)\s+([\d.]+)\s+([\d.]+)\s+(.+)$", line)
        assert m, line
        item = next(i for i in want["items"] if i["name"] == m[4])
        assert m[1] == item["level"] and float(m[2]) == round(item["score"] * 100, 1)
        assert float(m[3]) == round(WEIGHTS[item["level"]] * (100 - item["score"] * 100) / total, 1)
        losses.append(WEIGHTS[item["level"]] * (1 - item["score"]))
    assert losses == sorted(losses, reverse=True) and losses[0] > 0


def test_main_eval_doc_exits(rr, env):
    make_run(env, docs=(EVAL,))
    with pytest.raises(SystemExit):
        rr.main(["r1", "--gold-dir", str(make_gold(env, (EVAL,)))])
