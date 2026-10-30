"""역할 A: 검수 화면 입력. JSON을 모르는 검수자가 적은 글이 칸 모양의 TO21 값이 되고, 틀리면 저장 전에 막히는지 본다."""
import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import review_app as ra  # noqa: E402

TOX = "msds[0].toxicity[k=7664-93-9|TX_ORAL|LD50|랫드]"


def row(path, value="", **kw):
    return {"경로": path, "수정값": "", "Claude 값": value, "GPT 값": "", "검수 결과": "", **kw}


ROWS = [row("msds[0].components[k=7664-93-9].seq", "1"), row("msds[0].components[k=7664-93-9].name", "황산"),
        row(f"{TOX}.comp_ref", '"1"'), row(f"{TOX}.endpoint", "TX_ORAL")]


def typed(path, v):
    return ra._typed(path, {"수정값": v})["수정값"]


def test_value_follows_field_shape():
    q = json.loads(typed(f"{TOX}.q", "> 2000 mg/kg"))
    assert (q["lower_op"], q["lower"], q["unit"], q["status"]) == (">", 2000, "mg/kg", "값있음")
    assert json.loads(typed(f"{TOX}.q", "자료없음"))["status"] == "자료없음"
    assert typed(f"{TOX}.descriptor", "LC50") == "LC50"
    assert typed("msds[0].meta.revision_no", "3") == "3"
    assert typed("msds[0].meta.revision_label", "01") == "01"            # 글 칸: 숫자처럼 보여도 글자
    assert typed(f"{TOX}.comp_ref", "1") == '"1"'                        # 글 칸의 숫자는 따옴표로 남긴다
    assert typed("msds[0].composition.no_hazardous_component", "아니오") == "false"
    assert typed("msds[0].transport[k=육상].regulated", "null") == "null"


@pytest.mark.parametrize("path, v, why", [
    (f"{TOX}.descriptor", "엘디50", "목록에서 골라"),
    ("msds[0].transport[k=육상].packing_group", "3등급", "목록에서 골라"),
    ("msds[0].hazard.p_statements[k=P501].code", "P501X9", r"형식이 맞지 않아요 \(예: P280\)"),   # 영어 스키마 오류 대신
    ("msds[0].meta.revision_no", "셋", "숫자만"),
    (f"{TOX}.q", "- [Benzene] : LD50 Rat (OECD TG 401)", "수치를 읽지 못했습니다"),   # 줄 전체를 붙여 넣은 경우
])
def test_wrong_value_is_stopped_before_save(path, v, why):
    with pytest.raises(ValueError, match=why):
        typed(path, v)


def test_new_item_path_is_built_from_values():
    common = {"수정 원문 조각": "LD50 > 8260 mg/kg", "수정 쪽": "6"}
    got = ra._new_rows(TOX, "new", {"comp_ref": "1", "endpoint": "TX_DERMAL", "descriptor": "LD50", "species": "토끼", "q": "> 8260 mg/kg"},
                       common, ROWS)
    assert {r["경로"] for r in got} == {f"msds[0].toxicity[k=7664-93-9|TX_DERMAL|LD50|토끼].{k}"
                                        for k in ("comp_ref", "endpoint", "descriptor", "species", "q")}
    again = ra._new_rows(TOX, "new", {"comp_ref": "1", "endpoint": "TX_ORAL", "descriptor": "LD50", "species": "랫드"}, common, ROWS)
    assert again[0]["경로"].startswith(TOX[:-1] + "#2]")              # 같은 키가 이미 있으면 keyed_flatten처럼 '#2'"
    with pytest.raises(ValueError, match="대상 성분"):
        ra._new_rows(TOX, "new", {"endpoint": "TX_DERMAL"}, common, ROWS)
    assert [r["경로"] for r in ra._new_rows(TOX, "field", {"species": "랫드", "sex": ""}, common, ROWS)] == [f"{TOX}.species"]


def test_item_form_lists_missing_fields_by_name():
    f = ra._item_form(TOX, ROWS)
    names = {x["name"] for x in f["missing"]}
    assert "comp_ref" not in names and "q" in names
    keys = [x["name"] for x in f["new"]["fields"] if x["key"]]
    assert keys == ["comp_ref", "endpoint", "descriptor", "species"]


def test_must_matches_scorer():
    assert ra._must(f"{TOX}.q") == "11항 급성독성(경구·경피·흡입)"
    assert ra._must("msds[0].toxicity[k=7664-93-9|TX_STOT_SE|결과기술|].q") == ""
    assert ra._must("msds[0].regulations[k=1|OSH|OSH_MANAGED|].applicable").startswith("15항 국내 규제")
    assert ra._must("msds[0].transport[k=육상].packing_group").startswith("14항")


def test_convention_value_is_explained():
    item = "msds[0].toxicity[k=MIX|TX_INHAL|결과기술|]"
    rows = [row(f"{item}.status", "자료없음"), row(f"{item}.descriptor", "결과기술")]
    assert "표기 규칙" in ra._explain(rows[1], rows)


def test_pick_keeps_original_text():
    chars = [(ch, (10 * i, 0, 10 * i + 10, 10)) for i, ch in enumerate("P264씻으시오")]
    pg = ra._Page([(ra._norm(c), b) for c, b in chars], 1000, 1000)
    pg.raw = {id(b): c for c, b in chars}
    assert ra._pick(pg, 0.02, 0.005)["line"] == "P264씻으시오"


def test_no_matching_field_goes_to_extras():
    stmt = json.dumps({"seq": None, "key": None, "value": "설정되지 않음", "refs": None, "cond": None,
                       "std_code": None, "match_score": None, "text": "x"}, ensure_ascii=False)
    got = {r["경로"].rsplit(".", 1)[-1]: r["수정값"] for r in
           ra._new_rows("msds[0].transport[k=해상]", "extra", {"section_no": "14", "title_raw": "MARPOL 73/78", "": stmt}, {"수정 쪽": "9"}, ROWS)}
    assert got["reason"] == "필드없음" and got["section_no"] == "14" and got["page"] == "9" and json.loads(got["statements[0]"])["seq"] == 1
    with pytest.raises(ValueError, match="항 번호"):
        ra._new_rows("msds[0].transport[k=해상]", "extra", {"section_no": "열넷", "title_raw": "a", "": stmt}, {}, ROWS)


def test_empty_sub_list_gets_new_item():
    company = "msds[0].companies[k=제조자|가나]"
    rows = ROWS + [row(f"{company}.name", "가나")]
    sub = next(x["item"] for x in ra._item_form(company, rows)["lists"])
    assert sub == f"{company}.contacts[*]"
    got = ra._new_rows(sub, "new", {"type": "긴급", "value": "02-1"}, {}, rows)
    assert [r["경로"] for r in got] == [f"{company}.contacts[k=긴급].type", f"{company}.contacts[k=긴급].value"]


def test_page_must_be_number():
    sh = ra.Sheet.__new__(ra.Sheet)
    sh.results = {"수정"}
    with pytest.raises(ValueError, match="쪽은 숫자"):
        sh._check({"검수 결과": "수정", "수정값": "a", "수정 원문 조각": "a", "수정 쪽": "일곱쪽"})
    assert sh._check({"검수 결과": "수정", "수정값": "a", "수정 원문 조각": "a", "수정 쪽": "7, 8"})


def test_unchanged_edit_is_saved_as_adopt(tmp_path, monkeypatch):
    """값·근거 줄·쪽을 바꾸지 않은 '고치기' 저장은 '수정'이 아니라 모델 채택(맞음)으로 남는다."""
    import openpyxl
    from msds.review.sheet_spec import COLUMNS, SHEET_INFO, SHEET_MAIN
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = SHEET_MAIN
    ws.append(list(COLUMNS))
    for p, v in ((f"{TOX}.descriptor", "LD50"), (f"{TOX}.species", "랫드")):
        ws.append([{"경로": p, "Claude 값": v, "Claude 원문 조각": "LD50 > 2000 mg/kg 랫드", "Claude 쪽": 6}.get(c) for c in COLUMNS])
    wb.create_sheet(SHEET_INFO).append(["검수 시작", None])
    wb.save(tmp_path / "T.xlsx")
    monkeypatch.setattr(ra.paths, "review_sheet_path", lambda d: tmp_path / f"{d}.xlsx")
    sh = ra.Sheet("T")
    edit = lambda p, v, src="LD50 > 2000 mg/kg 랫드", pg="6": sh.save_row(p, {"검수 결과": "수정", "수정값": v, "수정 원문 조각": src, "수정 쪽": pg, "검수자": "가"})
    got = edit(f"{TOX}.descriptor", "LD50")
    assert got["검수 결과"] == "Claude 채택" and got["수정값"] == "" and got["수정 원문 조각"] == "" and got["검수자"] == "가"
    assert edit(f"{TOX}.descriptor", "LC50")["검수 결과"] == "수정"                          # 값을 바꿈
    assert edit(f"{TOX}.species", "랫드", src="랫드")["검수 결과"] == "수정"                  # 근거 줄을 바꿈
    assert edit(f"{TOX}.species", "랫드", pg="7")["검수 결과"] == "수정"                      # 쪽을 바꿈
    assert ra.Sheet("T").rows()[0]["검수 결과"] == "수정"                                      # 파일에도 그대로
    q = json.dumps({"raw": "> 2000 mg/kg", "approx": False, "value": None, "lower_op": ">", "lower": 2000, "upper_op": None,
                    "upper": None, "unit": "mg/kg", "dp": 0, "status": "값있음", "note": None})
    sh.wb[SHEET_MAIN].append([{"경로": f"{TOX}.q", "Claude 값": q, "Claude 원문 조각": "LD50 > 2000 mg/kg 랫드", "Claude 쪽": 6}.get(c) for c in COLUMNS])
    typed_q = json.loads(ra._typed(f"{TOX}.q", {"수정값": "> 2000 mg/kg"})["수정값"])
    assert typed_q["approx"] is None or typed_q == json.loads(q)                     # 화면이 다시 나눈 수치는 approx가 None
    assert edit(f"{TOX}.q", "> 2000 mg/kg")["검수 결과"] == "Claude 채택"            # approx False = None
    # 카드 '원문에 없어요' → '되돌리기': 삭제는 수정값·근거·쪽을 비우고, 되돌리기는 화면이 간직한 전 값을 모두 다시 보낸다
    keys = ("검수 결과", "수정값", "수정 원문 조각", "수정 쪽", "메모", "검수자")
    before = {k: v for k, v in edit(f"{TOX}.descriptor", "LC50").items() if k in keys}
    gone = sh.save_row(f"{TOX}.descriptor", {"검수 결과": "삭제", "메모": "원문에 없음", "수정값": "", "수정 원문 조각": "", "수정 쪽": "", "검수자": "가"})
    assert gone["검수 결과"] == "삭제" and gone["수정값"] == gone["수정 원문 조각"] == gone["수정 쪽"] == ""
    back = sh.save_row(f"{TOX}.descriptor", before)
    assert {k: back[k] for k in keys} == before and before["검수 결과"] == "수정"
    with pytest.raises(ValueError, match="모두 적어야"):                              # 결과만 보낸 '수정'은 막는다
        sh.save_row(f"{TOX}.descriptor", {"검수 결과": "수정"})
    # 엑셀에서 '6쪽'처럼 적힌 수정 쪽이 남은 줄도 맞음·메모는 저장된다 (보낸 값만 검사)
    ws, ri = sh.wb[SHEET_MAIN], sh._find(f"{TOX}.species")
    ws.cell(ri, sh.col["수정 쪽"]).value = "6쪽"
    assert sh.save_row(f"{TOX}.species", {"검수 결과": "Claude 채택", "검수자": "가"})["검수 결과"] == "Claude 채택"
    assert sh.save_row(f"{TOX}.species", {"메모": "엑셀에서 적은 쪽"})["메모"] == "엑셀에서 적은 쪽"


def test_restore_writes_previous_human_columns(tmp_path, monkeypatch):
    """카드 되돌리기(/api/restore): 판단 전 사람 열을 검사 없이 그대로 ('6쪽'·숫자 쪽도 바이트 그대로), 지운 누락 추가 줄은 다시 넣는다."""
    import openpyxl
    from msds.review.sheet_spec import COLUMNS, SHEET_INFO, SHEET_MAIN
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = SHEET_MAIN
    ws.append(list(COLUMNS))
    base = {"Claude 원문 조각": "LD50 > 2000 mg/kg 랫드", "Claude 쪽": 6, "일치": "Claude만"}
    ws.append([{**base, "경로": f"{TOX}.species", "Claude 값": "랫드", "검수 결과": "수정", "수정값": "쥐", "수정 원문 조각": "쥐", "수정 쪽": "6쪽",
                "검수자": "엑셀"}.get(c) for c in COLUMNS])
    ws.append([{**base, "경로": f"{TOX}.descriptor", "Claude 값": "LD50", "검수 결과": "Claude 채택", "수정 쪽": 7, "메모": "기존"}.get(c) for c in COLUMNS])
    wb.create_sheet(SHEET_INFO).append(["검수 시작", None])
    wb.save(tmp_path / "T.xlsx")
    monkeypatch.setattr(ra.paths, "review_sheet_path", lambda d: tmp_path / f"{d}.xlsx")
    cells = lambda: [[c.value for c in r] for r in openpyxl.load_workbook(tmp_path / "T.xlsx")[SHEET_MAIN].iter_rows(min_row=2)]
    sh = ra.Sheet("T")
    sh.add_rows([{"경로": f"{TOX}.guideline", "수정값": "OECD TG 401", "수정 원문 조각": "TG 401", "수정 쪽": "6"}])   # 화면으로 넣은 누락 추가 줄
    before = cells()
    prev = [dict(r) for r in sh.rows()]
    sh.save_rows([{"경로": r["경로"], "values": {"검수 결과": "삭제", "메모": r["메모"] or "원문에 없음", "수정값": "", "수정 원문 조각": "", "수정 쪽": ""}}
                  for r in prev[:2]])
    sh.remove_added(f"{TOX}.guideline")
    assert cells() != before and len(cells()) == 2
    with pytest.raises(ValueError, match="검수표에 없는 경로"):                       # 사람이 넣은 줄이 아니면 다시 넣지 않는다 (아무것도 고치지 않음)
        sh.restore([prev[0], {**prev[1], "경로": f"{TOX}.nothing"}])
    sh.restore(prev)
    assert cells() == before                                                          # '6쪽', 숫자 7, 메모, 다시 넣은 줄까지 그대로


def test_typed_keeps_cell_form():
    """이미 칸 글자 꼴인 값(사람이 따옴표까지 적은 값, 검수표에서 옮겨 붙인 값)은 한 번 더 바꾸지 않는다: 글 칸의 '"2"'가 '"\\"2\\""'가 되지 않게."""
    p = "msds[0].regulations[k=1|OSH|OSH_MANAGED|].value_raw"
    once = typed(p, "2")
    assert once == '"2"' and typed(p, once) == once
    q = typed(f"{TOX}.q", "> 2000 mg/kg")
    assert typed(f"{TOX}.q", q) == q and typed(f"{TOX}.comp_ref", "1") == '"1"'
    assert typed(f"{TOX}.descriptor", "LC50") == "LC50" and typed("msds[0].transport[k=육상].regulated", "비움") == "null"


def test_duplicate_item_is_detected():
    """숨은 카드(필수 칸만 등)와 같은 내용을 또 넣으면 저장 전에 묻는다. 값이 다르고 종류(키)만 겹치면 부드럽게 알린다."""
    company = "msds[0].companies[k=제조자|가나]"
    rows = ROWS + [row(f"{company}.name", "가나"), row(f"{company}.contacts[k=긴급].type", "긴급"),
                   row(f"{company}.contacts[k=긴급].value", "080-1")]
    again = ra._new_rows(f"{company}.contacts[*]", "new", {"type": "긴급", "value": "080-1"}, {}, rows)
    assert again[0]["경로"].startswith(f"{company}.contacts[k=긴급#2]") and ra._dup(again, rows) == {"dup": "same"}
    other = ra._new_rows(f"{company}.contacts[*]", "new", {"type": "긴급", "value": "080-2"}, {}, rows)
    assert ra._dup(other, rows) == {"dup": "kind", "kind": "긴급", "n": 1}      # 키만 겹침: '같은 내용'이라 하지 않는다
    assert ra._dup(ra._new_rows(f"{company}.contacts[*]", "new", {"type": "대표", "value": "02-9"}, {}, rows), rows) == {}
    assert ra._dup(ra._new_rows(f"{company}.contacts[*]", "new", {"type": "대표", "value": "080-1"}, {}, rows), rows) == {}   # 값 하나만 같음
    tox = ra._new_rows(TOX, "new", {"comp_ref": "1", "endpoint": "TX_DERMAL", "descriptor": "LD50"}, {}, ROWS)
    rows2 = ROWS + [row(f"msds[0].toxicity[k=7664-93-9|TX_DERMAL|LD50|토끼].{k}", v) for k, v in
                    (("comp_ref", '"1"'), ("endpoint", "TX_DERMAL"), ("descriptor", "LD50"), ("species", "토끼"))]
    assert ra._dup(tox, rows2) == {"dup": "same"}                       # 대상 성분 '1' = '"1"'
    gone = [{**r, "검수 결과": "삭제"} if r["경로"].endswith("TX_DERMAL|LD50|토끼].species") else r for r in rows2]
    assert ra._dup(tox, gone) == {}                                     # 이미 삭제한 항목은 같은 내용으로 세지 않는다


def test_duplicate_statement_ignores_screen_filled_fields():
    """문장 목록: 화면이 보낸 문장(순번 null, 원문 줄)과 있는 문장은 소제목·내용으로만 견준다 (번호 목록도)."""
    stmt = lambda seq, key, value, text: json.dumps({"seq": seq, "key": key, "value": value, "refs": None, "cond": None, "std_code": None,
                                                     "match_score": None, "text": text}, ensure_ascii=False)
    rows = ROWS + [row("msds[0].hazard.other_hazards[0]", stmt(1, None, "알려지지 않음.", "알려지지 않음.")),
                   row("msds[0].hazard.other_hazards[1]", stmt(2, "보충정보", "없음", "보충정보 없음")),
                   row("msds[0].extras[k=8|위생대책].statements[0]", stmt(1, None, "모든 의학적 감시에 대한 요구사항을 준수할 것.", "x"))]
    new = lambda item, v: ra._new_rows(item, "new", {"": stmt(None, None, v, "원문 줄 " + v)}, {}, rows)
    assert ra._dup(new("msds[0].hazard.other_hazards[*]", "알려지지  않음."), rows) == {"dup": "same"}
    assert ra._dup(new("msds[0].extras[k=8|위생대책].statements[*]", "모든 의학적 감시에 대한 요구사항을 준수할 것."), rows) == {"dup": "same"}
    assert ra._dup(new("msds[0].hazard.other_hazards[*]", "없음"), rows) == {}          # 소제목이 다르면 다른 문장


def test_duplicate_extra_ignores_seq_and_reason():
    """미정의 항목: 화면이 정한 순번·사유는 빼고 항 번호·제목·문장으로 견준다."""
    ex = "msds[0].extras[k=8|위생대책]"
    stmt = json.dumps({"seq": 1, "key": None, "value": "손을 씻을 것.", "refs": None, "cond": None, "std_code": None, "match_score": None,
                       "text": "손을 씻을 것."}, ensure_ascii=False)
    rows = ROWS + [row(f"{ex}.seq", "3"), row(f"{ex}.section_no", "8"), row(f"{ex}.title_raw", "위생대책"), row(f"{ex}.reason", "필드없음"),
                   row(f"{ex}.statements[0]", stmt)]
    new = ra._new_rows("msds[0].extras[*]", "extra", {"section_no": "8", "title_raw": "위생대책", "": stmt}, {}, rows)
    assert new[0]["경로"].startswith("msds[0].extras[k=8|위생대책#2]") and ra._dup(new, rows) == {"dup": "same"}
    other = ra._new_rows("msds[0].extras[*]", "extra", {"section_no": "8", "title_raw": "위생대책", "": stmt.replace("손을", "발을")}, {}, rows)
    assert ra._dup(other, rows)["dup"] == "kind"                        # 문장이 다르면 같은 내용이 아니다


def _sheet(tmp_path, monkeypatch, rows):
    """시험용 검수표 T (rows: [{열: 값}])."""
    import openpyxl
    from msds.review.sheet_spec import COLUMNS, SHEET_INFO, SHEET_MAIN
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = SHEET_MAIN
    ws.append(list(COLUMNS))
    for r in rows:
        ws.append([r.get(c) for c in COLUMNS])
    wb.create_sheet(SHEET_INFO).append(["검수 시작", None])
    wb.save(tmp_path / "T.xlsx")
    monkeypatch.setattr(ra.paths, "review_sheet_path", lambda d: tmp_path / f"{d}.xlsx")
    cells = lambda: [[(c.value, c.data_type) for c in r] for r in openpyxl.load_workbook(tmp_path / "T.xlsx")[SHEET_MAIN].iter_rows(min_row=2)]
    return ra.Sheet("T"), cells


def test_restore_keeps_cell_types_and_checks(tmp_path, monkeypatch):
    """되돌리기는 원래 셀 값 그대로(숫자 수정값·검수자, 메모 앞뒤 공백, 공백 붙은 결과, 엑셀이 날짜로 바꾼 칸). 수식은 글자로. 같은 줄 두 번·범위 밖 경로·없는 결과는 막는다."""
    base = {"Claude 원문 조각": "LD50 > 2000 mg/kg 랫드", "Claude 쪽": 6, "일치": "Claude만"}
    sh, cells = _sheet(tmp_path, monkeypatch, [
        {**base, "경로": f"{TOX}.species", "Claude 값": "랫드", "검수 결과": " 수정 ", "수정값": 7, "수정 원문 조각": "쥐", "수정 쪽": 6.0, "검수자": 123, "메모": " 공백 메모 ",
         "교차 확인자": datetime(2026, 10, 30, 9, 0)},
        {**base, "경로": f"{TOX}.descriptor", "Claude 값": "LD50", "메모": "=1+1"}])
    before = cells()
    prev = json.loads(json.dumps(sh.rows()))                       # 화면이 받는 그대로 (JSON)
    assert prev[0]["검수 결과"] == "수정" and prev[0]["_raw"] == {"검수 결과": " 수정 ", "수정값": 7, "수정 쪽": 6.0, "검수자": 123,
                                                              "교차 확인자": {"datetime": "2026-10-30T09:00:00"}}
    sh.save_rows([{"경로": r["경로"], "values": {"검수 결과": "삭제", "메모": "x", "수정값": "", "수정 원문 조각": "", "수정 쪽": ""}} for r in prev])
    sh.restore(prev)
    after = cells()
    assert after[0] == before[0]                                    # 숫자·공백 그대로
    assert [x for x in after[1] if x[0] == "=1+1"] == [("=1+1", "s")]   # 수식은 글자로 (실행 막기)
    for bad, why in ((prev + prev[:1], "두 번"), ([{**prev[0], "검수 결과": "아무거나", "_raw": {}}], "검수 결과는")):
        with pytest.raises(ValueError, match=why):
            sh.restore(bad)
    add = {"경로": "", "검수 결과": "누락 추가", "일치": "", "수정값": "x", "수정 원문 조각": "x", "수정 쪽": "1"}
    for path, why in (("msds[0].firefighting[k=1].nonsense", "스키마|범위 밖"), ("msds[0].zzz", "스키마|형식"),
                      ("msds[0].narratives[k=S4_EYE].title_raw", "범위 밖")):
        with pytest.raises(ValueError, match=why):
            sh.restore([{**add, "경로": path}])
    assert cells() == after                                         # 막힌 되돌리기는 아무것도 바꾸지 않는다


def test_remove_added_all_or_nothing(tmp_path, monkeypatch):
    """카드의 직접 넣은 줄은 한 번에 지운다. 하나라도 지울 수 없으면 한 줄도 지우지 않는다."""
    sh, cells = _sheet(tmp_path, monkeypatch, [{"경로": f"{TOX}.descriptor", "Claude 값": "LD50", "일치": "Claude만"}])
    sh.add_rows([{"경로": f"{TOX}.guideline", "수정값": "TG 401", "수정 원문 조각": "TG 401", "수정 쪽": "6"},
                 {"경로": f"{TOX}.sex", "수정값": "수컷", "수정 원문 조각": "수컷", "수정 쪽": "6"}])
    with pytest.raises(ValueError, match="누락 추가 줄만"):
        sh.remove_added([f"{TOX}.guideline", f"{TOX}.descriptor"])
    assert len(cells()) == 3
    sh.remove_added([f"{TOX}.guideline", f"{TOX}.sex"])
    assert [r["경로"] for r in ra.Sheet("T").rows()] == [f"{TOX}.descriptor"]


def test_save_failure_says_why(tmp_path, monkeypatch):
    """저장 실패 안내는 까닭별: 엑셀 잠금 파일 / 쓰기 권한 없음."""
    import os
    sh, _ = _sheet(tmp_path, monkeypatch, [{"경로": f"{TOX}.descriptor", "Claude 값": "LD50", "일치": "Claude만"}])
    (tmp_path / "~$T.xlsx").write_text("")
    with pytest.raises(PermissionError, match="엑셀에서 이 검수표가 열려 있어요"):
        sh.save_row(f"{TOX}.descriptor", {"메모": "a"})
    (tmp_path / "~$T.xlsx").unlink()
    os.chmod(tmp_path / "T.xlsx", 0o444)
    try:
        if not os.access(tmp_path / "T.xlsx", os.W_OK):               # root로 돌리면 권한 검사가 없다
            with pytest.raises(PermissionError, match="쓸 권한이 없어"):
                sh.save_row(f"{TOX}.descriptor", {"메모": "a"})
    finally:
        os.chmod(tmp_path / "T.xlsx", 0o644)
    sh = ra.Sheet("T")
    monkeypatch.setattr(sh.wb, "save", lambda p: (_ for _ in ()).throw(OSError(28, "No space left on device")))
    with pytest.raises(OSError, match="저장하지 못했어요 \\(No space left on device\\)") as e:
        sh.save_row(f"{TOX}.descriptor", {"메모": "a"})
    assert not isinstance(e.value, PermissionError) and ra.Sheet("T").rows()[0]["메모"] == ""   # 그 밖의 까닭: 아무것도 바뀌지 않음
    assert ra._err(KeyError("items")) == "요청에 ‘items’ 값이 없어요" and ra._err(ValueError("x")) == "x"


def test_saved_card_is_rebuilt_with_new_value(tmp_path, monkeypatch):
    """저장 뒤 화면이 받는 카드는 바뀐 값 기준 (글·풀이). 검수 결과 앞뒤 공백은 떼고 본다(골드와 같게)."""
    t = "msds[0].toxicity[k=MIX|TX_ORAL|LD50|]"
    sh, _ = _sheet(tmp_path, monkeypatch, [
        {"경로": f"{t}.endpoint", "Claude 값": "TX_ORAL", "Claude 원문 조각": "경구 LD50", "Claude 쪽": 1, "일치": "Claude만", "칸 이름": "11항 독성 · 지표"},
        {"경로": f"{t}.descriptor", "Claude 값": "LD50", "Claude 원문 조각": "경구 LD50", "Claude 쪽": 1, "일치": "Claude만", "검수 결과": " Claude 채택 "}])
    assert sh.rows()[1]["검수 결과"] == "Claude 채택"
    row = sh.save_row(f"{t}.endpoint", {"검수 결과": "수정", "수정값": "TX_DERMAL", "수정 원문 조각": "경피 LD50 > 2000", "수정 쪽": "1", "검수자": "가"})
    got = ra._update(sh, [row["경로"]])
    chip = next(p for p in got["cards"][t]["parts"] if p.get("path") == f"{t}.endpoint")
    assert chip["text"] == "급성 독성(경피)" and "경피" in chip["tip"] and "경구" not in chip["tip"]
    assert got["keys"] == [t] and got["rows"] == [ra.Sheet("T").rows()[0]] and got["gone"] == []


def test_update_rebuilds_all_cards_when_others_depend(tmp_path, monkeypatch):
    """저장·삭제 뒤 화면이 받는 것: 성분표·순번 줄을 바꾸면 문서의 모든 카드(다른 카드의 성분명·형제 순번), 아니면 그 카드만. 지운 줄은 gone."""
    tox = "msds[0].toxicity[k=71-43-2|TX_ORAL|LD50|]"
    comp = "msds[0].components[k=71-43-2]"
    base = {"일치": "Claude만", "Claude 원문 조각": "x", "Claude 쪽": 1}
    sh, _ = _sheet(tmp_path, monkeypatch, [{**base, "경로": f"{comp}.seq", "Claude 값": "1"}, {**base, "경로": f"{comp}.name", "Claude 값": "벤젠"},
                                           {**base, "경로": f"{tox}.comp_ref", "Claude 값": '"1"'}, {**base, "경로": f"{tox}.descriptor", "Claude 값": "LD50"}])
    sh.save_row(f"{comp}.name", {"검수 결과": "수정", "수정값": "톨루엔", "수정 원문 조각": "톨루엔", "수정 쪽": "1"})
    got = ra._update(sh, [f"{comp}.name"])
    assert got["keys"] is None and set(got["cards"]) == {comp, tox}
    assert next(p for p in got["cards"][tox]["parts"] if p.get("path") == f"{tox}.comp_ref")["text"] == "톨루엔"   # 다른 카드도 새 성분명
    assert "톨루엔" in got["explain"][f"{tox}.comp_ref"]
    narrow = ra._update(sh, [f"{tox}.descriptor"])
    assert narrow["keys"] == [tox] and set(narrow["cards"]) == {tox}
    old = sh.rows()                                                                       # 이전 상태를 알면: 바뀐 것만 본다
    sh.save_row(f"{comp}.seq", {"검수 결과": "Claude 채택"})
    assert ra._update(sh, [f"{comp}.seq"], old)["keys"] == [comp]                         # 값이 그대로인 채택: 그 카드만
    old = sh.rows()
    sh.save_row(f"{tox}.descriptor", {"검수 결과": "삭제", "메모": "x"})
    wide = ra._update(sh, [f"{tox}.descriptor"], old)
    assert wide["keys"] is None and wide["cards"][tox]["drop"] == {"by": [f"{tox}.descriptor"], "all": False}   # 항목이 골드에서 빠짐 → 모든 카드
    old = sh.rows()
    sh.save_row(f"{tox}.descriptor", {"검수 결과": "Claude 채택"})
    assert ra._update(sh, [f"{tox}.descriptor"], old)["keys"] is None                      # 다시 살아남: 모든 카드
    sh.add_rows([{"경로": f"{tox}.guideline", "수정값": "TG 401", "수정 원문 조각": "TG 401", "수정 쪽": "1"}])
    sh.remove_added([f"{tox}.guideline"])
    gone = ra._update(sh, [f"{tox}.guideline"])
    assert gone["gone"] == [f"{tox}.guideline"] and gone["rows"] == [] and f"{tox}.guideline" not in str(gone["cards"])


def test_partial_rebuild_equals_full(tmp_path, monkeypatch):
    """카드만 다시 만든 것(_update keys)이 문서 전체로 만든 같은 카드와 같다 (실데이터 한 건 전수)."""
    ra._use_repo_data()
    f = ra.paths.REVIEW / "T21-M013.xlsx"
    if not f.exists():
        pytest.skip("검수표 없음")
    sh = ra.Sheet.__new__(ra.Sheet)
    sh.path, sh.doc_id = f, "T21-M013"
    sh.load()
    rows = sh.rows()
    full = ra._view(rows, sh.doc_id)
    for k in sorted({ra.card_key(r["경로"]) for r in rows}):
        part = ra._view(rows, sh.doc_id, {k})
        assert part["cards"] == {k: full["cards"][k]}, k
        assert part["explain"] == {p: x for p, x in full["explain"].items() if ra.card_key(p) == k}, k


def test_cross_and_info_names_are_plain_text(tmp_path, monkeypatch):
    """교차 확인·문서 정보의 이름 칸도 수식이 되지 않게 글자로. 공백만 든 검수 결과는 미검수 (화면·골드와 같게)."""
    import openpyxl
    from msds.review.sheet_spec import SHEET_INFO, SHEET_MAIN
    sh, _ = _sheet(tmp_path, monkeypatch, [{"경로": f"{TOX}.descriptor", "Claude 값": "LD50", "일치": "Claude만", "우선순위": 1, "검수 결과": "  "}])
    with pytest.raises(ValueError, match="1순위 1줄이 아직 미검수"):
        sh.cross_done("가")
    sh.save_row(f"{TOX}.descriptor", {"검수 결과": "Claude 채택"})
    assert sh.cross_done("=1+1") == 1
    wb = openpyxl.load_workbook(tmp_path / "T.xlsx")
    c = wb[SHEET_MAIN].cell(2, 1 + list(ra.COLUMNS).index("교차 확인자"))
    info = next(b for a, b in wb[SHEET_INFO].iter_rows(max_col=2) if a.value == "교차 확인자")
    assert (c.value, c.data_type) == ("=1+1", "s") and (info.value, info.data_type) == ("=1+1", "s")


def test_restore_odd_adopt_and_korean_errors(tmp_path, monkeypatch):
    """엑셀로 적힌 'GPT 채택'(이 표에 GPT 값 없음)이 든 카드도 되돌린다. 오류 문구는 한국어."""
    sh, cells = _sheet(tmp_path, monkeypatch, [{"경로": f"{TOX}.descriptor", "Claude 값": "LD50", "일치": "Claude만", "검수 결과": "GPT 채택"}])
    before, prev = cells(), json.loads(json.dumps(sh.rows()))
    assert "GPT 채택" not in sh.results
    sh.save_rows([{"경로": f"{TOX}.descriptor", "values": {"검수 결과": "삭제", "메모": "원문에 없음"}}])
    sh.restore(prev)
    assert cells() == before
    with pytest.raises(ValueError, match=r"^검수 결과는 GPT 채택·Claude 채택·수정·삭제·누락 추가 중 하나여야 해요 \(지금: 아무거나\)$"):
        sh.restore([{**prev[0], "검수 결과": "아무거나"}])
    with pytest.raises(ValueError, match="^되돌릴 날짜 값을 읽지 못했어요: 어제$"):
        sh.restore([{**prev[0], "_raw": {"메모": {"datetime": "어제"}}}])


def test_every_changing_route_answers_with_update(tmp_path, monkeypatch):
    """줄을 바꾸는 모든 POST 길이 같은 꼴(_update: rows·gone·keys·cards·explain …)로 답한다: 화면은 apply() 하나로 반영한다."""
    import threading
    import urllib.request
    from http.server import HTTPServer
    comp, tox = "msds[0].components[k=71-43-2]", "msds[0].toxicity[k=71-43-2|TX_ORAL|LD50|]"
    base = {"일치": "Claude만", "Claude 원문 조각": "x", "Claude 쪽": 1}
    sh, _ = _sheet(tmp_path, monkeypatch, [{**base, "경로": f"{comp}.seq", "Claude 값": "1", "우선순위": 1},
                                           {**base, "경로": f"{tox}.comp_ref", "Claude 값": '"1"'}, {**base, "경로": f"{tox}.descriptor", "Claude 값": "LD50"}])
    srv = HTTPServer(("127.0.0.1", 0), ra.make_handler(sh, False, None))
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    def post(path, body):
        req = urllib.request.Request(f"http://127.0.0.1:{srv.server_port}{path}", json.dumps(body).encode(), {"Content-Type": "application/json"})
        return json.loads(urllib.request.urlopen(req).read())
    try:
        prev = json.loads(json.dumps(sh.rows()))
        got = {
            "save": post("/api/save", {"경로": f"{tox}.descriptor", "values": {"검수 결과": "Claude 채택", "검수자": "가"}}),
            "save_many": post("/api/save_many", {"items": [{"경로": f"{comp}.seq", "values": {"검수 결과": "Claude 채택"}}]}),
            "add_item": post("/api/add_item", {"item": tox, "mode": "field", "fields": {"guideline": "TG 401"},
                                               "values": {"수정 원문 조각": "TG 401", "수정 쪽": "1", "검수자": "가"}}),
            "remove": post("/api/remove", {"경로": [f"{tox}.guideline"]}),
            "restore": post("/api/restore", {"items": prev}),
        }
        sh.save_rows([{"경로": r["경로"], "values": {"검수 결과": "Claude 채택"}} for r in prev])
        got["cross"] = post("/api/cross", {"name": "나"})
    finally:
        srv.shutdown()
    for k, j in got.items():
        assert {"rows", "gone", "keys", "cards", "explain", "order", "sec", "spec", "forms", "must", "comps", "names"} <= set(j), k
    assert got["save"]["keys"] == [tox] and got["save_many"]["keys"] == [comp]               # 값이 그대로인 채택은 순번 줄이어도 그 카드만
    assert got["add_item"]["rows"][0]["경로"] == f"{tox}.guideline" and got["remove"]["gone"] == [f"{tox}.guideline"]
    assert {r["경로"] for r in got["restore"]["rows"]} == {r["경로"] for r in prev} and got["cross"]["count"] == 1


def test_blank_per_field_shape(tmp_path, monkeypatch):
    """칸 모양별 빈 값(blank): null 허용이면 null, 배열 칸(synonyms·notations)이면 [], 비울 수 없으면 None. 비운 칸은 항목을 지우지 않는다."""
    from review_cards import dropped
    assert ra._form("msds[0].components[k=1].synonyms")["blank"] == "[]"
    assert ra._form("msds[0].exposure_limits[k=1|KR|TWA].notations")["blank"] == "[]"
    assert ra._form(f"{TOX}.species")["blank"] == "null" and ra._form("msds[0].zzz")["blank"] is None
    comp = "msds[0].components[k=7664-93-9]"
    base = {"일치": "Claude만", "Claude 원문 조각": "x", "Claude 쪽": 1}
    sh, _ = _sheet(tmp_path, monkeypatch, [{**base, "경로": f"{comp}.seq", "Claude 값": "1"},
                                           {**base, "경로": f"{comp}.synonyms", "Claude 값": '["황산"]'}])
    got = sh.save_row(f"{comp}.synonyms", {"검수 결과": "수정", "수정값": "[]", "수정 원문 조각": "x", "수정 쪽": "1"})
    assert got["수정값"] == "[]" and dropped(sh.rows(), "gpt") == {}                       # 항목은 골드에 남는다


def test_comp_ref_must_be_in_component_table(tmp_path, monkeypatch):
    """대상 성분 번호는 같은 MSDS 건 성분표의 순번(골드에 남는 성분)이거나 MIX: 표에 없는 '99'는 저장 단계에서 막는다."""
    comp, tox = "msds[0].components[k=7664-93-9]", "msds[0].toxicity[k=7664-93-9|TX_ORAL|LD50|]"
    base = {"일치": "Claude만", "Claude 원문 조각": "x", "Claude 쪽": 1}
    sh, _ = _sheet(tmp_path, monkeypatch, [{**base, "경로": f"{comp}.seq", "Claude 값": "1"}, {**base, "경로": f"{tox}.comp_ref", "Claude 값": '"1"'}])
    fix = lambda v: {"검수 결과": "수정", "수정값": v, "수정 원문 조각": "x", "수정 쪽": "1"}
    with pytest.raises(ValueError, match=r"성분표에 없는 성분 번호예요 \(지금: 99\)"):
        sh.save_row(f"{tox}.comp_ref", fix("99"))
    assert sh.save_row(f"{tox}.comp_ref", fix("MIX"))["수정값"] == "MIX" and sh.save_row(f"{tox}.comp_ref", fix("비움"))["수정값"] == "null"
    sh.save_row(f"{comp}.seq", {"검수 결과": "삭제", "메모": "x"})                   # 골드에서 빠진 성분은 고를 수 없다
    with pytest.raises(ValueError, match="성분표에 없는"):
        sh.save_row(f"{tox}.comp_ref", {**fix("1"), "수정 원문 조각": "다른 근거"})
    # 바뀐 것 없는 '수정'은 맞음과 같은 길 (거절하지 않고 채택): 맞음·같아요와 같은 기준, 카드는 ⚠로 알린다
    assert sh.save_row(f"{tox}.comp_ref", fix("1"))["검수 결과"] == "Claude 채택"
    view = ra._update(sh, [f"{tox}.comp_ref"])
    chip = next(p for p in view["cards"][tox]["parts"] if p.get("path") == f"{tox}.comp_ref")
    assert chip["warn"].startswith("가리키는 성분이 골드에서 빠져요")


def test_gold_model_follows_build_gold_fallback(tmp_path, monkeypatch):
    """화면의 '골드에서 빠지는 항목'은 골드와 같은 기본값 모델로: build_gold.default_model (build_gold_file도 같은 함수를 쓴다)."""
    from msds.review import build_gold
    from msds.review.sheet_spec import DEFAULT_MODEL
    assert ra.default_model is build_gold.default_model
    monkeypatch.setattr(ra.paths, "silver_path", lambda t, d: tmp_path / f"{t}.json")
    assert ra.default_model("X") != DEFAULT_MODEL
    (tmp_path / f"{DEFAULT_MODEL}.json").write_text("{}")
    assert ra.default_model("X") == DEFAULT_MODEL
