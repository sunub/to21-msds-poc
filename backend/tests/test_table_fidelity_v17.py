"""v17 source-column, sign protection and pipe-serialization contracts."""
from collections import Counter
from copy import deepcopy
from pathlib import Path
import sys

from msds.preprocess import table_fidelity as tables, source_fidelity as symbols

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import ocr_batch_version17 as runner


def item(text, x, y, width=60):
    return {'text': text, 'box': [x, y, x + width, y + 10]}


def test_borderless_columns_keep_wrapped_names_delayed_aliases_and_blank_identifiers():
    header = ['화학물질명', '관용명 및 이명', 'CAS 번호', '식별번호', '함유량(%)']
    source = [item(t, n * 120, 0) for n, t in enumerate(header)]
    source += [item('Polymer with', 0, 30, 180), item('100-11-1', 240, 30), item('KE-001', 360, 30),
               item('1- <5', 480, 30), item('continued name', 0, 42), item('alias', 120, 55),
               item('Second', 0, 75), item('200-22-2', 240, 75), item('5-10%', 480, 75),
               item('4. 응급조치 요령', 0, 100)]
    saved = deepcopy(source)
    result = tables.resolve_page_data_tables(source, [])
    assert result['regions'][0]['grid'] == [header,
        ['Polymer with continued name', 'alias', '100-11-1', 'KE-001', '1- <5'],
        ['Second', '', '200-22-2', '', '5-10%']]
    assert source == saved
    assert Counter(''.join(i['text'] for i in source).replace(' ', '')) == Counter(''.join(i['text'] for i in result['items']).replace(' ', ''))


def test_transposed_table_requires_identifier_and_concentration_rows():
    source = [item(t, col * 200, row * 20) for row, values in enumerate([
        ['물질명', 'Substance A', 'Substance B'], ['CAS 번호', '100-11-1', '200-22-2'],
        ['함유량(%)', '25%', '75%']]) for col, t in enumerate(values)]
    result = tables.resolve_page_data_tables(source, [])
    assert result['regions'][0]['kind'] == 'transposed_header_table'
    assert result['regions'][0]['grid'][2] == ['함유량(%)', '25%', '75%']
    assert tables.resolve_page_data_tables(source[:6], [])['regions'] == []


def test_ambiguous_prose_or_a_header_without_identifier_values_is_not_a_table():
    source = [item(t, n * 120, 0) for n, t in enumerate(['화학물질명', 'CAS 번호', '함유량'])]
    source += [item('내용 설명', 0, 20), item('자료없음', 120, 20)]
    assert tables.resolve_page_data_tables(source, [])['regions'] == []


def test_category_rowspan_retains_a_covered_first_slot_without_repeating_text():
    header = ['종류', '물질명', 'CAS 번호', '함유량(%)']
    source = [item(t, col * 120, 0) for col, t in enumerate(header)]
    source += [item('TYPE', 0, 20), item('A', 120, 20), item('100-11-1', 240, 20), item('90%', 360, 20),
               item('B', 120, 40), item('200-22-2', 240, 40), item('10%', 360, 40)]
    result = tables.resolve_page_data_tables(source, [])
    assert result['regions'][0]['grid'][2] == ['', 'B', '200-22-2', '10%']
    assert result['regions'][0]['cell_kinds'][2][0] == 'rowspan_covered'
    assert runner.page_text(result['items'], result['tables'], [], False).splitlines()[-1].startswith(' | B |')


def test_pipe_content_is_escaped_without_losing_real_empty_columns():
    source = [item('heading', 0, 0), item('value', 100, 20)]
    grid = [['name', 'empty', 'value'], ['A|B', '', '100-11-1']]
    out = runner.page_text(source, [], [(source, grid)], False).splitlines()
    assert out == ['name | empty | value', r'A\|B |  | 100-11-1']


def test_emergency_code_normalization_does_not_touch_negative_values_ranges_or_formulae():
    source = [item('유출시 비상조치', 0, 0), item('S−V', 200, 0), item('−210 °C', 200, 20),
              item('10–20 %', 200, 40), item('S−V', 200, 60), item('100−11−1', 200, 80)]
    result, audit = symbols.normalize_emergency_codes(source)
    assert result[1]['text'] == 'S-V'
    assert [i['text'] for i in result[2:]] == [i['text'] for i in source[2:]]
    assert source[1]['text'] == 'S−V'
    assert len(audit) == 1


class Page:
    def __init__(self, text):
        self.text = text
    def get_text(self, _):
        return {'blocks': [{'lines': [{'spans': [{'chars': [
            {'c': c, 'bbox': [n * 4, 0, n * 4 + 3, 10]} for n, c in enumerate(self.text)]}]}]}]}


def test_punctuation_repair_requires_source_ascii_alignment_and_preserves_every_other_character():
    source = [item('Alpha:Beta', 0, 0, 100)]
    regions = [{'grid': [['성분', '관용명']], 'cells': [[None, None], [None, {'source_item_indices': [0]}]]}]
    repaired, audit = symbols.repair_ascii_punctuation(source, Page('Alpha;Beta'), 1, regions)
    assert repaired[0]['text'] == 'Alpha;Beta'
    assert source[0]['text'] == 'Alpha:Beta'
    assert audit[0]['changes'][0]['after'] == ';'
    assert symbols.repair_ascii_punctuation(source, Page('Alpha2;Beta'), 1, regions)[1] == []
    assert symbols.repair_ascii_punctuation(source, Page('Alpha;;Beta'), 1, regions)[1] == []
    assert symbols.repair_ascii_punctuation(source, Page('Alpha;Beta'), 1, [])[1] == []
