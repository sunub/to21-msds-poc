"""scripts/try_section.py 시험 (항 하나 시험, ADR-025).

쪽 글자·항목 분할·manifest·정답·기준 실행은 모두 tmp_path에 만든 가짜 MSDS다 (D-43). 저장소의 data/·runs/는 읽거나 쓰지 않는다.
모델 서버를 부르지 않는다: ChatClient의 client를 가짜 객체로 바꾼다 (test_B_compact 방식, ADR-007).
"""
import hashlib
import importlib
import json
import os
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from msds.common import manifest
from msds.common.paths import ROOT
from msds.extract import expand as ex
from msds.extract import rows as rw
from msds.extract import section_specs as ss
from msds.extract.client import ChatClient, load_model_config
from msds.extract.inputs import load_document
from msds.extract.section_prompts import build_system, prompt_hash

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
TAG = "qwen36_35b_runpod"          # rows_sections에 11이 있고 image_input이 참인 태그
DOC, EVAL = "T21-X01", "T21-X02"
BASE = "20261030_sections_qwen36_35b_runpod_s7_v9_dev10_r1"
ACUTE = "11항 급성독성"
OVERRIDE = "가상 안내문: 11항 독성 표만 한 줄에 한 행씩 옮긴다."
ROWS = [
    {"doc_id": DOC, "source_file": "가상 세정액 C.pdf", "purpose": "개발", "pages": "1", "text_layer": "정상",
     "language": "ko"},
    {"doc_id": EVAL, "source_file": "가상 평가 문서.pdf", "purpose": "평가", "pages": "1", "text_layer": "정상",
     "language": "ko"},
]
TOX = [("TX_ORAL", "LD50", "> 2000 mg/kg", "랫드", "경구 LD50"),
       ("TX_DERMAL", "LD50", "> 2000 mg/kg", "토끼", "경피 LD50"),
       ("TX_INHAL", "LC50", "> 5 mg/L", "랫드", "흡입 LC50")]


# ── 가짜 문서 ──────────────────────────────────────────

def page() -> tuple[list[str], dict]:
    """가짜 MSDS 한 쪽: 문서 머리 한 줄, 1~16항마다 제목 줄과 내용 줄. 11항은 독성 3줄. 반환: (줄 글, 항목 분할)."""
    body = {1: ["제품명 | 가상 세정액 C"], 3: ["가상물질 갑 | 1234-56-6 | 10 ~ 20"],
            11: [f"가상물질 갑 | {t[4]} | {t[2]} | {t[3]}" for t in TOX]}
    texts, spans = ["물질안전보건자료"], {}
    for n in range(1, 17):
        start = len(texts) + 1
        texts += [f"{n}. {ss.load_specs()[n].title}", *body.get(n, [f"가상 내용 {n}"])]
        spans[str(n)] = {"start": f"p1:L{start}", "end": f"p1:L{len(texts)}", "method": "title"}
    return texts, spans


def first_body_line(no: int, k: int = 0) -> str:
    """no항 제목 다음 k번째 내용 줄의 줄 번호."""
    start = int(page()[1][str(no)]["start"].split(":L")[1])
    return f"p1:L{start + 1 + k}"


def tox_rows(bad: bool = False) -> str:
    """11항 행 형식 응답: 독성 3행. bad면 열 수가 크게 모자라 버려지는 줄 하나를 더한다."""
    cols = rw.row_tables(11)["toxicity"]
    out = ["### toxicity", " | ".join(cols)]
    for k, (ep, desc, q, species, _) in enumerate(TOX):
        r = {"comp_name": "가상물질 갑", "comp_cas": "1234-56-6", "endpoint": ep, "descriptor": desc, "q": q,
             "species": species, "status": "값있음", "line": first_body_line(11, k)}
        out.append(" | ".join(r.get(c, "") for c in cols))
    if bad:
        out.append(f"가상물질 갑 | TX_ORAL | {first_body_line(11)}")
    return "\n".join(out)


def empty(no: int) -> dict:
    props = ss.response_schema(no)["properties"]
    return {k: ({"lines": {}} if v.get("type") == "object" else []) for k, v in props.items()}


def base_parts() -> dict[int, dict]:
    """기준 실행의 항별 응답: 제품명과 성분 하나. 11항 독성은 0행."""
    r = {n: empty(n) for n in range(1, 17)}
    r[1]["product"] = {"name": "가상 세정액 C", "lines": {"name": first_body_line(1)}}
    r[3].update(composition={"type": "혼합물", "lines": {"type": first_body_line(3)}},
                components=[{"name": "가상물질 갑", "cas_no": "1234-56-6",
                             "content": {"raw": "10 ~ 20", "lower_op": ">=", "lower": 10, "upper_op": "<=",
                                         "upper": 20, "unit": "%"}, "line": first_body_line(3)}])
    return r


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def make_base(env: Path, name: str = BASE, tag: str = TAG, started: str = "2026-10-30T10:00:00+09:00",
              outputs: bool = True) -> Path:
    """가짜 기준 실행: raw/ 16개(채택된 응답), outputs/, run_info.yaml."""
    run = env / "runs" / name
    parts = base_parts()
    for no, parsed in parts.items():
        write_json(run / "raw" / f"{DOC}_m0_s{no:02d}.json",
                   {"doc_id": DOC, "msds_index": 0, "section": no, "reextracted": False, "ok": True,
                    "parsed": parsed, "raw_text": "", "mode": "json_schema", "finish_reason": "stop"})
    if outputs:
        lines = load_document(DOC, env / "pages", env / "sections", env / "codes").lines
        out, _ = ex.to_to21(manifest.get(DOC), [parts], lines, f"{tag}:가상/모델")
        write_json(run / "outputs" / f"{DOC}.json", out)
    info = {"model_tag": tag, "model": "가상/모델", "prompt_version": "s7",
            "pages_dir": os.path.relpath(env / "pages", ROOT), "started_at": started}
    (run / "run_info.yaml").write_text(yaml.safe_dump(info, allow_unicode=True), encoding="utf-8")
    return run


@pytest.fixture
def env(tmp_path, monkeypatch):
    texts, spans = page()
    pages = tmp_path / "pages" / DOC
    pages.mkdir(parents=True)
    (pages / "p001.txt").write_text("".join(f"L{i:03d} {t}\n" for i, t in enumerate(texts, 1)), encoding="utf-8")
    write_json(tmp_path / "sections" / f"{DOC}.json", {"msds": [{"pages": [1, 1], "sections": spans}]})
    path = tmp_path / "manifest.csv"
    manifest.save(ROWS, path)
    orig = manifest.load
    monkeypatch.setattr(manifest, "load", lambda p=path: orig(p))
    monkeypatch.setenv("RUNPOD_VLLM_BASE_URL", "http://test/v1")
    monkeypatch.setenv("RUNPOD_VLLM_API_KEY", "test")
    monkeypatch.setattr(ChatClient, "_working_mode", {})
    # 정답: 기준 응답의 11항을 독성 3행으로 바꾼 것
    lines = load_document(DOC, tmp_path / "pages", tmp_path / "sections", tmp_path / "codes").lines
    parts = {**base_parts(), 11: rw.parse_rows(tox_rows(), 11)[0]}
    gold, _ = ex.to_to21(manifest.get(DOC), [parts], lines, "가상엔진")
    write_json(tmp_path / "gold" / f"{DOC}.json", gold)
    make_base(tmp_path)
    return tmp_path


@pytest.fixture
def ts(env, monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    mod = importlib.import_module("try_section")
    monkeypatch.setattr(mod, "SECTIONS_DIR", env / "sections")
    monkeypatch.setattr(mod, "CODES_DIR", env / "codes")
    monkeypatch.setattr(mod, "RUNS", env / "runs")
    return mod


# ── 가짜 모델 서버 ─────────────────────────────────────

def resp(content: str):
    return SimpleNamespace(
        choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=100, completion_tokens=10, total_tokens=110))


class FakeCompletions:
    """받은 인자를 모으고 reply(인자)의 글을 돌려준다."""

    def __init__(self, reply):
        self.reply = reply
        self.calls: list[dict] = []

    def create(self, **kw):
        self.calls.append(kw)
        return resp(self.reply(kw))


def section_of(kw: dict) -> int:
    return int(re.match(r"\[(\d+)항 원문\]", kw["messages"][1]["content"][0]["text"]).group(1))


def comp_rows() -> str:
    """3항 행 형식 응답: 성분 하나."""
    cols = rw.row_tables(3)["components"]
    r = {"name": "가상물질 갑", "cas_no": "1234-56-6", "content": "10 ~ 20 %", "line": first_body_line(3)}
    return "\n".join(["### components", " | ".join(cols), " | ".join(r.get(c, "") for c in cols)])


def reply_all(kw: dict) -> str:
    """문서 전체 실행용: JSON 경로는 기준 응답, 행 형식은 3항 성분 하나·11항 독성 3행이고 나머지는 첫 표 머리글만."""
    no = section_of(kw)
    if "response_format" in kw:
        return json.dumps(base_parts()[no], ensure_ascii=False)
    return {3: comp_rows(), 11: tox_rows()}.get(no) or f"### {next(iter(rw.row_tables(no)))}"


def fake_client(reply) -> tuple[ChatClient, list[dict]]:
    client = ChatClient(load_model_config(TAG))
    fake = FakeCompletions(reply)
    client.client = SimpleNamespace(chat=SimpleNamespace(completions=fake))
    return client, fake.calls


class Factory:
    """try_section.ChatClient 자리에 넣는다. 만든 클라이언트와 받은 요청을 모은다."""

    def __init__(self, reply):
        self.reply = reply
        self.made: list[ChatClient] = []
        self.calls: list[dict] = []

    def __call__(self, cfg):
        client = ChatClient(cfg)
        fake = FakeCompletions(self.reply)
        fake.calls = self.calls
        client.client = SimpleNamespace(chat=SimpleNamespace(completions=fake))
        self.made.append(client)
        return client


def files_text(folder: Path) -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(folder.rglob("*")) if p.is_file())


def h(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


# ── plan ───────────────────────────────────────────────

def test_plan_section_11(ts, env):
    p = ts.plan(DOC, TAG, [11], env / "pages")
    assert (p["doc_id"], p["model_tag"], p["model"]) == (DOC, TAG, load_model_config(TAG)["model"])
    assert p["sections_method"] == "file" and p["msds_count"] == 1
    s = p["sections"][11]
    spans = page()[1]
    assert s["section"] == 11 and s["rows"] is True
    assert (s["first"], s["last"]) == (spans["11"]["start"], spans["11"]["end"])
    assert s["lines"] == 5 and s["preamble_lines"] == 1          # 문서 머리 1줄 + 제목 1줄 + 독성 3줄
    assert s["pages"] == [1] and s["images"] == []
    assert s["system"] == build_system(11, rows=True)
    assert s["prompt_hash"] == prompt_hash(11, True)


def test_plan_section_2_images(ts, env):
    p = ts.plan(DOC, TAG, [2], env / "pages")
    assert p["sections"][2]["rows"] is False and p["sections"][2]["images"] == []
    assert any("2항 쪽 이미지 없음" in w for w in p["warnings"])
    (env / "pages" / DOC / "p001.png").write_bytes(b"")
    assert ts.plan(DOC, TAG, [2], env / "pages")["sections"][2]["images"] == ["p001.png"]


def test_plan_rejects_eval_doc(ts, env):
    with pytest.raises(ValueError, match="D-43"):
        ts.plan(EVAL, TAG, [11], env / "pages")


def test_main_rejects_eval_doc(ts, env, capsys):
    with pytest.raises(SystemExit):
        ts.main(["--model", TAG, "--doc", EVAL, "--section", "11", "--pages-dir", str(env / "pages")])
    assert "D-43" in capsys.readouterr().err


def test_dry_run_makes_no_client(ts, env, monkeypatch, capsys):
    factory = Factory(lambda kw: tox_rows())
    monkeypatch.setattr(ts, "ChatClient", factory)
    assert ts.main(["--model", TAG, "--doc", DOC, "--section", "11", "--pages-dir", str(env / "pages"),
                    "--dry-run"]) == 0
    assert factory.made == [] and factory.calls == []
    out = capsys.readouterr().out
    assert "①" in out and "②" in out and "③" not in out
    assert prompt_hash(11, True) in out
    assert build_system(11, rows=True) not in out                # --show-prompt 없이는 해시와 길이만
    assert not (env / "runs" / "manual").exists()


def test_show_prompt_prints_system(ts, env, monkeypatch, capsys):
    monkeypatch.setattr(ts, "ChatClient", Factory(lambda kw: tox_rows()))
    ts.main(["--model", TAG, "--doc", DOC, "--section", "11", "--pages-dir", str(env / "pages"), "--dry-run",
             "--show-prompt"])
    assert build_system(11, rows=True).strip() in capsys.readouterr().out


# ── run_sections_once ──────────────────────────────────

def test_run_sections_once_rows(ts, env):
    client, calls = fake_client(lambda kw: tox_rows(bad=True))
    doc = load_document(DOC, env / "pages", env / "sections", env / "codes")
    res = ts.run_sections_once(client, load_model_config(TAG), doc, [11], env / "pages")
    r = res[11]
    assert r["section"] == 11 and r["ok"] is True and r["mode"] == "rows" and r["finish_reason"] == "stop"
    assert len(r["parsed"]["toxicity"]) == 3
    assert [t["endpoint"] for t in r["parsed"]["toxicity"]] == ["TX_ORAL", "TX_DERMAL", "TX_INHAL"]
    assert r["dropped_rows"] == 1
    assert any("열 3개" in e for e in r["errors"])
    assert r["raw_text"] == tox_rows(bad=True)
    assert len(calls) == 2 and r["reextracted"] is False        # 버린 줄이 있어 한 번 더 보냈지만 나아지지 않았다
    assert r["usage"]["prompt_tokens"] == 200 and r["seconds"] >= 0
    assert r["prompt_hash"] == prompt_hash(11, True)
    assert calls[0]["messages"][0]["content"] == build_system(11, rows=True)
    assert "response_format" not in calls[0]


def test_run_sections_once_clean_rows_one_call(ts, env):
    client, calls = fake_client(lambda kw: tox_rows())
    doc = load_document(DOC, env / "pages", env / "sections", env / "codes")
    r = ts.run_sections_once(client, load_model_config(TAG), doc, [11], env / "pages")[11]
    assert len(calls) == 1 and r["dropped_rows"] == 0 and r["errors"] == [] and r["check_problems"] == []


def test_system_override_sent_but_not_saved(ts, env):
    client, calls = fake_client(lambda kw: tox_rows())
    doc = load_document(DOC, env / "pages", env / "sections", env / "codes")
    res = ts.run_sections_once(client, load_model_config(TAG), doc, [11], env / "pages",
                               system_override={11: OVERRIDE})
    assert calls[0]["messages"][0]["content"] == OVERRIDE
    assert res[11]["prompt_hash"] == h(OVERRIDE)
    assert OVERRIDE not in json.dumps({k: v for k, v in res[11].items()}, ensure_ascii=False)

    p = ts.plan(DOC, TAG, [11], env / "pages")
    p["sections"][11].update(system=OVERRIDE, prompt_hash=h(OVERRIDE), system_override=True)
    score = ts.patch_and_score(env / "runs" / BASE, DOC, res, env / "pages", env / "gold")
    run = ts.save_manual_run(env / "runs" / "manual", DOC, [11], p, res, score)
    assert {"plan.json", "result.json", "run_info.yaml"} <= {x.name for x in run.iterdir()}
    assert (run / "raw" / f"{DOC}_m0_s11.json").exists()
    saved = files_text(run)
    assert OVERRIDE not in saved
    assert build_system(11, rows=True)[:300] not in saved
    assert h(OVERRIDE) in (run / "plan.json").read_text(encoding="utf-8")
    assert read_json(run / "raw" / f"{DOC}_m0_s11.json")["prompt_hash"] == h(OVERRIDE)
    assert yaml.safe_load((run / "run_info.yaml").read_text(encoding="utf-8"))["prompt_hashes"][11] == h(OVERRIDE)


# ── patch_and_score ────────────────────────────────────

def acute(scores: dict) -> float:
    return next(v for k, v in scores["items"].items() if k.startswith(ACUTE))


def test_patch_and_score_raises_acute(ts, env):
    client, _ = fake_client(lambda kw: tox_rows())
    doc = load_document(DOC, env / "pages", env / "sections", env / "codes")
    res = ts.run_sections_once(client, load_model_config(TAG), doc, [11], env / "pages")
    s = ts.patch_and_score(env / "runs" / BASE, DOC, res, env / "pages", env / "gold")
    assert acute(s["after"]) > acute(s["before"])
    assert acute(s["after"]) == pytest.approx(1.0)
    assert s["after"]["weighted"] > s["before"]["weighted"]
    assert len(s["before"]["items"]) == len(s["after"]["items"]) == 23
    changed = {c["name"]: c for c in s["changed"]}
    name = next(n for n in changed if n.startswith(ACUTE))
    assert changed[name]["before"] == acute(s["before"]) and changed[name]["after"] == acute(s["after"])
    m = s["patched_doc"]["msds"][0]
    assert len(m["toxicity"]) == 3 and all(t["comp_ref"] == "1" for t in m["toxicity"])
    assert m["product"]["name"] == "가상 세정액 C"               # 다른 항은 기준 실행의 응답 그대로
    assert s["warnings"] == []


def test_patch_and_score_failed_section_is_empty(ts, env):
    """새 결과가 실패면 실행기처럼 그 항을 비운다."""
    res = {11: {"ok": False, "parsed": None}}
    s = ts.patch_and_score(env / "runs" / BASE, DOC, res, env / "pages", env / "gold")
    assert s["patched_doc"]["msds"][0]["toxicity"] == []


def test_patch_and_score_warns_on_other_pages_dir(ts, env):
    s = ts.patch_and_score(env / "runs" / BASE, DOC, {}, env / "pages", env / "gold")
    assert s["changed"] == [] and s["warnings"] == []           # 고친 항이 없으면 기준 실행과 같은 문서로 펼친다
    info = yaml.safe_load((env / "runs" / BASE / "run_info.yaml").read_text(encoding="utf-8"))
    info["pages_dir"] = "data/pages/chars_wrap"
    (env / "runs" / BASE / "run_info.yaml").write_text(yaml.safe_dump(info, allow_unicode=True), encoding="utf-8")
    assert any("쪽 글자 폴더" in w for w in ts.patch_and_score(
        env / "runs" / BASE, DOC, {}, env / "pages", env / "gold")["warnings"])


# ── pick_base_run ──────────────────────────────────────

def test_pick_base_run(ts, env):
    runs = env / "runs"
    make_base(env, "20261031_sections_qwen36_35b_runpod_s7_v9_dev10_r2", started="2026-10-31T09:00:00+09:00")
    make_base(env, "20261101_sections_qwen3_30b_a3b_rngd_dev10_r1", tag="qwen3_30b_a3b_rngd",
              started="2026-11-01T09:00:00+09:00")                                   # 다른 모델
    make_base(env, "20261101_sections_qwen36_35b_runpod_probe", started="2026-11-01T09:00:00+09:00")  # dev10 아님
    make_base(env, "20261102_sections_qwen36_35b_runpod_dev10_r1", started="2026-11-02T09:00:00+09:00",
              outputs=False)                                                         # 이 문서 결과 없음
    assert ts.pick_base_run(runs, TAG, DOC) == runs / "20261031_sections_qwen36_35b_runpod_s7_v9_dev10_r2"
    assert ts.pick_base_run(runs, "gpt_oss_20b_rngd", DOC) is None


# ── save_manual_run ────────────────────────────────────

def test_saved_run_reads_with_summarize_run(ts, env, monkeypatch):
    client, _ = fake_client(lambda kw: tox_rows())
    doc = load_document(DOC, env / "pages", env / "sections", env / "codes")
    res = ts.run_sections_once(client, load_model_config(TAG), doc, [11], env / "pages")
    p = ts.plan(DOC, TAG, [11], env / "pages")
    score = ts.patch_and_score(env / "runs" / BASE, DOC, res, env / "pages", env / "gold")
    run = ts.save_manual_run(env / "runs" / "manual", DOC, [11], p, res, score)
    assert run.parent == env / "runs" / "manual" and run.name.endswith(f"_{DOC}_s11")

    info = yaml.safe_load((run / "run_info.yaml").read_text(encoding="utf-8"))
    run_info_keys = ["model_tag", "model", "prompt_version", "rows_sections", "rows_max_tokens", "image_input",
                     "prompt_hashes", "schema_version", "pages_dir", "concurrency", "started_at", "git_commit"]
    assert list(info) == run_info_keys
    assert info["model_tag"] == TAG
    assert read_json(run / "outputs" / f"{DOC}.json") == score["patched_doc"]
    result = read_json(run / "result.json")
    assert result["after"] == score["after"] and result["before"] == score["before"]
    assert "patched_doc" not in result
    assert "system" not in read_json(run / "plan.json")["sections"]["11"]

    monkeypatch.syspath_prepend(str(SCRIPTS))
    br = importlib.import_module("b_app_runs")
    s = br.summarize_run(run, env / "gold", cache_dir=None)
    assert (s["kind"], s["name"], s["model_tag"]) == ("manual", f"manual/{run.name}", TAG)
    assert s["docs"] == [DOC]
    assert s["weighted"] == pytest.approx(score["after"]["weighted"])
    assert s["progress"]["running"] is False and s["progress"]["done"] == 1


# ── 명령줄 ─────────────────────────────────────────────

def test_main_sections_json(ts, env, monkeypatch, capsys):
    factory = Factory(lambda kw: tox_rows())
    monkeypatch.setattr(ts, "ChatClient", factory)
    system_file = env / "system.txt"
    system_file.write_text(OVERRIDE, encoding="utf-8")
    assert ts.main(["--model", TAG, "--doc", DOC, "--section", "11", "--pages-dir", str(env / "pages"),
                    "--gold-dir", str(env / "gold"), "--out-dir", str(env / "runs" / "manual"),
                    "--system-file", str(system_file), "--json"]) == 0
    assert len(factory.made) == 1 and len(factory.calls) == 1
    assert factory.calls[0]["messages"][0]["content"] == OVERRIDE
    text = capsys.readouterr().out
    assert OVERRIDE not in text
    out = json.loads(text)
    assert out["plan"]["sections"]["11"]["prompt_hash"] == h(OVERRIDE)
    assert out["results"]["11"]["raw_text"] == tox_rows()
    assert out["base_run"].endswith(BASE)                      # --base-run 없이 고른 기준 실행
    assert any(c["name"].startswith(ACUTE) for c in out["score"]["changed"])
    assert out["fields"]["11"]["toxicity"] == 3
    saved = Path(out["saved"])
    assert saved.parent == env / "runs" / "manual" and OVERRIDE not in files_text(saved)


def test_main_sections_human_output(ts, env, monkeypatch, capsys):
    monkeypatch.setattr(ts, "ChatClient", Factory(lambda kw: tox_rows(bad=True)))
    ts.main(["--model", TAG, "--doc", DOC, "--section", "11", "--pages-dir", str(env / "pages"),
             "--base-run", BASE, "--gold-dir", str(env / "gold"), "--out-dir", str(env / "runs" / "manual")])
    out = capsys.readouterr().out
    for mark in "①②③④⑤⑥":
        assert mark in out
    assert "버린 줄 1" in out and "toxicity 3행" in out
    assert re.search(r"11항 급성독성\S* \d+\.\d → 100\.0", out)


def test_main_system_file_needs_one_section(ts, env, capsys):
    system_file = env / "system.txt"
    system_file.write_text(OVERRIDE, encoding="utf-8")
    with pytest.raises(SystemExit):
        ts.main(["--model", TAG, "--doc", DOC, "--section", "11", "--section", "15", "--pages-dir",
                 str(env / "pages"), "--system-file", str(system_file)])
    assert "--system-file" in capsys.readouterr().err


def test_main_all_runs_document(ts, env, monkeypatch, capsys):
    factory = Factory(reply_all)
    monkeypatch.setattr(ts, "ChatClient", factory)
    assert ts.main(["--model", TAG, "--doc", DOC, "--all", "--pages-dir", str(env / "pages"),
                    "--gold-dir", str(env / "gold"), "--out-dir", str(env / "runs" / "manual"), "--json"]) == 0
    assert len(factory.made) == 1
    assert sorted({section_of(kw) for kw in factory.calls}) == list(range(1, 17))
    out = json.loads(capsys.readouterr().out)
    run = Path(out["saved"])
    assert run.parent == env / "runs" / "manual" and run.name.endswith(f"_{DOC}_all")
    assert (run / "outputs" / f"{DOC}.json").exists() and (run / "run_info.yaml").exists()
    assert out["summary"]["docs"] == [DOC] and out["summary"]["weighted"] is not None
    assert any(c["name"].startswith(ACUTE) for c in out["score"]["changed"])
