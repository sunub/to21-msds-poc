"""Audited symbol normalization and source-PDF punctuation corroboration."""
from __future__ import annotations

import copy
import re
from . import layout, table_fidelity


def normalize_emergency_codes(items):
    result, audit = copy.deepcopy(items), []
    pattern = re.compile(r'(?<![A-Za-z0-9])([FS])[‐‑‒–—−]([A-Z])(?![A-Za-z0-9])')
    for n, item in enumerate(result):
        if not pattern.search(item['text']):
            continue
        labels = [other for other in items if re.search(r'(?:유출시|화재시)\s*비상조치', other['text'])
                  and layout._same_row(item, other)]
        if not labels:
            continue
        before = item['text']
        item['text'] = pattern.sub(r'\1-\2', before)
        audit.append({'item_index': n, 'before': before, 'after': item['text'], 'box': item['box'],
                      'method': 'ASCII separator normalization only in confirmed emergency-code context',
                      'source_labels': [i['text'] for i in labels]})
    return result, audit


def _ascii_signature(text):
    return ''.join(c for c in text if 33 <= ord(c) <= 126 and c not in ':;')


def repair_ascii_punctuation(items, page, scale, regions):
    """Use native ASCII punctuation only when the whole line's ASCII agrees.

    Some PDFs map Korean glyphs incorrectly but keep ASCII characters intact.
    Matching ASCII content and punctuation count corroborates line alignment.
    Korean characters, numbers, signs, spaces and word spelling never change.
    """
    eligible = set()
    for region in regions:
        roles = [table_fidelity._role(t) for t in region['grid'][0]]
        if 'alias' not in roles:
            continue
        col = roles.index('alias')
        for row in region['cells'][1:]:
            if row[col] is not None:
                eligible.update(row[col]['source_item_indices'])
    chars = []
    for block in page.get_text('rawdict')['blocks']:
        for line in block.get('lines', []):
            for span in line['spans']:
                for char in span['chars']:
                    chars.append({'text': char['c'], 'box': [v * scale for v in char['bbox']]})
    result, audit = copy.deepcopy(items), []
    for index in sorted(eligible):
        item = result[index]
        if ':' not in item['text']:
            continue
        x0, y0, x1, y1 = item['box']
        selected = [c for c in chars if x0 - 1 <= (c['box'][0] + c['box'][2]) / 2 <= x1 + 1
                    and y0 <= (c['box'][1] + c['box'][3]) / 2 <= y1]
        selected.sort(key=lambda c: c['box'][0])
        native = ''.join(c['text'] for c in selected)
        source_punct = [c for c in selected if c['text'] in ':;']
        positions = [n for n, c in enumerate(item['text']) if c in ':;']
        if not positions or len(positions) != len(source_punct):
            continue
        if _ascii_signature(native) != _ascii_signature(item['text']):
            continue
        text = list(item['text'])
        changes = []
        for position, source in zip(positions, source_punct):
            if text[position] != source['text']:
                changes.append({'offset': position, 'before': text[position], 'after': source['text'],
                                'source_box': source['box']})
                text[position] = source['text']
        if not changes:
            continue
        before = item['text']
        item['text'] = ''.join(text)
        audit.append({'item_index': index, 'before': before, 'after': item['text'], 'box': item['box'],
                      'method': 'Native PDF ASCII punctuation; equal ASCII signature and equal punctuation count',
                      'ascii_signature': _ascii_signature(native), 'native_text': native, 'changes': changes})
    return result, audit
