"""추출 파인튜닝 학습 데이터 시험 (11/03 F, msds.finetune.dataset).

- 정답 글은 실제 추출이 읽는 방법(행: parse_rows, JSON: json.loads + 스키마)으로 다시 읽어 같은 값이 나와야 한다.
- 안내문은 실제 추출 때 학생이 받는 글과 같아야 한다(ChatClient가 보내는 글과 비교).
- manifest 개발·평가 문서는 학습에 들어가지 않는다(D-43).
뒤쪽 실제 실행 시험은 runs/의 qwen36 실행과 data/pages/T21-M001이 있을 때만 돈다(D-47).
"""
import json
import shutil
from types import SimpleNamespace

import pytest

from msds.common.paths import DATA, ROOT
from msds.extract.client import ChatClient
from msds.extract.rows import ROWS_SECTIONS_DEFAULT, parse_qm, parse_rows, rows_guide
from msds.extract.section_specs import response_schema
from msds.finetune.dataset import (Student, TeacherRun, build_examples, canonical, drop_pictograms, json_text, qm_text,
                                   rows_text, split_by_doc, system_prompt, target_problems)

RUN = ROOT / "runs" / "20261101_sections_qwen36_s10_v17_dev10_r1"
has_run = pytest.mark.skipif(not ((RUN / "raw").is_dir() and (DATA / "pages" / "T21-M001").is_dir()),
                             reason="qwen36 실행 기록 또는 T21-M001 쪽 글자가 없습니다")


@pytest.mark.parametrize("no", ROWS_SECTIONS_DEFAULT)
def test_행_형식_정답은_parse_rows로_다시_읽으면_같은_값(no):
    parsed, _ = parse_rows(rows_guide(no), no)            # 안내문의 예시 행(가짜 값)을 정답처럼 쓴다
    assert any(v for k, v in parsed.items() if k != "composition"), "예시 행이 읽히지 않음"
    text = rows_text(parsed, no)
    back, errors = parse_rows(text, no)
    assert errors == [] and back == parsed
    assert target_problems(text, parsed, no, True, {r for r in _line_ids(parsed)}) == []


def _line_ids(node):
    if isinstance(node, dict):
        for k, v in node.items():
            if k in ("line", "start", "end") and isinstance(v, str):
                yield v
            elif k == "lines" and isinstance(v, dict):
                yield from (x for x in v.values() if isinstance(x, str))
            else:
                yield from _line_ids(v)
    elif isinstance(node, list):
        for v in node:
            yield from _line_ids(v)


def test_원문_표기가_없는_숫자_묶음은_나눈_칸으로_다시_쓴다():
    assert qm_text({"raw": " 20 ~ 30 % "}) == "20 ~ 30 %"
    for q in ({"lower_op": ">=", "lower": 95, "unit": "%"}, {"value": 1.5, "unit": "mg/L", "approx": True},
              {"lower_op": ">=", "lower": 40, "upper_op": "<", "upper": 50, "unit": "%"}, {"upper_op": "<", "upper": 0.1},
              {"lower_op": ">", "lower": 10, "upper_op": "<=", "upper": 20, "unit": "%"}):
        back = parse_qm(qm_text(q))
        assert {k: back.get(k) for k in q} == q, qm_text(q)
    assert qm_text({"lower_op": ">", "lower": 10, "upper_op": "<=", "upper": 20, "unit": "%"}).startswith("lower_op:>,")  # 원문 표기로 못 쓰는 범위


def test_행이_없는_표는_머리글만_쓰고_값의_세로줄은_바꾼다():
    text = rows_text({"physchem": [{"prop_code": "APPEARANCE_COLOR", "text_value": "무색|투명", "line": "p5:L2"}],
                      "extras": []}, 9)
    assert text.splitlines()[-1] == "### extras" and "무색/투명" in text and "무색|투명" not in text


def test_JSON_정답은_공백_없고_스키마_순서이며_필수가_아닌_빈_칸을_뺀다():
    parsed = {"extras": [], "hazard": {"signal_word": None, "classified": True, "classes": [], "lines": {"classified": "p1:L5"}},
              "narratives": []}
    text = json_text(parsed, 2)
    back = json.loads(text)
    assert " " not in text.replace("분류 ", "") and list(back) == ["hazard", "narratives", "extras"]   # 최상위 표는 필수라 남는다
    assert "signal_word" not in back["hazard"] and "classes" not in back["hazard"]
    schema = response_schema(2)
    assert canonical(back, schema, schema["$defs"]) == back


def test_이미지를_받지_않는_학생의_2항_정답에서_그림문자를_뺀다():
    p = {"hazard": {"classified": True, "pictograms": [{"code": "GHS02"}]}, "narratives": [], "extras": []}
    assert "pictograms" not in drop_pictograms(p)["hazard"] and p["hazard"]["pictograms"]   # 원본은 그대로


def test_학생_설정에서_행_형식·JSON_방식·이미지를_읽는다():
    d = Student.from_config(None)
    assert d.rows_sections == tuple(ROWS_SECTIONS_DEFAULT) and d.json_mode == "json_schema_compact" and not d.image_input
    s = Student.from_config({"tag": "x", "rows_sections": [3], "structured": ["none"], "image_input": True,
                             "params": {"extra_body": {"chat_template_kwargs": {"enable_thinking": False}}}})
    assert s.is_rows(3) and not s.is_rows(8) and s.image_input and s.chat_template_kwargs == {"enable_thinking": False}


@pytest.mark.parametrize("mode,hint", [("json_schema_compact", False), ("none", True)])
def test_안내문은_ChatClient가_실제로_보내는_글과_같다(monkeypatch, mode, hint):
    monkeypatch.setenv("FT_TEST_URL", "http://127.0.0.1:9/v1")
    client = ChatClient({"model": "m", "base_url_env": "FT_TEST_URL", "api_key_env": "FT_TEST_KEY", "structured": [mode],
                         "run": {"max_retries": 0}})
    sent = []

    def fake(messages, *args, **kwargs):
        sent.append(messages)
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content="{}"))],
                               usage=None)
    monkeypatch.setattr(client, "_call_with_backoff", fake)
    from msds.extract.section_prompts import build_system
    student = Student("x", (), mode, False)
    client.call(build_system(1), [{"type": "text", "text": "[1항 원문]"}], response_schema(1), "sec01", require_all=False)
    assert sent[0][0]["content"] == system_prompt(1, student)
    assert ("[응답 형식]" in system_prompt(1, student)) is hint


def test_검증_문서는_학습_문서와_겹치지_않는다():
    ex = [{"doc_id": f"D{i}", "id": f"D{i}_s{s}"} for i in range(20) for s in (1, 3)]
    train, val, docs = split_by_doc(ex, 0.1, 2026)
    assert len(docs) == 2 and {e["doc_id"] for e in val} == set(docs)
    assert not {e["doc_id"] for e in train} & set(docs) and len(train) + len(val) == len(ex)
    assert split_by_doc(ex, 0.1, 2026)[2] == docs                       # 같은 시드면 같은 문서


@has_run
def test_실제_실행_기록으로_만든_예시는_실제_추출과_같은_모양이다(tmp_path):
    # T21-M001 기록만 떼어 쓴다. 실행 폴더의 다른 문서는 PC마다 쪽 글자가 있고 없고가 달라 버리는 수가 바뀐다
    # (11/03 사용자 PC: 쪽 글자 없음 36, 교사 실패 2, 줄 번호 다름 1로 버려짐 — 버리는 규칙대로 동작)
    one = tmp_path / RUN.name
    (one / "raw").mkdir(parents=True)
    shutil.copy(RUN / "run_info.yaml", one)
    for f in (RUN / "raw").glob("T21-M001_m0_s*.json"):
        shutil.copy(f, one / "raw")
    run = TeacherRun.load(one, DATA / "pages")
    assert build_examples([run], Student.from_config(None)).examples == []    # T21-M001은 개발 문서라 빠진다 (D-43)
    r = build_examples([run], Student.from_config(None), allow_held_out=True)
    assert len(r.examples) == 9 and not r.dropped                               # 추출 대상 9개 항
    for e in r.examples:
        sys_, user, ans = (m["content"] for m in e["messages"])
        assert user.startswith(f"[{e['section']}항 원문]\n")
        if e["format"] == "rows":
            assert ans.startswith("### ") and "## [응답 형식] 한 줄에 한 행" in sys_
        else:
            assert json.loads(ans) and "\n" not in ans
    s = Student.from_config({"rows_sections": [3, 8, 9, 11, 12, 14, 15], "structured": ["json_schema"], "image_input": True})
    assert 2 not in {e["section"] for e in build_examples([run], s, allow_held_out=True).examples}
