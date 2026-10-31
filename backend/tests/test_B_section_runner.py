"""extract/section_runner.py와 scripts/run_sections.py 시험.

쪽 글자·항목 분할·manifest는 tmp_path에 만든 가짜 MSDS다 (D-43). 모델 서버와 .env를 쓰지 않는다:
call(system, user_parts, schema, schema_name, require_all)과 call_text(system, user_parts)만 가진
가짜 클라이언트를 넘긴다 (ADR-007).
"""
import base64
import copy
import importlib
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pymupdf
import pytest
import yaml

from msds.common import manifest
from msds.common.merge import SCHEMA_VERSION
from msds.common.paths import PAGES
from msds.common.schema import validate, validate_to21
from msds.extract import pictogram_check as pc
from msds.extract import rows as rw
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


def rows11(tox_line: str = "p2:L14", extra: str = "") -> str:
    """11항 행 글: 독성 1행, 발암성 해당없음 1행. 줄은 가짜 문서의 11항 내용 줄(p2:L14). extra는 cmr 표 끝에 붙인다."""
    t = rw.row_tables(11)
    comp = {"comp_name": "가상물질 갑", "comp_cas": "1234-56-6"}
    tox = {**comp, "endpoint": "TX_ORAL", "descriptor": "LD50", "q": "> 2000 mg/kg", "species": "랫드",
           "status": "값있음", "line": tox_line}
    cmr = {**comp, "hazard": "발암성", "agency": "IARC", "status": "해당없음", "line": "p2:L14"}
    out = []
    for name, r in (("toxicity", tox), ("cmr", cmr)):
        out += [f"### {name}", " | ".join(t[name]), " | ".join(r.get(c, "") for c in t[name])]
    return "\n".join(out + ([extra] if extra else []))


def bad_line() -> dict:
    """2항 응답에 원문에 없는 줄 번호가 하나 있다."""
    r = copy.deepcopy(responses()[2])
    r["hazard"]["classes"][0]["line"] = "p9:L99"
    return r


class FakeClient:
    """항 번호마다 plan의 응답(dict, 행 글 또는 예외)을 차례로 돌려주고, 다 쓰면 responses()의 응답을 돌려준다.
    call_text(행 형식)는 다 쓰면 11항이면 rows11()을 돌려준다. fail에 든 항은 언제나 예외를 낸다."""

    def __init__(self, plan: dict[int, list] | None = None, fail: set[int] = frozenset()):
        self.plan = {k: list(v) for k, v in (plan or {}).items()}
        self.fail = fail
        self.calls: list[dict] = []
        self._lock = threading.Lock()

    def call(self, system, user_parts, schema, schema_name, require_all=True):
        no = int(schema_name.removeprefix("sec"))
        with self._lock:
            self.calls.append({"no": no, "method": "call", "system": system, "user": user_parts[0]["text"],
                               "parts": user_parts, "schema": schema, "schema_name": schema_name,
                               "require_all": require_all})
            out = self.plan[no].pop(0) if self.plan.get(no) else responses()[no]
        if no in self.fail:
            raise ConnectionError("가짜 연결 오류")
        if isinstance(out, Exception):
            raise out
        return CallResult(out, json.dumps(out, ensure_ascii=False), "json_schema", "stop",
                          {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110},
                          0.01, "fake-model", 1, [])

    def call_text(self, system, user_parts, max_tokens=None):
        no = int(re.match(r"\[(\d+)항 원문\]", user_parts[0]["text"]).group(1))
        with self._lock:
            self.calls.append({"no": no, "method": "call_text", "system": system, "user": user_parts[0]["text"],
                               "parts": user_parts, "max_tokens": max_tokens})
            out = self.plan[no].pop(0) if self.plan.get(no) else rows11()
        if no in self.fail:
            raise ConnectionError("가짜 연결 오류")
        if isinstance(out, Exception):
            raise out
        return CallResult(None, out, "rows", "stop", {"prompt_tokens": 100, "completion_tokens": 10,
                                                      "total_tokens": 110}, 0.01, "fake-model", 1, [])

    def calls_for(self, no: int) -> list[dict]:
        return [c for c in self.calls if c["no"] == no]


@pytest.fixture(autouse=True)
def plain_json_cfg(request, monkeypatch):
    """models.yaml의 TAG는 행 형식(rows_sections)을 켜 두었다. 옛 JSON 경로 시험은 그 설정을 뺀 사본으로 돌린다.
    행 형식 시험(rows_cfg)과 실제 설정을 보는 run_config 시험은 이 대체를 쓰지 않는다."""
    if "run_config" in request.node.name:
        return
    cfg = {k: v for k, v in load_model_config(TAG).items() if k != "rows_sections"}
    monkeypatch.setattr(sr, "load_model_config", lambda tag: cfg if tag == TAG else load_model_config(tag))


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


H_ONLY = {"hazard": {"classified": True, "h_statements": [{"code": "H225", "line": "p1:L5"}], "lines": {}}}
CLASS_ROW = {"group": "물리적", "class_code": "PH_FLAM_LIQ", "category": "2", "line": "p1:L4"}


def test_classes_check_h_codes_without_classes():
    """2항에 H코드는 있는데 유해성 분류가 비면 문제 하나 (ADR-024)."""
    ids = {"p1:L4", "p1:L5"}
    problems = sr.check_section(copy.deepcopy(H_ONLY), ids, no=2)
    assert len(problems) == 1 and "hazard.classes" in problems[0]
    empty_list = copy.deepcopy(H_ONLY)
    empty_list["hazard"]["classes"] = []
    assert len(sr.check_section(empty_list, ids, no=2)) == 1


def test_classes_check_no_problem_cases():
    ids = {"p1:L4", "p1:L5"}
    with_classes = copy.deepcopy(H_ONLY)
    with_classes["hazard"]["classes"] = [CLASS_ROW]
    assert sr.check_section(with_classes, ids, no=2) == []
    no_h = copy.deepcopy(H_ONLY)
    del no_h["hazard"]["h_statements"]
    assert sr.check_section(no_h, ids, no=2) == []
    no_h["hazard"]["h_statements"] = []
    assert sr.check_section(no_h, ids, no=2) == []
    not_classified = copy.deepcopy(H_ONLY)
    not_classified["hazard"]["classified"] = False
    assert sr.check_section(not_classified, ids, no=2) == []
    assert sr.check_section(copy.deepcopy(H_ONLY), ids, no=11) == []
    assert sr.check_section(copy.deepcopy(H_ONLY), ids) == []
    assert sr.check_section(None, set(), no=2) == []


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
    assert set(c) == {"sections", "schema_errors", "to21_validator", "expand_problems", "warnings", "needs_review",
                      "sections_method", "pictogram_check"}
    assert c["sections_method"] == "file"
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
    # 1항 제목(p1:L2) 앞 p1:L1은 문서 머리라 3항 구간 앞에 붙는다 (ADR-020)
    assert sec3["user"] == ("[3항 원문]\np1:L1 물질안전보건자료\n"
                            "p1:L8 3. 구성성분의 명칭 및 함유량\np1:L9 가상물질 갑 | 1234-56-6 | 10 ~ 20")
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


def with_h(classes: bool) -> dict:
    """2항 응답에 H코드 한 줄. classes가 거짓이면 유해성 분류를 쓰지 않은 응답."""
    r = copy.deepcopy(responses()[2])
    r["hazard"]["h_statements"] = [{"code": "H319", "line": "p1:L7"}]
    if not classes:
        del r["hazard"]["classes"]
    return r


def test_classes_reextract_when_first_has_no_classes(env):
    client = FakeClient(plan={2: [with_h(False), with_h(True)]})
    summary = run(env, client)
    calls = client.calls_for(2)
    assert len(calls) == 2
    assert "hazard.classes" in calls[1]["user"]
    assert summary["reextracted"] == 1
    s = section_check(env, 2)
    assert s["reextracted"] is True and s["check_problems"] == []
    raw = read_json(env / "runs" / RUN / "raw" / f"{DOC}_m0_s02.json")
    assert len(raw["parsed"]["hazard"]["classes"]) == 1
    out = read_json(env / "runs" / RUN / "outputs" / f"{DOC}.json")
    assert [c["class_code"] for c in out["msds"][0]["hazard"]["classes"]] == ["HH_EYE_DMG"]


def test_classes_reextract_still_empty_keeps_first(env):
    """둘째도 비면 문제 수가 같아 첫 것을 쓰고 사람 검토로 남긴다. 재추출은 한 번뿐이다."""
    client = FakeClient(plan={2: [with_h(False), with_h(False)]})
    summary = run(env, client)
    assert len(client.calls_for(2)) == 2
    assert summary["reextracted"] == 0
    s = section_check(env, 2)
    assert s["reextracted"] is False and s["ok"] is True
    assert len(s["check_problems"]) == 1 and "hazard.classes" in s["check_problems"][0]
    assert {"msds_index": 0, "section": 2} in checks(env)["needs_review"]


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


def test_preamble_in_every_section_request(env):
    """가짜 문서의 1항 제목(p1:L2) 앞 줄 p1:L1은 문서 머리라 모든 항 호출에 붙는다 (ADR-020)."""
    client = FakeClient()
    run(env, client)
    assert len(client.calls) == 16
    assert all(c["user"].split("\n")[1] == "p1:L1 물질안전보건자료" for c in client.calls)
    assert "p1:L1 물질안전보건자료\np1:L8 3. 구성성분의 명칭 및 함유량" in client.calls_for(3)[0]["user"]


def test_preamble_line_allowed_as_evidence(env):
    r3 = copy.deepcopy(responses()[3])
    r3["components"][0]["line"] = "p1:L1"          # 머리 줄은 3항 요청에 들어 있어 근거로 쓸 수 있다
    client = FakeClient(plan={3: [r3]})
    run(env, client)
    assert section_check(env, 3)["check_problems"] == []
    assert len(client.calls_for(3)) == 1


def test_preamble_line_outside_section_is_problem(env):
    """줄 번호 검사는 건의 쪽 전체가 아니라 그 항 요청에 보낸 줄(머리 + 항 구간) 기준이다."""
    other_span = copy.deepcopy(responses()[3])
    other_span["components"][0]["line"] = "p1:L11"   # 같은 건 같은 쪽이지만 4항 구간
    missing = copy.deepcopy(responses()[3])
    missing["components"][0]["line"] = "p9:L1"       # 문서에 없는 줄
    client = FakeClient(plan={3: [other_span, missing]})
    run(env, client)
    calls = client.calls_for(3)
    assert len(calls) == 2
    assert "p1:L11" not in calls[0]["user"] and "p1:L11" in calls[1]["user"]   # 재추출 피드백
    s = section_check(env, 3)
    assert s["check_problems"] == ["components[0].line: 원문에 없는 줄 번호 p1:L11"]
    raw = read_json(env / "runs" / RUN / "raw" / f"{DOC}_m0_s03.json")
    assert raw["reextract_attempt"]["check_problems"] == ["components[0].line: 원문에 없는 줄 번호 p9:L1"]
    assert {"msds_index": 0, "section": 3} in checks(env)["needs_review"]


def test_no_sections_file_warns(env):
    (env / "sections" / f"{DOC}.json").unlink()
    client = FakeClient()
    run(env, client)
    assert "항목 분할 파일 없음: 임시 분할 (찾은 항 16/16, MSDS 1건)" in checks(env)["warnings"]
    # 임시 분할: 제목으로 찾은 그 항의 줄만 들어간다
    assert "p1:L3" in client.calls_for(1)[0]["user"]
    assert "p2:L24" not in client.calls_for(1)[0]["user"]


def test_checks_record_sections_method(env):
    run(env, FakeClient())
    assert checks(env)["sections_method"] == "file"

    (env / "sections" / f"{DOC}.json").unlink()
    run(env, FakeClient())
    assert checks(env)["sections_method"] == "provisional"

    for name in ("p001.txt", "p002.txt"):
        (env / "pages" / DOC / name).write_text("L1 가상 내용\n", encoding="utf-8")
    client = FakeClient()
    run(env, client)
    assert checks(env)["sections_method"] == "fallback"
    assert "항목 분할 파일 없음: 대체 경로" in checks(env)["warnings"]
    # 대체 경로: 항마다 MSDS 전체 줄이 들어간다
    assert "p2:L1" in client.calls_for(1)[0]["user"]


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


# ── 행 형식 항 (ADR-019) ───────────────────────────────

@pytest.fixture
def rows_cfg(monkeypatch):
    """rows_sections: [11]인 가짜 설정. models.yaml은 이 step에서 바꾸지 않는다."""
    cfg = {**load_model_config(TAG), "rows_sections": [11]}
    monkeypatch.setattr(sr, "load_model_config", lambda tag: cfg)
    return cfg


def test_rows_section_goes_to_call_text(env, rows_cfg):
    client = FakeClient()
    summary = run(env, client)
    assert (summary["sections_ok"], summary["sections_failed"], summary["reextracted"]) == (16, 0, 0)
    assert len(client.calls) == 16
    assert [c["method"] for c in client.calls_for(11)] == ["call_text"]
    assert all(c["method"] == "call" for c in client.calls if c["no"] != 11)
    assert client.calls_for(11)[0]["system"] == build_system(11, rows=True)
    assert client.calls_for(12)[0]["system"] == build_system(12)

    s = section_check(env, 11)
    assert s["mode"] == "rows" and s["ok"] and s["errors"] == [] and s["check_problems"] == []
    assert section_check(env, 3)["mode"] == "json_schema"
    raw = read_json(env / "runs" / RUN / "raw" / f"{DOC}_m0_s11.json")
    assert raw["mode"] == "rows" and raw["raw_text"] == rows11()
    assert raw["parsed"]["toxicity"][0]["q"]["lower"] == 2000

    out = read_json(env / "runs" / RUN / "outputs" / f"{DOC}.json")
    assert validate_to21(out) == []
    tox, cmr = out["msds"][0]["toxicity"], out["msds"][0]["cmr"]
    assert len(tox) == 1 and tox[0]["comp_ref"] == "1" and tox[0]["q"]["status"] == "값있음"
    assert len(cmr) == 1 and cmr[0]["status"] == "해당없음"


def test_rows_default_config_never_calls_call_text(env):
    """rows_sections가 없는 태그는 모든 항이 JSON 경로(call)다."""
    client = FakeClient()
    run(env, client)
    assert len(client.calls) == 16 and all(c["method"] == "call" for c in client.calls)


def test_rows_parse_error_goes_to_feedback(env, rows_cfg):
    client = FakeClient(plan={11: [rows11(extra="가상물질 갑 | 1234-56-6 | p2:L14")]})
    summary = run(env, client)
    calls = client.calls_for(11)
    assert [c["method"] for c in calls] == ["call_text", "call_text"]
    assert "[다시 확인할 점]" not in calls[0]["user"]
    assert "[다시 확인할 점]" in calls[1]["user"]
    assert "cmr p2:L14 가상물질 갑 | 1234-56-6 | p2:L14: 열 3개, 기대 8개" in calls[1]["user"]
    assert summary["reextracted"] == 1
    s = section_check(env, 11)
    assert s["reextracted"] is True and s["ok"] and s["errors"] == []
    assert checks(env)["needs_review"] == []
    raw = read_json(env / "runs" / RUN / "raw" / f"{DOC}_m0_s11.json")
    assert raw["first_attempt"]["errors"] == ["cmr p2:L14 가상물질 갑 | 1234-56-6 | p2:L14: 열 3개, 기대 8개"]


def test_rows_errors_twice_keep_rows_and_review(env, rows_cfg):
    """두 번 다 틀린 줄이 있으면 첫 시도의 살아남은 행을 쓰고 사람 검토로 표시한다."""
    bad = rows11(extra="가상물질 갑 | p2:L14")
    client = FakeClient(plan={11: [bad, bad]})
    summary = run(env, client)
    assert len(client.calls_for(11)) == 2
    assert summary["reextracted"] == 0 and summary["sections_failed"] == 0
    s = section_check(env, 11)
    assert s["ok"] is True and s["reextracted"] is False and len(s["errors"]) == 1
    assert checks(env)["needs_review"] == [{"msds_index": 0, "section": 11}]
    out = read_json(env / "runs" / RUN / "outputs" / f"{DOC}.json")
    assert len(out["msds"][0]["toxicity"]) == 1 and len(out["msds"][0]["cmr"]) == 1


def test_rows_bad_line_id_reextracted(env, rows_cfg):
    """행 글의 줄 번호가 원문에 없으면 JSON 경로와 같이 줄 번호 검사로 한 번 더 보낸다."""
    client = FakeClient(plan={11: [rows11(tox_line="p9:L99")]})
    run(env, client)
    calls = client.calls_for(11)
    assert len(calls) == 2 and "p9:L99" in calls[1]["user"]
    assert section_check(env, 11)["reextracted"] is True


def test_rows_no_header_fails_then_retried(env, rows_cfg):
    client = FakeClient(plan={11: ["표가 없습니다.", "표가 없습니다."]})
    summary = run(env, client)
    assert len(client.calls_for(11)) == 2
    assert "표 머리글이 없음" in client.calls_for(11)[1]["user"]
    s = section_check(env, 11)
    assert s["ok"] is False and s["mode"] == "rows"
    assert summary["sections_failed"] == 1
    c = checks(env)
    assert {"msds_index": 0, "section": 11} in c["needs_review"]
    assert any(p["section"] == 11 and p["kind"] == "missing_section" for p in c["expand_problems"])


def test_rows_call_exception_retried(env, rows_cfg):
    client = FakeClient(plan={11: [TimeoutError("가짜 시간 초과")]})
    summary = run(env, client)
    assert [c["method"] for c in client.calls_for(11)] == ["call_text", "call_text"]
    assert summary["reextracted"] == 1 and section_check(env, 11)["ok"] is True


def test_rows_max_tokens_passed_to_call_text(env, rows_cfg):
    """행 형식 호출은 설정의 rows_max_tokens를 출력 한도로 보낸다. 재추출도 같다 (ADR-021)."""
    rows_cfg["rows_max_tokens"] = 16384
    client = FakeClient(plan={11: [rows11(extra="가상물질 갑 | p2:L14")]})
    run(env, client)
    assert [c["max_tokens"] for c in client.calls_for(11)] == [16384, 16384]


def test_rows_max_tokens_absent_is_none(env, rows_cfg):
    """설정에 없으면 None을 넘겨 call_text가 max_tokens를 쓴다."""
    client = FakeClient()
    run(env, client)
    assert [c["max_tokens"] for c in client.calls_for(11)] == [None]


def test_save_run_info_rows_max_tokens(tmp_path, rows_cfg):
    sr.save_run_info(tmp_path / "a", TAG)
    rows_cfg["rows_max_tokens"] = 16384
    sr.save_run_info(tmp_path / "b", TAG)
    info = {k: yaml.safe_load((tmp_path / k / "run_info.yaml").read_text(encoding="utf-8")) for k in "ab"}
    assert info["a"]["rows_max_tokens"] is None and info["b"]["rows_max_tokens"] == 16384


def test_save_run_info_rows_prompt_hash(tmp_path, rows_cfg):
    """행 형식 항은 실제로 보내는 안내문(rows=True)의 해시를 남긴다."""
    sr.save_run_info(tmp_path / "r", TAG)
    info = yaml.safe_load((tmp_path / "r" / "run_info.yaml").read_text(encoding="utf-8"))
    assert info["prompt_hashes"][11] == prompt_hash(11, rows=True) != prompt_hash(11)
    assert info["prompt_hashes"][3] == prompt_hash(3)


# ── 3항 성분 목록 (ADR-030) ────────────────────────────

LIST_HEAD = "[3항 성분 목록]"
COMP_SECTIONS = (8, 11, 12, 15)


def two_components() -> dict:
    """3항 응답: 가짜 성분 둘(하나는 CAS 없음)과 이름이 빈 행 하나."""
    r = copy.deepcopy(responses()[3])
    r["components"] += [{"name": "가상물질 을", "line": "p1:L9"}, {"name": " ", "cas_no": "9999-99-9", "line": "p1:L9"}]
    return r


class OrderClient(FakeClient):
    """call·call_text의 시작과 끝을 차례로 남긴다. 3항 호출은 끝나기 전에 잠깐 쉰다(다른 항이 먼저 시작할 틈)."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.events: list[tuple[str, int]] = []

    def _wrap(self, no: int, fn):
        with self._lock:
            self.events.append(("start", no))
        try:
            if no == 3:
                time.sleep(0.3)
            return fn()
        finally:
            with self._lock:
                self.events.append(("end", no))

    def call(self, system, user_parts, schema, schema_name, require_all=True):
        no = int(schema_name.removeprefix("sec"))
        return self._wrap(no, lambda: super(OrderClient, self).call(system, user_parts, schema, schema_name,
                                                                    require_all))

    def call_text(self, system, user_parts, max_tokens=None):
        no = int(re.match(r"\[(\d+)항 원문\]", user_parts[0]["text"]).group(1))
        return self._wrap(no, lambda: super(OrderClient, self).call_text(system, user_parts, max_tokens))


def test_component_list_sent_after_section_3(env):
    client = OrderClient(plan={3: [two_components()]})
    summary = run(env, client)
    assert summary["sections_failed"] == 0
    ev = client.events
    end3 = ev.index(("end", 3))
    for no in COMP_SECTIONS:                           # 3항이 끝난 뒤에야 보낸다
        assert ev.index(("start", no)) > end3, no
    for no in set(range(1, 17)) - set(COMP_SECTIONS) - {3}:   # 나머지 항은 3항을 기다리지 않는다
        assert ev.index(("start", no)) < end3, no
    listed = f"{LIST_HEAD}\n- 가상물질 갑 / 1234-56-6\n- 가상물질 을 / CAS 없음"
    for no in COMP_SECTIONS:
        [c] = client.calls_for(no)
        assert c["user"].endswith("\n\n" + listed), no
        assert "9999-99-9" not in c["user"]            # 이름이 빈 행은 뺀다
    assert all(LIST_HEAD not in c["user"] for c in client.calls if c["no"] not in COMP_SECTIONS)
    assert all(c["system"] == build_system(c["no"]) for c in client.calls)   # 목록은 system 글에 넣지 않는다


def test_component_list_on_reextract(env, rows_cfg):
    """재추출(두 번째 시도) 글에도 목록이 있다. 목록은 다시 확인할 점 앞이다. 행 형식 항도 같다."""
    client = FakeClient(plan={11: [rows11(tox_line="p9:L99")], 8: [TimeoutError("가짜 시간 초과")]})
    run(env, client)
    for no in (8, 11):
        calls = client.calls_for(no)
        assert len(calls) == 2, no
        assert LIST_HEAD in calls[0]["user"] and "[다시 확인할 점]" not in calls[0]["user"]
        second = calls[1]["user"]
        assert second.index(LIST_HEAD) < second.index("[다시 확인할 점]")
        assert "- 가상물질 갑 / 1234-56-6" in second
    assert [c["method"] for c in client.calls_for(11)] == ["call_text", "call_text"]


def no_components() -> dict:
    r = copy.deepcopy(responses()[3])
    r["components"] = []
    return r


def nameless_components() -> dict:
    r = copy.deepcopy(responses()[3])
    del r["components"][0]["name"]
    return r


@pytest.mark.parametrize("case", ["fail", "empty", "nameless"])
def test_component_list_absent_without_section_3_components(env, case):
    """3항이 실패했거나 이름 있는 성분이 없으면 어느 항에도 목록이 없다."""
    client = (FakeClient(fail={3}) if case == "fail"
              else FakeClient(plan={3: [no_components() if case == "empty" else nameless_components()]}))
    run(env, client)
    assert len(client.calls_for(3)) >= 1
    assert all(len(client.calls_for(no)) == 1 for no in COMP_SECTIONS)
    assert all(LIST_HEAD not in c["user"] for c in client.calls)
    raw = read_json(env / "runs" / RUN / "raw" / f"{DOC}_m0_s08.json")
    assert raw["components_given"] is None


def test_component_list_raw_components_given(env):
    run(env, FakeClient(plan={3: [two_components()]}))
    for no in range(1, 17):
        raw = read_json(env / "runs" / RUN / "raw" / f"{DOC}_m0_s{no:02d}.json")
        want = [["가상물질 갑", "1234-56-6"], ["가상물질 을", None]] if no in COMP_SECTIONS else None
        assert raw["components_given"] == want, no


def test_component_list_timing_and_summary_unchanged(env):
    """3항을 먼저 부르는 것 말고는 시간 기록과 반환 요약의 꼴이 그대로다."""
    summary = run(env, FakeClient())
    assert set(summary) == {"doc_id", "seconds", "sections_ok", "sections_failed", "reextracted", "schema_errors",
                            "warnings"}
    calls = [r for r in timing(env) if r["stage"] == "call"]
    assert [r["section"] for r in calls] == list(range(1, 17))
    assert [(s["msds_index"], s["section"]) for s in checks(env)["sections"]] == [(0, n) for n in range(1, 17)]


def test_component_list_per_msds(env):
    """다중 MSDS 문서: 건마다 자기 3항 목록을 받는다."""
    pages = env / "pages" / DOC
    (pages / "p003.txt").write_text(PAGE1.replace("가상 세정액 B", "가상 세정액 C")
                                    .replace("가상물질 갑 | 1234-56-6", "가상물질 병 | 3456-78-8"), encoding="utf-8")
    (pages / "p004.txt").write_text(page2(), encoding="utf-8")
    second = {k: {**v, "start": v["start"].replace("p1:", "p3:").replace("p2:", "p4:"),
                  "end": v["end"].replace("p1:", "p3:").replace("p2:", "p4:")} for k, v in spans().items()}
    (env / "sections" / f"{DOC}.json").write_text(json.dumps(
        {"msds": [{"pages": [1, 2], "sections": spans()}, {"pages": [3, 4], "sections": second}]}), encoding="utf-8")
    r3_second = copy.deepcopy(responses()[3])
    r3_second["components"][0].update(name="가상물질 병", cas_no="3456-78-8", line="p3:L9")
    r3_second["composition"]["lines"]["type"] = "p3:L8"

    class Client(FakeClient):
        def call(self, system, user_parts, schema, schema_name, require_all=True):
            if schema_name == "sec03" and "p3:L9" in user_parts[0]["text"]:
                with self._lock:
                    self.calls.append({"no": 3, "method": "call", "system": system, "user": user_parts[0]["text"],
                                       "parts": user_parts})
                return CallResult(copy.deepcopy(r3_second), "{}", "json_schema", "stop", {}, 0.01, "fake-model", 1, [])
            return super().call(system, user_parts, schema, schema_name, require_all)

    client = Client()
    run(env, client)
    for no in COMP_SECTIONS:
        calls = client.calls_for(no)
        assert len(calls) == 2, no
        m1 = [c for c in calls if "p4:L" in c["user"]]
        m0 = [c for c in calls if "p2:L" in c["user"]]
        assert len(m0) == len(m1) == 1, no
        assert m0[0]["user"].endswith(f"{LIST_HEAD}\n- 가상물질 갑 / 1234-56-6"), no
        assert m1[0]["user"].endswith(f"{LIST_HEAD}\n- 가상물질 병 / 3456-78-8"), no
    raw = {i: read_json(env / "runs" / RUN / "raw" / f"{DOC}_m{i}_s11.json") for i in (0, 1)}
    assert raw[0]["components_given"] == [["가상물질 갑", "1234-56-6"]]
    assert raw[1]["components_given"] == [["가상물질 병", "3456-78-8"]]


# ── 2항 쪽 이미지 (ADR-019) ───────────────────────────

IMAGE_NOTE = "[2항이 있는 쪽 이미지. 그림문자(마름모 안 그림)를 보고 pictograms에 GHS 코드를 적는다]"


@pytest.fixture
def image_cfg(monkeypatch):
    """image_input: true인 가짜 설정. models.yaml은 이 step에서 바꾸지 않는다."""
    cfg = {**load_model_config(TAG), "image_input": True}
    monkeypatch.setattr(sr, "load_model_config", lambda tag: cfg)
    return cfg


def fake_png(path: Path, width: int, height: int) -> Path:
    """tmp_path에 만드는 회색 PNG. 실제 쪽 이미지(data/pages/)를 읽지 않는다 (D-43)."""
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, width, height), False)
    pix.clear_with(200)
    pix.save(str(path))
    return path


def set_span(env: Path, no: int, start: str, end: str) -> None:
    path = env / "sections" / f"{DOC}.json"
    data = read_json(path)
    data["msds"][0]["sections"][str(no)] = {"start": start, "end": end, "method": "title"}
    path.write_text(json.dumps(data), encoding="utf-8")


def images(call: dict) -> list[pymupdf.Pixmap]:
    return [pymupdf.Pixmap(base64.b64decode(p["image_url"]["url"].split(",", 1)[1]))
            for p in call["parts"] if p["type"] == "image_url"]


def test_image_parts_only_for_section_2(env, image_cfg):
    set_span(env, 2, "p1:L5", "p2:L2")                      # 2항이 두 쪽에 걸친다
    fake_png(env / "pages" / DOC / "p001.png", 60, 40)
    fake_png(env / "pages" / DOC / "p002.png", 30, 80)
    client = FakeClient()
    summary = run(env, client)
    assert summary["sections_failed"] == 0 and summary["warnings"] == []
    sec2 = client.calls_for(2)[0]
    assert [(p.width, p.height) for p in images(sec2)] == [(60, 40), (30, 80)]   # 쪽 순서대로
    assert [p["type"] for p in sec2["parts"]] == ["text", "text", "image_url", "image_url"]
    assert sec2["parts"][1]["text"] == IMAGE_NOTE
    assert all(images(c) == [] and len(c["parts"]) == 1 for c in client.calls if c["no"] != 2)


def test_image_at_most_two_pages(env, image_cfg):
    (env / "pages" / DOC / "p003.txt").write_text("L1 가상 내용 3쪽\n", encoding="utf-8")
    set_span(env, 2, "p1:L5", "p3:L1")
    for n in (1, 2, 3):
        fake_png(env / "pages" / DOC / f"p{n:03d}.png", 10 * n, 10)
    client = FakeClient()
    run(env, client)
    assert [p.width for p in images(client.calls_for(2)[0])] == [10, 20]


def test_image_long_side_capped_1200(env, image_cfg):
    fake_png(env / "pages" / DOC / "p001.png", 1500, 300)
    client = FakeClient()
    run(env, client)
    [img] = images(client.calls_for(2)[0])
    assert max(img.width, img.height) <= 1200 and img.width >= 1199


def test_image_also_on_reextract(env, image_cfg):
    fake_png(env / "pages" / DOC / "p001.png", 60, 40)
    client = FakeClient(plan={2: [bad_line()]})
    run(env, client)
    calls = client.calls_for(2)
    assert len(calls) == 2 and "[다시 확인할 점]" in calls[1]["user"]
    assert [len(images(c)) for c in calls] == [1, 1]


def test_image_input_absent_sends_text_only(env):
    """image_input이 없는 태그(RNGD)는 PNG가 있어도 글만 보낸다."""
    assert not load_model_config(TAG).get("image_input")
    fake_png(env / "pages" / DOC / "p001.png", 60, 40)
    client = FakeClient()
    run(env, client)
    assert all(len(c["parts"]) == 1 and images(c) == [] for c in client.calls)


def test_image_png_missing_warns(env, image_cfg):
    client = FakeClient()
    summary = run(env, client)
    assert summary["sections_failed"] == 0
    assert len(client.calls_for(2)[0]["parts"]) == 1                # 이미지도 안내 글도 붙이지 않는다
    warning = "2항 쪽 이미지 없음: p001.png, 글만 보냄 (MSDS 0)"
    assert warning in checks(env)["warnings"] and warning in summary["warnings"]


def test_preamble_page_not_in_image_pages(env, image_cfg):
    """쪽 이미지는 2항 구간이 있는 쪽만 붙인다. 문서 머리(p1:L1)의 쪽은 세지 않는다."""
    set_span(env, 2, "p2:L1", "p2:L2")
    fake_png(env / "pages" / DOC / "p001.png", 60, 40)
    fake_png(env / "pages" / DOC / "p002.png", 30, 80)
    client = FakeClient()
    run(env, client)
    sec2 = client.calls_for(2)[0]
    assert "p1:L1 물질안전보건자료" in sec2["user"]
    assert [(p.width, p.height) for p in images(sec2)] == [(30, 80)]


# ── 그림문자 대조 (ADR-019) ────────────────────────────

FAKE_MAP = "h_code,class_code,category,pictogram,signal_word,source,note\nH900,FAKE_A,1,GHS02,위험,가짜 출처,\n"


def with_pictograms(codes: list[str]) -> dict:
    """2항 응답: 가짜 H코드 H900 한 줄과 모델이 읽은 그림문자."""
    r = copy.deepcopy(responses()[2])
    r["hazard"]["h_statements"] = [{"code": "H900", "text": "가짜 유해 문구", "line": "p1:L6"}]
    r["hazard"]["pictograms"] = [{"code": c} for c in codes]
    return r


@pytest.fixture
def fake_map(env, tmp_path, monkeypatch):
    path = tmp_path / "hazard_label_map.csv"
    path.write_text(FAKE_MAP, encoding="utf-8")
    monkeypatch.setattr(pc, "HAZARD_MAP", path)
    # 가짜 문서 글에도 H900이 있어야 원문 대조 규칙이 H코드를 비우지 않는다 (source_rules, ADR-029)
    with (env / "pages" / DOC / "p001.txt").open("a", encoding="utf-8") as f:
        f.write("L13 H900 가짜 유해 문구\n")


def test_pictograms_match_map(env, fake_map):
    assert validate(with_pictograms(["GHS02"]), ss.response_schema(2)) == []
    run(env, FakeClient(plan={2: [with_pictograms(["GHS02"])]}))
    c = checks(env)
    assert c["pictogram_check"] == [{"msds_index": 0, "model": ["GHS02"], "inferred": ["GHS02"], "missing": [],
                                     "extra": [], "ok": True, "unmapped_h": []}]
    assert c["needs_review"] == []
    out = read_json(env / "runs" / RUN / "outputs" / f"{DOC}.json")
    assert out["msds"][0]["hazard"]["pictograms"] == [{"code": "GHS02", "detection": None}]


def test_pictograms_mismatch_marks_review_without_reextract(env, fake_map):
    client = FakeClient(plan={2: [with_pictograms(["GHS07"])]})
    summary = run(env, client)
    assert len(client.calls_for(2)) == 1 and summary["reextracted"] == 0     # 대조 결과로 다시 보내지 않는다
    c = checks(env)
    assert c["pictogram_check"] == [{"msds_index": 0, "model": ["GHS07"], "inferred": ["GHS02"],
                                     "missing": ["GHS02"], "extra": ["GHS07"], "ok": False,
                                         "unmapped_h": []}]
    assert c["needs_review"] == [{"msds_index": 0, "section": 2}]


def test_pictograms_map_missing_skipped(env, tmp_path, monkeypatch):
    monkeypatch.setattr(pc, "HAZARD_MAP", tmp_path / "없음.csv")
    run(env, FakeClient(plan={2: [with_pictograms(["GHS07"])]}))
    c = checks(env)
    assert c["pictogram_check"] == [{"msds_index": 0, "skipped": "hazard_label_map.csv 없음"}]
    assert c["needs_review"] == []


def test_pictograms_check_uses_configs_copy_by_default(env):
    """실제 표(configs/)가 있으면 실행에서는 늘 대조한다. 가짜 응답에는 H코드가 없어 추론도 비어 있다."""
    run(env, FakeClient())
    assert checks(env)["pictogram_check"] == [{"msds_index": 0, "model": [], "inferred": [], "missing": [],
                                               "extra": [], "ok": True, "unmapped_h": []}]


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


# ── manifest 밖 문서: 쪽 글자 폴더의 meta.json으로 문서 정보를 만든다 (format40) ──

OUTSIDE = "RAW-99"
OUTSIDE_META = {"doc_id": OUTSIDE, "version": "가상판", "source_file": "99_가상 세척제.pdf", "page_count": 2,
                "dpi": 200, "text_layer": "정상",
                "pages": [{"page": 1, "state": "정상", "text_source": "텍스트층"},
                          {"page": 2, "state": "정상", "text_source": "텍스트층"}]}


def write_outside(pages: Path, doc_id: str = OUTSIDE, meta: dict | None = OUTSIDE_META) -> Path:
    """pages 아래에 가짜 문서 폴더: DOC과 같은 쪽 글자 2쪽과 meta.json(meta가 None이면 없음)."""
    d = pages / doc_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "p001.txt").write_text(PAGE1, encoding="utf-8")
    (d / "p002.txt").write_text(page2(), encoding="utf-8")
    if meta is not None:
        (d / "meta.json").write_text(json.dumps({**meta, "doc_id": doc_id}, ensure_ascii=False), encoding="utf-8")
    return d


def run_outside(env: Path, doc_id: str = OUTSIDE) -> dict:
    (env / "sections" / f"{doc_id}.json").write_text(json.dumps({"msds": [{"pages": [1, 2], "sections": spans()}]}),
                                                     encoding="utf-8")
    return sr.run_document(doc_id, TAG, RUN, FakeClient(), pages_dir=env / "pages", sections_dir=env / "sections",
                           codes_dir=env / "codes", runs_dir=env / "runs")


def test_pages_meta_reads_meta_json(tmp_path):
    write_outside(tmp_path)
    assert sr.doc_meta_from_pages(OUTSIDE, tmp_path) == {
        "doc_id": OUTSIDE, "source_file": "99_가상 세척제.pdf", "pages": 2, "text_layer": "정상",
        "language": None, "purpose": "기타"}


def test_pages_meta_page_count_missing_counts_page_files(tmp_path):
    write_outside(tmp_path, meta={k: v for k, v in OUTSIDE_META.items() if k != "page_count"})
    (tmp_path / OUTSIDE / "p002.png").write_bytes(b"")          # 그림·config는 세지 않는다
    assert sr.doc_meta_from_pages(OUTSIDE, tmp_path)["pages"] == 2


def test_pages_meta_missing_is_none(tmp_path):
    write_outside(tmp_path, meta=None)
    assert sr.doc_meta_from_pages(OUTSIDE, tmp_path) is None
    assert sr.doc_meta_from_pages("RAW-98", tmp_path) is None   # 폴더도 없음


def test_pages_meta_run_document_outside_manifest(env):
    write_outside(env / "pages")
    summary = run_outside(env)
    out = read_json(env / "runs" / RUN / "outputs" / f"{OUTSIDE}.json")
    assert validate_to21(out) == []
    assert out["doc"]["doc_id"] == OUTSIDE and out["doc"]["source_file"] == "99_가상 세척제.pdf"
    assert (out["doc"]["page_count"], out["doc"]["text_layer"], out["doc"]["language"]) == (2, "정상", None)
    assert out["msds"][0]["product"]["name"] == "가상 세정액 B"
    warnings = read_json(env / "runs" / RUN / "checks" / f"{OUTSIDE}.json")["warnings"]
    assert [w for w in warnings if "manifest에 없는 문서" in w] == ["manifest에 없는 문서: 쪽 글자 폴더의 meta.json을 씀"]
    assert summary["warnings"] == warnings


def test_pages_meta_run_document_without_meta_raises(env):
    write_outside(env / "pages", meta=None)
    with pytest.raises(KeyError, match=OUTSIDE):
        run_outside(env)


def test_pages_meta_manifest_row_wins_over_meta(env):
    """manifest에 있는 문서는 meta.json이 있어도 manifest 행을 쓰고 경고를 남기지 않는다."""
    (env / "pages" / DOC / "meta.json").write_text(
        json.dumps({**OUTSIDE_META, "doc_id": DOC, "source_file": "다른 이름.pdf"}, ensure_ascii=False),
        encoding="utf-8")
    summary = run(env, FakeClient())
    assert read_json(env / "runs" / RUN / "outputs" / f"{DOC}.json")["doc"]["source_file"] == "가상 세정액 B.pdf"
    assert summary["warnings"] == []


def ids(rows: list[dict]) -> list[str]:
    return [r["doc_id"] for r in rows]


def test_pages_meta_select_targets_mixed_docs(env, script):
    write_outside(env / "pages")
    got = script.select_targets([DOC, OUTSIDE], None, False, env / "pages")
    assert ids(got) == [DOC, OUTSIDE]
    assert got[0] == manifest.get(DOC)
    assert got[1] == sr.doc_meta_from_pages(OUTSIDE, env / "pages")


def test_pages_meta_select_targets_manifest_only_same_as_select_docs(env, script):
    assert script.select_targets([DOC, "T21-X03"], None, False, env / "pages") == \
        script.select_docs([DOC, "T21-X03"], None, False)
    assert script.select_targets(None, "개발", False, env / "pages") == script.select_docs(None, "개발", False)


def test_pages_meta_select_targets_unknown_without_meta(env, script):
    write_outside(env / "pages", meta=None)
    with pytest.raises(KeyError, match=OUTSIDE):
        script.select_targets([DOC, OUTSIDE], None, False, env / "pages")


def test_pages_meta_select_targets_eval_mixed_needs_allow_eval(env, script):
    write_outside(env / "pages")
    with pytest.raises(ValueError, match="T21-X02"):
        script.select_targets([OUTSIDE, "T21-X02"], None, False, env / "pages")
    assert ids(script.select_targets([OUTSIDE, "T21-X02"], None, True, env / "pages")) == ["T21-X02", OUTSIDE]


def test_pages_meta_select_targets_all_in_pages_dir(env, script):
    """meta.json이 있는 폴더만 문서 번호 순으로. manifest에 있는 문서는 manifest 행을 쓴다. DOC 폴더는 meta.json이 없다."""
    pages = env / "pages"
    for d in (OUTSIDE, "RAW-10", "T21-X03"):
        write_outside(pages, d)
    (pages / "빈 폴더").mkdir()
    got = script.select_targets(None, None, False, pages, all_in_pages_dir=True)
    assert ids(got) == ["RAW-10", OUTSIDE, "T21-X03"]
    assert got[2] == manifest.get("T21-X03")
    assert got[0]["purpose"] == "기타" and got[0]["source_file"] == "99_가상 세척제.pdf"


def test_pages_meta_select_targets_all_in_pages_dir_eval(env, script):
    write_outside(env / "pages")
    write_outside(env / "pages", "T21-X02")          # manifest의 평가용 문서
    with pytest.raises(ValueError, match="T21-X02"):
        script.select_targets(None, None, False, env / "pages", all_in_pages_dir=True)
    got = script.select_targets(None, None, True, env / "pages", all_in_pages_dir=True)
    assert ids(got) == [OUTSIDE, "T21-X02"]


def test_pages_meta_select_targets_all_in_pages_dir_errors(env, script, tmp_path):
    with pytest.raises(ValueError):                  # meta.json이 있는 폴더가 없다
        script.select_targets(None, None, False, env / "pages", all_in_pages_dir=True)
    write_outside(env / "pages")
    with pytest.raises(ValueError):                  # --docs·--purpose와 같이 쓰지 않는다
        script.select_targets([DOC], None, False, env / "pages", all_in_pages_dir=True)
    with pytest.raises(ValueError):
        script.select_targets(None, "개발", False, env / "pages", all_in_pages_dir=True)


# ── run_config: 실행 기록에 행 형식·이미지 입력 설정을 남긴다 (ADR-019) ──

def test_run_config_save_run_info_defaults(tmp_path):
    cfg = load_model_config(TAG)
    sr.save_run_info(tmp_path / "r", TAG)
    info = yaml.safe_load((tmp_path / "r" / "run_info.yaml").read_text(encoding="utf-8"))
    assert info["rows_sections"] == list(cfg.get("rows_sections") or [])
    assert info["image_input"] is bool(cfg.get("image_input"))
    assert info["prompt_version"] == SECTION_PROMPT_VERSION


def test_run_config_save_run_info_missing_settings(tmp_path, monkeypatch):
    """설정에 없으면 []와 false다."""
    cfg = {k: v for k, v in load_model_config("qwen3vl4b_rngd").items() if k not in ("rows_sections", "image_input")}
    monkeypatch.setattr(sr, "load_model_config", lambda tag: cfg)
    sr.save_run_info(tmp_path / "r", "qwen3vl4b_rngd")
    info = yaml.safe_load((tmp_path / "r" / "run_info.yaml").read_text(encoding="utf-8"))
    assert info["rows_sections"] == [] and info["image_input"] is False


def test_run_config_save_run_info_writes_settings(tmp_path):
    sr.save_run_info(tmp_path / "r", "qwen36_35b_runpod")
    info = yaml.safe_load((tmp_path / "r" / "run_info.yaml").read_text(encoding="utf-8"))
    assert info["rows_sections"] == [3, 8, 9, 11, 12, 14, 15] and info["image_input"] is True


def test_run_config_save_run_info_rows_max_tokens(tmp_path):
    sr.save_run_info(tmp_path / "a", "qwen36_35b_runpod")
    sr.save_run_info(tmp_path / "b", TAG)
    info = {k: yaml.safe_load((tmp_path / k / "run_info.yaml").read_text(encoding="utf-8")) for k in "ab"}
    assert info["a"]["rows_max_tokens"] == 16384 and info["b"]["rows_max_tokens"] is None
