"""읽기 순서: 글 조각의 상자 좌표 → 사람이 읽는 순서의 줄 목록 (recursive XY-cut).

텍스트층(PyMuPDF 줄, pt)과 OCR 조각(dpi 픽셀)에 똑같이 쓴다. 조각은 {"text", "box": [x0, y0, x1, y1]}.
PDF에 저장된 순서는 사람이 읽는 순서와 다를 수 있다 (S001 2쪽: 2번 항목 본문이 1번보다 먼저 저장돼 있다).

문서마다 양식이 달라 픽셀 기준값을 두지 않는다. 기준값은 모두 그 쪽 조각 높이의 중앙값(h)에 대한 배수다.
1. 영역을 가로지르는 빈 띠 중 가장 넓은 곳에서 자르고, 나뉜 양쪽을 다시 자른다
   - 가로 띠(줄 사이)는 위아래로, 세로 띠(GUTTER×h 이상)는 좌우로 나눈다
   - 세로 띠 양쪽의 줄 높이가 맞으면(항목명|값, 표의 행) 단이 아니라 한 줄이므로 좌우로 자르지 않는다
2. 더 자를 수 없는 영역은 줄로 묶어 위에서 아래, 줄 안에서는 왼쪽에서 오른쪽으로 읽는다

한계: 두 단 본문의 줄 높이가 양쪽에서 똑같이 맞으면 단으로 보지 않고 줄마다 좌우를 이어 읽는다.
"""
from __future__ import annotations

import re
import statistics
import unicodedata

SHRINK = 0.15      # 위아래로 상자 높이의 이 비율만큼 줄여서 본다 (조금 겹쳐 잡힌 이웃 줄을 떼어 낸다)
GUTTER = 1.0       # 세로 빈 띠가 조각 높이의 이 배수 이상이어야 단 사이로 본다 (낱말 사이는 이보다 좁다)
ALIGNED = 0.5      # 적은 쪽 조각의 이 비율 이상이 반대쪽 조각과 높이가 겹치면 단이 아니라 한 줄이다


def _y(it: dict) -> tuple[float, float]:
    y0, y1 = it["box"][1], it["box"][3]
    d = (y1 - y0) * SHRINK
    return y0 + d, y1 - d


def _gaps(spans: list[tuple[float, float]], min_gap: float) -> list[tuple[float, float]]:
    """구간들을 투영했을 때 min_gap보다 넓은 빈 곳. (가운데 좌표, 너비) 목록."""
    cuts = []
    spans = sorted(spans)
    end = spans[0][1]
    for a, b in spans[1:]:
        if a - end > min_gap:
            cuts.append(((end + a) / 2, a - end))
        end = max(end, b)
    return cuts


def _split(items: list[dict], cuts: list[float], key) -> list[list[dict]]:
    parts: list[list[dict]] = [[] for _ in range(len(cuts) + 1)]
    for it in items:
        parts[sum(1 for c in cuts if key(it) > c)].append(it)
    return [p for p in parts if p]


def _same_row(a: dict, b: dict) -> bool:
    """a의 세로 중심이 b의 높이 안에 든다. 조금 겹치기만 한 어긋난 줄은 같은 줄이 아니다."""
    y0, y1 = _y(b)
    return y0 <= sum(_y(a)) / 2 <= y1


def _aligned(parts: list[list[dict]]) -> bool:
    """좌우로 나눈 부분들의 줄 높이가 맞는가 (항목명|값, 표의 행)."""
    for left, right in zip(parts, parts[1:]):
        small, big = sorted([left, right], key=len)
        hit = sum(1 for a in small if any(_same_row(a, b) for b in big))
        if hit / len(small) < ALIGNED:
            return False
    return True


def _rows(items: list[dict]) -> list[list[dict]]:
    """더 자를 수 없는 영역을 줄로 묶는다. 세로 중심이 줄의 높이 안에 들면 같은 줄이다."""
    rows: list[dict] = []
    for it in sorted(items, key=lambda i: i["box"][1]):
        cy = (it["box"][1] + it["box"][3]) / 2
        for r in rows:
            if r["y0"] <= cy <= r["y1"]:
                r["items"].append(it)
                break
        else:
            rows.append({"y0": it["box"][1], "y1": it["box"][3], "items": [it]})
    return [sorted(r["items"], key=lambda i: i["box"][0]) for r in rows]


_SUBHEADING_NAMES = frozenset({"신호어", "유해위험문구", "예방조치문구", "signalword",
                              "hazardstatements", "precautionarystatements"})


def _subheading_cut(items: list[dict], gaps: list[tuple[float, float]], h: float) -> float | None:
    """짧은 GHS 소제목 바로 위를 가로지르는 실제 빈 띠가 있으면 읽기 영역을 나눈다.

    본문 속 단어는 경계가 아니다. 조각 전체가 표준 소제목이고 그 위에 영역 전체의 빈 띠가 있어야 한다.
    이 경계를 먼저 따르면 앞의 H 문구를 다음 P 문구 구역의 왼쪽 라벨 뒤로 보내지 않는다.
    """
    boundaries = []
    for item in items:
        name = re.sub(r"[\s·ㆍ•∙:：]", "", unicodedata.normalize("NFKC", item["text"])).casefold()
        if name not in _SUBHEADING_NAMES:
            continue
        top = _y(item)[0]
        boundaries.extend(center for center, width in gaps if abs(center + width / 2 - top) <= 0.25 * h)
    return min(boundaries, default=None)


def _cut(items: list[dict], h: float, *, repair_table_layout: bool = False) -> list[list[dict]]:
    """가장 넓은 빈 띠 한 곳에서 자르고 양쪽을 다시 자른다.

    한 번에 모든 줄 사이를 자르면 두 단 본문이 줄마다 잘려 좌우가 섞인다. 단 사이 띠는 줄 사이보다 넓어서
    가장 넓은 곳부터 자르면 단이 먼저 떨어진다.
    """
    if len(items) == 1:
        return [items]
    ys = _gaps([_y(i) for i in items], 0)
    boundary = _subheading_cut(items, ys, h) if repair_table_layout else None
    if boundary is not None:
        top, bottom = _split(items, [boundary], lambda i: sum(_y(i)) / 2)
        return (_cut(top, h, repair_table_layout=repair_table_layout)
                + _cut(bottom, h, repair_table_layout=repair_table_layout))
    xs = [g for g in _gaps([(i["box"][0], i["box"][2]) for i in items], GUTTER * h)]
    x_cut = None
    if xs:
        cut, width = max(xs, key=lambda g: g[1])
        cols = _split(items, [cut], lambda i: (i["box"][0] + i["box"][2]) / 2)
        if not _aligned(cols):
            x_cut = (cols, width)
    y_width = max((g[1] for g in ys), default=None)
    if x_cut and (y_width is None or x_cut[1] > y_width):
        return [row for c in x_cut[0] for row in _cut(c, h, repair_table_layout=repair_table_layout)]
    if ys:
        cut = max(ys, key=lambda g: g[1])[0]
        top, bottom = _split(items, [cut], lambda i: sum(_y(i)) / 2)
        return (_cut(top, h, repair_table_layout=repair_table_layout)
                + _cut(bottom, h, repair_table_layout=repair_table_layout))
    return _rows(items)


def _inside(it: dict, box) -> bool:
    cx, cy = (it["box"][0] + it["box"][2]) / 2, (it["box"][1] + it["box"][3]) / 2
    return box[0] <= cx <= box[2] and box[1] <= cy <= box[3]


def _table_rows(items: list[dict], tables: list[list[list]], *, preserve_empty_cells: bool = False) -> list[dict]:
    """선으로 그린 표의 한 행에 든 조각을 칸 순서대로 이어 조각 하나로 바꾼다.

    칸 안 줄 간격과 행 사이 간격이 같으면 위치만으로는 행 경계를 알 수 없다 (M005 2쪽: 6.8pt / 7.1pt).
    여러 줄 칸 옆에 한 줄 칸이 있으면 줄로 읽을 때 칸끼리 섞이므로, 그려진 선이 정한 칸 경계를 따른다.
    글이 든 칸이 둘 이상인 행만 바꾼다. 칸 사이는 공백 두 칸으로 띄운다 (글자는 그대로 둔다).
    preserve_empty_cells이면 데이터 표의 빈 칸도 parts에 남긴다. 항목 틀의 가상 열과 합친 칸의 None은 제외한다.
    """
    used: set[int] = set()
    merged = []
    for table_index, table in enumerate(tables):
        keep_empty = preserve_empty_cells and is_data_table(table_grid(items, table))
        for row_index, row in enumerate(table):
            cells = []
            cell_boxes = []
            for box in sorted((c for c in row if c), key=lambda c: c[0]):
                members = [i for i in items if id(i) not in used and _inside(i, box)]
                if members or keep_empty:
                    cells.append(members)
                    cell_boxes.append(box)
                    used.update(id(i) for i in members)
            if len(cells) < 2 or not any(cells):
                for members in cells:    # 칸 하나뿐이면 그대로 두고 XY-cut에 맡긴다
                    used.difference_update(id(i) for i in members)
                continue
            boxes = [i["box"] for c in cells for i in c]
            parts = [{"text": " ".join(i["text"].strip() for r in _rows(c) for i in r),
                      "x0": min((i["box"][0] for i in c), default=box[0]),
                      "x1": max((i["box"][2] for i in c), default=box[2])}
                     for c, box in zip(cells, cell_boxes)]
            merged_item = {"text": "  ".join(p["text"] for p in parts), "parts": parts,
                           "box": [min(b[0] for b in boxes), min(b[1] for b in boxes),
                                   max(b[2] for b in boxes), max(b[3] for b in boxes)]}
            if preserve_empty_cells:
                # 실제 칸 경계가 있는 행은 빈 칸 때문에 이웃 행과 합치지 않는다.
                merged_item["table_row"] = [table_index, row_index]
            merged.append(merged_item)
    return [i for i in items if id(i) not in used] + merged


def page_tables(page, scale: float = 1.0) -> list[list[list]]:
    """PyMuPDF 쪽에서 선으로 그린 표 → 표마다 행 목록, 행마다 칸 상자 (합친 칸 자리는 None).

    scale은 조각 좌표 단위로 바꾸는 배수다 (OCR 조각이면 dpi/72).
    """
    return [[[None if c is None else [v * scale for v in c] for c in r.cells] for r in t.rows]
            for t in page.find_tables().tables]


HEADER_MAX = 30   # 머리글 칸 글자 수 상한. 이보다 길면 머리글이 아니라 값이다


def table_grid(items: list[dict], table: list[list]) -> list[list[str]]:
    """선으로 그린 표 하나(page_tables의 한 표) → 행마다 칸 글. 합친 칸 자리(None)와 빈 칸은 ""."""
    items = [i for i in items if i["text"].strip()]
    grid = []
    for row in table:
        cells = []
        for box in row:
            members = [i for i in items if box and _inside(i, box)]
            cells.append(" ".join(i["text"].strip() for r in _rows(members) for i in r))
        grid.append(cells)
    return grid


def is_data_table(grid: list[list[str]]) -> bool:
    """데이터 표(성분·노출기준·NFPA 등)인가, 항목|값을 담는 틀인가.

    데이터 표는 3열 이상이고 첫 행이 머리글이다. 머리글은 칸 둘 이상에 짧은 이름이 들고 숫자가 없다.
    2열 표, 첫 행이 항 제목 한 칸뿐인 표, 첫 행부터 값(숫자·문장)이 든 표는 틀로 본다
    (개발 문서 2026-10-28: '특성|제품', 'H335|문구', '16 기타 참고사항', 전화번호 목록).
    """
    if not grid or len(grid[0]) < 3:
        return False
    head = [c for c in grid[0] if c.strip()]
    return len(head) >= 2 and all(len(c) <= HEADER_MAX and not any(ch.isdigit() for ch in c) for c in head)


def table_columns(table: list[list]) -> list[tuple[float, float]]:
    """표의 열 자리 (x0, x1). 열마다 합치지 않은 칸들의 좌우 끝."""
    return [(min(r[c][0] for r in table if r[c]), max(r[c][2] for r in table if r[c]))
            for c in range(len(table[0]))]


def continue_grid(items: list[dict], table: list[list], cols: list[tuple[float, float]],
                  head: list[str]) -> list[list[str]] | None:
    """앞 쪽 데이터 표가 이 쪽에서 이어지는데 열 선이 없는 경우, 앞 쪽 열 자리로 칸을 나눈다.

    M013 3쪽: 성분 표가 머리글을 되풀이하며 이어지지만 열 선이 없어 2열로만 잡힌다.
    행 자리는 이 쪽에 그려진 행 선을 따른다. 첫 행이 앞 쪽 머리글과 같아야 이어진 표로 본다.
    글이 든 칸이 하나뿐인 행(다음 항 제목)에서 표가 끝난다. 아니면 None.
    """
    x0 = min(c[0] for r in table for c in r if c)
    x1 = max(c[2] for r in table for c in r if c)
    edges = [(x0 if i == 0 else a, x1 if i == len(cols) - 1 else b) for i, (a, b) in enumerate(cols)]
    rows = []
    for r in table:
        y0, y1 = min(c[1] for c in r if c), max(c[3] for c in r if c)
        rows.append([[a, y0, b, y1] for a, b in edges])
    grid = table_grid(items, rows)
    same = "".join("".join(c.split()) for c in grid[0]) == "".join("".join(c.split()) for c in head)
    if not same:
        return None
    end = next((i for i, r in enumerate(grid) if i and sum(1 for c in r if c.strip()) < 2), len(grid))
    return grid[:end]


def _data_cells(items: list[dict], table: list[list], *, leading_edge: bool = False) -> list[list[dict | None]]:
    """조각 하나를 한 셀에만 배정한다. 긴 이름도 글자 단위로 쪼개지 않는다.

    복원한 열에서는 조각의 시작 x를 쓴다. 빈 옆 칸까지 길게 인쇄된 이름의 중심으로 열을 바꾸지 않기 위해서다.
    y는 줄의 중심을 써서 글자 상자가 가로 선을 약간 넘는 경우를 허용한다.
    """
    cells = [[None if box is None else {"box": list(box), "source_item_indices": []} for box in row]
             for row in table]
    for index, item in enumerate(items):
        if not item["text"].strip():
            continue
        x = item["box"][0] if leading_edge else (item["box"][0] + item["box"][2]) / 2
        y = (item["box"][1] + item["box"][3]) / 2
        for row in cells:
            target = next((cell for cell in row if cell is not None
                           and cell["box"][0] - 1e-3 <= x <= cell["box"][2] + 1e-3
                           and cell["box"][1] <= y <= cell["box"][3]), None)
            if target is not None:
                target["source_item_indices"].append(index)
                break
    for row in cells:
        for cell in row:
            if cell is not None:
                members = [items[i] for i in cell["source_item_indices"]]
                cell["text"] = " ".join(i["text"].strip() for line in _rows(members) for i in line)
    return cells


def _cell_grid(cells: list[list[dict | None]]) -> list[list[str]]:
    return [[cell["text"] if cell is not None else "" for cell in row] for row in cells]


def _continued_data_geometry(items: list[dict], table: list[list], schema: dict) -> list[list] | None:
    """직전 쪽의 명시적 열 이름이 같은 위치에서 반복될 때만 연속 표의 실제 영역을 복원한다."""
    cols, head = schema.get("cols", []), schema.get("head", [])
    if len(cols) < 3 or len(cols) != len(head) or not all(str(c).strip() for c in head):
        return None
    if any(a >= b for a, b in cols) or any(a[1] > b[0] + 1e-3 for a, b in zip(cols, cols[1:])):
        return None
    rows = []
    for row in table:
        boxes = [c for c in row if c is not None]
        if not boxes:
            break
        top, bottom = min(c[1] for c in boxes), max(c[3] for c in boxes)
        rows.append([[left, top, right, bottom] for left, right in cols])
    cells = _data_cells(items, rows, leading_edge=True)
    grid = _cell_grid(cells)
    norm = lambda value: "".join(unicodedata.normalize("NFKC", value).split())
    if not grid or list(map(norm, grid[0])) != list(map(norm, head)):
        return None
    end = len(rows)
    for index, row in enumerate(cells[1:], 1):
        members = [items[i] for cell in row if cell is not None for i in cell["source_item_indices"]]
        if any(_is_section_heading(i["text"]) for i in members) or sum(bool(c.strip()) for c in grid[index]) < 2:
            end = index
            break
    return rows[:end] if end >= 2 else None


def _logical_data_geometry(items: list[dict], table: list[list]) -> list[list]:
    """본문 셀이 덮는 머리글의 여백 조각만 합쳐 실제 열을 복원한다.

    글이 든 머리글 두 개를 덮는 본문 셀은 진짜 병합 셀이다. 그 셀로 열을 합치지 않는다.
    열 이름이 있는 빈 데이터 열은 남기고, 머리글·본문 모두 빈 여백 조각만 제외한다.
    """
    if len(table) < 2 or len(table[0]) < 3 or any(box is None for box in table[0]):
        return table
    cells = _data_cells(items, table)
    head = cells[0]
    if sum(bool(cell["text"]) for cell in head) < 2:
        return table
    parent = list(range(len(head)))

    def find(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for row in table[1:]:
        for box in row:
            if box is None:
                continue
            hits = [index for index, cell in enumerate(head)
                    if min(box[2], cell["box"][2]) - max(box[0], cell["box"][0]) > 1e-3]
            if len(hits) > 1 and sum(bool(head[i]["text"]) for i in hits) <= 1:
                for index in hits[1:]:
                    parent[find(index)] = find(hits[0])
    groups = []
    for index in range(len(head)):
        if not groups or find(index) != find(groups[-1][0]):
            groups.append([])
        groups[-1].append(index)
    groups = [group for group in groups
              if any(row[i] is not None and row[i]["text"] for row in cells for i in group)]
    if len(groups) < 3 or (len(groups) == len(head) and all(len(g) == 1 for g in groups)):
        return table
    cols = [[head[group[0]]["box"][0], head[group[-1]]["box"][2]] for group in groups]
    cols[0][0], cols[-1][1] = head[0]["box"][0], head[-1]["box"][2]
    # 제거한 빈 여백은 앞 셀의 빈 가장자리다. 데이터 값을 옮기거나 복제하지 않는다.
    for previous, following in zip(cols, cols[1:]):
        previous[1] = following[0]
    rows = []
    for row in table:
        boxes = [box for box in row if box is not None]
        top, bottom = min(b[1] for b in boxes), max(b[3] for b in boxes)
        resolved = [[left, top, right, bottom] for left, right in cols]
        for box in boxes:
            covered = [index for index, (left, right) in enumerate(cols)
                       if box[0] <= left + 1e-3 and box[2] >= right - 1e-3]
            if len(covered) > 1:
                first, last = covered[0], covered[-1]
                resolved[first] = [cols[first][0], top, cols[last][1], bottom]
                for index in covered[1:]:
                    resolved[index] = None
        rows.append(resolved)
    return rows


def _join_data_name_rows(items: list[dict], table: list[list]) -> list[list]:
    """가까운 이름 줄이 명시적 연결어 뒤에서 이어질 때만 하나의 성분 행으로 묶는다.

    detector가 텍스트 줄을 행으로 잘랐지만 다른 식별 값은 앞 줄에만 있는 경우다.
    빈 CAS를 가진 별도 성분이나 전체 폭 설명행을 일반적으로 앞 행에 합치지 않는다.
    """
    rows = [[None if box is None else list(box) for box in row] for row in table]
    index = 2
    while index < len(rows):
        cells = _data_cells(items, rows, leading_edge=True)
        previous, current = cells[index - 1], cells[index]
        before = [c for c in previous if c is not None and c["text"]]
        after = [c for c in current if c is not None and c["text"]]
        if (len(before) >= 3 and len(after) == 1 and current[0] is after[0]
                and previous[0] is not None and all(c is not None for c in current)
                and re.search(r"(?:\b(?:and|or)|[,\-])\s*$", previous[0]["text"], re.IGNORECASE)
                and re.match(r"^[a-z]", after[0]["text"])):
            first_items = [items[i] for i in previous[0]["source_item_indices"]]
            tail_items = [items[i] for i in after[0]["source_item_indices"]]
            h = statistics.median(i["box"][3] - i["box"][1] for i in first_items + tail_items)
            gap = min(i["box"][1] for i in tail_items) - max(i["box"][3] for i in first_items)
            same_start = abs(min(i["box"][0] for i in tail_items) - min(i["box"][0] for i in first_items)) <= h / 2
            if same_start and 0 <= gap <= h / 2:
                bottom = max(c[3] for c in rows[index] if c is not None)
                for box in rows[index - 1]:
                    if box is not None:
                        box[3] = bottom
                rows.pop(index)
                continue
        index += 1
    return rows


def resolve_page_data_tables(items: list[dict], tables: list[list[list]], previous_schema: dict | None = None) -> dict:
    """v16: TXT·MD·근거 상자가 공유하는 데이터 표 셀과 읽기 조각을 만든다.

    이전 쪽의 명시적 머리글을 첫 표에서 열별로 재확인한 경우에만 연속 표를 복원한다.
    그 밖의 표는 기존 데이터 표 판별과 항 제목 침범 검사를 따른다. 빈 실제 셀과 병합 None을 구별한다.
    원본 items·tables는 바꾸지 않으며, body_items는 원래 객체를 유지해 Docling의 중복 소비를 막는다.
    """
    regions, consumed = [], set()
    order = sorted(range(len(tables)), key=lambda n: min((c[1], c[0]) for r in tables[n] for c in r if c))
    for position, table_index in enumerate(order):
        original = tables[table_index]
        restored = (_continued_data_geometry(items, original, previous_schema)
                    if position == 0 and previous_schema else None)
        normalized = _logical_data_geometry(items, original) if restored is None else original
        geometry = _join_data_name_rows(items, restored or normalized)
        cells = _data_cells(items, geometry, leading_edge=restored is not None or normalized is not original)
        grid = _cell_grid(cells)
        if not is_data_table(grid) or _table_crosses_heading(items, geometry):
            continue
        indices = {i for row in cells for cell in row if cell is not None for i in cell["source_item_indices"]}
        if not indices or indices.intersection(consumed):
            continue
        boxes = [c for row in geometry for c in row if c is not None]
        region = {"kind": "continued_data_table" if restored is not None else "ruled_data_table",
                  "source_table_index": table_index, "table": geometry, "cells": cells, "grid": grid,
                  "cell_kinds": [["merged" if c is None else "text" if c["text"] else "empty" for c in row]
                                 for row in cells],
                  "box": [min(c[0] for c in boxes), min(c[1] for c in boxes),
                          max(c[2] for c in boxes), max(c[3] for c in boxes)],
                  "source_item_indices": sorted(indices),
                  "schema_source_page": previous_schema.get("source_page") if restored is not None else None}
        regions.append(region)
        consumed.update(indices)

    atoms = []
    for region_index, region in enumerate(regions):
        for row_index, row in enumerate(region["cells"]):
            present = [c for c in row if c is not None]
            indices = [i for cell in present for i in cell["source_item_indices"]]
            if not indices:
                continue
            parts = [{"text": c["text"], "x0": c["box"][0], "x1": c["box"][2],
                      "source_item_indices": c["source_item_indices"]} for c in present]
            boxes = [c["box"] for c in present]
            atoms.append({"text": "  ".join(c["text"] for c in present), "parts": parts,
                          "box": [min(c[0] for c in boxes), min(c[1] for c in boxes),
                                  max(c[2] for c in boxes), max(c[3] for c in boxes)],
                          "table_row": ["resolved", region_index, row_index],
                          "source_item_indices": indices})

    def overlaps(table, region):
        boxes = [c for row in table for c in row if c is not None]
        left, top = min(c[0] for c in boxes), min(c[1] for c in boxes)
        right, bottom = max(c[2] for c in boxes), max(c[3] for c in boxes)
        a, b, c, d = region["box"]
        return min(right, c) > max(left, a) and min(bottom, d) > max(top, b)

    remaining = [table for table in tables if not any(overlaps(table, region) for region in regions)]
    body = [item for index, item in enumerate(items) if index not in consumed]
    next_schema = None
    for region in regions:
        head, row = region["grid"][0], region["table"][0]
        # 머리글에 이름이 없는 가상 열, 병합 칸, 본문 값으로 열 schema를 만들지 않는다.
        if len(head) >= 3 and all(head) and all(box is not None for box in row):
            cols = [(box[0], box[2]) for box in row]
            if all(a[1] <= b[0] + 1e-3 for a, b in zip(cols, cols[1:])):
                next_schema = {"cols": cols, "head": list(head)}
    return {"items": body + atoms, "body_items": body, "tables": remaining, "regions": regions,
            "next_schema": next_schema, "source_data_indices": sorted(consumed)}


def table_md(grid: list[list[str]]) -> str:
    """칸 격자 → Markdown 표. 첫 행을 머리글로 쓴다. 칸 안의 '|'는 '\\|'로 바꾼다."""
    def line(cells):
        return "| " + " | ".join(c.replace("|", "\\|") for c in cells) + " |\n"
    return line(grid[0]) + line(["---"] * len(grid[0])) + "".join(line(r) for r in grid[1:])


# MSDS 1~16항 제목에 들어가는 낱말 (문서마다 표현이 조금씩 다르다: '응급조치요령'/'응급처치요령', '안정성'/'안전성')
SECTION_WORDS = {
    1: ("화학제품", "identification"),
    # 2013년 이전 구양식은 2항이 구성성분, 3항이 유해·위험성이다. 번호는 원문대로 보존한다.
    2: ("유해", "위험", "hazard", "구성성분", "구성 성분", "composition", "ingredient"),
    3: ("구성성분", "구성 성분", "composition", "ingredient", "유해", "위험", "hazard"),
    4: ("응급", "first-aid", "first aid"),
    5: ("화재", "폭발", "fire"), 6: ("누출", "accidental", "release"),
    7: ("취급", "저장", "handling", "storage"), 8: ("노출", "보호구", "exposure", "protection"),
    9: ("물리", "특성", "physical", "chemical properties"), 10: ("반응", "stability", "reactivity"),
    11: ("독성", "toxicological"), 12: ("환경", "ecological"), 13: ("폐기", "disposal"),
    14: ("운송", "transport"), 15: ("법", "regulatory"),
    16: ("참고", "기타정보", "기타 정보", "other information"),
}
_SECTION_NO = re.compile(r"^(\d{1,2})(?:(?:\s*[.:]\s*)+|\s+)(?=[가-힣A-Za-z])", re.I)
# '3. 제목', '3.제목', '3 제목', '3: 제목'(045), OCR의 '13. . 제목', 영문 제목. '2차'는 아니다


def section_headings(items: list[dict], after: int = 0) -> list[tuple[float, int, str]]:
    """조각 → 이 쪽의 항 제목 [(줄 위 y, 항 번호, 제목)]. 위에서 아래 순서.

    줄 글이 '번호. 한글'(또는 '번호 한글', '번호: 한글')로 시작하고, 번호가 1~16이며 그 항의 낱말(SECTION_WORDS)이
    들어 있어야 한다. 번호는 앞 항(after, 앞 쪽까지 본 마지막 항)보다 커야 한다. 본문의 번호 목록('1. 눈에 들어갔을 때')과
    1항 안의 '12.연료 및 연료 첨가제'(S013) 같은 줄을 항으로 잡지 않기 위해서다.
    다만 1항은 언제든 다시 시작한다. 목차(S001 1쪽) 뒤의 본문과, MSDS 여러 건을 이은 문서(039)가 그렇다.
    """
    out = []
    for row in _rows([i for i in items if i["text"].strip()]):
        row = sorted(row, key=lambda i: i["box"][0])
        text = re.sub(r"\s+", " ", " ".join(i["text"].strip() for i in row)).strip()
        m = _SECTION_NO.match(text)
        if not m:
            continue
        n = int(m[1])
        compact = text.replace(" ", "").casefold()
        if (after < n <= 16 or n == 1) and any(w.replace(" ", "").casefold() in compact for w in SECTION_WORDS[n]):
            out.append((min(i["box"][1] for i in row), n, text))
            after = n
    return out


def reading_order(items: list[dict], tables: list[list[list]] | None = None, *,
                  preserve_empty_cells: bool = False, repair_table_layout: bool = False) -> list[list[dict]]:
    """조각 → 읽는 순서의 줄 목록. 글자가 없는 조각은 뺀다.

    tables(page_tables)를 주면 선으로 그린 표의 행을 먼저 한 조각으로 묶은 뒤 읽는다.
    v15 옵션: 빈 칸 보존과 잘못 잡힌 표·두 열 줄바꿈 수정을 각각 켠다. 기존 호출의 동작은 유지한다.
    """
    items = [i for i in items if i["text"].strip()]
    if not items:
        return []
    source_height = statistics.median(i["box"][3] - i["box"][1] for i in items)
    if tables and repair_table_layout:
        # 표 탐지기가 줄 없는 본문까지 가상의 표로 확장하면 항 제목이 이전 값에 섞인다.
        # 제목과 다른 높이의 본문을 같은 행으로 잡은 표만 버리고 원래 조각의 좌표를 따른다.
        tables = [t for t in tables if not _table_crosses_heading(items, t)]
    if tables:
        items = _table_rows(items, tables, preserve_empty_cells=preserve_empty_cells)
    h = source_height if repair_table_layout else statistics.median(i["box"][3] - i["box"][1] for i in items)
    return join_wrapped(_cut(items, h, repair_table_layout=repair_table_layout), h,
                        repair_table_layout=repair_table_layout)


def _is_section_heading(text: str) -> bool:
    text = text.strip()
    match = _SECTION_NO.match(text)
    if not match:
        return False
    number = int(match[1])
    return number in SECTION_WORDS and any(w in text.replace(" ", "") for w in SECTION_WORDS[number])


def _table_crosses_heading(items: list[dict], table: list[list]) -> bool:
    """항 제목과 다른 물리적 줄의 본문을 한 표 행에 넣은 오탐인가."""
    for row in table:
        members = [i for i in items if any(box and _inside(i, box) for box in row)]
        headings = [i for i in members if _is_section_heading(i["text"])]
        if any(not _same_row(other, heading) for heading in headings for other in members if other is not heading):
            return True
    return False


COL_TOL = 1.0     # 두 칸의 시작 x가 h의 이 배수 안이면 같은 열이다
WRAP_FILL = 2.0   # 칸 글이 그 열의 오른쪽 끝에서 h의 이 배수 안까지 차 있으면 다음 줄로 넘어간 것이다
LINE_GAP = 1.0    # 다음 줄이 위 줄 아래 h의 이 배수 안에서 시작해야 이어진 줄이다
MIN_WRAP_COL = 6.0   # 열 너비가 h의 이 배수보다 좁으면 잇지 않는다. 짧은 낱말만 있는 열은 줄이 넘어갈 일이 없다
                     # (M013 6·7쪽 독성 표: 'LD50' 아래 '경피'·'흡입' 라벨을 넘어간 글로 붙였다, 2026-10-29)


def _parts(item: dict) -> list[dict]:
    return item.get("parts") or [{"text": item["text"], "x0": item["box"][0], "x1": item["box"][2]}]


def join_wrapped(rows: list[list[dict]], h: float, *, repair_table_layout: bool = False) -> list[list[dict]]:
    """칸 글이 다음 줄로 넘어간 것을 위 줄의 그 칸에 잇는다 (항목명|값의 긴 값, 성분 표의 긴 이름).

    다음 줄을 위 줄에 잇는 조건 (모두)
    - 바로 아래 줄이다 (LINE_GAP)
    - 칸 수가 위 줄보다 적고, 칸마다 시작 x가 위 줄의 어느 칸과 같다 (새 행은 칸이 다 있다)
    - 그 칸의 위 줄 글이 열 오른쪽 끝까지 찼다 (WRAP_FILL). 짧은 칸 아래 줄은 빈 칸이 있는 새 행이다
    - 그 열이 MIN_WRAP_COL×h 이상 넓다. 좁은 열은 모든 칸이 '끝까지 찬' 것처럼 보이지만 라벨일 뿐이다
    잇는 곳은 공백 하나, '-'로 끝났으면 붙인다 (CAS '64742-' / '94-5').
    """
    every = [p for r in rows for i in r for p in _parts(i)]

    def right_edge(x0: float) -> float:
        return max(p["x1"] for p in every if abs(p["x0"] - x0) <= COL_TOL * h)

    out: list[list[dict]] = []
    for r in rows:
        row = [{**i, "box": list(i["box"]), "parts": [{**p, "last": p["x1"]} for p in _parts(i)],
                "table": "parts" in i} for i in r]
        prev = out[-1] if out else None
        pairs = _wrap_pairs(prev, row, h, right_edge, repair_table_layout=repair_table_layout) if prev else None
        if pairs is None:
            out.append(row)
            continue
        for (item, part), new in pairs:
            part["text"] += ("" if part["text"].endswith("-") else " ") + new["text"]
            part["last"] = new["x1"]
            item["box"][3] = max(item["box"][3], max(i["box"][3] for i in row))
    for row in out:
        for i in row:
            i["text"] = "  ".join(p["text"] for p in i["parts"]) if i["table"] else i["parts"][0]["text"]
            if not i.pop("table"):
                del i["parts"]
    return out


def _wrap_pairs(prev: list[dict], row: list[dict], h: float, right_edge, *, repair_table_layout: bool = False):
    """row가 prev에서 넘어온 줄이면 [((prev 조각, 그 칸), row의 칸)], 아니면 None."""
    top, bottom = min(i["box"][1] for i in row), max(i["box"][3] for i in prev)
    if not (-0.5 * h <= top - bottom <= LINE_GAP * h):
        return None
    above = [(i, p) for i in prev for p in i["parts"]]
    below = [p for i in row for p in i["parts"]]
    if repair_table_layout:
        if any("table_row" in i or _is_section_heading(i["text"]) for i in prev + row):
            return None
        if len(above) == len(below) == 2:
            return _wrapped_label_pairs(above, below, h, top - bottom)
    if len(below) >= len(above):
        return None
    pairs, used = [], set()
    for new in below:
        hit = [(i, p) for i, p in above if abs(p["x0"] - new["x0"]) <= COL_TOL * h and id(p) not in used]
        if not hit:
            return None
        i, p = hit[0]
        edge = right_edge(p["x0"])
        # 줄 끝에 문장이 먼저 끝난 긴 설명도 같은 값 칸에서 바로 이어질 수 있다.
        # 두 열의 항목|설명 배치, 좁은 행간, 넓은 값 열, 양쪽 모두 서술문인 경우만 허용한다.
        prose_continuation = (repair_table_layout and len(above) == 2 and len(below) == 1
                              and p is above[-1][1] and top - bottom <= 0.4 * h
                              and edge - p["x0"] >= 12 * h
                              and _prose(p["text"]) and _prose(new["text"]))
        if (p["last"] < edge - WRAP_FILL * h and not prose_continuation) or edge - p["x0"] < MIN_WRAP_COL * h:
            return None
        used.add(id(p))
        pairs.append(((i, p), new))
    return pairs


_LABEL_START = re.compile(r"^(?:[가-힣]|[A-Za-z]|\d{1,2})[.)]\s*")


def _prose(text: str) -> bool:
    return len(text.strip()) >= 20 and len(text.split()) >= 3 and bool(re.search(r"[가-힣A-Za-z]", text))


def _wrapped_label_pairs(above, below, h: float, gap: float):
    """항목명과 설명이 동시에 접힌 두 열을 칸별로 잇는다. 새 목록 항목은 경계다."""
    if gap > 0.4 * h or any(abs(old[1]["x0"] - new["x0"]) > COL_TOL * h
                            for old, new in zip(above, below)):
        return None
    left, value = above[0][1], above[1][1]
    if not _LABEL_START.match(left["text"].strip()) or _LABEL_START.match(below[0]["text"].strip()):
        return None
    width = value["x0"] - left["x0"]
    if width < MIN_WRAP_COL * h or left["last"] - left["x0"] < 0.7 * width:
        return None
    if not _prose(value["text"]) or not _prose(below[1]["text"]):
        return None
    return list(zip(above, below))


def reading_text(items: list[dict], tables: list[list[list]] | None = None) -> str:
    """조각 → 읽는 순서의 글. 줄 안의 조각은 공백 하나로 잇는다.

    줄 첫 조각의 앞 공백은 남긴다. 텍스트층은 항목의 층위를 앞 공백으로 들여 쓴 문서가 많다
    (S001 '          -예방'). 공백 없이 좌표로만 들여 쓴 문서는 예전(get_text)처럼 들여쓰기가 없다.
    """
    return "\n".join(row[0]["text"].rstrip() + "".join(" " + i["text"].strip() for i in row[1:])
                     for row in reading_order(items, tables))


def page_lines(page) -> list[list[dict]]:
    """PyMuPDF 쪽 → 줄마다 조각 목록 [{text, bbox}] (get_text('dict') 순서)."""
    return [[{"text": s["text"], "bbox": s["bbox"]} for s in ln["spans"]]
            for b in page.get_text("dict")["blocks"] for ln in b.get("lines", [])]


def layer_items(page) -> list[dict]:
    """PyMuPDF 쪽 → 텍스트층 줄 조각 (pt 좌표). 겹쳐 찍은 사본은 지운다."""
    from .render import drop_overstrike

    return line_items(drop_overstrike(page_lines(page))[0])


SEG_GAP = 1.0      # 같은 줄에서 글자 사이가 글자 크기의 이 배수보다 넓으면 다른 조각(칸)이다
SPACE_GAP = 0.15   # 이 배수보다 넓으면 띄어쓴 곳이다
DUP_DX = 1.0       # 같은 글자가 이 거리(pt) 안에 또 있으면 겹쳐 찍은 사본이다 (45번: 0.1pt씩 밀어 5번)


def char_items(page) -> list[dict]:
    """PyMuPDF 쪽 → 글자를 좌표로 다시 맞춘 조각 [{text, box}] (pt).

    한 줄을 글자·띄어쓰기·문장부호의 여러 층으로 찍은 문서가 있다 (M013: '64742945'와 '- -'가 따로 나온다).
    줄(PyMuPDF line) 단위로 읽으면 층마다 따로 나와 섞이지 않는다. 그래서 글자를 세로 중심으로 줄에 모으고,
    줄 안에서는 x 순서로 놓는다. 같은 자리의 같은 글자는 겹쳐 찍은 사본이라 하나만 남긴다.
    공백 글자는 쓰지 않고 글자 사이 간격으로 띄어쓰기를 다시 정한다. SEG_GAP보다 넓은 곳에서 조각을 나눈다.
    다만 줄 맨 앞의 공백 글자는 남긴다. 항목의 층위를 앞 공백으로 들여 쓴 문서가 있다 (S001 '          -예방').
    """
    chars = []
    for b in page.get_text("rawdict")["blocks"]:
        for ln in b.get("lines", []):
            for s in ln["spans"]:
                for c in s["chars"]:
                    x0, y0, x1, y1 = c["bbox"]
                    chars.append({"c": c["c"], "x0": x0, "x1": x1, "y0": y0, "y1": y1,
                                  "cy": (y0 + y1) / 2, "size": s["size"], "ws": not c["c"].strip()})
    rows: list[list[dict]] = []
    for c in sorted(chars, key=lambda c: c["cy"]):
        r = rows[-1] if rows else None
        if r and abs(c["cy"] - r[0]["cy"]) <= 0.4 * max(c["size"], r[0]["size"]):
            r.append(c)
        else:
            rows.append([c])
    out = []
    for r in rows:
        r.sort(key=lambda c: c["x0"])
        text_chars = [c for c in r if not c["ws"]]
        if not text_chars:
            continue
        lead = {round(c["x0"]) for c in r if c["ws"] and c["x1"] <= text_chars[0]["x0"] + DUP_DX}   # 사본은 한 번만
        first = len(out)
        seg: list[dict] = []
        for c in text_chars:
            prev = seg[-1] if seg else None
            if prev and c["c"] == prev["c"] and abs(c["x0"] - prev["x0"]) < DUP_DX:
                continue
            if prev and c["x0"] - prev["x1"] > SEG_GAP * c["size"]:
                out.append(_seg_item(seg))
                seg = []
            seg.append(c)
        if seg:
            out.append(_seg_item(seg))
        out[first]["text"] = " " * len(lead) + out[first]["text"]
    return out


def _seg_item(seg: list[dict]) -> dict:
    text = seg[0]["c"]
    for a, b in zip(seg, seg[1:]):
        text += (" " if b["x0"] - a["x1"] > SPACE_GAP * b["size"] else "") + b["c"]
    return {"text": text, "box": [min(c["x0"] for c in seg), min(c["y0"] for c in seg),
                                  max(c["x1"] for c in seg), max(c["y1"] for c in seg)]}


def line_items(lines: list[list[dict]]) -> list[dict]:
    """줄마다 조각 목록 → 줄 하나를 조각 하나로 (상자는 조각들을 감싸는 상자)."""
    out = []
    for line in lines:
        if not line:
            continue
        boxes = [s["bbox"] for s in line]
        out.append({"text": "".join(s["text"] for s in line),
                    "box": [min(b[0] for b in boxes), min(b[1] for b in boxes),
                            max(b[2] for b in boxes), max(b[3] for b in boxes)]})
    return out
