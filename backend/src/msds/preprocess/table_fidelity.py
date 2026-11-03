"""v17 table reconstruction from source headers, coordinates and source items.

No document IDs, fixture answers, old TXT or Markdown are extraction inputs.
Native ruled/continued tables retain the v16 implementation. A conservative
header-based fallback handles composition tables missed by the line detector.
"""
from __future__ import annotations

import bisect
import re
import statistics
from . import layout

CAS = re.compile(r'(?<!\d)\d{2,7}-\d{2}-\d(?!\d)')


def _role(text):
    s = re.sub(r'\s+', '', text).casefold()
    if 'cas' in s:
        return 'cas'
    if any(k in s for k in ('함유량', '농도', 'conc.', 'concentration')):
        return 'quantity'
    if any(k in s for k in ('관용명', '이명', 'synonym')):
        return 'alias'
    if any(k in s for k in ('식별번호', '식별번호', '제품식별', 'identification')):
        return 'identifier'
    if s in ('종류', 'type', 'grade'):
        return 'category'
    if s in ('물질명', '화학물질명', '성분', '성분명', 'ingredients', 'ingredient'):
        return 'name'
    return None


def _boundary(text):
    s = text.strip()
    return (layout._is_section_heading(s) or bool(re.match(r'^SECTION\s+\d+\b', s, re.I))
            or s.startswith(('※', 'KO (', 'MSDS KOREA')))


def _text(items, indices):
    members = [items[i] for i in indices]
    return ' '.join(i['text'].strip() for row in layout._rows(members) for i in row)


def _fallback_regions(items, consumed):
    source = [i for n, i in enumerate(items) if n not in consumed and i['text'].strip()]
    if not source:
        return []
    indices = {id(item): n for n, item in enumerate(items)}
    physical = layout._rows(source)
    height = statistics.median(i['box'][3] - i['box'][1] for i in source)
    regions = []
    for row_index, header in enumerate(physical):
        header = sorted(header, key=lambda i: i['box'][0])
        if not 3 <= len(header) <= 12 or any(indices[id(i)] in consumed for i in header):
            continue
        roles = [_role(i['text']) for i in header]
        normal = ('name' in roles and 'quantity' in roles and ('cas' in roles or 'identifier' in roles)
                  and all(r is not None for r in roles))
        transpose = roles[0] == 'name' and all(r is None for r in roles[1:])
        if not normal and not transpose:
            continue
        after = []
        bottom = max(i['box'][3] for i in header)
        for row in physical[row_index + 1:]:
            if any(_boundary(i['text']) for i in row):
                break
            if min(i['box'][1] for i in row) - bottom > 3 * height:
                break
            if any(indices[id(i)] in consumed for i in row):
                break
            after.extend(row)
            bottom = max(i['box'][3] for i in row)
        if not after:
            continue
        edges = [min(header[0]['box'][0], min(i['box'][0] for i in after))]
        edges += [(a['box'][2] + b['box'][0]) / 2 for a, b in zip(header, header[1:])]
        edges += [max(header[-1]['box'][2], max(i['box'][2] for i in after))]
        if any(a >= b for a, b in zip(edges, edges[1:])):
            continue
        def column(item):
            return min(len(header) - 1, max(0, bisect.bisect_right(edges[1:-1], item['box'][0])))
        groups = []
        if transpose:
            rows = layout._rows(after)
            if not {'cas', 'quantity'} <= {_role(r[0]['text']) for r in rows}:
                continue
            if any(len(r) != len(header) for r in rows):
                continue
            groups = [[indices[id(i)] for i in r] for r in rows]
        else:
            name_col = roles.index('name')
            id_col = roles.index('cas') if 'cas' in roles else roles.index('identifier')
            anchors = []
            for i in after:
                if column(i) != id_col or not CAS.search(i['text']):
                    continue
                peers = [p for p in after if column(p) == name_col and layout._same_row(i, p)]
                if peers:
                    anchors.append(min([i['box'][1], *[p['box'][1] for p in peers]]))
            anchors = sorted(set(anchors))
            if not anchors:
                continue
            groups = [[] for _ in anchors]
            for i in after:
                row_n = max(0, bisect.bisect_right(anchors, i['box'][1] + height * 0.25) - 1)
                groups[row_n].append(indices[id(i)])
        header_ids = [indices[id(i)] for i in header]
        all_groups = [header_ids, *groups]
        cells, kinds = [], []
        for n, group in enumerate(all_groups):
            top = min(items[i]['box'][1] for i in group)
            end = max(items[i]['box'][3] for i in group)
            row, row_kinds = [], []
            for col in range(len(header)):
                ids = [i for i in group if (header_ids.index(i) if n == 0 else column(items[i])) == col]
                text = _text(items, ids)
                kind = 'text' if text else 'empty'
                if n > 1 and roles[col] == 'category' and not text and cells[n - 1][col]['text']:
                    kind = 'rowspan_covered'
                row.append({'text': text, 'box': [edges[col], top, edges[col + 1], end],
                            'source_item_indices': ids})
                row_kinds.append(kind)
            cells.append(row)
            kinds.append(row_kinds)
        used = {i for group in all_groups for i in group}
        if consumed.intersection(used):
            continue
        consumed.update(used)
        regions.append({'kind': 'transposed_header_table' if transpose else 'coordinate_header_table',
                        'source_table_index': -1, 'table': [[c['box'] for c in r] for r in cells],
                        'cells': cells, 'grid': [[c['text'] for c in r] for r in cells],
                        'cell_kinds': kinds, 'box': [edges[0], min(items[i]['box'][1] for i in used),
                                                   edges[-1], max(items[i]['box'][3] for i in used)],
                        'source_item_indices': sorted(used), 'schema_source_page': None})
    return regions


def resolve_page_data_tables(items, tables, previous_schema=None):
    base = layout.resolve_page_data_tables(items, tables, previous_schema)
    consumed = set(base['source_data_indices'])
    extra = _fallback_regions(items, consumed)
    if not extra:
        return base
    regions = base['regions'] + extra
    atoms = []
    for ri, region in enumerate(regions):
        for rn, row in enumerate(region['cells']):
            present = [c for c in row if c is not None]
            ids = [i for c in present for i in c['source_item_indices']]
            if not ids:
                continue
            parts = [{'text': c['text'], 'x0': c['box'][0], 'x1': c['box'][2],
                      'source_item_indices': c['source_item_indices']} for c in present]
            boxes = [c['box'] for c in present]
            atoms.append({'text': '  '.join(c['text'] for c in present), 'parts': parts,
                          'box': [min(b[0] for b in boxes), min(b[1] for b in boxes),
                                  max(b[2] for b in boxes), max(b[3] for b in boxes)],
                          'table_row': ['v17', ri, rn], 'source_item_indices': ids})
    def overlap(table, region):
        boxes = [c for row in table for c in row if c]
        a, b, c, d = region['box']
        return (min(max(x[2] for x in boxes), c) > max(min(x[0] for x in boxes), a)
                and min(max(x[3] for x in boxes), d) > max(min(x[1] for x in boxes), b))
    remaining = [t for t in base['tables'] if not any(overlap(t, r) for r in extra)]
    body = [i for n, i in enumerate(items) if n not in consumed]
    return {**base, 'items': body + atoms, 'body_items': body, 'tables': remaining,
            'regions': regions, 'source_data_indices': sorted(consumed)}
