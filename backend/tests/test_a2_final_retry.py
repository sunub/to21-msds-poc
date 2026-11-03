"""Final validation can retry one located section without private TO21 assets."""
import json
from types import SimpleNamespace
import pytest

from msds.extract import section_runner as runner


@pytest.mark.parametrize('retry_name,accepted', [('수정', True), ('여전히오류', False)])
def test_final_validator_error_retries_once_and_keeps_improved_result(tmp_path, monkeypatch,
                                                                     retry_name, accepted):
    cfg = {'model': 'fake', 'rows_sections': [], 'concurrency': 1}
    first = {'ok': True, 'parsed': {'name': '원본'}, 'raw_text': '원본', 'mode': 'json_object',
             'finish_reason': 'stop', 'usage': {}, 'attempts': 1, 'errors': [], 'requests': [],
             'seconds': .1, 'check_problems': []}
    retry = {**first, 'parsed': {'name': retry_name}, 'raw_text': retry_name}
    calls = []
    document = SimpleNamespace(doc_id='U-20261103-001', msds=[SimpleNamespace(index=0)],
                               lines=[], warnings=[], sections_method='test')
    monkeypatch.setattr(runner, 'EXTRACT_SECTIONS', (1,))
    monkeypatch.setattr(runner, 'SKIPPED_SECTIONS', ())
    monkeypatch.setattr(runner, 'load_model_config', lambda tag: cfg)
    monkeypatch.setattr(runner.manifest, 'get', lambda doc_id: {})
    monkeypatch.setattr(runner, 'load_document', lambda *args: document)
    monkeypatch.setattr(runner, 'section_plan', lambda doc: {'type': 'plan', 'sections': []})
    monkeypatch.setattr(runner, 'build_system', lambda *args: 'system')
    monkeypatch.setattr(runner, 'response_schema', lambda no: {})
    monkeypatch.setattr(runner, 'model_lines', lambda *args: [])
    monkeypatch.setattr(runner, 'section_lines', lambda *args, **kwargs: [])
    monkeypatch.setattr(runner, '_run_section', lambda *args: (
        runner.SectionResult(0, 1, first['parsed'], True, [], .1, {}, 1, False), first, None))
    monkeypatch.setattr(runner, '_attempt', lambda *args: (calls.append(args), retry)[1])
    monkeypatch.setattr(runner, 'to_to21', lambda row, parts, lines, model: (
        {'msds': [{'product': {'name': parts[0][1]['name']}}]}, []))
    monkeypatch.setattr(runner, 'validate_to21', lambda out: [])
    monkeypatch.setattr(runner, 'run_to21_validator', lambda out: (
        [] if out['msds'][0]['product']['name'] == '수정' else [
            {'level': '오류', 'field': 'msds[0].product.name', 'message': '값 확인'}]))
    monkeypatch.setattr(runner, 'load_hazard_map', lambda: {})
    monkeypatch.setattr(runner, 'check_msds', lambda msds, hazard_map: {'ok': True})
    events = []
    summary = runner.run_document(document.doc_id, 'fake', document.doc_id, client=object(),
                                  pages_dir=tmp_path, sections_dir=tmp_path, runs_dir=tmp_path,
                                  on_event=events.append)
    checks = json.loads((tmp_path / document.doc_id / 'checks' / f'{document.doc_id}.json').read_text())
    raw = json.loads(runner.raw_path(tmp_path / document.doc_id, document.doc_id, 0, 1).read_text())
    assert len(calls) == 1
    assert summary['reextracted'] == int(accepted) and summary['schema_errors'] == 0
    assert len(checks['to21_validator']) == int(not accepted)
    assert raw['parsed'] == {'name': '수정' if accepted else '원본'}
    assert 'final_validation_attempt' in raw
    assert any(e['type'] == 'section_done' and e['reextracted'] for e in events) == accepted
