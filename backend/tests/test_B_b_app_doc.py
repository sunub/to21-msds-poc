"""scripts/b_app_doc.py 시험 (작업 화면 탭 ③ 원문 대조, ADR-025).

쪽 글자·쪽 좌표·쪽 그림은 tmp_path에 만든 가짜 MSDS다. 결과·정답 문서는 test_B_expand의 가짜 MSDS를 펼친 것이다 (D-43).
저장소의 data/pages/, runs/는 읽지 않는다. 모델 서버를 부르지 않는다.
"""
import copy
import importlib
import json
from collections import Counter, defaultdict

import pytest

from msds.common import paths
from msds.common.jsonpath import get, set_
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


# ── value_items: 값 → 그 값이 들어가는 채점 항목 (app-redo-api2 step 1) ──

def _has_scorer() -> bool:
    try:
        return paths.to21_file("scorer").exists()
    except FileNotFoundError:
        return False


needs_scorer = pytest.mark.skipif(not _has_scorer(), reason="TO21 제공 파일이 없습니다 (to21/README.md 참고)")


def _q(raw, value=None, unit=None, **kw):
    return {"raw": raw, "approx": None, "value": value, "lower_op": None, "lower": None, "upper_op": None,
            "upper": None, "unit": unit, "dp": 0, "status": "값있음", "note": None, **kw}


def scored_doc() -> dict:
    """채점 항목마다 비교할 값이 있도록 test_B_expand의 가짜 MSDS를 넓힌다. 값은 모두 직접 만든 가짜다 (D-43).
    성분 3(가상물질 병)은 다른 표 행이 가리키지 않아, CAS를 바꿔도 3항 밖 항목이 흔들리지 않는다."""
    doc = make_doc(X01)
    m = doc["msds"][0]
    m["meta"]["msds_no"] = "AA0000-000000"
    m["companies"][0]["site"] = "가상 공장"
    m["hazard"]["pictograms"] = [{"code": "GHS07", "detection": None}]
    m["hazard"]["h_statements"] = [{"seq": 1, "code": "H319", "system": None, "mark": None, "text": "가상 H 문구"}]
    m["hazard"]["p_statements"] = [{"seq": 1, "code": "P264", "type": None, "text": "가상 P 문구"}]
    m["components"][0]["ke_no"] = "KE-00000"
    m["components"].append({**copy.deepcopy(m["components"][1]), "seq": 3, "name": "가상물질 병",
                            "cas_no": "3456-78-8", "content": _q("1 ~ 5", lower_op=">=", lower=1, upper_op="<=",
                                                                  upper=5, unit="%")})
    row = {"comp_ref": "MIX", "q": None, "text_value": None, "cond": None, "seq": None, "data_source": None}
    m["physchem"] += [{**row, "prop_code": "PH", "q": _q("7", 7)},
                      {**row, "prop_code": "APPEARANCE_COLOR", "text_value": "무색"}]
    m["toxicity"].append({**copy.deepcopy(m["toxicity"][0]), "endpoint": "TX_SKIN", "descriptor": "결과기술",
                          "q": None, "status": "자료없음"})
    m["ecotox"] = [{"comp_ref": "2", "endpoint": "ECO_FISH", "descriptor": "LC50", "q": _q("10 mg/L", 10, "mg/L"),
                    "species": "가상 어류", "duration_value": None, "duration_unit": None, "guideline": None,
                    "data_source": None, "statements": [], "status": None}]
    reg = m["regulations"][0]
    m["regulations"] += [{**reg, "seq": 2, "law": "KREACH", "item_code": "KREACH_EXIST",
                          "threshold": _q("1 % 이상", lower_op=">=", lower=1, unit="%")},
                         {**reg, "seq": 3, "law": "INTL", "item_code": "INTL_EU"}]
    m["transport"][0].update({"regulated": True, "un_no": "1993", "hazard_class": "3", "packing_group": "III"})
    return doc


def perturb(doc: dict, path: str, change) -> dict:
    """msds 첫 건의 칸 하나만 바꾼 사본. 바꿀 값과 원래 값이 둘 다 객체면 합친다(숫자 묶음·문장의 일부만 바꾼다)."""
    out = copy.deepcopy(doc)
    m = out["msds"][0]
    old = get(m, path)
    set_(m, path, {**old, **change} if isinstance(old, dict) and isinstance(change, dict) else change)
    return out


# (칸 경로, 바꿀 값). 바꾼 뒤 점수가 떨어진 항목 집합이 그 칸의 items와 같아야 한다.
PERTURB = [
    ("meta.last_revision_date", "2020-01-01"),                    # 관리정보
    ("product.name", "가상 다른 제품"),                              # 제품명
    ("companies[0].site", "가상 다른 공장"),                         # 회사명(사업장)
    ("companies[0].contacts[0].value", "111-1111-1111"),          # 긴급연락처
    ("hazard.signal_word", "위험"),
    ("hazard.pictograms[0].code", "GHS05"),
    ("hazard.h_statements[0].code", "H318"),
    ("hazard.p_statements[0].code", "P280"),
    ("hazard.classes[0].category", "1"),                          # 유해성 분류
    ("components[2].cas_no", "9999-99-9"),                        # 성분 키: 성분·성분 필드·함유량이 함께 흔들린다
    ("components[0].name", "가상물질 정"),                           # CAS가 있으면 이름은 성분 필드에만
    ("components[0].ke_no", "KE-99999"),
    ("components[1].content", {"value": 0.7, "raw": "0.7"}),      # 함유량
    ("exposure_limits[0].q", {"value": 2, "raw": "2 ppm"}),       # 8항
    ("physchem[0].q", {"value": 61, "raw": "61 ℃"}),               # 인화점(9항 필수)
    ("physchem[1].q", {"value": 8, "raw": "8"}),                  # pH(9항 필수)
    ("physchem[2].text_value", "노란색"),                            # 색(9항 기타)
    ("toxicity[0].q", {"lower": 300, "raw": "> 300 mg/kg"}),      # 급성 경구 독성
    ("toxicity[1].status", "미기재"),                                # 기타 독성
    ("cmr[0].class", "1"),                                        # CMR
    ("ecotox[0].q", {"value": 20, "raw": "20 mg/L"}),             # 12항
    ("regulations[0].applicable", "비해당"),                         # 국내 법 해당 여부
    ("regulations[1].threshold", {"lower": 5, "raw": "5 % 이상"}),  # 국내 법 기준농도
    ("regulations[2].applicable", "비해당"),                         # 해외 규제
    ("transport[0].un_no", "1263"),                               # 14항
    ("narratives[0].statements[0]", {"value": "가상 다른 문장"}),     # 서술형
    ("narratives[1].item_code", "S7_STORAGE"),                    # 서술형 항목 코드(짝 키)
    # 채점에 들어가지 않는 칸: 바꿔도 떨어지는 항목이 없고 items도 빈 목록이다
    ("product.uses", ["가상 다른 용도"]),
    ("hazard.classes[0].group", "물리"),
    ("toxicity[0].species", "마우스"),
    ("physchem[0].cond", {"method": "개방식"}),
    ("narratives[0].title_raw", "가상 다른 제목"),
    ("extras[0].q", {"value": 9.9, "raw": "9.90"}),
]


@needs_scorer
@pytest.mark.parametrize("path,change", PERTURB, ids=[p for p, _ in PERTURB])
def test_value_items_match_score_drops(bd, path, change):
    """값 하나만 바꾸고 실제 TO21 채점기를 돌리면, 점수가 떨어진 항목이 정확히 그 값의 items다."""
    from msds.evaluate.score import score_pair
    gold = scored_doc()
    base = {i["name"]: i["score"] for i in score_pair(gold, gold)["items"]}
    assert all(s == 1.0 for s in base.values())
    pred = perturb(gold, path, change)
    assert get(pred["msds"][0], path) != get(gold["msds"][0], path)
    dropped = {i["name"] for i in score_pair(gold, pred)["items"] if i["score"] < base[i["name"]]}
    assert set(bd.value_items(path, gold["msds"][0])) == dropped
    assert bd.value_items(f"msds[0].{path}", gold["msds"][0]) == bd.value_items(path, gold["msds"][0])


@needs_scorer
def test_item_rules_follow_criteria(bd, monkeypatch):
    """ITEM_RULES의 이름과 순서가 채점 기준(criteria) 23개와 같다. 채점기 판이 바뀌어 이름이 달라지면 여기서 잡힌다."""
    monkeypatch.syspath_prepend(str(SCRIPTS))
    runs = importlib.import_module("b_app_runs")
    names = [i["name"] for i in runs.criteria()["items"]]
    assert list(bd.ITEM_RULES) == names
    assert bd.ITEM_RULES[names[0]] == []                                   # MSDS 건수는 값 칸이 아니다
    items = bd.value_items("components[2].cas_no", scored_doc()["msds"][0])
    assert items == [n for n in names if n in items] and len(items) == 3   # criteria 순서


def test_value_items_selects_rows_like_scorer(bd):
    """행을 고르는 규칙: 필수 물성·급성 독성·국내 법은 코드로 나뉘고, 기준농도는 값이 있을 때만, 운송은 첫 행만,
    긴급연락처는 첫 긴급 연락처만, 성분 이름은 CAS가 없을 때만 성분 짝 키다."""
    m = scored_doc()["msds"][0]
    m["transport"].append({**m["transport"][0], "mode": "해상"})
    m["companies"][0]["contacts"] = [{"type": "대표", "value": "222-2222-2222", "hours": None},
                                     {"type": "긴급", "value": "000-0000-0000", "hours": None},
                                     {"type": "긴급", "value": "333-3333-3333", "hours": None}]
    m["components"][1]["cas_no"] = None

    def one(path):
        items = bd.value_items(path, m)
        return items[0] if len(items) == 1 else items

    assert one("physchem[1].prop_code").startswith("9항 필수")
    assert one("physchem[2].prop_code").startswith("9항 기타")
    assert one("toxicity[0].endpoint").startswith("11항 급성")
    assert one("toxicity[1].endpoint").startswith("11항 기타")
    assert one("regulations[0].applicable").startswith("15항 국내 규제(")
    assert one("regulations[0].law").startswith("15항 국내 규제(")       # 기준농도가 없는 행
    assert len(bd.value_items("regulations[1].law", m)) == 2               # 국내 + 기준농도
    assert one("regulations[1].threshold") == "15항 국내 규제 기준농도"
    assert one("regulations[2].comp_ref").startswith("15항 해외")
    assert one("transport[0].un_no").startswith("14항")
    assert bd.value_items("transport[1].un_no", m) == []
    assert bd.value_items("companies[0].contacts[0].value", m) == []      # 긴급이 아니다
    assert one("companies[0].contacts[1].value").startswith("제품명")
    assert bd.value_items("companies[0].contacts[2].value", m) == []      # 둘째 긴급 연락처는 비교하지 않는다
    assert one("companies[0].contacts[0].type").startswith("제품명")       # 긴급인지 고르는 칸
    assert len(bd.value_items("components[1].name", m)) == 3              # CAS가 없으면 이름이 성분 짝 키
    assert len(bd.value_items("components[0].name", m)) == 1
    assert bd.value_items("hazard.other_hazards[0]", m) == []
    assert bd.value_items("없는표[0].x", m) == []


def test_flatten_values_items_follow_item_section(bd, monkeypatch):
    """items가 있는 값의 항이 그 항목의 항(b_app_text.item_section)과 같다. 항이 없는 항목은 서술형뿐이고 서술 값에만 붙는다."""
    monkeypatch.syspath_prepend(str(SCRIPTS))
    bt = importlib.import_module("b_app_text")
    values = bd.flatten_values(scored_doc(), as_dicts(LINES))
    assert values and all(isinstance(v["items"], list) for v in values)
    seen = set()
    for v in values:
        for name in v["items"]:
            seen.add(name)
            sec = bt.item_section({"name": name}, {"items": []})
            if sec is None:
                assert name.startswith("서술형") and v["table"] == "narratives", (v["path"], name)
            else:
                assert sec == v["section"], (v["path"], name)
    assert len(seen) == len(bd.ITEM_RULES) - 1                            # MSDS 건수만 값이 없다
    assert find(values, "msds[0].toxicity[0].q")["items"] == ["11항 급성독성(경구·경피·흡입)"]
    assert find(values, "msds[0].extras[0].q")["items"] == []


def test_flatten_values_items_keep_other_keys(bd, monkeypatch):
    """items를 더해도 기존 키와 값, 근거 줄은 그대로다."""
    old_keys = {"path", "key", "section", "table", "row", "field", "value", "text", "lines"}
    doc = scored_doc()
    values = bd.flatten_values(doc, as_dicts(LINES))
    assert all(set(v) == old_keys | {"items"} for v in values)
    monkeypatch.setattr(bd, "value_items", lambda path, m: ["가짜"])
    other = bd.flatten_values(doc, as_dicts(LINES))
    assert [{k: v[k] for k in old_keys} for v in values] == [{k: v[k] for k in old_keys} for v in other]
    assert all(v["items"] == ["가짜"] for v in other)                      # items는 value_items에서만 온다


def test_doc_view_items_keep_lines_and_line_index(bd, view_env, monkeypatch):
    dv = bd.doc_view(view_env / "runs" / "r1", X01, view_env / "pages9", view_env / "gold")
    assert dv["values"] and all("items" in v for v in dv["values"])
    assert dv["silver_only"] and all(isinstance(g["items"], list) for g in dv["silver_only"])
    tox = [g for g in dv["silver_only"] if g["path"] == "msds[0].toxicity[0].q"]
    assert tox and tox[0]["items"] == ["11항 급성독성(경구·경피·흡입)"]   # 결과가 빠뜨린 값도 항목으로 고를 수 있다
    monkeypatch.setattr(bd, "value_items", lambda path, m: [])
    before = bd.doc_view(view_env / "runs" / "r1", X01, view_env / "pages9", view_env / "gold")
    strip = lambda vs: [{k: x for k, x in v.items() if k != "items"} for v in vs]  # noqa: E731
    assert strip(dv["values"]) == strip(before["values"])
    assert strip(dv["silver_only"]) == strip(before["silver_only"])
    assert dv["line_index"] == before["line_index"]


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


# ── field_counts: S01 문제 건수를 S02와 같은 칸 단위로 센다 (사용자 결정 10/31) ──

def _source_view_counts(dv):
    """원문 대조 화면(js/source.js의 sourceKind·sourceProblems)이 doc_view를 나누는 방식 그대로 센다."""
    out = Counter()
    for v in dv["values"]:
        if v["silver"]["same"]:
            continue
        kind = "made" if v["silver"]["value"] is None else "wrong"
        for item in v["items"]:
            out[(item, v["section"], kind)] += 1
    for g in dv["silver_only"]:
        for item in g["items"]:
            out[(item, g["section"], "missing")] += 1
    return out


def test_field_counts_match_source_view_classes(bd, view_env):
    pred = make_doc(X01, toxicity=True)                                    # 독성 행을 빠뜨렸다 → 못 뽑음
    m = pred["msds"][0]
    m["hazard"]["signal_word"] = "위험"                                     # 정답 짝이 다르다 → 틀림
    m["cmr"].append({**copy.deepcopy(m["cmr"][0]), "agency": "가상기관"})    # 정답에 없는 행 → 만듦
    make_run(view_env / "runs", "r3", {X01: pred})
    gold = json.loads((view_env / "gold" / f"{X01}.json").read_text(encoding="utf-8"))
    got = bd.field_counts(pred, gold)
    dv = bd.doc_view(view_env / "runs" / "r3", X01, view_env / "pages9", view_env / "gold")
    assert got == _source_view_counts(dv)
    assert {kind for (_, _, kind) in got} == {"wrong", "made", "missing"}
    signal = find(bd.flatten_values(pred), "msds[0].hazard.signal_word")
    assert signal["items"]
    for item in signal["items"]:
        assert got[(item, signal["section"], "wrong")] == 1
    assert bd.field_counts(gold, gold) == Counter()                        # 같은 문서는 문제 값이 없다


def test_run_field_counts_reads_outputs_and_skips_docs_without_output_or_gold(bd, view_env):
    run = view_env / "runs" / "r1"
    out = bd.run_field_counts(run, view_env / "gold", [X01, X09, "T21-X99"])
    pred = json.loads((run / "outputs" / f"{X01}.json").read_text(encoding="utf-8"))
    gold = json.loads((view_env / "gold" / f"{X01}.json").read_text(encoding="utf-8"))
    assert out[X01] == bd.field_counts(pred, gold)
    assert "T21-X99" not in out                                            # 결과 파일이 없다
    (view_env / "gold" / f"{X01}.json").unlink()
    assert X01 not in bd.run_field_counts(run, view_env / "gold", [X01])   # 정답이 없으면 셀 수 없다


def test_doc_view_refuses_eval_doc(bd, view_env):
    with pytest.raises(PermissionError):
        bd.doc_view(view_env / "runs" / "r1", X09, view_env / "pages9", view_env / "gold")
    with pytest.raises(PermissionError):                                   # manifest에 없는 문서도 용도를 알 수 없어 막는다
        bd.doc_view(view_env / "runs" / "r1", "T21-X77", view_env / "pages9", view_env / "gold")


# ── 실버 값의 추정 줄 (app-redo-api2 step 2) ──────────────

def doc_view_r1(bd, env, gold_dir=None):
    return bd.doc_view(env / "runs" / "r1", X01, env / "pages9", gold_dir or env / "gold")


def gold_doc(env) -> dict:
    return json.loads((env / "gold" / f"{X01}.json").read_text(encoding="utf-8"))


def under(values, *rows) -> list[dict]:
    return [v for v in values if any(v["path"].startswith(f"msds[0].{r}") for r in rows)]


def test_doc_view_silver_only_gets_text_matched_lines(bd, view_env):
    """결과가 빠뜨린 독성 행: 실버 근거 글이 가짜 쪽 줄 p5:L8의 글과 같으므로 그 줄이 추정 줄로 붙는다."""
    ev = next(e for e in gold_doc(view_env)["msds"][0]["evidence"] if e["field"] == "toxicity[0]")
    line = next(l for l in LINES if l.id == "p5:L8")
    assert (ev["page"], ev["source_text"]) == (line.page, line.text)
    dv = doc_view_r1(bd, view_env)
    missed = [g for g in dv["silver_only"] if g["table"] == "toxicity"]
    assert missed and all(g["lines"] == ["p5:L8"] for g in missed)
    sl = dv["silver_lines"]
    assert sl["basis"] == "text_match"
    assert sl["total"] == len(bd.flatten_values(gold_doc(view_env)))      # 실버 값 전체(결과와 짝지은 값 포함)
    assert len([g for g in dv["silver_only"] if g["lines"]]) <= sl["found"] < sl["total"]   # 근거 없는 칸(신호어 등)도 있다
    assert all(set(v["silver"]) == {"value", "same", "text"} for v in dv["values"])          # 짝지은 실버 값의 키는 그대로


def test_doc_view_silver_lines_not_found(bd, view_env):
    """근거 글이 다른 쪽에 있거나(독성) 어디에도 없으면(CMR) 줄을 붙이지 않고, found가 그 값 수만큼 준다."""
    before = doc_view_r1(bd, view_env)
    gold = gold_doc(view_env)
    for e in gold["msds"][0]["evidence"]:
        if e["field"].startswith("toxicity[0]"):
            e["page"] = 1                                                   # 같은 글이 1쪽에는 없다
        if e["field"] == "cmr[0]":
            e["source_text"] = "어디에도 없는 가상 글"
    write_json(view_env / "gold2" / f"{X01}.json", gold)
    after = doc_view_r1(bd, view_env, view_env / "gold2")
    moved = under(bd.flatten_values(gold_doc(view_env), as_dicts(LINES)), "toxicity[0]", "cmr[0]")
    assert moved and all(v["lines"] for v in moved)                         # 고치기 전에는 줄을 찾았다
    assert all(g["lines"] == [] for g in after["silver_only"] if g["table"] == "toxicity")
    assert after["silver_lines"]["total"] == before["silver_lines"]["total"]
    assert before["silver_lines"]["found"] - after["silver_lines"]["found"] == len(moved)


def test_doc_view_silver_lines_keep_result_lines_and_line_index(bd, view_env, tmp_path):
    """실버 줄은 line_index에 넣지 않는다. 실버가 있든 없든 결과 값의 줄과 line_index는 같다."""
    dv = doc_view_r1(bd, view_env)
    alone = doc_view_r1(bd, view_env, tmp_path / "빈 정답지")
    assert alone["has_gold"] is False
    assert dv["line_index"] == alone["line_index"]
    assert [(v["path"], v["lines"]) for v in dv["values"]] == [(v["path"], v["lines"]) for v in alone["values"]]
    assert "p5:L8" not in dv["line_index"]                                  # 빠뜨린 독성 행의 추정 줄은 값을 켜지 않는다


def test_doc_view_silver_without_evidence(bd, view_env):
    gold = gold_doc(view_env)
    del gold["msds"][0]["evidence"]
    write_json(view_env / "gold2" / f"{X01}.json", gold)
    dv = doc_view_r1(bd, view_env, view_env / "gold2")
    assert dv["silver_only"] and all(g["lines"] == [] for g in dv["silver_only"])
    assert dv["silver_lines"] == {"basis": "text_match", "found": 0, "total": len(bd.flatten_values(gold))}


def test_doc_view_and_pages_view_without_gold_have_no_silver_lines(bd, view_env, tmp_path):
    assert doc_view_r1(bd, view_env, tmp_path / "빈 정답지")["silver_lines"] is None
    assert bd.pages_view(X01, view_env / "pages9")["silver_lines"] is None


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


def test_route_doc_adds_legend_and_text_without_changing_values(app, view_env):
    ctx = make_ctx(app, view_env, view_env / "pages9")
    expected = app.bdoc.doc_view(view_env / "runs" / "r1", X01, ctx.pages_dir, ctx.gold_dir)
    code, _, body = app.route("GET", "/api/doc", {"run": ["r1"], "doc": [X01]}, None, ctx)
    data = json.loads(body)
    assert code == 200
    assert data["legend"] == app.bt.doc_legend()
    assert data["ui_text"] == app.bt.doc_ui_text(expected)
    assert {k: v for k, v in data.items() if k not in {"legend", "ui_text", "set", "image_base", "image_query", "key"}} \
        == json.loads(json.dumps(expected))


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



def test_route_doc_errors_have_message_and_fix_without_lock_reason(app, view_env):
    ctx = make_ctx(app, view_env, view_env / "pages9")
    for q in ({"run": ["r1"], "doc": [X09]}, {"doc": [X09]}, {"run": ["r1"], "doc": [X02]}):
        code, _, body = app.route("GET", "/api/doc", q, None, ctx)
        data = json.loads(body)
        assert code == 404 and all(data[k].strip() for k in ("error", "message", "fix")), q
        assert "평가" not in data["error"] + data["message"] + data["fix"], q    # 잠긴 이유는 말하지 않는다
    (view_env / "pages_empty" / X01).mkdir(parents=True)                       # 문서 폴더는 있는데 쪽 글자가 없다
    code, _, body = app.route("GET", "/api/doc", {"doc": [X01]}, None, make_ctx(app, view_env, view_env / "pages_empty"))
    data = json.loads(body)
    assert code == 404 and data["error"] == f"쪽 글자가 없습니다: pages_empty/{X01}" and data["message"] and data["fix"]

def test_route_page_png(app, env, one_page):
    ctx = make_ctx(app, env, one_page)
    code, ctype, body = app.route("GET", "/pages/T21-X01/p001.png", {}, None, ctx)
    assert (code, ctype, body) == (200, "image/png", PNG)
    assert app.route("GET", "/pages/T21-X01/p002.png", {}, None, ctx)[0] == 404       # 없는 쪽



def test_route_page_errors_have_message_and_fix(app, env, one_page):
    write_page(one_page / X09, 1, PAGE_TXT, ENTRIES)
    ctx = make_ctx(app, env, one_page)
    for path, want in (("/pages/T21-X09/p001.png", 404), ("/pages/T21-X01/p009.png", 404), ("/pages/x/p1.png", 400)):
        code, _, body = app.route("GET", path, {}, None, ctx)
        data = json.loads(body)
        assert code == want and all(data[k].strip() for k in ("error", "message", "fix")), path
        assert "평가" not in data["error"] + data["message"] + data["fix"], path

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


def test_source_calls_doc_api_and_uses_the_returned_page_route():
    # 옛 파일의 문자열 검사를 새 화면의 실제 요청·이미지 주소 검사로 이관한다.
    from test_B_b_app_dom import run_js
    from test_B_b_app_source_ui import fixture

    run_js(fixture() + r"""
view.image_base='/pages/T21-X01/';
await go('s02',{run:'current',doc:'T21-X01',section:8});
const request=calls.find(path=>path.startsWith('/api/doc?'));
assert.ok(request);
assert.equal(new URLSearchParams(request.split('?')[1]).get('doc'),'T21-X01');
assert.equal(el('source-page').querySelector('img').getAttribute('src'),
 '/pages/T21-X01/p002.png?set=prev%2Ffake');
""")


# ── 묶음을 따르는 원문 대조 (ADR-028) ─────────────────

V9_PAGE = ["L001 가상 판 9 첫 줄", "L002 제품명 : 가상 세정액 A", "L003 가상물질 갑 | 1234-56-6"]
V13_PAGE = ["L001 가상 판 13 첫 줄", "L002 가상 다른 판"]
STARTUP_PAGE = ["L001 켤 때 받은 가상 판", "L002 가상 글"]
RAW_PAGE = ["L001 가상 신규 문서", "L002 제품명 : 가상 도료 B"]
V9_PNG = b"\x89PNG\r\n\x1a\nfake-v9"
RAW_PNG = b"\x89PNG\r\n\x1a\nfake-raw"
ADDED = {"legend", "ui_text", "set", "image_base", "image_query", "key"}


@pytest.fixture
def sets_env(env):
    """가짜 data/pages: prev/v9(X01·X02·X09), prev/v13(X01), 바로 아래 RAW-90(meta.json 있음)·RAW-91(없음).
    앱을 켤 때 받은 폴더(startup/)에는 X01만 다른 글로 있다. 실행 r1은 옛 경로 data/pages/v9로 돌았다고 적혀 있다."""
    root = env / "data" / "pages"
    for d in (X01, X02, X09):
        write_page(root / "prev" / "v9" / d, 1, V9_PAGE, ENTRIES, png=V9_PNG)
    write_page(root / "prev" / "v13" / X01, 1, V13_PAGE, [])
    write_page(root / "RAW-90", 1, RAW_PAGE, png=RAW_PNG)                 # pNNN.json이 없는 판
    write_json(root / "RAW-90" / "meta.json", {"doc_id": "RAW-90", "source_file": "가상.pdf"})
    write_page(root / "RAW-91", 1, RAW_PAGE)                               # meta.json 없음 → 용도를 모름
    write_page(env / "startup" / X01, 1, STARTUP_PAGE, [])
    make_run(env / "runs", "r1", {X01: make_doc(X01), X09: make_doc(X09)}, info={"pages_dir": "data/pages/v9"})
    return env


def sets_ctx(app, env, **kw):
    return app.AppContext(runs_dir=env / "runs", gold_dir=env / "gold", pages_dir=env / "startup",
                          static_dir=app.STATIC, cache_dir=None, gaps_file=env / "silver_gaps.yaml",
                          pages_root=kw.pop("pages_root", env / "data" / "pages"), **kw)


def get_doc(app, ctx, **q):
    code, _, body = app.route("GET", "/api/doc", {k: [v] for k, v in q.items()}, None, ctx)
    return code, json.loads(body)


def texts(data):
    return [l["text"] for l in data["lines"]]


def plain(page):
    return [t.split(" ", 1)[1] for t in page]


def test_allowed_doc_with_folder(bd, sets_env):
    root = sets_env / "data" / "pages"
    assert bd.allowed_doc(X01) is True and bd.allowed_doc(X09) is False
    assert bd.allowed_doc("RAW-90") is False                              # 인자 하나: manifest 밖은 막는다(옛 동작)
    assert bd.allowed_doc("RAW-90", root / "RAW-90") is True              # meta.json의 doc_id가 폴더 이름과 같다
    assert bd.allowed_doc("RAW-91", root / "RAW-91") is False
    assert bd.allowed_doc(X09, root / "prev" / "v9" / X09) is False


def test_pages_view(bd, sets_env):
    root = sets_env / "data" / "pages"
    pv = bd.pages_view("RAW-90", root)
    assert texts(pv) == plain(RAW_PAGE) and all(l["bbox"] is None for l in pv["lines"])   # 칸 좌표 없이 글자만
    assert pv["doc_id"] == "RAW-90" and pv["pages"] == [1] and pv["sections"] == {}
    assert (pv["values"], pv["silver_only"], pv["line_index"], pv["has_gold"], pv["warnings"]) == ([], [], {}, False, [])
    dv = bd.doc_view(sets_env / "runs" / "r1", X01, root / "prev" / "v9", sets_env / "gold")
    assert set(pv) == set(dv)
    assert bd.pages_view(X01, root / "prev" / "v9")["lines"][2]["bbox"] == [10, 98, 400, 122]
    for doc_id, folder in (("RAW-91", root), (X09, root / "prev" / "v9")):
        with pytest.raises(PermissionError):
            bd.pages_view(doc_id, folder)


def test_doc_view_locks_by_folder(bd, sets_env):
    root = sets_env / "data" / "pages"
    make_run(sets_env / "runs", "r_raw", {"RAW-90": make_doc("RAW-90"), "RAW-91": make_doc("RAW-91")})
    dv = bd.doc_view(sets_env / "runs" / "r_raw", "RAW-90", root, sets_env / "gold")
    assert texts(dv) == plain(RAW_PAGE)
    with pytest.raises(PermissionError):
        bd.doc_view(sets_env / "runs" / "r_raw", "RAW-91", root, sets_env / "gold")


def test_route_doc_follows_moved_run_folder(app, sets_env):
    root = sets_env / "data" / "pages"
    code, data = get_doc(app, sets_ctx(app, sets_env), run="r1", doc=X01)
    assert code == 200
    assert texts(data) == plain(V9_PAGE)                                   # 켤 때 받은 폴더(startup/)가 아니다
    assert data["set"]["id"] == "prev/v9" and data["set"]["source"] == "moved"
    assert data["set"]["label"] == app.bt.set_label("prev/v9")
    assert data["set"]["note"] == app.bt.SET_TEXT["run_moved"].format(recorded="data/pages/v9", id="prev/v9")
    assert data["set"]["note"] not in data["warnings"]
    assert data["image_base"] == f"/pages/{X01}/" and data["image_query"] == "?set=prev%2Fv9"
    expected = app.bdoc.doc_view(sets_env / "runs" / "r1", X01, root / "prev" / "v9", sets_env / "gold")
    assert {k: v for k, v in data.items() if k not in ADDED} == json.loads(json.dumps(expected))


def test_route_doc_run_folder_as_recorded(app, sets_env):
    make_run(sets_env / "runs", "r_new", {X01: make_doc(X01)}, info={"pages_dir": "data/pages/prev/v13"})
    code, data = get_doc(app, sets_ctx(app, sets_env), run="r_new", doc=X01)
    assert code == 200 and texts(data) == plain(V13_PAGE)
    assert data["set"] == {"id": "prev/v13", "label": "prev/v13", "source": "run", "note": None}


def test_route_doc_set_param_comes_first(app, sets_env):
    ctx = sets_ctx(app, sets_env)
    code, data = get_doc(app, ctx, run="r1", doc=X01, set="prev/v13")
    assert code == 200 and texts(data) == plain(V13_PAGE)
    assert data["set"] == {"id": "prev/v13", "label": "prev/v13", "source": "param", "note": None}
    assert data["image_query"] == "?set=prev%2Fv13"
    code, data = get_doc(app, ctx, run="r1", doc=X01, set="없는_묶음")
    assert code == 404
    assert get_doc(app, ctx, run="r1", doc=X01, set="../x")[0] == 404
    assert get_doc(app, ctx, run="r1", doc=X01, set=".")[0] == 404        # 그 묶음에 문서가 없다
    code, data = get_doc(app, ctx, run="r1", doc=X09, set="prev/v9")
    assert code == 404 and "평가" not in data["error"]


def test_route_doc_run_folder_not_found_falls_back(app, sets_env, monkeypatch):
    ctx = sets_ctx(app, sets_env)
    make_run(sets_env / "runs", "r_lost", {X01: make_doc(X01), X02: make_doc(X02)},
             info={"pages_dir": "data/pages/없는판"})
    code, data = get_doc(app, ctx, run="r_lost", doc=X01)
    assert code == 200 and texts(data) == plain(STARTUP_PAGE)              # 3. 켤 때 받은 폴더
    assert data["set"]["id"] is None and data["set"]["source"] == "startup"
    assert data["set"]["note"] == app.bt.SET_TEXT["run_missing"].format(recorded="data/pages/없는판", name="startup")
    assert data["image_query"] == ""
    monkeypatch.setattr(app.bsets, "DEFAULT_SET", "prev/v9")
    code, data = get_doc(app, ctx, run="r_lost", doc=X02)                  # 4. 켤 때 받은 폴더에 없으면 기본 묶음
    assert code == 200 and texts(data) == plain(V9_PAGE)
    assert data["set"]["id"] == "prev/v9" and data["set"]["source"] == "default"
    assert data["set"]["note"] == app.bt.SET_TEXT["run_missing"].format(recorded="data/pages/없는판", name="prev/v9")
    make_run(sets_env / "runs", "r_none", {X01: make_doc(X01)}, info={"pages_dir": None})
    code, data = get_doc(app, ctx, run="r_none", doc=X01)
    assert code == 200 and "기록 없음" in data["set"]["note"]


def test_route_doc_without_run(app, sets_env, monkeypatch):
    ctx = sets_ctx(app, sets_env)
    code, data = get_doc(app, ctx, doc="RAW-90", set=".")
    assert code == 200 and texts(data) == plain(RAW_PAGE)
    assert data["values"] == [] and data["lines"] and data["has_gold"] is False
    assert data["set"] == {"id": ".", "label": app.bt.set_label("."), "source": "param", "note": None}
    assert data["image_base"] == "/pages/RAW-90/" and data["image_query"] == "?set=."
    assert {k: v for k, v in data.items() if k not in ADDED} == app.bdoc.pages_view("RAW-90", sets_env / "data" / "pages")
    assert get_doc(app, ctx, doc="RAW-91", set=".")[0] == 404
    code, data = get_doc(app, ctx, doc=X09, set="prev/v9")
    assert code == 404 and "평가" not in data["error"]
    code, data = get_doc(app, ctx, doc=X09)
    assert code == 404 and "평가" not in data["error"]
    code, data = get_doc(app, ctx, doc=X01)                                # 묶음 없이: 켤 때 받은 폴더
    assert code == 200 and texts(data) == plain(STARTUP_PAGE)
    assert data["set"] == {"id": None, "label": "startup", "source": "startup", "note": None}
    monkeypatch.setattr(app.bsets, "DEFAULT_SET", "prev/v9")
    code, data = get_doc(app, ctx, doc=X02)
    assert code == 200 and data["set"]["source"] == "default" and data["set"]["note"] is None
    assert get_doc(app, ctx, doc="RAW-01", run="없는실행")[0] == 404
    assert get_doc(app, ctx, doc="raw-90", set=".")[0] == 400
    assert get_doc(app, ctx, doc="..", set=".")[0] == 400


def test_route_doc_without_root_is_old_behavior(app, sets_env):
    ctx = make_ctx(app, sets_env, sets_env / "startup")
    assert ctx.pages_root is None
    code, data = get_doc(app, ctx, run="r1", doc=X01)
    assert code == 200 and texts(data) == plain(STARTUP_PAGE)
    assert data["set"]["source"] == "startup" and data["set"]["id"] is None
    assert get_doc(app, ctx, run="r1", doc=X01, set="prev/v9")[0] == 404  # 묶음 목록이 없다


def test_route_page_png_with_set(app, sets_env):
    ctx = sets_ctx(app, sets_env)

    def png(path, **q):
        return app.route("GET", path, {k: [v] for k, v in q.items()}, None, ctx)

    assert png("/pages/RAW-90/p001.png", set=".") == (200, "image/png", RAW_PNG)
    assert png(f"/pages/{X01}/p001.png", set="prev/v9") == (200, "image/png", V9_PNG)
    assert png(f"/pages/{X01}/p001.png") == (200, "image/png", PNG)        # 쿼리가 없으면 켤 때 받은 폴더
    for path, q in ((f"/pages/{X09}/p001.png", "prev/v9"), (f"/pages/{X01}/p001.png", "../x"),
                    ("/pages/RAW-91/p001.png", "."), (f"/pages/{X01}/p001.png", "."),
                    (f"/pages/{X01}/p002.png", "prev/v9"), (f"/pages/{X01}/p001.png", "없는_묶음")):
        code, _, body = png(path, set=q)
        assert code == 404 and body not in (PNG, V9_PNG, RAW_PNG), (path, q)
    assert png("/pages/RAW-90/p001.png")[0] == 404                         # 켤 때 받은 폴더에 없다
    assert png("/pages/raw-90/p001.png", set=".")[0] == 400
    no_root = make_ctx(app, sets_env, sets_env / "startup")
    assert app.route("GET", f"/pages/{X01}/p001.png", {"set": ["prev/v9"]}, None, no_root)[0] == 404


# ── row_groups: 칸을 표의 행으로 묶는다 (phase app-steps step 4, STEPS.md A4·A5) ──

KINDS = ("wrong", "made", "missing")
ITEM_8 = "8항 노출기준(성분·출처·종류·값)"


def rows_gold() -> dict:
    """성분 이름이 가짜성분A·B·C인 가짜 문서. 번호는 seq 1·2·3이다 (D-43, 직접 만든 값)."""
    doc = scored_doc()
    m = doc["msds"][0]
    for c, name in zip(m["components"], ("가짜성분A", "가짜성분B", "가짜성분C")):
        c["name"] = name
    m["regulations"][0]["item_raw"] = "가짜 측정 대상"
    return doc


def edited(*edits) -> dict:
    """rows_gold에 (경로, 값)을 적용한 결과 문서."""
    doc = rows_gold()
    for path, value in edits:
        set_(doc["msds"][0], path, value)
    return doc


def rows_view(bd, env, pred, gold=None, name="rg"):
    write_json(env / "gold" / f"{X01}.json", gold if gold is not None else rows_gold())
    make_run(env / "runs", name, {X01: pred})
    return bd.doc_view(env / "runs" / name, X01, env / "pages9", env / "gold")


def group(dv, table, row=None, gold_row=None):
    hits = [g for g in dv["row_groups"] if g["table"] == table and g["row"] == row and g["gold_row"] == gold_row]
    assert len(hits) == 1, (table, row, gold_row, [(g["table"], g["row"], g["gold_row"]) for g in dv["row_groups"]])
    return hits[0]


def cell(g, path, side="result"):
    hits = [c for c in g["cells"] if c["path"] == path and c["side"] == side]
    assert len(hits) == 1, path
    return hits[0]


def test_row_group_gathers_cells_of_one_row_with_table_title_and_counts(bd, view_env):
    dv = rows_view(bd, view_env, edited(("exposure_limits[0].q.raw", "9 ppm")))
    g = group(dv, "exposure_limits", row=0, gold_row=0)
    paths = [v["path"] for v in dv["values"] if v["table"] == "exposure_limits" and v["row"] == 0]
    assert len(paths) >= 4 and [c["path"] for c in g["cells"]] == paths     # 같은 행의 칸을 모두 담는다
    assert g["table_label"] == "노출기준" and g["section"] == 8 and g["paired"] is True
    assert g["title"] == "가짜성분A / 국내기준 / TWA"
    assert g["counts"] == {"wrong": 1, "made": 0, "missing": 0}
    assert cell(g, "msds[0].exposure_limits[0].q")["kind"] == "wrong"
    assert cell(g, "msds[0].exposure_limits[0].standard")["kind"] == "same"
    assert cell(g, "msds[0].exposure_limits[0].q")["items"] == [ITEM_8]


def test_silver_only_cell_joins_the_paired_result_row(bd, view_env):
    dv = rows_view(bd, view_env, edited(("toxicity[0].species", None)))
    g = group(dv, "toxicity", row=0, gold_row=0)
    only = cell(g, "msds[0].toxicity[0].species", side="silver_only")
    assert only["kind"] == "missing" and only["field"] == "species"
    assert g["paired"] is True and g["counts"] == {"wrong": 0, "made": 0, "missing": 1}
    # 빠뜨린 칸이 구분 값이어도 짝 정답 행의 값으로 제목을 만든다
    assert g["title"] == "가짜성분B / 급성 독성(경구) / LD50 / 랫드"


def test_gold_row_without_a_pair_is_grouped_by_gold_row_and_marked(bd, view_env):
    pred = rows_gold()
    pred["msds"][0]["toxicity"] = []
    dv = rows_view(bd, view_env, pred)
    g = group(dv, "toxicity", row=None, gold_row=0)
    assert g["paired"] is False and g["table_label"] == "독성" and g["section"] == 11
    assert {c["side"] for c in g["cells"]} == {"silver_only"} and {c["kind"] for c in g["cells"]} == {"missing"}
    assert g["counts"] == {"wrong": 0, "made": 0, "missing": len(g["cells"])} and len(g["cells"]) >= 4
    assert g["title"] == "가짜성분B / 급성 독성(경구) / LD50 / 랫드"


def test_result_row_without_a_pair_is_made_and_marked(bd, view_env):
    pred = rows_gold()
    pred["msds"][0]["cmr"].append({**copy.deepcopy(pred["msds"][0]["cmr"][0]), "agency": "가상기관", "hazard": "생식독성",
                                   "class": "9", "comp_ref": "3", "status": "자료없음"})
    dv = rows_view(bd, view_env, pred)
    g = group(dv, "cmr", row=1, gold_row=None)
    assert g["paired"] is False and {c["kind"] for c in g["cells"]} == {"made"}
    assert g["counts"] == {"wrong": 0, "made": len(g["cells"]), "missing": 0}
    assert g["title"] == "가짜성분C / 생식독성 / 가상기관"                   # 이름표가 없는 값은 원래 표기 그대로


def test_row_paired_by_similar_cells_uses_its_own_comp_ref(bd, view_env):
    dv = rows_view(bd, view_env, edited(("exposure_limits[0].comp_ref", "MIX")))
    g = group(dv, "exposure_limits", row=0, gold_row=0)
    assert g["title"] == "제품 전체 / 국내기준 / TWA"
    assert cell(g, "msds[0].exposure_limits[0].comp_ref")["kind"] == "wrong"


def test_comp_ref_links_to_components_of_the_same_document(bd, view_env):
    """성분 번호는 문서마다 다르다. AI 행은 AI의 3항으로, 정답 행은 정답의 3항으로 잇는다."""
    pred = rows_gold()
    m = pred["msds"][0]
    m["components"][0]["name"], m["components"][1]["name"] = "가짜성분B", "가짜성분A"   # AI는 번호를 바꿔 뽑았다
    m["toxicity"] = []
    m["exposure_limits"][0]["comp_ref"] = "2"                                         # AI의 2번 = 가짜성분A
    dv = rows_view(bd, view_env, pred)
    assert group(dv, "toxicity", row=None, gold_row=0)["title"].startswith("가짜성분B / ")   # 정답의 2번
    assert group(dv, "exposure_limits", row=0, gold_row=0)["title"] == "가짜성분A / 국내기준 / TWA"


def test_unlinked_comp_ref_shows_the_row_number_and_invents_no_name(bd, view_env):
    dv = rows_view(bd, view_env, edited(("exposure_limits[0].comp_ref", "9")))
    assert group(dv, "exposure_limits", row=0, gold_row=0)["title"] == "1행 / 국내기준 / TWA"
    gold = rows_gold()
    gold["msds"][0]["exposure_limits"][0]["comp_ref"] = "9"
    pred = rows_gold()
    pred["msds"][0]["exposure_limits"] = []
    dv = rows_view(bd, view_env, pred, gold, name="rg2")
    assert group(dv, "exposure_limits", row=None, gold_row=0)["title"] == "정답 1행 / 국내기준 / TWA"


def test_blank_comp_ref_uses_the_paired_gold_row(bd, view_env):
    dv = rows_view(bd, view_env, edited(("exposure_limits[0].comp_ref", None)))
    g = group(dv, "exposure_limits", row=0, gold_row=0)
    assert g["title"] == "가짜성분A / 국내기준 / TWA"
    assert cell(g, "msds[0].exposure_limits[0].comp_ref", side="silver_only")["kind"] == "missing"


def test_non_table_value_is_a_one_cell_group(bd, view_env):
    dv = rows_view(bd, view_env, edited(("hazard.signal_word", "위험"), ("meta.msds_no", None)))
    signal = [g for g in dv["row_groups"] if g["cells"][0]["path"] == "msds[0].hazard.signal_word"]
    assert len(signal) == 1
    g = signal[0]
    assert (g["row"], g["gold_row"], g["paired"], g["table_label"]) == (None, None, None, "유해성")
    assert [c["kind"] for c in g["cells"]] == ["wrong"] and g["counts"] == {"wrong": 1, "made": 0, "missing": 0}
    assert g["title"] == "신호어"
    only = [g for g in dv["row_groups"] if g["cells"][0]["path"] == "msds[0].meta.msds_no"]
    assert len(only) == 1 and only[0]["cells"][0]["side"] == "silver_only" and only[0]["title"] == "제출번호"
    assert only[0]["counts"] == {"wrong": 0, "made": 0, "missing": 1}


@pytest.mark.parametrize("section,table,path,title", [
    (8, "exposure_limits", "exposure_limits[0].q.raw", "가짜성분A / 국내기준 / TWA"),
    (9, "physchem", "physchem[0].q.raw", "제품 전체 / 인화점"),
    (11, "toxicity", "toxicity[0].q.raw", "가짜성분B / 급성 독성(경구) / LD50 / 랫드"),
    (11, "cmr", "cmr[0].class", "제품 전체 / 발암성 / IARC"),
    (12, "ecotox", "ecotox[0].q.raw", "가짜성분B / 어류 독성 / LC50 / 가상 어류"),
    (15, "regulations", "regulations[0].applicable", "가짜성분A / 산업안전보건법 / 가짜 측정 대상"),
])
def test_rows_of_sections_8_9_11_12_15(bd, view_env, section, table, path, title):
    """계획 9장에서 재 보지 않은 부분: 항마다 묶음·짝·제목이 맞고, 정답 행만 남아도 같은 제목이다."""
    dv = rows_view(bd, view_env, edited((path, "가짜 다른 값")))
    g = group(dv, table, row=0, gold_row=0)
    assert g["section"] == section and g["paired"] is True and g["title"] == title
    assert g["counts"] == {"wrong": 1, "made": 0, "missing": 0}
    assert g["table_label"] == bd.bt.UI_TEXT["source"]["table_names"][table]
    others = [o for o in dv["row_groups"] if o is not g]
    assert all(sum(o["counts"].values()) == 0 for o in others)              # 다른 묶음에는 문제가 없다
    pred = rows_gold()
    pred["msds"][0][table] = []
    alone = group(rows_view(bd, view_env, pred, name=f"rg_{table}"), table, row=None, gold_row=0)
    assert alone["section"] == section and alone["paired"] is False and alone["title"] == title


def many_problems() -> dict:
    pred = edited(("exposure_limits[0].q.raw", "9 ppm"), ("hazard.signal_word", "위험"), ("meta.msds_no", None),
                  ("toxicity[0].species", None), ("components[0].ke_no", None), ("components[1].content.raw", "9"))
    m = pred["msds"][0]
    m["cmr"].append({**copy.deepcopy(m["cmr"][0]), "agency": "가상기관", "hazard": "생식독성", "comp_ref": "3"})
    m["ecotox"] = []
    del m["regulations"][1:]                                                # 정답 행 1·2가 짝 없이 남는다
    return pred


def test_groups_keep_every_cell_exactly_once(bd, view_env):
    dv = rows_view(bd, view_env, many_problems())
    got = [(c["side"], c["path"]) for g in dv["row_groups"] for c in g["cells"]]
    want = [("result", v["path"]) for v in dv["values"]] + [("silver_only", g["path"]) for g in dv["silver_only"]]
    assert sorted(got) == sorted(want) and len(got) == len(set(got))        # 잃지도 겹치지도 않는다
    kinds = Counter(c["kind"] for g in dv["row_groups"] for c in g["cells"])
    assert {k: kinds[k] for k in KINDS} == {k: sum(g["counts"][k] for g in dv["row_groups"]) for k in KINDS}
    problems = sum(not v["silver"]["same"] for v in dv["values"]) + len(dv["silver_only"])
    assert sum(sum(g["counts"].values()) for g in dv["row_groups"]) == problems > 0
    assert kinds["made"] > 0 and kinds["wrong"] > 0 and kinds["missing"] > 0


def test_groups_are_ordered_by_section_then_table_and_gold_rows_come_last(bd, view_env):
    pred = many_problems()
    pred["msds"][0]["toxicity"].pop(0)
    dv = rows_view(bd, view_env, pred)
    sections = [g["section"] if g["section"] is not None else 99 for g in dv["row_groups"]]
    assert sections == sorted(sections)
    tox = [g for g in dv["row_groups"] if g["table"] == "toxicity"]
    assert [g["paired"] for g in tox] == sorted((g["paired"] for g in tox), reverse=True)
    assert len({g["id"] for g in dv["row_groups"]}) == len(dv["row_groups"])  # 다시 고를 때 쓰는 표시가 겹치지 않는다


def test_row_groups_only_add_a_key(bd, view_env):
    dv = rows_view(bd, view_env, many_problems())
    assert set(dv) == {"doc_id", "pages", "lines", "sections", "values", "silver_only", "line_index", "has_gold",
                       "silver_lines", "warnings", "row_groups"}
    assert {k for v in dv["values"] for k in v} == {"path", "key", "section", "table", "row", "field", "value", "text",
                                                    "lines", "items", "silver"}
    assert {k for v in dv["silver_only"] for k in v} == {"path", "key", "section", "table", "row", "field", "value",
                                                         "text", "lines", "items", "pair_row"}
    assert set(dv["row_groups"][0]) == {"id", "table", "table_label", "section", "row", "gold_row", "paired", "title",
                                        "cells", "counts"}
    assert set(dv["row_groups"][0]["cells"][0]) == {"path", "side", "field", "section", "kind", "items"}


def test_route_doc_carries_row_groups(app, view_env):
    write_json(view_env / "gold" / f"{X01}.json", rows_gold())
    make_run(view_env / "runs", "rg", {X01: many_problems()})
    ctx = make_ctx(app, view_env, view_env / "pages9")
    code, _, body = app.route("GET", "/api/doc", {"run": ["rg"], "doc": [X01]}, None, ctx)
    data = json.loads(body)
    assert code == 200 and data["row_groups"]
    assert data["row_groups"] == json.loads(json.dumps(
        app.bdoc.doc_view(view_env / "runs" / "rg", X01, ctx.pages_dir, ctx.gold_dir)["row_groups"]))
    assert {"values", "silver_only", "line_index", "legend", "ui_text", "set", "key"} <= data.keys()


def test_without_gold_rows_are_uncompared_and_have_no_pair_mark(bd, view_env):
    (view_env / "gold" / f"{X01}.json").unlink()
    dv = bd.doc_view(view_env / "runs" / "r1", X01, view_env / "pages9", view_env / "gold")
    assert dv["row_groups"] and {c["kind"] for g in dv["row_groups"] for c in g["cells"]} == {"uncompared"}
    assert all(g["paired"] is None and g["gold_row"] is None for g in dv["row_groups"])
    assert all(sum(g["counts"].values()) == 0 for g in dv["row_groups"])


def test_pages_view_has_no_row_groups(bd, view_env):
    assert bd.pages_view(X01, view_env / "pages9")["row_groups"] == []


# ── 문제 행 수: 문제 목록(/api/run의 losses)에 싣는다 ──

def test_problem_counts_keep_field_counts_and_count_a_row_once(bd):
    pred, gold = edited(("exposure_limits[0].q.raw", "9 ppm"), ("exposure_limits[0].limit_type", "STEL")), rows_gold()
    field, rows = bd.problem_counts(pred, gold)
    assert field == bd.field_counts(pred, gold)
    assert sum(n for (item, _, _), n in field.items() if item == ITEM_8) == 2  # 칸은 둘
    assert rows[(ITEM_8, 8)] == 1                                              # 행은 하나


def test_problem_counts_count_a_row_for_each_item_of_its_problem_cells(bd):
    pred = edited(("components[1].content.raw", "9"), ("components[1].ke_no", "KE-99999"))
    _, rows = bd.problem_counts(pred, rows_gold())
    assert rows[("함유량(부등호·값·단위 6요소)", 3)] == 1
    assert rows[("구성성분 필드(성분명·KE)", 3)] == 1
    assert rows[("구성성분(CAS 기준 매칭)", 3)] == 0                            # 문제 칸이 이 항목에 들어가지 않는다


def test_problem_counts_match_row_groups_of_the_view(bd, view_env):
    pred, gold = many_problems(), rows_gold()
    dv = rows_view(bd, view_env, pred, gold)
    want = Counter()
    for g in dv["row_groups"]:
        for item in {i for c in g["cells"] if c["kind"] in KINDS for i in c["items"]}:
            want[(item, g["section"])] += 1
    _, rows = bd.problem_counts(pred, gold)
    assert rows == want and sum(rows.values()) > 0
    assert bd.problem_counts(gold, gold) == (Counter(), Counter())             # 같은 문서는 문제가 없다


def test_run_problem_counts_skip_docs_without_output_or_gold(bd, view_env):
    run = view_env / "runs" / "r1"
    field, rows = bd.run_problem_counts(run, view_env / "gold", [X01, X09, "T21-X99"])
    pred = json.loads((run / "outputs" / f"{X01}.json").read_text(encoding="utf-8"))
    gold = json.loads((view_env / "gold" / f"{X01}.json").read_text(encoding="utf-8"))
    assert (field[X01], rows[X01]) == bd.problem_counts(pred, gold)
    assert "T21-X99" not in field and "T21-X99" not in rows
    assert field == bd.run_field_counts(run, view_env / "gold", [X01, X09, "T21-X99"])
