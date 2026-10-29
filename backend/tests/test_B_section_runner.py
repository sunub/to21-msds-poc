"""extract/section_runner.py와 scripts/run_sections.py 시험.

쪽 글자·항목 분할·manifest는 tmp_path에 만든 가짜 MSDS다 (D-43). 모델 서버와 .env를 쓰지 않는다:
call(system, user_parts, schema, schema_name, require_all)만 가진 가짜 클라이언트를 넘긴다 (ADR-007).
"""
import copy
import importlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import yaml

from msds.common import manifest
from msds.common.merge import SCHEMA_VERSION
from msds.common.paths import PAGES
from msds.common.schema import validate, validate_to21
from msds.extract import section_runner as sr
from msds.extract import section_specs as ss
from msds.extract.client import CallResult, load_model_config
from msds.extract.section_prompts import SECTION_PROMPT_VERSION, build_system, prompt_hash

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
TAG = "qwen3_30b_a3b_rngd"
DOC = "T21-X01"
RUN = "test_run"
ROWS = [
    {"doc_id": DOC, "source_file": "가상 세정액 B.pdf", "purpose": "개발", "pages": "2",
     "text_layer": "정상", "language": "ko"},
    {"doc_id": "T21-X02", "source_file": "가상 평가 문서.pdf", "purpose": "평가", "pages": "1",
     "text_layer": "정상", "language": "ko"},
    {"doc_id": "T21-X03", "source_file": "가상 개발 문서.pdf", "purpose": "개발", "pages": "1",
     "text_layer": "정상", "language": "ko"},
]

PAGE1 = """L1 물질안전보건자료
L2 1. 화학제품과 회사에 관한 정보
L3 제품명 : 가상 세정액 B
L4 제조자 : 가상화학
L5 2. 유해성·위험성
L6 유해성·위험성 분류 : 해당
L7 심한 눈 자극성 : 구분 2
L8 3. 구성성분의 명칭 및 함유량
L9 가상물질 갑 | 1234-56-6 | 10 ~ 20
L10 4. 응급조치 요령
L11 가. 눈에 들어갔을 때
L12 - 즉시 다량의 물로 씻어내시오.
"""


def page2() -> str:
    """5~16항: 항마다 제목 줄과 내용 줄 하나."""
    out = []
    for n in range(5, 17):
        a = 2 * (n - 5) + 1
        out += [f"L{a} {n}. {ss.load_specs()[n].title}", f"L{a + 1} 가상 내용 {n}"]
    return "\n".join(out) + "\n"


def spans() -> dict:
    s = {"1": ("p1:L2", "p1:L4"), "2": ("p1:L5", "p1:L7"), "3": ("p1:L8", "p1:L9"), "4": ("p1:L10", "p1:L12")}
    for n in range(5, 17):
        a = 2 * (n - 5) + 1
        s[str(n)] = (f"p2:L{a}", f"p2:L{a + 1}")
    return {k: {"start": a, "end": b, "method": "title"} for k, (a, b) in s.items()}


def empty(no: int) -> dict:
    """값이 하나도 없는 응답: 객체 칸은 lines만, 배열 칸은 []."""
    props = ss.response_schema(no)["properties"]
    return {k: ({"lines": {}} if v.get("type") == "object" else []) for k, v in props.items()}


def responses() -> dict[int, dict]:
    r = {n: empty(n) for n in range(1, 17)}
    r[1].update(product={"name": "가상 세정액 B", "lines": {"name": "p1:L3"}},
                companies=[{"role": "제조자", "name": "가상화학", "contacts": [], "line": "p1:L4"}])
    r[2]["hazard"] = {"classified": True, "lines": {"classified": "p1:L6"},
                      "classes": [{"group": "건강", "class_code": "HH_EYE_DMG", "category": "2", "line": "p1:L7"}]}
    r[3].update(composition={"type": "혼합물", "lines": {"type": "p1:L8"}},
                components=[{"name": "가상물질 갑", "cas_no": "1234-56-6",
                             "content": {"raw": "10 ~ 20", "lower_op": ">=", "lower": 10, "upper_op": "<=",
                                         "upper": 20, "unit": "%"}, "line": "p1:L9"}])
    r[4]["narratives"] = [{"item_code": ss.load_specs()[4].narrative_codes[0], "title_raw": "가. 눈에 들어갔을 때",
                           "start": "p1:L11", "end": "p1:L12"}]
    return r


def bad_line() -> dict:
    """2항 응답에 원문에 없는 줄 번호가 하나 있다."""
    r = copy.deepcopy(responses()[2])
    r["hazard"]["classes"][0]["line"] = "p9:L99"
    return r


class FakeClient:
    """항 번호마다 plan의 응답(dict 또는 예외)을 차례로 돌려주고, 다 쓰면 responses()의 응답을 돌려준다.
    fail에 든 항은 언제나 예외를 낸다."""

    def __init__(self, plan: dict[int, list] | None = None, fail: set[int] = frozenset()):
        self.plan = {k: list(v) for k, v in (plan or {}).items()}
        self.fail = fail
        self.calls: list[dict] = []
        self._lock = threading.Lock()

    def call(self, system, user_parts, schema, schema_name, require_all=True):
        no = int(schema_name.removeprefix("sec"))
        with self._lock:
            self.calls.append({"no": no, "system": system, "user": user_parts[0]["text"],
                               "schema": schema, "schema_name": schema_name, "require_all": require_all})
            out = self.plan[no].pop(0) if self.plan.get(no) else responses()[no]
        if no in self.fail:
            raise ConnectionError("가짜 연결 오류")
        if isinstance(out, Exception):
            raise out
        return CallResult(out, json.dumps(out, ensure_ascii=False), "json_schema", "stop",
                          {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110},
                          0.01, "fake-model", 1, [])

    def calls_for(self, no: int) -> list[dict]:
        return [c for c in self.calls if c["no"] == no]


@pytest.fixture
def env(tmp_path, monkeypatch):
    """tmp_path에 가짜 쪽 글자·항목 분할·manifest를 만든다. 저장소의 data/·runs/는 건드리지 않는다."""
    pages = tmp_path / "pages" / DOC
    pages.mkdir(parents=True)
    (pages / "p001.txt").write_text(PAGE1, encoding="utf-8")
    (pages / "p002.txt").write_text(page2(), encoding="utf-8")
    sections = tmp_path / "sections"
    sections.mkdir()
    (sections / f"{DOC}.json").write_text(json.dumps({"msds": [{"pages": [1, 2], "sections": spans()}]}),
                                          encoding="utf-8")
    path = tmp_path / "manifest.csv"
    manifest.save(ROWS, path)
    orig = manifest.load
    monkeypatch.setattr(manifest, "load", lambda p=path: orig(p))
    return tmp_path


def run(env: Path, client, **kw) -> dict:
    return sr.run_document(DOC, TAG, RUN, client, pages_dir=env / "pages", sections_dir=env / "sections",
                           codes_dir=env / "codes", runs_dir=env / "runs", **kw)


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def timing(env: Path) -> list[dict]:
    text = (env / "runs" / RUN / "timing.jsonl").read_text(encoding="utf-8")
    return [json.loads(x) for x in text.splitlines()]


def checks(env: Path) -> dict:
    return read_json(env / "runs" / RUN / "checks" / f"{DOC}.json")


def section_check(env: Path, no: int) -> dict:
    return next(s for s in checks(env)["sections"] if s["section"] == no)


# ── 시험 입력 ──────────────────────────────────────────

@pytest.mark.parametrize("no", range(1, 17))
def test_fake_responses_follow_section_schema(no):
    """가짜 응답이 실제 중간 형식(response_schema)에 맞아야 시험이 의미가 있다."""
    assert validate(responses()[no], ss.response_schema(no)) == []


# ── check_section ──────────────────────────────────────

def test_check_section_finds_unknown_line_ids():
    parsed = {
        "meta": {"lines": {"name": "p1:L3", "msds_no": None, "doc_code": "p9:L1"}},
        "companies": [{"line": "p1:L4", "contacts": [{"line": "p0:L0"}]}],
        "narratives": [{"item_code": "X", "start": "p1:L11", "end": "p8:L1"}],
        "toxicity": [{"line": 22}],
        "extras": [],
    }
    assert sr.check_section(parsed, {"p1:L3", "p1:L4", "p1:L11"}) == [
        "meta.lines.doc_code: 원문에 없는 줄 번호 p9:L1",
        "companies[0].contacts[0].line: 원문에 없는 줄 번호 p0:L0",
        "narratives[0].end: 원문에 없는 줄 번호 p8:L1",
        "toxicity[0].line: 원문에 없는 줄 번호 22",
    ]


def test_check_section_ok_and_none():
    assert sr.check_section(responses()[2], {"p1:L6", "p1:L7"}) == []
    assert sr.check_section(None, set()) == []


# ── 문서 하나 끝까지 ───────────────────────────────────

def test_end_to_end_writes_all_files(env):
    run_path = env / "runs" / RUN
    sr.save_run_info(run_path, TAG)
    client = FakeClient()
    summary = run(env, client)

    assert summary["doc_id"] == DOC
    assert (summary["sections_ok"], summary["sections_failed"], summary["reextracted"]) == (16, 0, 0)
    assert summary["schema_errors"] == 0
    assert summary["warnings"] == []

    out = read_json(run_path / "outputs" / f"{DOC}.json")
    assert validate_to21(out) == []
    assert out["doc"]["doc_id"] == DOC and out["doc"]["source_file"] == "가상 세정액 B.pdf"
    model = load_model_config(TAG)["model"]
    assert out["doc"]["extraction"]["engine"] == f"{TAG}:{model}"
    m = out["msds"][0]
    assert m["product"]["name"] == "가상 세정액 B"
    assert m["components"][0]["cas_no"] == "1234-56-6"
    assert m["narratives"][0]["statements"][0]["text"] == "- 즉시 다량의 물로 씻어내시오."

    c = checks(env)
    assert set(c) == {"sections", "schema_errors", "to21_validator", "expand_problems", "warnings", "needs_review"}
    assert [(s["msds_index"], s["section"]) for s in c["sections"]] == [(0, n) for n in range(1, 17)]
    assert all(s["ok"] and s["errors"] == [] and s["check_problems"] == [] and not s["reextracted"]
               for s in c["sections"])
    assert c["schema_errors"] == [] and c["expand_problems"] == [] and c["needs_review"] == []
    assert isinstance(c["to21_validator"], list)

    raws = sorted(p.name for p in (run_path / "raw").iterdir())
    assert raws == [f"{DOC}_m0_s{n:02d}.json" for n in range(1, 17)]
    raw = read_json(run_path / "raw" / f"{DOC}_m0_s03.json")
    assert raw["parsed"] == responses()[3]
    assert raw["mode"] == "json_schema" and raw["finish_reason"] == "stop" and raw["attempts"] == 1
    assert raw["usage"]["prompt_tokens"] == 100 and raw["errors"] == []
    assert "first_attempt" not in raw

    assert (run_path / "timing.jsonl").exists()
    assert (run_path / "run_info.yaml").exists()


def test_calls_one_section_each_with_its_lines(env):
    client = FakeClient()
    run(env, client)
    assert sorted(c["schema_name"] for c in client.calls) == [f"sec{n:02d}" for n in range(1, 17)]
    sec3 = client.calls_for(3)[0]
    assert sec3["system"] == build_system(3)
    assert sec3["schema"] == ss.response_schema(3)
    assert sec3["user"] == "[3항 원문]\np1:L8 3. 구성성분의 명칭 및 함유량\np1:L9 가상물질 갑 | 1234-56-6 | 10 ~ 20"
    assert all("[다시 확인할 점]" not in c["user"] for c in client.calls)


def test_all_calls_send_require_all_false(env):
    """항목별 경로는 서버 스키마의 필수 칸을 줄여 보낸다. 재추출 호출도 같다 (ADR-017)."""
    client = FakeClient(plan={2: [bad_line()], 5: [TimeoutError("가짜 시간 초과")]})
    run(env, client)
    assert len(client.calls) == 18
    assert [c["require_all"] for c in client.calls] == [False] * 18


def test_bad_line_is_reextracted_once(env):
    client = FakeClient(plan={2: [bad_line()]})
    summary = run(env, client)
    calls = client.calls_for(2)
    assert len(calls) == 2
    assert "[다시 확인할 점]" not in calls[0]["user"]
    assert "[다시 확인할 점]" in calls[1]["user"]
    assert "p9:L99" in calls[1]["user"]
    assert summary["reextracted"] == 1

    s = section_check(env, 2)
    assert s["reextracted"] is True and s["ok"] is True and s["check_problems"] == []
    raw = read_json(env / "runs" / RUN / "raw" / f"{DOC}_m0_s02.json")
    assert raw["parsed"] == responses()[2]
    assert raw["first_attempt"]["parsed"] == bad_line()
    assert raw["first_attempt"]["check_problems"] == ["hazard.classes[0].line: 원문에 없는 줄 번호 p9:L99"]
    rows = [t for t in timing(env) if t["stage"] == "reextract"]
    assert [(t["msds_index"], t["section"]) for t in rows] == [(0, 2)]


def test_reextract_not_better_keeps_first(env):
    """재추출도 같은 문제면 첫 결과를 쓰고, 값은 남기고 사람 검토로 표시한다."""
    client = FakeClient(plan={2: [bad_line(), bad_line()]})
    summary = run(env, client)
    assert len(client.calls_for(2)) == 2
    assert summary["reextracted"] == 0 and summary["sections_failed"] == 0
    s = section_check(env, 2)
    assert s["reextracted"] is False and s["ok"] is True
    assert s["check_problems"] == ["hazard.classes[0].line: 원문에 없는 줄 번호 p9:L99"]
    c = checks(env)
    assert c["needs_review"] == [{"msds_index": 0, "section": 2}]
    out = read_json(env / "runs" / RUN / "outputs" / f"{DOC}.json")
    assert out["msds"][0]["hazard"]["classes"][0]["class_code"] == "HH_EYE_DMG"
    raw = read_json(env / "runs" / RUN / "raw" / f"{DOC}_m0_s02.json")
    assert raw["reextract_attempt"]["parsed"] == bad_line()


def test_failed_call_is_retried_and_replaced(env):
    client = FakeClient(plan={5: [TimeoutError("가짜 시간 초과")]})
    summary = run(env, client)
    assert len(client.calls_for(5)) == 2
    assert "가짜 시간 초과" in client.calls_for(5)[1]["user"]
    assert summary["sections_failed"] == 0 and summary["reextracted"] == 1
    assert section_check(env, 5)["ok"] is True
    raw = read_json(env / "runs" / RUN / "raw" / f"{DOC}_m0_s05.json")
    assert raw["first_attempt"]["requests"] == []


def test_raw_keeps_requests(env):
    """client의 요청 기록이 raw/에 그대로 남는다. 출력 한도에 걸린 앞 요청도 보인다."""
    reqs = [{"mode": "json_schema", "finish_reason": "length", "usage": {"completion_tokens": 8192}},
            {"mode": "json_schema_compact", "finish_reason": "stop", "usage": {"completion_tokens": 57}}]

    class Client(FakeClient):
        def call(self, system, user_parts, schema, schema_name, require_all=True):
            r = super().call(system, user_parts, schema, schema_name, require_all)
            if schema_name == "sec03":
                r.requests = reqs
            return r

    run(env, Client())
    assert read_json(env / "runs" / RUN / "raw" / f"{DOC}_m0_s03.json")["requests"] == reqs
    assert read_json(env / "runs" / RUN / "raw" / f"{DOC}_m0_s04.json")["requests"] == []


def test_exception_section_fails_others_remain(env):
    client = FakeClient(fail={3})
    summary = run(env, client)
    assert len(client.calls_for(3)) == 2          # 한 번만 다시 보낸다
    assert summary["sections_failed"] == 1 and summary["sections_ok"] == 15

    s = section_check(env, 3)
    assert s["ok"] is False and s["reextracted"] is False
    assert any("가짜 연결 오류" in e for e in s["errors"])
    c = checks(env)
    assert {"msds_index": 0, "section": 3} in c["needs_review"]
    assert any(p["section"] == 3 and p["kind"] == "missing_section" for p in c["expand_problems"])

    out = read_json(env / "runs" / RUN / "outputs" / f"{DOC}.json")
    assert validate_to21(out) == []
    assert out["msds"][0]["product"]["name"] == "가상 세정액 B"
    assert out["msds"][0]["components"] == []
    assert len(list((env / "runs" / RUN / "raw").iterdir())) == 16


def test_timing_rows(env):
    run(env, FakeClient(plan={2: [bad_line()]}))
    rows = timing(env)
    keys = {"doc_id", "stage", "msds_index", "section", "seconds", "prompt_tokens", "completion_tokens"}
    assert all(set(r) == keys and r["doc_id"] == DOC for r in rows)
    stages = [r["stage"] for r in rows]
    assert stages.count("total") == 1
    assert stages.count("call") == 16
    assert stages.count("reextract") == 1
    assert stages.count("inputs") == stages.count("expand") == stages.count("checks") == 1
    calls = [r for r in rows if r["stage"] == "call"]
    assert sorted(r["section"] for r in calls) == list(range(1, 17))
    assert all(r["prompt_tokens"] == 100 and r["completion_tokens"] == 10 for r in calls)


def test_over_time_limit_warns(env, monkeypatch):
    monkeypatch.setattr(sr, "DOC_TIME_LIMIT", 0)
    summary = run(env, FakeClient())
    assert any("5분 초과" in w for w in summary["warnings"])
    assert any("5분 초과" in w for w in checks(env)["warnings"])


def test_no_sections_file_warns(env):
    (env / "sections" / f"{DOC}.json").unlink()
    client = FakeClient()
    run(env, client)
    assert "항목 분할 파일 없음: 대체 경로" in checks(env)["warnings"]
    # 대체 경로: 항마다 MSDS 전체 줄이 들어간다
    assert "p2:L24" in client.calls_for(1)[0]["user"]


def test_workers_default_from_config(env, monkeypatch):
    seen = []

    class Pool(ThreadPoolExecutor):
        def __init__(self, max_workers=None, **kw):
            seen.append(max_workers)
            super().__init__(max_workers=max_workers, **kw)

    monkeypatch.setattr(sr, "ThreadPoolExecutor", Pool)
    run(env, FakeClient())
    run(env, FakeClient(), max_workers=3)
    assert seen == [load_model_config(TAG)["concurrency"], 3]


# ── 실행 기록과 명세서 내용 (D-47) ─────────────────────

def test_save_run_info(tmp_path, monkeypatch):
    cfg = load_model_config(TAG)
    monkeypatch.setenv(cfg["base_url_env"], "http://secret-host.invalid:9999/v1")
    monkeypatch.setenv(cfg["api_key_env"], "sk-secret-test-key")
    sr.save_run_info(tmp_path / "r", TAG)
    text = (tmp_path / "r" / "run_info.yaml").read_text(encoding="utf-8")
    info = yaml.safe_load(text)
    assert info["model_tag"] == TAG and info["model"] == cfg["model"]
    assert info["prompt_version"] == SECTION_PROMPT_VERSION
    assert info["prompt_hashes"] == {n: prompt_hash(n) for n in range(1, 17)}
    assert info["schema_version"] == SCHEMA_VERSION
    assert info["started_at"].endswith("+09:00")
    assert info["git_commit"] is None or isinstance(info["git_commit"], str)
    assert info["pages_dir"] == "data/pages"
    for secret in ("secret-host", "sk-secret", cfg["base_url_env"], cfg["api_key_env"]):
        assert secret not in text


def test_save_run_info_pages_dir(tmp_path):
    """쪽 글자 폴더를 바꿔 돌렸으면 저장소 기준 상대 경로로 남긴다 (절대 경로의 사용자 이름을 남기지 않는다)."""
    sr.save_run_info(tmp_path / "r", TAG, pages_dir=PAGES / "chars_wrap")
    info = yaml.safe_load((tmp_path / "r" / "run_info.yaml").read_text(encoding="utf-8"))
    assert info["pages_dir"] == "data/pages/chars_wrap"


def test_save_run_info_concurrency_default(tmp_path):
    sr.save_run_info(tmp_path / "r", TAG)
    info = yaml.safe_load((tmp_path / "r" / "run_info.yaml").read_text(encoding="utf-8"))
    assert info["concurrency"] == load_model_config(TAG)["concurrency"]


def test_save_run_info_concurrency_max_workers(tmp_path):
    sr.save_run_info(tmp_path / "r", TAG, max_workers=1)
    info = yaml.safe_load((tmp_path / "r" / "run_info.yaml").read_text(encoding="utf-8"))
    assert info["concurrency"] == 1


def test_workers_concurrency_fallback():
    assert sr.workers({"concurrency": 8}, 3) == 3
    assert sr.workers({"concurrency": 8}) == 8
    assert sr.workers({}) == 16


def test_no_system_prompt_or_schema_in_run_files(env):
    run_path = env / "runs" / RUN
    sr.save_run_info(run_path, TAG)
    run(env, FakeClient(plan={2: [bad_line()]}, fail={3}))
    files = [run_path / "run_info.yaml", *sorted((run_path / "raw").iterdir())]
    assert len(files) == 17
    needles = []
    for n in range(1, 17):
        head = build_system(n)[:50]
        needles += [head, json.dumps(head, ensure_ascii=False)[1:-1]]   # JSON 안에서는 따옴표가 \"로 바뀐다
    for f in files:
        text = f.read_text(encoding="utf-8")
        assert not [x for x in needles if x in text], f.name
        assert "$defs" not in text, f.name


# ── scripts/run_sections.py ────────────────────────────

@pytest.fixture
def script(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    return importlib.import_module("run_sections")


def test_select_docs_rejects_eval(env, script):
    with pytest.raises(ValueError, match="T21-X02"):
        script.select_docs([DOC, "T21-X02"], None, False)
    assert [r["doc_id"] for r in script.select_docs([DOC, "T21-X02"], None, True)] == [DOC, "T21-X02"]


def test_select_docs_by_purpose(env, script):
    assert [r["doc_id"] for r in script.select_docs(None, "개발", False)] == [DOC, "T21-X03"]
    with pytest.raises(ValueError):
        script.select_docs(None, None, False)          # 평가용이 섞인 전체 목록
    with pytest.raises(KeyError):
        script.select_docs(["T21-NONE"], None, False)
