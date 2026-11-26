"""단계별 지표(CER·WER·TEDS·칸 값 재현율) 계산 함수 시험. 실제 데이터 없이 돈다."""
import pytest

from msds.evaluate import stage_metrics as sm


# ── 글자·낱말 오류율 ──────────────────────────────────────
def test_edit_distance_basic():
    assert sm.edit_distance("abc", "abc") == 0
    assert sm.edit_distance("abc", "abd") == 1
    assert sm.edit_distance("", "abc") == 3
    assert sm.edit_distance("kitten", "sitting") == 3
    assert sm.edit_distance(["가", "나"], ["가"]) == 1


def test_cer_ignores_spaces_and_width():
    assert sm.cer("abc", "abd") == pytest.approx(1 / 3)
    assert sm.cer("물 질 명", "물질명") == 0          # 띄어쓰기는 보지 않는다
    assert sm.cer("ＡＢＣ", "ABC") == 0               # NFKC
    assert sm.cer("", "abc") is None                  # 정답이 비면 잴 수 없다


def test_bag_cer_ignores_order():
    assert sm.cer("가나다라", "다라가나") > 0
    assert sm.bag_cer("가나다라", "다라가나") == 0
    assert sm.bag_cer("가나다라", "가나다") == pytest.approx(1 / 4)


def test_wer_counts_words():
    assert sm.wer("인화성 액체 구분2", "인화성 액체 구분2") == 0
    assert sm.wer("인화성 액체 구분2", "인화성 엑체 구분2") == pytest.approx(1 / 3)


def test_substring_distance_finds_best_window():
    assert sm.substring_distance("질소", "제품명: 질소 (NITROGEN)") == 0
    assert sm.substring_distance("질소가스", "제품명: 질소 (NITROGEN)") == 2
    assert sm.substring_distance("", "아무 글") == 0


# ── 표 구조 (TEDS) ──────────────────────────────────────
G = [["물질명", "CAS"], ["질소", "7727-37-9"]]


def test_teds_identical_is_one():
    t = sm.table_tree(G)
    assert sm.teds(t, sm.table_tree(G)) == 1.0


def test_teds_missing_row():
    # 정답 노드 7개(표1·행2·칸4), 예측 4개 → 지워야 할 노드 3개
    got = sm.teds(sm.table_tree(G), sm.table_tree(G[:1]))
    assert got == pytest.approx(1 - 3 / 7)


def test_teds_structure_only_ignores_text():
    wrong = [["가", "나"], ["다", "라"]]
    assert sm.teds(sm.table_tree(G), sm.table_tree(wrong), structure_only=True) == 1.0
    assert sm.teds(sm.table_tree(G), sm.table_tree(wrong)) < 1.0


def test_table_tree_spans_hide_covered_cells():
    rows = [["물질명", "NFPA", ""], ["", "보건", "화재"]]
    spans = [{"r": 0, "c": 0, "rs": 2, "cs": 1}, {"r": 0, "c": 1, "rs": 1, "cs": 2}]
    t = sm.table_tree(rows, spans)
    cells = [td for tr in t.children for td in tr.children]
    assert [c.text for c in cells] == ["물질명", "NFPA", "보건", "화재"]
    assert (cells[0].rowspan, cells[1].colspan) == (2, 2)
    # 병합을 놓친 예측(칸을 다 펼친 표)은 구조 점수가 1보다 작다
    assert sm.teds(t, sm.table_tree(rows), structure_only=True) < 1.0


def test_line_tables_group_consecutive_cell_lines():
    text = "9. 물리화학적 특성\n특성 | 제품\n1)외관 | 무색\n2)냄새 | 무취\n설명 문장\n물질명 | CAS\n"
    assert sm.line_tables(text) == [[["특성", "제품"], ["1)외관", "무색"], ["2)냄새", "무취"]],
                                    [["물질명", "CAS"]]]
    assert sm.line_tables("칸 없는 글\n또 한 줄") == []


def test_row_kept_ignores_line_breaks_and_separators():
    page = sm.normalize("카. 증기압 < 5 mmHg\n나. 적절한 공학적 관리 방폭 처리된 전체 및\n국소배기장치.")
    assert sm.row_kept(["카. 증기압", "< 5 mmHg"], page)
    assert sm.row_kept(["나. 적절한 공학적 관리", "방폭 처리된 전체 및 국소배기장치."], page)   # 줄바꿈은 본다
    assert not sm.row_kept(["카. 증기압", "< 7 hPa"], page)


def test_boundary_kept_needs_separator_between_cells():
    with_bar = sm.normalize("특성 | 제품\n1)외관 | 무색")
    no_bar = sm.normalize("가. 외관 (물리적 상태, 색 등) 액체")
    assert sm.boundary_kept(["1)외관", "무색"], with_bar)
    assert not sm.boundary_kept(["가. 외관 (물리적 상태, 색 등)", "액체"], no_bar)   # 띄어쓰기는 경계가 아니다
    assert sm.boundary_kept(["물질명", "", "CAS"], sm.normalize("물질명 | | CAS"))  # 빈 칸은 건너뛴다
    assert sm.boundary_kept(["한 칸만"], no_bar) is None                            # 경계가 없는 행


def test_read_md_table():
    md = "| 물질명 | CAS |\n| --- | --- |\n| 질소 | 7727-37-9 |\n"
    assert sm.read_md_table(md) == G


# ── 정답 근거 글(evidence.source_text) 대조 ──────────────────
def test_snippet_parts_split_table_cells():
    assert sm.snippet_parts("나. 최초작성일 | 2010-06-21") == ["나. 최초작성일", "2010-06-21"]
    assert sm.snippet_parts(" | 질소 | ") == ["질소"]
    assert sm.snippet_parts("· GHS : (가스 실린더 그림)") == ["· GHS :"]          # 그림 설명은 원문 글자가 아니다
    assert sm.snippet_parts("PRODUCT : ... 작업환경측정대상물질 ...") == ["PRODUCT :", "작업환경측정대상물질"]


def test_snippet_score():
    page = "가. 제품명 : 질소(NITROGEN)\n나. 최초작성일 2010-06-21"
    assert sm.snippet_score("나. 최초작성일 | 2010-06-21", page) == {"errors": 0, "chars": 17, "exact": True}
    got = sm.snippet_score("나. 최초작성일 | 2010-06-22", page)
    assert got["errors"] == 1 and not got["exact"]
    assert sm.snippet_score("황산", page)["errors"] == 2


def test_dedupe_evidence():
    ev = [{"field": "a", "page": 6, "source_text": "개정횟수 | 0 회"},
          {"field": "b", "page": 6, "source_text": "개정횟수 | 0 회"},
          {"field": "c", "page": 1, "source_text": None}]
    assert sm.dedupe_evidence(ev) == [(6, "개정횟수 | 0 회")]


# ── 틀린 칸 원인 나누기 ──────────────────────────────────
def test_value_found_normalizes():
    page = "CAS No. 7727 - 37 - 9\n끓는점 : -195.80 ℃"
    assert sm.value_found("7727-37-9", page)
    assert sm.value_found("-195.80", page)
    assert sm.value_found("195.8", page)          # 숫자는 끝자리 0을 봐준다
    assert not sm.value_found("1195.8", page)
    assert not sm.value_found("산소", page)
    assert sm.value_found("1004", "밀도 1,004 kg/m3")              # 천 단위 쉼표
    assert not sm.value_found("13", "1,3-부타디엔")                  # 1,3-은 천 단위가 아니다
    assert sm.value_found("5480", "LD50 5480 mg/kg Rat")            # 앞 낱말의 숫자와 붙이지 않는다


def test_detail_values_pull_scalars_from_scorer_tuples():
    content = ("MIX", "BOILING", None, (-195.79, None, None, None, None, "C", "값있음"))
    assert sm.detail_values(content) == ["-195.79"]
    assert sm.detail_values("정답='㈜SKC에어가스' / 추출='(주)SKC에어가스'") == ["㈜SKC에어가스"]
    assert sm.detail_values("정답=None / 추출='2010-06-21'") == []
    # 수가 있으면 수·CAS만 본다 (부등호·단위·분류 이름은 원문 표기가 다르다)
    assert sm.detail_values(("106-99-0", "LD50", (5480, None, ">=", "mg/kg"))) == ["106-99-0", "5480"]
    assert sm.detail_values(("MIX", "생물학적 노출기준")) == ["생물학적 노출기준"]


# ── 반복 실행 안정도 ─────────────────────────────────────
def test_field_agreement_ignores_row_order_and_bookkeeping():
    a = {"product": {"name": "질소", "code": None},
         "toxicity": [{"endpoint": "TX_ORAL", "seq": 1, "evidence": "x"}, {"endpoint": "TX_INHAL", "seq": 2}],
         "evidence": [{"page": 1}]}
    b = {"product": {"name": "질소가스", "code": None},
         "toxicity": [{"endpoint": "TX_INHAL", "seq": 1}, {"endpoint": "TX_ORAL", "seq": 2}, {"endpoint": "TX_DERMAL"}],
         "evidence": [{"page": 9}]}
    got = sm.field_agreement(a, b)
    assert got["product"] == {"same": 1, "total": 2}        # name 다름, code 같음
    assert got["toxicity"] == {"same": 2, "total": 3}       # 순서·seq는 보지 않고, 한쪽에만 있는 행은 다름
    assert "evidence" not in got                            # 근거 기록은 비교하지 않는다


def test_field_agreement_empty_lists():
    assert sm.field_agreement({"cmr": []}, {"cmr": []}) == {"cmr": {"same": 0, "total": 0}}
