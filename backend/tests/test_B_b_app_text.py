"""표시 이름 규칙 시험. 실제 실행의 이름만 쓰며 문서 내용이나 서버는 읽지 않는다."""
import copy
import importlib

import pytest

from test_B_compare_models import SCRIPTS


@pytest.fixture
def text(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    return importlib.import_module("b_app_text")


@pytest.mark.parametrize("tag, expected", [
    ("qwen36_35b_runpod", "Qwen3.6 35B (RunPod)"),
    ("qwen3_30b_a3b_rngd", "Qwen3 30B (RNGD)"),
    ("gpt_oss_20b_rngd", "gpt-oss 20B (RNGD)"),
    ("nuextract2_8b_runpod", "NuExtract 2.0 8B (RunPod)"),
    ("qwen3vl4b_rngd", "Qwen3-VL 4B (RNGD)"),
    ("qwen38", "Qwen3.8 27B (vLLM)"),
    ("claude", "Claude (실버 초안)"),
    ("gpt", "GPT"),
    ("future_model", "future_model"),
    (None, ""),
    ("", ""),
])
def test_model_labels(text, tag, expected):
    assert text.model_label(tag) == expected


@pytest.mark.parametrize("name, title", [
    ("20261030_sections_qwen36_35b_runpod_s7_v9_cls_dev10_r2",
     "10/30 Qwen3.6 35B (RunPod) · 안내문 s7 · 입력 version9 · 분류 검사 · 개발 10건 · 2회차"),
    ("20261027_silver_claude_p3_dev",
     "10/27 실버 초안(Claude) · 안내문 p3 · 개발 10건"),
    ("20261029_sections_qwen3_30b_a3b_rngd_s4_cw_optonly_probe",
     "10/29 Qwen3 30B (RNGD) · 안내문 s4 · 입력 chars_wrap · 선택 항목만 · 탐색"),
    ("20261028_sections_qwen3_30b_a3b_rngd_s2_cw_s003_w1_r2",
     "10/28 Qwen3 30B (RNGD) · 안내문 s2 · 입력 chars_wrap · 문서 T21-S003 한 건 · 동시 1개 · 2회차"),
    ("20261028_sections_gpt_oss_20b_rngd_s2_cw_s003_w1_r2",
     "10/28 gpt-oss 20B (RNGD) · 안내문 s2 · 입력 chars_wrap · 문서 T21-S003 한 건 · 동시 1개 · 2회차"),
    ("20261028_sections_nuextract2_8b_runpod_cw_s016_ex",
     "10/28 NuExtract 2.0 8B (RunPod) · 입력 chars_wrap · 문서 T21-S016 한 건 · 예시 포함"),
    ("20261027_silver_claude_p3_eval039",
     "10/27 실버 초안(Claude) · 안내문 p3 · 평가 T21-039 한 건"),
])
def test_real_run_names(text, name, title):
    assert text.run_label({"name": name}) == {
        "title": title, "subtitle": name, "parts": title.split(" · "),
    }


def test_metadata_wins_without_repeating_name_tokens(text):
    info = {"name": "20261030_sections_gpt_oss_20b_rngd_s2_cw_probe",
            "model_tag": "qwen36_35b_runpod", "prompt_version": "s7",
            "pages_dir": "data/pages/version9/", "started_at": "2026-01-02T03:04:05+09:00",
            "docs": ["T21-X01"]}
    before = copy.deepcopy(info)
    result = text.run_label(info)
    assert result["title"] == "10/30 Qwen3.6 35B (RunPod) · 안내문 s7 · 입력 version9 · 탐색"
    assert info == before
    assert text.run_label(info) == result


@pytest.mark.parametrize("info, title", [
    ({}, ""),
    ({"name": "custom_unknown", "started_at": "2026-02-03T12:00:00+09:00"}, "2/3 · custom · unknown"),
    ({"name": "custom", "started_at": "invalid"}, "custom"),
    ({"name": "20260230_sections_gpt_probe", "started_at": "2026-03-01"}, "3/1 GPT · 탐색"),
    ({"name": "20261030_sections_future_model_s8_v13_new", "model_tag": "future_model"},
     "10/30 future_model · 안내문 s8 · 입력 version13 · new"),
    ({"name": "20261030_sections_claude_p3_dev", "prompt_version": "p3"},
     "10/30 Claude (실버 초안) · 안내문 p3 · 개발 10건"),
    ({"name": "manual/20261030_qwen38_s7_v9_probe", "kind": "manual"},
     "[수동] 10/30 Qwen3.8 27B (vLLM) · 안내문 s7 · 입력 version9 · 탐색"),
    ({"name": "20260102_sections_gpt_s7_chars_wrap_dev10"},
     "1/2 GPT · 안내문 s7 · 입력 chars_wrap · 개발 10건"),
    ({"name": "20261028_sections_qwen3_30b_a3b_rngd_s2_version2_diag2"},
     "10/28 Qwen3 30B (RNGD) · 안내문 s2 · 입력 version2 · 진단 2"),
])
def test_partial_metadata_and_unknown_tokens(text, info, title):
    result = text.run_label(info)
    assert result["title"] == title
    assert result["subtitle"] == info.get("name", "")
    assert result["parts"] == title.split(" · ")


@pytest.mark.parametrize("token, expected", [
    ("eval", "평가 10건"), ("probe3", "탐색 3회"), ("diag", "진단"),
    ("none", "안내문 없음"), ("wsonly", "공백 줄임만"),
    ("m013", "문서 T21-M013 한 건"), ("S003", "문서 T21-S003 한 건"),
    ("s12", "안내문 s12"), ("v2", "입력 version2"), ("unknown", "unknown"),
])
def test_condition_tokens(text, token, expected):
    assert text.run_label({"name": f"20261030_sections_gpt_{token}"})["title"] == f"10/30 GPT · {expected}"
