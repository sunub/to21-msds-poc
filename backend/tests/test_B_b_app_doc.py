"""scripts/b_app_doc.py 시험 (작업 화면 탭 ③ 원문 대조, ADR-025).

쪽 글자·쪽 좌표·쪽 그림은 tmp_path에 만든 가짜 MSDS다. 결과·정답 문서는 test_B_expand의 가짜 MSDS를 펼친 것이다 (D-43).
저장소의 data/pages/, runs/는 읽지 않는다. 모델 서버를 부르지 않는다.
"""
import copy
import importlib
import json
from collections import defaultdict

import pytest

from test_B_b_app_runs import env, make_run  # noqa: F401  env는 픽스처
from test_B_compare_models import SCRIPTS, X01, X02, X09, make_doc, write_json
from test_B_expand import LINES
from test_B_sections import titled

PNG = b"\x89PNG\r\n\x1a\nfake-page"
# 가짜 쪽 하나: 줄 6개, 칸(' | ')이 있는 줄 둘
PAGE_TXT = ["L001 가상 물질안전보건자료",
            "L002 제품명 : 가상 세정액 A",
            "L003 가상물질 갑 | 1234-56-6",
            "L004 가상물질 을 | 2345-67-7",
            "L005 긴급전화 : 000-0000-0000",
            "L006 끝 줄"]
ENTRIES = [{"text": "가상 물질안전보건자료", "bbox": [10, 10, 200, 30], "source": "pdf_text"},
           {"text": "제품명: 가상 세정액 A", "bbox": [10, 40, 220, 60], "source": "pdf_text"},       # 띄어쓰기만 다름
           {"text": "가상물질 갑", "bbox": [10, 100, 120, 120], "source": "pdf_text"},
           {"text": "1234-56-6", "bbox": [300, 98, 400, 122], "source": "pdf_text"},
           {"text": "가상물질 을", "bbox": [10, 130, 120, 150], "source": "paddle_image_only"},
           {"text": "２３４５－６７－７", "bbox": [300, 131, 410, 152], "source": "paddle_image_only"}]  # 전각 글자


@pytest.fixture
def bd(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    return importlib.import_module("b_app_doc")


@pytest.fixture
def app(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    return importlib.import_module("b_app")


def write_page(doc_dir, page, txt, entries=None, png=PNG):
    doc_dir.mkdir(parents=True, exist_ok=True)
    (doc_dir / f"p{page:03d}.txt").write_text("\n".join(txt) + "\n", encoding="utf-8")
    if entries is not None:
        write_json(doc_dir / f"p{page:03d}.json", {"page": page, "mode": "pdf_plus_paddle", "entries": entries})
    if png is not None:
        (doc_dir / f"p{page:03d}.png").write_bytes(png)


@pytest.fixture
def one_page(tmp_path):
    """tmp_path/pages/T21-X01/p001.{txt,json,png}"""
    pages = tmp_path / "pages"
    write_page(pages / X01, 1, PAGE_TXT, ENTRIES)
    return pages


def write_lines(pages, doc_id, lines):
    """Line 목록을 쪽마다 'L003 글자' 형식의 pNNN.txt로 쓴다. 근거 줄 번호가 test_B_expand의 LINES와 같아진다."""
    by_page = defaultdict(list)
    for line in lines:
        by_page[line.page].append(f"L{line.no:03d} {line.text}")
    for page, txt in by_page.items():
        write_page(pages / doc_id, page, txt, entries=[])
    return pages


def as_dicts(lines):
    return [{"id": l.id, "page": l.page, "no": l.no, "text": l.text} for l in lines]


def find(values, path):
    hits = [v for v in values if v["path"] == path]
    assert len(hits) == 1, path
    return hits[0]


# ── page_lines ─────────────────────────────────────────

def test_page_lines_bbox(bd, one_page):
    lines = bd.page_lines(X01, one_page)
    assert [l["id"] for l in lines] == [f"p1:L{n}" for n in range(1, 7)]
    assert lines[2] == {"id": "p1:L3", "page": 1, "no": 3, "text": "가상물질 갑 | 1234-56-6",
                        "bbox": [10, 98, 400, 122]}                         # 칸 둘의 합
    assert lines[3]["bbox"] == [10, 130, 410, 152]                         # 전각 글자도 NFKC로 맞춘다
    assert lines[1]["bbox"] == [10, 40, 220, 60]                           # 띄어쓰기·문장부호는 키에서 뺀다
    assert lines[4]["bbox"] is None and lines[5]["bbox"] is None           # entries에 없는 줄


def test_page_lines_without_json(bd, one_page):
    (one_page / X01 / "p001.json").unlink()
    lines = bd.page_lines(X01, one_page)
    assert len(lines) == 6 and all(l["bbox"] is None for l in lines)
    write_json(one_page / X01 / "p001.json", {"page": 1})                  # entries가 없는 파일
    assert all(l["bbox"] is None for l in bd.page_lines(X01, one_page))


def test_page_lines_entry_used_once(bd, tmp_path):
    pages = tmp_path / "pages"
    write_page(pages / X01, 1, ["L001 가상 독성 | 자료없음", "L002 가상 생태 | 자료없음", "L003 자료없음"],
               [{"text": "자료없음", "bbox": [300, 10, 360, 30]}, {"text": "자료 없음", "bbox": [300, 40, 360, 60]},
                {"text": "가상 독성", "bbox": [10, 10, 100, 30]}])
    lines = bd.page_lines(X01, pages)
    assert lines[0]["bbox"] == [10, 10, 360, 30]                           # 같은 쪽에서 아직 안 쓴 첫 번째
    assert lines[1]["bbox"] == [300, 40, 360, 60]                          # '가상 생태' 칸은 못 찾고 둘째 '자료없음'만
    assert lines[2]["bbox"] is None                                        # 남은 entry가 없다


# ── section_spans ──────────────────────────────────────

def test_section_spans(bd, tmp_path):
    pages = tmp_path / "pages"
    body = ["가상 물질안전보건자료"] + titled(range(1, 17)) + ["끝 줄"]
    write_page(pages / X01, 1, [f"L{i:03d} {t}" for i, t in enumerate(body, 1)], [])
    spans = bd.section_spans(X01, pages)
    assert sorted(spans) == list(range(1, 17))
    assert spans[1] == {"start": "p1:L2", "end": "p1:L3"}
    assert spans[16] == {"start": "p1:L32", "end": "p1:L34"}


def test_section_spans_missing_titles(bd, one_page):
    assert bd.section_spans(X01, one_page) == {}                            # 제목이 없으면 대체 경로: 항 구간 없음


# ── flatten_values ─────────────────────────────────────

def test_flatten_values_toxicity_row(bd):
    values = bd.flatten_values(make_doc(X01), as_dicts(LINES))
    tox = [v for v in values if v["table"] == "toxicity"]
    assert tox and all(v["section"] == 11 and v["row"] == 0 for v in tox)
    assert all(v["lines"] == ["p5:L8"] for v in tox)
    q = find(values, "msds[0].toxicity[0].q")
    assert q["field"] == "q" and q["text"] == "> 2000 mg/kg"               # 숫자 묶음은 한 칸, 보이는 글은 raw
    assert find(values, "msds[0].toxicity[0].species")["value"] == "랫드"


def test_flatten_values_sections_and_lines(bd):
    values = bd.flatten_values(make_doc(X01), as_dicts(LINES))
    signal = find(values, "msds[0].hazard.signal_word")
    assert (signal["section"], signal["table"], signal["row"], signal["field"]) == (2, "hazard", None, "signal_word")
    cls = find(values, "msds[0].hazard.classes[0].category")
    assert (cls["table"], cls["row"], cls["field"], cls["lines"]) == ("hazard.classes", 0, "category", ["p1:L20"])
    assert find(values, "msds[0].meta.revision_no")["section"] == 16
    assert find(values, "msds[0].meta.revision_no")["lines"] == ["p7:L3"]           # 16항 값이 1항 값을 대신했다
    assert find(values, "msds[0].product.name")["section"] == 1
    assert find(values, "msds[0].components[1].cas_no")["lines"] == ["p2:L6"]
    stmt = find(values, "msds[0].narratives[0].statements[1]")                     # 서술형은 문장마다 하나
    assert (stmt["section"], stmt["lines"]) == (4, ["p3:L1"])                       # 근거는 서술 구간 첫 줄
    assert find(values, "msds[0].narratives[1].statements[0]")["section"] == 7
    assert find(values, "msds[0].extras[0].q")["section"] == 9                      # extras는 행의 section_no
    assert not [v for v in values if v["path"].startswith(("msds[0].evidence", "msds[0].validation"))]
    assert not [v for v in values if v["field"].endswith("seq")]                    # 코드가 매기는 순번
    assert stmt["text"] == "콘택트렌즈: 착용하고 있으면 제거하시오."
    cond = find(values, "msds[0].physchem[0].cond")
    assert cond["text"] == "method 밀폐식"                                          # 조건은 값이 있는 칸만 보인다
    doc = make_doc(X01)
    doc["msds"][0]["physchem"][0]["cond"] = {k: None for k in cond["value"]}
    assert "msds[0].physchem[0].cond" not in {v["path"] for v in bd.flatten_values(doc)}   # 칸이 모두 비면 값이 아니다


def test_flatten_values_without_lines(bd):
    values = bd.flatten_values(make_doc(X01))
    assert values and all(v["lines"] == [] for v in values)


def test_flatten_values_ambiguous_line_prefers_section_span(bd):
    doc = make_doc(X01)
    dup = {"id": "p5:L1", "page": 5, "no": 1, "text": "가상물질 을 | 경구 LD50 > 2000 mg/kg (랫드)"}  # 같은 글이 9항 자리에도
    lines = [dup if l["id"] == "p5:L1" else l for l in as_dicts(LINES)]
    assert find(bd.flatten_values(doc, lines), "msds[0].toxicity[0].q")["lines"] == ["p5:L1"]   # 구간을 모르면 첫 줄
    spans = {9: {"start": "p5:L1", "end": "p5:L5"}, 11: {"start": "p5:L8", "end": "p5:L10"}}
    assert find(bd.flatten_values(doc, lines, spans), "msds[0].toxicity[0].q")["lines"] == ["p5:L8"]


def test_flatten_values_same_text_lines_follow_row_order(bd):
    """같은 쪽에 같은 글의 줄이 여럿이면, 그 글을 근거로 쓴 행이 나온 순서대로 k번째 행에 k번째 줄을 준다."""
    doc = {"msds": [{
        "toxicity": [{"endpoint": "TX_ORAL", "status": "자료없음", "statements": [{"seq": 1, "key": None, "value": "가상",
                                                                              "text": "가상", "refs": None}]},
                     {"endpoint": "TX_DERMAL", "status": "자료없음"}],
        "evidence": [{"field": "toxicity[0]", "page": 5, "source_text": "- | 자료없음"},
                     {"field": "toxicity[0].statements[0]", "page": 5, "source_text": "- | 자료없음"},
                     {"field": "toxicity[1]", "page": 5, "source_text": "- | 자료없음"}]}]}
    lines = [{"id": "p5:L1", "page": 5, "text": "가상 급성독성(경구)"}, {"id": "p5:L2", "page": 5, "text": "- | 자료없음"},
             {"id": "p5:L3", "page": 5, "text": "가상 급성독성(경피)"}, {"id": "p5:L4", "page": 5, "text": "- | 자료없음"}]
    values = bd.flatten_values(doc, lines)
    assert find(values, "msds[0].toxicity[0].endpoint")["lines"] == ["p5:L2"]
    assert find(values, "msds[0].toxicity[0].statements[0]")["lines"] == ["p5:L2"]     # 같은 행의 근거는 같은 줄
    assert find(values, "msds[0].toxicity[1].endpoint")["lines"] == ["p5:L4"]


def test_section_map_matches_item_sections(bd, monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    diff = importlib.import_module("b_app_diff")
    for item, tables in diff.ITEM_TABLES.items():
        for t in tables:
            assert bd.SECTION_OF[t] in diff.sections_of(item), (item, t)
    for item, key in (("관리정보", "meta"), ("제품명", "product"), ("신호어", "hazard"), ("14항", "transport")):
        assert bd.SECTION_OF[key] in diff.sections_of(item), item


# ── align_silver ───────────────────────────────────────

def test_align_silver(bd):
    gold = make_doc(X01)
    pred = make_doc(X01, toxicity=True)                                    # 결과가 독성 행을 빠뜨렸다
    m = pred["msds"][0]
    m["hazard"]["signal_word"] = "위험"
    m["components"].reverse()                                              # 행 순서가 실버와 달라도 CAS로 맞춘다
    m["product"]["name"] = "가상  세정액 A"                                  # 공백 차이만
    m["cmr"].append({**copy.deepcopy(m["cmr"][0]), "agency": "가상기관"})    # 결과에만 있는 행
    values = bd.flatten_values(pred)
    out = bd.align_silver(values, gold)
    assert set(out) == {v["path"] for v in values}
    assert out["msds[0].hazard.signal_word"] == {"value": "경고", "same": False}
    assert out["msds[0].components[0].name"] == {"value": "가상물질 을", "same": True}
    assert out["msds[0].components[1].cas_no"] == {"value": "1234-56-6", "same": True}
    assert out["msds[0].product.name"]["same"] is True
    assert out["msds[0].cmr[1].agency"] == {"value": None, "same": False}
    assert not [p for p in out if ".toxicity" in p]                        # 실버에만 있는 행은 결과 쪽 대응이 없다


def test_align_silver_pairs_rows_with_different_key(bd):
    """키 칸(성분)이 달라 키 경로가 어긋나도, 남은 행끼리 같은 칸이 절반 이상(2칸 이상)이면 짝짓는다."""
    gold = make_doc(X01)
    pred = make_doc(X01)
    m = pred["msds"][0]
    m["regulations"][0]["comp_ref"] = "MIX"                                # 실버는 성분 1(CAS)
    m["extras"][0].update({"section_no": 11, "title_raw": "다른 제목", "page": 6,
                           "q": {**m["extras"][0]["q"], "raw": "9.99", "value": 9.99}})   # 같은 칸이 둘뿐(reason·comp_ref)
    out = bd.align_silver(bd.flatten_values(pred), gold)
    assert out["msds[0].regulations[0].law"] == {"value": "OSH", "same": True}
    assert out["msds[0].regulations[0].comp_ref"] == {"value": "1", "same": False}
    assert out["msds[0].extras[0].title_raw"] == {"value": None, "same": False}


def test_align_silver_empty_list_equals_null(bd):
    gold = make_doc(X01)
    pred = make_doc(X01)
    for s in pred["msds"][0]["narratives"][0]["statements"]:
        s["refs"] = None if s["refs"] == [] else []
    out = bd.align_silver(bd.flatten_values(pred), gold)
    assert out["msds[0].narratives[0].statements[0]"]["same"] is True


# ── doc_view ───────────────────────────────────────────

@pytest.fixture
def view_env(env):
    write_lines(env / "pages9", X01, LINES)
    write_lines(env / "pages9", X09, LINES)
    pred = make_doc(X01, toxicity=True)
    make_run(env / "runs", "r1", {X01: pred, X09: make_doc(X09)})
    return env


def test_doc_view(bd, view_env):
    env = view_env
    dv = bd.doc_view(env / "runs" / "r1", X01, env / "pages9", env / "gold")
    assert dv["doc_id"] == X01 and dv["pages"] == [1, 2, 3, 4, 5, 6, 7]
    assert [l["id"] for l in dv["lines"]] == [l.id for l in LINES]
    assert isinstance(dv["sections"], dict)
    paths = {v["path"] for v in dv["values"]}
    for lid, listed in dv["line_index"].items():
        assert listed == [v["path"] for v in dv["values"] if lid in v["lines"]], lid
    assert "msds[0].cmr[0].agency" in dv["line_index"]["p5:L10"]
    assert set(dv["line_index"]) <= {l.id for l in LINES}
    assert all(p in paths for ps in dv["line_index"].values() for p in ps)
    agency = find(dv["values"], "msds[0].cmr[0].agency")
    assert (agency["silver"]["value"], agency["silver"]["same"], agency["silver"]["text"]) == ("IARC", True, "IARC")
    missed = [g for g in dv["silver_only"] if g["table"] == "toxicity"]  # 결과가 빠뜨린 독성 행은 실버 쪽에만
    assert missed and all(g["section"] == 11 for g in missed)
    assert not [g for g in dv["silver_only"] if g["table"] == "cmr"]
    assert all(g["pair_row"] is None for g in missed)                      # 결과에 짝 행이 없다


def test_doc_view_silver_only_cell_of_paired_row(bd, view_env):
    pred = make_doc(X01)
    pred["msds"][0]["toxicity"][0]["species"] = None                       # 짝 행은 있는데 칸 하나를 빠뜨렸다
    make_run(view_env / "runs", "r2", {X01: pred})
    dv = bd.doc_view(view_env / "runs" / "r2", X01, view_env / "pages9", view_env / "gold")
    only = [g for g in dv["silver_only"] if g["table"] == "toxicity"]
    assert [(g["field"], g["value"], g["pair_row"]) for g in only] == [("species", "랫드", 0)]
    assert find(dv["values"], "msds[0].toxicity[0].q")["silver"]["same"] is True


def test_doc_view_without_gold(bd, view_env):
    (view_env / "gold" / f"{X01}.json").unlink()
    dv = bd.doc_view(view_env / "runs" / "r1", X01, view_env / "pages9", view_env / "gold")
    assert dv["has_gold"] is False and dv["silver_only"] == []
    assert all(v["silver"]["value"] is None and v["silver"]["same"] is False for v in dv["values"])


def test_doc_view_refuses_eval_doc(bd, view_env):
    with pytest.raises(PermissionError):
        bd.doc_view(view_env / "runs" / "r1", X09, view_env / "pages9", view_env / "gold")
    with pytest.raises(PermissionError):                                   # manifest에 없는 문서도 용도를 알 수 없어 막는다
        bd.doc_view(view_env / "runs" / "r1", "T21-X77", view_env / "pages9", view_env / "gold")


# ── 라우트 ─────────────────────────────────────────────

def make_ctx(app, env, pages):
    return app.AppContext(runs_dir=env / "runs", gold_dir=env / "gold", pages_dir=pages,
                          static_dir=app.STATIC, cache_dir=None, gaps_file=env / "silver_gaps.yaml")


def test_route_doc(app, view_env):
    ctx = make_ctx(app, view_env, view_env / "pages9")
    code, ctype, body = app.route("GET", "/api/doc", {"run": ["r1"], "doc": [X01]}, None, ctx)
    data = json.loads(body)
    assert code == 200 and ctype.startswith("application/json")
    assert data["doc_id"] == X01 and data["values"] and data["line_index"]


def test_route_doc_errors(app, view_env):
    ctx = make_ctx(app, view_env, view_env / "pages9")

    def call(q):
        code, _, body = app.route("GET", "/api/doc", q, None, ctx)
        return code, json.loads(body)

    code, data = call({"run": ["r1"], "doc": [X09]})
    assert code == 404 and "평가" not in data["error"]                    # 이유를 말하지 않는다
    assert call({"run": ["없는실행"], "doc": [X01]})[0] == 404
    assert call({"run": ["r1"], "doc": [X02]})[0] == 404                   # 결과 파일이 없는 문서
    assert call({"run": ["r1"]})[0] == 400
    assert call({"run": ["r1"], "doc": ["../T21-X01"]})[0] == 400


def test_route_page_png(app, env, one_page):
    ctx = make_ctx(app, env, one_page)
    code, ctype, body = app.route("GET", "/pages/T21-X01/p001.png", {}, None, ctx)
    assert (code, ctype, body) == (200, "image/png", PNG)
    assert app.route("GET", "/pages/T21-X01/p002.png", {}, None, ctx)[0] == 404       # 없는 쪽


@pytest.mark.parametrize("path", ["/pages/../x.png", "/pages/T21-X01/evil.txt", "/pages/%2e%2e/T21-X01/p001.png",
                                  "/pages/T21-X01/p1.png", "/pages/t21-x01/p001.png", "/pages/T21-X01/../p001.png",
                                  "/pages/T21-X01/p001.png/x", "/pages/T21-X01/p001.txt", "/pages/T21-X01"])
def test_route_page_rejects_other_paths(app, env, one_page, path):
    assert app.route("GET", path, {}, None, make_ctx(app, env, one_page))[0] == 400


def test_route_page_eval_doc_404(app, env, one_page):
    write_page(one_page / X09, 1, PAGE_TXT, ENTRIES)
    code, ctype, body = app.route("GET", "/pages/T21-X09/p001.png", {}, None, make_ctx(app, env, one_page))
    assert code == 404 and body != PNG
    write_page(one_page / "T21-X77", 1, PAGE_TXT, ENTRIES)                 # manifest에 없는 문서
    assert app.route("GET", "/pages/T21-X77/p001.png", {}, None, make_ctx(app, env, one_page))[0] == 404


def test_app_js_calls_doc_api(app):
    js = (app.STATIC / "app.js").read_text(encoding="utf-8")
    assert "/api/doc" in js and "/pages/" in js
