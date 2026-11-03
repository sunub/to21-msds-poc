"""A2 전달에 필요한 실제 모델 설정 기록."""
import yaml
import pytest

from msds.extract import section_runner


def test_run_info_records_hash_of_actual_model_entry(tmp_path, monkeypatch):
    cfg = {'tag': 'local', 'model': 'm', 'params': {'temperature': 0}, 'run': {'request_timeout': 600}}
    monkeypatch.setattr(section_runner, 'load_model_config', lambda _: dict(cfg))
    monkeypatch.setattr(section_runner, 'prompt_hash', lambda *_: 'f' * 64)
    monkeypatch.setattr(section_runner, '_git_commit', lambda: 'a' * 40)
    section_runner.save_run_info(tmp_path / 'run', 'local', tmp_path / 'pages')
    info = yaml.safe_load((tmp_path / 'run' / 'run_info.yaml').read_text(encoding='utf-8'))
    assert info['model_config_sha256'] == section_runner.model_config_sha256(cfg)
    assert section_runner.model_config_sha256(cfg) == section_runner.model_config_sha256({**cfg, 'run': {}})
    assert section_runner.model_config_sha256(cfg) != section_runner.model_config_sha256({**cfg, 'model': 'other'})


def test_changed_model_config_aborts_before_any_model_request(tmp_path, monkeypatch):
    cfg = {'tag': 'local', 'model': 'm', 'run': {}}
    monkeypatch.setattr(section_runner, 'load_model_config', lambda _: cfg)
    run = tmp_path / 'run'
    run.mkdir()
    (run / 'run_info.yaml').write_text('model_config_sha256: ' + '0' * 64, encoding='utf-8')
    with pytest.raises(RuntimeError, match='모델 설정이 바뀌어'):
        section_runner.run_document('U-20261103-001', 'local', 'run', runs_dir=tmp_path)
