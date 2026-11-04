"""최종 선정 모델 ft_q38의 설정이 개발 채점 때와 같은지 본다 (B-46)."""
from msds.extract.client import load_model_config
from msds.extract.section_runner import model_config_sha256

# 개발 골드 10건 채점(runs/20261104_dev10_ft_q38/run_info.yaml)의 model_config_sha256
DEV_CONFIG_SHA256 = "5d39c9aa2c0c9fbc6abcf4ba0b436d8e810ebe7f06ed944fb96322a3afd1355b"


def test_ft_q38_config_is_the_one_scored_on_dev_docs():
    cfg = load_model_config("ft_q38")
    assert cfg["model"] == "ft"            # vLLM의 --lora-modules 이름
    assert "section_models" not in cfg     # 2항도 LoRA로 보낸다
    assert model_config_sha256(cfg) == DEV_CONFIG_SHA256
