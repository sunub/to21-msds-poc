"""항목별 추출용 모델 태그 설정 확인 (역할 B).

모델 서버와 네트워크를 부르지 않는다. models.yaml만 읽는다.
"""
import pytest

from msds.extract.client import load_model_config

NEW_TAGS = {
    "qwen3_30b_a3b_rngd": ("furiosa-ai/Qwen3-30B-A3B-Instruct-2507-FP8", "RNGD_BASE_URL", "RNGD_API_KEY"),
    "gpt_oss_20b_rngd": ("furiosa-ai/gpt-oss-20b", "RNGD_BASE_URL", "RNGD_API_KEY"),
    "qwen3vl4b_rngd": ("furiosa-ai/Qwen3-VL-4B-Instruct", "RNGD_BASE_URL", "RNGD_API_KEY"),
    "qwen36_35b_runpod": ("Qwen/Qwen3.6-35B-A3B-FP8", "RUNPOD_VLLM_BASE_URL", "RUNPOD_VLLM_API_KEY"),
    "nuextract2_8b_runpod": ("numind/NuExtract-2.0-8B", "RUNPOD_VLLM_BASE_URL", "RUNPOD_VLLM_API_KEY"),
}
RNGD_TAGS = {"qwen3_30b_a3b_rngd", "gpt_oss_20b_rngd", "qwen3vl4b_rngd"}


@pytest.mark.parametrize("tag", NEW_TAGS)
def test_태그가_표와_같다(tag):
    model, base_env, key_env = NEW_TAGS[tag]
    cfg = load_model_config(tag)
    assert cfg["model"] == model
    assert cfg["base_url_env"] == base_env
    assert cfg["api_key_env"] == key_env


@pytest.mark.parametrize("tag", NEW_TAGS)
def test_온도_0과_동시_호출_수(tag):
    cfg = load_model_config(tag)
    assert cfg["params"]["temperature"] == 0
    assert isinstance(cfg["concurrency"], int) and cfg["concurrency"] >= 1
    assert cfg["max_tokens"] == 8192


@pytest.mark.parametrize("tag", NEW_TAGS)
def test_compact는_RNGD_태그에만_있다(tag):
    has = "json_schema_compact" in load_model_config(tag)["structured"]
    assert has == (tag in RNGD_TAGS)


@pytest.mark.parametrize("tag", RNGD_TAGS)
def test_RNGD는_max_completion_tokens를_쓴다(tag):
    assert load_model_config(tag)["token_param"] == "max_completion_tokens"


def test_qwen36은_생각_모드를_끈다():
    cfg = load_model_config("qwen36_35b_runpod")
    assert cfg["params"]["extra_body"]["chat_template_kwargs"]["enable_thinking"] is False


def test_nuextract는_구조화_출력을_쓰지_않는다():
    cfg = load_model_config("nuextract2_8b_runpod")
    assert cfg["structured"] == ["none"]
    assert cfg["request_style"] == "nuextract_template"


@pytest.mark.parametrize("tag,model", [
    ("gpt", "gpt-5.6-sol"),
    ("claude", "claude-fable-5"),
    ("qwen38", "Qwen/Qwen3.8-27B"),
])
def test_기존_태그는_그대로다(tag, model):
    assert load_model_config(tag)["model"] == model
