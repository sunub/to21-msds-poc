"""scripts/b_app_journey.py 시험 (첫 사용 기록 journey v2, ADR-028, STRUCTURE '저장 형태 — journey v2').

기록 파일은 tmp_path에만 쓴다. 저장소의 runs/manual/journey.json은 읽거나 쓰지 않는다.
두 탭 동시 저장과 다시 보기는 b_app.route("PUT", "/api/journey")로 부른다. 서버 소켓은 열지 않는다.
"""
import copy
import importlib
import json
import threading
import time

import pytest

from test_B_compare_models import SCRIPTS

T0 = "2026-10-31T00:55:00.000Z"
T1 = "2026-10-31T00:58:00.000Z"
T2 = "2026-10-31T01:02:00.000Z"
JOB_A = "20261031_095500_try_a1b2c3"
JOB_B = "20261031_100200_try_d4e5f6"


@pytest.fixture
def bjn(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    return importlib.import_module("b_app_journey")


@pytest.fixture
def app(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    return importlib.import_module("b_app")


@pytest.fixture
def jfile(tmp_path):
    return tmp_path / "runs" / "manual" / "journey.json"


@pytest.fixture
def jctx(app, tmp_path, jfile):
    return app.AppContext(runs_dir=tmp_path / "runs", gold_dir=tmp_path / "gold", pages_dir=tmp_path / "pages",
                          cache_dir=None, journey_file=jfile)


def blank() -> dict:
    return {"version": 2,
            "progress": {"active": None, "dismissed_at": None,
                         "t1": {"state": "not_started", "step": 0, "updated_at": None},
                         "t2": {"state": "not_started", "step": 0, "updated_at": None}},
            "outcomes": {"t1": {"real": None}, "t2": {"real": None, "practice": None}},
            "pending": None, "migrated_from": None}


def won(first: str, last: str, count: int, job: str | None = None, *, t2: bool = True) -> dict:
    o = {"first_at": first, "last_at": last, "count": count}
    return {**o, "last_job": job} if t2 else o


def example() -> dict:
    """STRUCTURE의 v2 예시와 같은 모양."""
    j = blank()
    j["progress"] = {"active": "t2", "dismissed_at": None,
                     "t1": {"state": "completed", "step": 3, "updated_at": T1},
                     "t2": {"state": "in_progress", "step": 1, "updated_at": T2}}
    j["outcomes"]["t1"]["real"] = won(T1, T1, 1, t2=False)
    j["outcomes"]["t2"]["practice"] = won(T0, T0, 1, JOB_A)
    return j


def guide() -> dict:
    """처음 사용 안내(Wispr 구조, 승인 10/31)의 진행. progress.guide는 선택 칸이다."""
    return {"state": "in_progress", "screen": "G07", "choices": ["score", "retest"], "skipped": ["p2"],
            "updated_at": T2}


def write(path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False), encoding="utf-8")


def put(app, ctx, journey):
    code, ctype, body = app.route("PUT", "/api/journey", {}, json.dumps({"journey": journey}).encode(), ctx)
    assert ctype.startswith("application/json")
    return code, json.loads(body)


def has_hangul(s: str) -> bool:
    return any("가" <= ch <= "힣" for ch in s)


# ── 기본값과 읽기 ───────────────────────────────────────

def test_default_is_v2_blank(bjn):
    assert bjn.default() == blank()
    a, b = bjn.default(), bjn.default()
    a["outcomes"]["t1"]["real"] = won(T0, T0, 1, t2=False)
    assert b == blank()                                   # 부를 때마다 새 dict


def test_load_missing_file_gives_default_and_creates_nothing(bjn, jfile):
    assert bjn.load(jfile) == (blank(), [])
    assert not jfile.exists() and not jfile.parent.exists()


def test_load_keeps_other_parts_when_progress_is_broken(bjn, jfile):
    stored = example()
    stored["progress"]["t1"]["step"] = 9                  # 갈래 1은 0~3
    write(jfile, stored)
    before = jfile.read_bytes()
    journey, problems = bjn.load(jfile)
    assert [p["part"] for p in problems] == ["progress"]
    assert set(problems[0]) == {"part", "message"} and has_hangul(problems[0]["message"])
    assert journey["progress"] == blank()["progress"]
    assert journey["outcomes"] == example()["outcomes"]   # 성공 기록은 남는다
    assert jfile.read_bytes() == before                   # 읽기는 파일을 고치지 않는다


def test_load_each_broken_part_is_reported_alone(bjn, jfile):
    stored = example()
    stored["outcomes"]["t2"]["practice"]["count"] = 0
    stored["pending"] = {"attempt": "a1", "job": None, "mode": "기타", "started_at": T0}
    write(jfile, stored)
    journey, problems = bjn.load(jfile)
    assert [p["part"] for p in problems] == ["outcomes", "pending"]
    assert journey["progress"] == example()["progress"]
    assert journey["outcomes"] == blank()["outcomes"] and journey["pending"] is None


@pytest.mark.parametrize("text", ["{깨진 JSON", "[1, 2]", json.dumps({**blank(), "version": 1})])
def test_load_broken_file_is_file_problem(bjn, jfile, text):
    write(jfile, text)
    journey, problems = bjn.load(jfile)
    assert journey == blank()
    assert [p["part"] for p in problems] == ["file"] and has_hangul(problems[0]["message"])


# ── 검사 ───────────────────────────────────────────────

def test_validate_accepts_structure_example_and_limits(bjn):
    assert bjn.validate(example()) == example()
    j = example()
    j["progress"]["t2"]["step"] = 4                       # 갈래 2는 0~4
    j["pending"] = {"attempt": "4f1c-9a", "job": None, "mode": "practice", "started_at": T2}
    j["migrated_from"] = 1
    j["outcomes"]["t2"]["real"] = won(T1, T2, 64, "x" * 64)
    assert bjn.validate(j) == j


def _broken(change):
    j = example()
    change(j)
    return j


BAD = {
    "문서 번호 칸": lambda j: j.update(doc_id="T21-X01"),
    "성공 기록 안의 값 칸": lambda j: j["outcomes"]["t1"]["real"].update(value="가짜 값"),
    "판정 전 시도의 경로 칸": lambda j: j.update(pending={"attempt": "a", "job": None, "mode": "real",
                                                   "started_at": T0, "path": "/tmp/x"}),
    "형식 번호 1": lambda j: j.update(version=1),
    "형식 번호 참거짓": lambda j: j.update(version=True),
    "빠진 칸": lambda j: j["progress"].pop("t2"),
    "밀리초 없는 시각": lambda j: j["progress"]["t1"].update(updated_at="2026-10-31T00:58:00Z"),
    "시간대 붙은 시각": lambda j: j["outcomes"]["t1"]["real"].update(first_at="2026-10-31T09:58:00.000+09:00"),
    "횟수 0": lambda j: j["outcomes"]["t2"]["practice"].update(count=0),
    "횟수 참거짓": lambda j: j["outcomes"]["t2"]["practice"].update(count=True),
    "횟수 소수": lambda j: j["outcomes"]["t2"]["practice"].update(count=1.5),
    "갈래 1 단계 4": lambda j: j["progress"]["t1"].update(step=4),
    "갈래 2 단계 5": lambda j: j["progress"]["t2"].update(step=5),
    "음수 단계": lambda j: j["progress"]["t2"].update(step=-1),
    "모르는 상태": lambda j: j["progress"]["t1"].update(state="done"),
    "모르는 갈래": lambda j: j["progress"].update(active="t3"),
    "모르는 방식": lambda j: j.update(pending={"attempt": "a", "job": None, "mode": "dry", "started_at": T0}),
    "빈칸 든 작업 번호": lambda j: j["outcomes"]["t2"]["practice"].update(last_job="job 1"),
    "한글 작업 번호": lambda j: j["outcomes"]["t2"]["practice"].update(last_job="작업1"),
    "65자 작업 번호": lambda j: j["outcomes"]["t2"]["practice"].update(last_job="x" * 65),
    "갈래 1 성공의 작업 번호": lambda j: j["outcomes"]["t1"]["real"].update(last_job=JOB_A),
    "옮김 표시 2": lambda j: j.update(migrated_from=2),
    "안내 화면 G18": lambda j: j["progress"].update(guide={**guide(), "screen": "G18"}),
    "안내 화면 G00": lambda j: j["progress"].update(guide={**guide(), "screen": "G00"}),
    "안내 화면 장면 이름": lambda j: j["progress"].update(guide={**guide(), "screen": "G07-success"}),
    "안내 선택 모르는 값": lambda j: j["progress"].update(guide={**guide(), "choices": ["score", "docs"]}),
    "안내 선택 겹침": lambda j: j["progress"].update(guide={**guide(), "choices": ["score", "score"]}),
    "안내 선택 목록 아님": lambda j: j["progress"].update(guide={**guide(), "choices": "score"}),
    "건너뛴 직접 해 보기 p4": lambda j: j["progress"].update(guide={**guide(), "skipped": ["p4"]}),
    "안내 상태 모르는 값": lambda j: j["progress"].update(guide={**guide(), "state": "done"}),
    "안내 진행 안의 문서 번호": lambda j: j["progress"].update(guide={**guide(), "doc_id": "T21-X01"}),
    "안내 진행 빠진 칸": lambda j: j["progress"].update(guide={k: v for k, v in guide().items() if k != "skipped"}),
}


@pytest.mark.parametrize("name", list(BAD))
def test_validate_rejects_in_korean(bjn, name):
    with pytest.raises(ValueError) as e:
        bjn.validate(_broken(BAD[name]))
    assert has_hangul(str(e.value))


@pytest.mark.parametrize("obj", [None, [], "기록", 2])
def test_validate_rejects_non_object(bjn, obj):
    with pytest.raises(ValueError):
        bjn.validate(obj)


# ── 합치기 ─────────────────────────────────────────────

def test_merge_keeps_outcomes_when_incoming_is_empty(bjn):
    stored = example()
    stored["outcomes"]["t2"]["real"] = won(T1, T2, 2, JOB_B)
    merged = bjn.merge(stored, blank())
    assert merged["outcomes"] == stored["outcomes"]


def test_merge_does_not_lower_count_or_move_first_at_later(bjn):
    stored = blank()
    stored["outcomes"]["t1"]["real"] = won(T0, T2, 3, t2=False)
    stored["outcomes"]["t2"]["practice"] = won(T0, T2, 3, JOB_B)
    incoming = blank()
    incoming["outcomes"]["t1"]["real"] = won(T1, T1, 1, t2=False)
    incoming["outcomes"]["t2"]["practice"] = won(T1, T1, 1, JOB_A)
    keep = copy.deepcopy((stored, incoming))
    merged = bjn.merge(stored, incoming)
    assert merged["outcomes"]["t1"]["real"] == won(T0, T2, 3, t2=False)
    assert merged["outcomes"]["t2"]["practice"] == won(T0, T2, 3, JOB_B)   # 늦은 쪽(저장된 쪽)의 작업 번호
    assert (stored, incoming) == keep                                      # 받은 dict는 바꾸지 않는다


def test_merge_takes_later_last_at_and_its_job(bjn):
    stored = blank()
    stored["outcomes"]["t2"]["real"] = won(T1, T1, 2, JOB_A)
    incoming = blank()
    incoming["outcomes"]["t2"]["real"] = won(T0, T2, 1, JOB_B)
    assert bjn.merge(stored, incoming)["outcomes"]["t2"]["real"] == won(T0, T2, 2, JOB_B)
    fresh = bjn.merge(blank(), incoming)                                   # 저장된 기록이 없으면 들어온 값
    assert fresh["outcomes"]["t2"]["real"] == won(T0, T2, 1, JOB_B)


def test_merge_replaces_progress_and_pending_and_keeps_migrated(bjn):
    stored = example()
    stored["migrated_from"] = 1
    stored["pending"] = {"attempt": "a1", "job": JOB_A, "mode": "real", "started_at": T0}
    incoming = blank()
    merged = bjn.merge(stored, incoming)
    assert merged["progress"] == blank()["progress"] and merged["pending"] is None
    assert merged["migrated_from"] == 1 and merged["version"] == 2
    assert bjn.merge(blank(), {**blank(), "migrated_from": 1})["migrated_from"] == 1


def test_guide_progress_is_optional_and_checked(bjn, jfile):
    """progress.guide는 없어도 된다(지금까지의 기록). 있으면 화면 G01~G17, 고른 것·건너뛴 것은 정해진 이름만."""
    assert "guide" not in bjn.default()["progress"]                      # 기본값은 지금 모양 그대로
    assert bjn.validate(example()) == example()
    j = example()
    j["progress"]["guide"] = guide()
    assert bjn.validate(j) == j
    for screen in ("G01", "G10", "G15", "G16", "G17", None):
        j["progress"]["guide"] = {**guide(), "screen": screen}
        assert bjn.validate(j) == j, screen
    j["progress"]["guide"] = {"state": "not_started", "screen": None, "choices": [], "skipped": [], "updated_at": None}
    assert bjn.validate(j) == j
    j["progress"]["guide"] = {**guide(), "choices": ["score", "source", "retest", "ai"], "skipped": ["p1", "p2", "p3"]}
    assert bjn.validate(j) == j
    write(jfile, j)
    assert bjn.load(jfile) == (j, [])                                    # 읽을 때도 그대로 남는다


def test_broken_guide_resets_progress_only(bjn, jfile):
    j = example()
    j["progress"]["guide"] = {**guide(), "screen": "G99"}
    write(jfile, j)
    journey, problems = bjn.load(jfile)
    assert [p["part"] for p in problems] == ["progress"]
    assert journey["progress"] == blank()["progress"] and journey["outcomes"] == example()["outcomes"]


def test_merge_takes_incoming_guide(bjn):
    stored, incoming = example(), example()
    stored["progress"]["guide"] = guide()
    incoming["progress"]["guide"] = {**guide(), "screen": "G11", "skipped": []}
    assert bjn.merge(stored, incoming)["progress"]["guide"] == incoming["progress"]["guide"]
    assert "guide" not in bjn.merge(stored, example())["progress"]      # 진행은 마지막 PUT이 이긴다


# ── 저장 ───────────────────────────────────────────────

def test_put_and_get_keep_guide_progress(app, jctx, jfile):
    j = example()
    j["progress"]["guide"] = guide()
    code, data = put(app, jctx, j)
    assert code == 200 and data["journey"]["progress"]["guide"] == guide()
    code, _, body = app.route("GET", "/api/journey", {}, None, jctx)
    assert code == 200 and json.loads(body)["journey"]["progress"]["guide"] == guide()


def test_save_writes_whole_file_and_leaves_no_temp(bjn, jfile):
    bjn.save(jfile, example())                           # 폴더가 없으면 만든다
    assert list(jfile.parent.iterdir()) == [jfile]
    assert json.loads(jfile.read_text(encoding="utf-8")) == example()
    assert bjn.load(jfile) == (example(), [])
    bjn.save(jfile, blank())                             # 있는 파일을 바꿔 쓴다
    assert list(jfile.parent.iterdir()) == [jfile] and bjn.load(jfile) == (blank(), [])


def test_save_failure_keeps_old_file_and_no_temp(bjn, jfile, monkeypatch):
    bjn.save(jfile, example())
    before = jfile.read_bytes()

    def broken(*a):
        raise OSError("가짜 쓰기 실패")
    monkeypatch.setattr(bjn.os, "replace", broken)
    with pytest.raises(OSError):
        bjn.save(jfile, blank())
    assert jfile.read_bytes() == before and list(jfile.parent.iterdir()) == [jfile]


# ── 길(route)로 부르기 ──────────────────────────────────

def test_two_tabs_put_at_once_keep_both(app, jctx, jfile, monkeypatch):
    real_load = app.bjn.load

    def slow_load(path):                                  # 잠금이 없으면 두 요청이 같은 빈 기록을 읽는다
        got = real_load(path)
        time.sleep(0.05)
        return got
    monkeypatch.setattr(app.bjn, "load", slow_load)
    tab1, tab2 = blank(), blank()
    tab1["outcomes"]["t1"]["real"] = won(T1, T1, 1, t2=False)
    tab2["outcomes"]["t2"]["practice"] = won(T0, T0, 1, JOB_A)
    gate, codes = threading.Barrier(2), []

    def send(j):
        gate.wait()
        codes.append(put(app, jctx, j)[0])
    threads = [threading.Thread(target=send, args=(j,)) for j in (tab1, tab2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert codes == [200, 200]
    outcomes = json.loads(jfile.read_text(encoding="utf-8"))["outcomes"]
    assert outcomes["t1"]["real"] == won(T1, T1, 1, t2=False)
    assert outcomes["t2"]["practice"] == won(T0, T0, 1, JOB_A)


def test_replay_put_changes_progress_only(app, jctx, jfile):
    first = example()
    first["outcomes"]["t2"]["real"] = won(T1, T2, 1, JOB_B)
    first["pending"] = {"attempt": "a1", "job": JOB_B, "mode": "real", "started_at": T1}
    assert put(app, jctx, first)[0] == 200
    replay = blank()                                      # 다시 보기: 진행·판정 전 시도만 처음으로, 성공 기록은 비워 보냄
    code, data = put(app, jctx, replay)
    assert code == 200 and data["problems"] == []
    assert data["journey"]["outcomes"] == first["outcomes"]
    assert data["journey"]["progress"] == blank()["progress"] and data["journey"]["pending"] is None
    assert json.loads(jfile.read_text(encoding="utf-8")) == data["journey"]
