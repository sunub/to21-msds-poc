"""비교 실험 모델 태그 설정 (역할 B, ADR-010, ADR-011).

모델 서버와 네트워크를 부르지 않는다. configs/models.yaml만 읽는다.
"""
import pytest

from msds.extract.client import load_model_config

NEW_TAGS = ["gemma4_31b_rngd", "qwen3vl4b_rngd", "qwen3vl4b_a100"]


def test_gemma_rngd():
    m = load_model_config("gemma4_31b_rngd")
    assert m["model"] == "furiosa-ai/gemma-4-31B-it-FP8-block"
    assert m["params"] == {"temperature": 0,
                           "extra_body": {"chat_template_kwargs": {"enable_thinking": False}}}


def test_qwen3vl4b_rngd():
    m = load_model_config("qwen3vl4b_rngd")
    assert m["model"] == "furiosa-ai/Qwen3-VL-4B-Instruct"
    assert m["params"] == {"temperature": 0}


def test_qwen3vl4b_a100():
    m = load_model_config("qwen3vl4b_a100")
    assert m["model"] == "Qwen/Qwen3-VL-4B-Instruct"


def test_4b_tags_differ_only_in_model():
    a = load_model_config("qwen3vl4b_rngd")
    b = load_model_config("qwen3vl4b_a100")
    for m in (a, b):
        m.pop("model")
        m.pop("tag")
    assert a == b


@pytest.mark.parametrize("tag", NEW_TAGS)
def test_common_settings(tag):
    m = load_model_config(tag)
    assert m["base_url_env"] == "VLLM_BASE_URL"
    assert m["api_key_env"] == "VLLM_API_KEY"
    assert m["token_param"] == "max_completion_tokens"
    assert m["structured"] == ["json_schema", "none"]
    assert m["max_tokens"] == 32000
    assert m["image_detail"] == "high"
    assert m["evidence_method"] == "vLM"
    assert "fallback_models" not in m


def test_existing_tags_unchanged():
    q = load_model_config("qwen38")
    assert q["model"] == "Qwen/Qwen3.8-27B-FP8"
    assert q["fallback_models"] == ["Qwen/Qwen3.6-27B-FP8"]
    assert "token_param" not in q
    assert load_model_config("gpt")["model"] == "gpt-5.6-sol"
    assert load_model_config("claude")["model"] == "claude-fable-5"


def test_run_settings_unchanged():
    run = load_model_config("qwen38")["run"]
    assert run["max_retries"] == 2
    assert run["request_timeout"] == 600
    assert run["render_dpi"] == 200
