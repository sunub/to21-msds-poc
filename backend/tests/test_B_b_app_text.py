"""표시 이름 규칙 시험. 실제 실행의 이름만 쓰며 문서 내용이나 서버는 읽지 않는다."""
import copy
import importlib
from pathlib import Path

import pytest

from test_B_compare_models import SCRIPTS


@pytest.mark.parametrize("connected, level, fact", [
    (["가짜 모델"], "ok", "연결돼 있습니다"),
    (["다른 모델"], "hint", "연결돼 있지 않습니다"),
    (None, "error", "확인하지 못했습니다"),
])
def test_connection_note_facts_and_offline_reading(text, connected, level, fact):
    note = text.connection_note("가짜 모델", connected, "고급을 켜고 서버 탭에서 모델을 올리세요.")
    assert note["level"] == level
    assert "가짜 모델" in note["text"] and fact in note["text"]
    assert "서버 없이" in note["text"]
    assert "점수" in note["text"] and "비교" in note["text"] and "원문 대조" in note["text"]
    assert "④ 작업" in note["text"]
    if level != "ok":
        assert "고급을 켜고 서버 탭" in note["text"]


def test_connection_notes_cover_loading_and_both_advanced_states(text):
    notes = text.connection_notes("가짜 모델")
    for state in ("ok", "hint", "error", "loading"):
        assert set(notes[state]) == {"advanced_on", "advanced_off"}
        assert all("가짜 모델" in note["text"] for note in notes[state].values())
    assert notes["loading"]["advanced_off"]["level"] == "hint"
    assert "확인하는 중" in notes["loading"]["advanced_off"]["text"]
    assert "None" not in text.connection_note(None, [], "서버 탭에서 올리세요.")["text"]


def test_value_tip_lines_translate_and_keep_unknown_nonempty_values(text):
    value = {"seq": 1, "value": "직접 만든 값", "text": "가짜 원문", "refs": ["p5:L25", "p5:L26"],
             "cond": None, "key": "", "empty": [], "std_code": None, "match_score": 0,
             "unknown": False, "nested": {"value": "두\n줄", "cond": None}}
    before = copy.deepcopy(value)
    lines = text.value_tip_lines(value, text.VALUE_FIELD_LABELS)
    assert lines == ["순서: 1", "값: 직접 만든 값", "원문 글: 가짜 원문", "근거 줄: p5:L25, p5:L26",
                     "맞춤 점수: 0", "unknown: false", "nested: 값: 두 줄"]
    assert value == before
    assert text.value_tip_lines({"value": "", "refs": [], "cond": None}, text.VALUE_FIELD_LABELS) == []
    assert text.value_tip_lines([{"value": "가짜"}, "둘"], text.VALUE_FIELD_LABELS) == ["값: 가짜, 둘"]


def test_start_text_contract(text):
    start = text.START_TEXT
    assert len(start["intro"]) == 3 and all(start["intro"])
    assert [s["no"] for s in start["steps"]] == [1, 2, 3]
    assert len(start["later"]) == 3
    tabs = {"score", "doc", "diff", "jobs", "servers"}
    for step in start["steps"]:
        assert all(step[k] for k in ("title", "why", "button", "tab"))
        assert step["tab"] in tabs
    for later in start["later"]:
        assert all(later[k] for k in ("title", "line", "button", "tab"))
        assert later["tab"] in tabs
    for key in ("empty_runs", "no_drops", "no_line"):
        assert isinstance(start[key], str) and start[key]
    assert "runs/" in start["empty_runs"] and "run_sections.py" in start["empty_runs"]
    assert "②" in start["no_drops"] and "다른 값" in start["no_line"]


@pytest.fixture
def text(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    return importlib.import_module("b_app_text")


@pytest.fixture
def diff_info():
    return {
        "weighted": {"a": 73.2, "b": 72.7, "delta": -.5},
        "items": [{"name": "11항 급성독성", "delta": -12.4},
                  {"name": "8항 노출기준", "delta": 4.2}],
        "conditions": [{"what": name, "changed": False} for name in
                       ["모델", "안내문 버전", "입력 판", "동시 호출", "코드 커밋"]],
        "prompt_changed_sections": [],
    }


@pytest.mark.parametrize("delta, phrase", [(-.5, "0.5점 내려갔습니다"),
                                          (.5, "0.5점 올랐습니다"), (0, "같습니다")])
def test_diff_headline_direction_and_labels(text, diff_info, delta, phrase):
    diff_info["weighted"]["delta"] = delta
    before = copy.deepcopy(diff_info)
    result = text.diff_headline(diff_info, "이전 실행", "새 실행")
    assert phrase in result["headline"]
    assert "이전 실행" in result["headline"] and "새 실행" in result["headline"]
    assert "모두 같습니다." in result["headline"]
    assert result["biggest"] == {"name": "11항 급성독성", "delta": -12.4}
    assert result["same_conditions"] is True
    assert diff_info == before


def test_diff_headline_changed_conditions_and_prompt_content(text, diff_info):
    diff_info["conditions"][0]["changed"] = True
    diff_info["conditions"][2]["changed"] = True
    diff_info["prompt_changed_sections"] = [11]
    result = text.diff_headline(diff_info, "A", "B")
    assert result["same_conditions"] is False
    assert result["headline"].endswith("조건이 다릅니다: 모델, 입력 판, 안내문 글.")


def test_diff_headline_commit_only_is_not_same(text, diff_info):
    diff_info["conditions"][-1]["changed"] = True
    result = text.diff_headline(diff_info, "A", "B")
    assert result["same_conditions"] is False
    assert result["headline"].endswith("조건이 다릅니다: 코드 커밋.")


def test_diff_headline_biggest_absolute_change_prefers_drop_on_tie(text, diff_info):
    diff_info["items"] = [{"name": "오름", "delta": 20}, {"name": "내림", "delta": -20},
                          {"name": "작은 내림", "delta": -3}, {"name": "미채점", "delta": None}]
    assert text.diff_headline(diff_info, "A", "B")["biggest"] == {"name": "내림", "delta": -20}
    diff_info["items"][0]["delta"] = 21
    assert text.diff_headline(diff_info, "A", "B")["biggest"] == {"name": "오름", "delta": 21}


@pytest.mark.parametrize("items", [[], [{"name": "미채점", "delta": None}]])
def test_diff_headline_no_comparable_items(text, diff_info, items):
    diff_info["items"] = items
    assert text.diff_headline(diff_info, "A", "B") == {
        "headline": "비교할 항목이 없습니다.", "biggest": None, "same_conditions": True}


FLUTTER = "조건이 모두 같아 이 차이는 실행마다 생기는 흔들림일 가능성이 큽니다."


def test_diff_headline_adds_flutter_only_when_same_conditions(text, diff_info):
    diff_info["same_conditions"] = True
    result = text.diff_headline(diff_info, "A", "B")
    assert result["headline"].endswith("조건(모델·안내문·입력 판·동시 호출·코드 커밋)은 모두 같습니다. " + FLUTTER)
    assert set(result) == {"headline", "biggest", "same_conditions"} and result["same_conditions"] is True
    diff_info["same_conditions"] = False                                  # 조건은 같아도 채점 문서가 다르다
    assert FLUTTER not in text.diff_headline(diff_info, "A", "B")["headline"]
    diff_info["same_conditions"] = True
    diff_info["conditions"][0]["changed"] = True
    result = text.diff_headline(diff_info, "A", "B")
    assert FLUTTER not in result["headline"] and result["headline"].endswith("조건이 다릅니다: 모델.")


def test_diff_headline_unscored_total_does_not_claim_equal(text, diff_info):
    diff_info["weighted"]["delta"] = None
    headline = text.diff_headline(diff_info, "A", "B")["headline"]
    assert "종합 점수를 비교할 수 없습니다" in headline


def test_diff_ui_text_counts_hidden_items_including_unscored(text, diff_info):
    diff_info["items"].append({"name": "미채점", "delta": None})
    result = text.diff_ui_text(diff_info)
    assert result["hidden"] == "내려가지 않았거나 점수가 없는 항목 2개 숨김"
    assert result["candidate"] == "후보입니다. 확정은 ③ 원문 대조에서 눈으로 합니다."


def test_doc_legend_matches_existing_css_colors_and_returns_fresh_values(text):
    expected = [("same", "실버와 같음", "#8c959f"),
                ("diff", "실버와 다르거나 실버에 없음", "#bc4c00"),
                ("silver_only", "실버에만 있음(결과가 빠뜨림)", "#cf222e"),
                ("picked", "고른 값·줄", "#fff8c5")]
    legend = text.doc_legend()
    assert [(v["key"], v["label"], v["color"]) for v in legend] == expected
    css = (SCRIPTS / "b_app_static" / "app.css").read_text()
    assert all(color in css for _, _, color in expected)
    legend[0]["color"] = "changed"
    assert text.doc_legend()[0]["color"] == "#8c959f"


def test_doc_ui_text_summaries_count_values_and_missing_cells_separately(text):
    view = {"values": [{"section": 3, "silver": {"same": True}},
                       {"section": 3, "silver": {"same": False}}],
            "silver_only": [{"section": 3}, {"section": None}]}
    before = copy.deepcopy(view)
    result = text.doc_ui_text(view)
    assert result["sections"] == {
        "3": "값 2개 중 실버와 다른 것 1개, 결과가 빠뜨린 것 1개",
        "?": "값 0개 중 실버와 다른 것 0개, 결과가 빠뜨린 것 1개"}
    assert "오른쪽에서 값을 누르면" in result["howto"]
    assert view == before


def test_order_models_stable_with_labels_and_without_mutating_input(text):
    models = [
        {"tag": "off1", "label": "꺼진 모델 1", "connected": False, "extra": [1]},
        {"tag": "unknown1", "label": "모르는 모델 1", "connected": None},
        {"tag": "on1", "label": "켜진 모델 1", "connected": True},
        {"tag": "on2", "label": "켜진 모델 2", "connected": True},
        {"tag": "off2", "label": "꺼진 모델 2", "connected": False},
        {"tag": "unknown2", "label": "모르는 모델 2", "connected": None},
    ]
    before = copy.deepcopy(models)
    result = text.order_models(models)
    assert [m["tag"] for m in result] == ["on1", "on2", "unknown1", "unknown2", "off1", "off2"]
    suffix = {True: "연결됨", None: "연결 모름", False: "연결 안 됨"}
    for m in result:
        assert m["option_label"] == f"{m['label']} — {suffix[m['connected']]}"
        assert {k: v for k, v in m.items() if k != "option_label"} == next(x for x in models if x["tag"] == m["tag"])
    assert models == before
    assert text.order_models([]) == []


@pytest.mark.parametrize("advanced", [False, True])
@pytest.mark.parametrize("connections", [[], [None, False], [True, False, None], [True, True]])
def test_try_hint_connection_count_and_advanced(text, advanced, connections):
    models = [{"connected": c} for c in connections]
    count = connections.count(True)
    guide = "" if advanced else "고급을 켜고 "
    expected = (f"연결된 모델 {count}개. 모델을 고르고 돌리기를 누르세요." if count else
                "연결된 모델이 없어 서버 없이 입력·안내문만 봅니다(dry-run). "
                f"모델을 쓰려면 {guide}서버 탭에서 먼저 올리세요.")
    assert text.try_hint(models, advanced) == {"dry_run_forced": not count, "note": expected}


def test_field_help_and_try_stage_help_are_complete(text):
    assert set(text.FIELD_HELP) == {"model", "doc", "pages", "scope", "prompt", "base_run",
                                    "dry_run", "repeat", "run_name", "compare_label"}
    assert all(isinstance(v, str) and v.strip() for v in text.FIELD_HELP.values())
    assert len(text.TRY_STAGE_HELP) == 6
    assert text.TRY_STAGE_HELP["① 보낸 입력"].startswith("모델에게 준 줄 글자")
    assert text.TRY_STAGE_HELP["② 안내문"].startswith("모델에게 준 지시문")
    assert "중간 형식" in text.TRY_STAGE_HELP["④ 읽은 결과"]
    assert all(text.TRY_STAGE_HELP.values())


@pytest.fixture
def score_info():
    return {
        "weighted": 72.7, "must_passed": 5, "must_total": 17,
        "items": [
            {"name": "8항 노출기준", "level": "필수", "target": .95, "score": .403,
             "pass": False, "빠뜨림": 47, "틀림": 47, "지어냄": 47},
            {"name": "11항 기타 독성", "level": "중요", "target": .9, "score": .1,
             "pass": False, "빠뜨림": 1, "틀림": 4, "지어냄": 4},
            {"name": "9항 기타 물성", "level": "일반", "target": .8, "score": 0,
             "pass": False, "빠뜨림": 0, "틀림": 1, "지어냄": 3},
            {"name": "14항 운송", "level": "필수", "target": .95, "score": 1,
             "pass": True, "빠뜨림": 0, "틀림": 0, "지어냄": 0},
        ],
    }


def test_status_ranks_weighted_gaps_and_cause_ties_without_mutation(text, score_info):
    before = copy.deepcopy(score_info)
    result = text.score_status(score_info, {"pass_score": 90})
    assert result["verdict"] == "fail"
    for phrase in ("72.7점", "90점", "17.3점", "필수 17개 중 목표 달성 5개"):
        assert phrase in result["headline"]
    drops = result["top_drops"]
    assert [d["name"] for d in drops] == ["8항 노출기준", "11항 기타 독성", "9항 기타 물성"]
    assert [d["cause"] for d in drops] == ["빠뜨림", "틀림", "지어냄"]
    assert [d["weight"] for d in drops] == [3, 2, 1]
    assert drops[0]["score"] == pytest.approx(40.3)
    assert drops[0]["target"] == 95
    assert drops[0]["gap"] == pytest.approx(54.7)
    assert drops[0]["sentence"] == "8항 노출기준 40.3점(목표 95). 주원인은 빠뜨림 47개입니다."
    assert drops[0]["section"] == 8
    assert score_info == before


@pytest.mark.parametrize("connected", [None, False, True])
def test_status_next_action_uses_last_known_connection(text, score_info, connected):
    result = text.score_status(score_info, {"pass_score": 90}, connected=connected)
    expected = ("④ 작업 탭에서 8항만 다시 시험해 보세요." if connected else
                "③ 원문 대조에서 8항 노출기준의 틀린 값이 원문 어디서 왔는지 확인하세요.")
    assert result["next_action"] == expected


def test_status_section_from_help_or_falls_back_to_source(text, score_info):
    score_info["items"] = [{**score_info["items"][0], "name": "가짜 검사"}]
    c = {"pass_score": 90, "items": [{"name": "가짜 검사", "help": "3항의 가짜 값을 비교합니다."}]}
    result = text.score_status(score_info, c, connected=True)
    assert result["top_drops"][0]["section"] == 3
    assert result["next_action"] == "④ 작업 탭에서 3항만 다시 시험해 보세요."
    result = text.score_status(score_info, {"pass_score": 90}, connected=True)
    assert result["top_drops"][0]["section"] is None
    assert result["next_action"].startswith("③ 원문 대조에서 가짜 검사")


def test_status_pass_none_and_weighted_pass_with_required_failure(text):
    c = {"pass_score": 90, "items": [{"level": "필수"}, {"level": "필수"}]}
    good = text.score_status({"weighted": 90, "must_passed": 2, "items": []}, c)
    assert good["verdict"] == "pass"
    assert "필수 2개 모두 목표를 넘었습니다" in good["headline"]
    assert good["top_drops"] == []
    assert good["next_action"] == "두 목표를 모두 넘었습니다. ② 두 실행 비교로 흔들림을 확인하세요."
    missing = text.score_status({"weighted": None}, c)
    assert missing["verdict"] == "none"
    assert missing["headline"] == "점수가 없는 실행입니다."
    assert missing["top_drops"] == [] and "합격" not in missing["next_action"]
    failed = text.score_status({"weighted": 93, "must_passed": 1}, c)
    assert failed["verdict"] == "fail" and "필수 2개 중 목표 달성 1개" in failed["headline"]
    assert "-3" not in failed["headline"] and "두 목표를 모두 넘었습니다" not in failed["next_action"]


def test_status_limits_three_ignores_unscored_and_preserves_zero(text, score_info):
    score_info["items"] += [
        {**score_info["items"][0], "name": "12항 생태", "score": 0},
        {**score_info["items"][0], "name": "미채점", "score": None},
    ]
    score_info["weighted"] = 0
    result = text.score_status(score_info, {"pass_score": 90})
    assert result["verdict"] == "fail" and "0.0점" in result["headline"]
    assert len(result["top_drops"]) == 3
    assert result["top_drops"][0]["name"] == "12항 생태"
    assert result["top_drops"][0]["score"] == 0


def test_summary_history_uses_scored_main_runs_and_label(text):
    runs = [{"kind": "run", "name": "a", "weighted": 0},
            {"kind": "run", "name": "b", "weighted": 81.25, "label": {"title": "가짜 실행"}},
            {"kind": "run", "name": "pending", "weighted": None},
            {"kind": "manual", "name": "manual/c", "weighted": 100}]
    assert text.card_summary("history", {"runs": runs}) == "실행 2개, 최고 81.2점(가짜 실행)"
    assert text.card_summary("history", {"runs": runs[:1]}) == "실행 1개, 최고 0.0점(a)"


def test_summary_history_skips_silver_runs_and_prefers_comparable(text):
    runs = [{"kind": "run", "name": "silver", "weighted": 93.4, "run_kind": "silver", "comparable": False},
            {"kind": "run", "name": "probe", "weighted": 80.0, "run_kind": "probe", "comparable": False},
            {"kind": "run", "name": "dev", "weighted": 72.7, "run_kind": "dev10", "comparable": True,
             "label": {"title": "가짜 본 실행"}}]
    assert text.card_summary("history", {"runs": runs}) == "실행 2개, 최고 72.7점(가짜 본 실행)"
    assert text.card_summary("history", {"runs": runs[:2]}) == "실행 1개, 최고 80.0점(probe)"
    assert text.card_summary("history", {"runs": runs[:1]}) == "자료 없음"


def test_run_kind_labels(text):
    assert text.RUN_KIND_LABELS == {
        "dev10": "개발 10건 본 실행", "single": "한 문서 시험", "probe": "일부 문서 탐색", "silver": "실버 만들기",
        "eval": "평가 실행(점수 없음)", "outside": "신규 문서 실행(점수 없음)", "models": "비교표"}
    for kind, label in text.RUN_KIND_LABELS.items():
        assert text.run_kind_label(kind) == label
    assert text.run_kind_label(None) == ""


TWO_MUST = {"pass_score": 90, "items": [{"level": "필수"}, {"level": "필수"}]}


def test_status_shows_two_targets(text):
    result = text.score_status({"weighted": 72.66, "must_passed": 1, "items": []}, TWO_MUST)
    assert result["headline"] == ("72.7점입니다. 가중 종합 목표선 90점까지 17.3점 남았습니다. "
                                  "필수 2개 중 목표 달성 1개입니다.")
    assert result["targets"] == {"weighted": {"line": 90, "value": 72.66, "met": False},
                                 "must": {"total": 2, "met_count": 1, "met": False}}
    assert result["verdict"] == "fail"
    mixed = text.score_status({"weighted": 93, "must_passed": 1, "items": []}, TWO_MUST)
    assert mixed["headline"] == "93.0점입니다. 가중 종합이 목표선 90점을 넘었습니다. 필수 2개 중 목표 달성 1개입니다."
    assert mixed["targets"]["weighted"]["met"] is True and mixed["targets"]["must"]["met"] is False


def test_status_both_targets_met(text):
    result = text.score_status({"weighted": 90, "must_passed": 2, "items": []}, TWO_MUST)
    assert result["headline"] == "90.0점입니다. 가중 종합이 목표선 90점을 넘었습니다. 필수 2개 모두 목표를 넘었습니다."
    assert result["targets"] == {"weighted": {"line": 90, "value": 90, "met": True},
                                 "must": {"total": 2, "met_count": 2, "met": True}}
    assert result["next_action"] == "두 목표를 모두 넘었습니다. ② 두 실행 비교로 흔들림을 확인하세요."
    assert result["verdict"] == "pass"


def test_score_targets(text):
    assert text.score_targets({"weighted": None}, TWO_MUST) is None
    assert text.score_targets({}, TWO_MUST) is None
    info = {"weighted": 50.0, "must_passed": 3, "must_total": 17}         # 실행의 must_total이 먼저다
    assert text.score_targets(info, TWO_MUST)["must"] == {"total": 17, "met_count": 3, "met": False}
    assert text.score_status(info, TWO_MUST)["targets"] == text.score_targets(info, TWO_MUST)
    assert text.score_status({"weighted": None}, TWO_MUST)["targets"] is None


def test_text_module_has_no_pass_word(text):
    assert "합격" not in Path(text.__file__).read_text(encoding="utf-8")
    assert "합격" not in text.START_TEXT["no_drops"] + text.GLOSSARY["필수"]["short"]


def test_summary_docs_handles_zero_and_missing_time_independently(text):
    info = {"per_doc": {"T21-X01": {"weighted": 0, "seconds": 15},
                        "T21-X02": {"weighted": 80, "seconds": 84}}}
    assert text.card_summary("docs", info) == "문서 2건, 가장 낮은 T21-X01 0.0점, 가장 오래 걸린 T21-X02 84초"
    info["per_doc"]["T21-X02"]["seconds"] = None
    assert "가장 오래 걸린 T21-X01 15초" in text.card_summary("docs", info)
    info["per_doc"]["T21-X01"]["seconds"] = None
    assert "시간 자료 없음" in text.card_summary("docs", info)


def test_summary_grid_matches_cell_priority_including_multi_msds(text):
    info = {"grid": {"T21-X01": {"1": {"ok": True}, "2": {"ok": True, "reextracted": True}},
                     "T21-X02": {"m0:1": {"ok": True, "reextracted": True, "limit_kind": "긴출력"},
                                 "m1:1": {"ok": False, "reextracted": True, "limit_kind": "공백폭주"}}}}
    assert text.card_summary("grid", info) == "호출 4개 중 성공 1, 재추출 1, 한도 걸림 1, 실패 1"


def test_summary_rows_includes_all_nine_and_largest_absolute_shortfall(text):
    keys = ("components", "exposure_limits", "physchem", "toxicity", "cmr", "ecotox", "regulations", "intl_class", "extras")
    info = {"rows": {key: {"pred": 2, "gold": 2} for key in keys}}
    info["rows"]["toxicity"] = {"pred": 3, "gold": 12}
    info["rows"]["cmr"] = {"pred": 0, "gold": 2}
    assert text.card_summary("rows", info) == "표 9개 중 정답보다 적은 표 2개(가장 모자란 독성 (11항) 3/12)"
    for row in info["rows"].values():
        row["pred"] = row["gold"]
    assert text.card_summary("rows", info) == "표 9개 중 정답보다 적은 표 0개"


@pytest.mark.parametrize("kind", ["history", "docs", "grid", "rows"])
def test_summary_empty(text, kind):
    assert text.card_summary(kind, {}) == "자료 없음"


def test_glossary_has_required_terms_and_safe_examples(text):
    required = {
        "실버", "골드", "가중 종합", "필수 통과", "필수", "중요", "일반", "항", "항목",
        "안내문", "안내문 버전", "입력 판", "쪽 글자", "줄 번호", "기준 실행", "dry-run",
        "시험", "본 실행", "비교표", "빠뜨림", "지어냄", "틀림", "값 없는 행", "호출 격자",
        "재추출", "출력 한도", "공백폭주", "반복", "모델 태그", "RunPod", "RNGD", "Pod",
        "회차", "extras", "실버 빈 곳", "동시 호출", "행 형식", "흔들림",
    }
    assert len(text.GLOSSARY) >= 28
    assert required <= text.GLOSSARY.keys()
    entries = text.glossary_entries()
    assert [e["term"] for e in entries] == sorted(text.GLOSSARY)
    for entry in entries:
        assert set(entry) == {"term", "short", "example", "also"}
        assert entry["short"].strip() and entry["example"].strip()
        assert "\n" not in entry["example"]
        assert "T21-025" not in entry["short"] + entry["example"]
        assert isinstance(entry["also"], list)


def test_explain_resolves_terms_and_every_alias(text):
    assert text.explain("실버")
    assert text.explain("없는말") is None
    seen = set(text.GLOSSARY)
    for term, entry in text.GLOSSARY.items():
        assert text.explain(term) == entry["short"]
        for alias in entry["also"]:
            assert alias and alias not in seen
            seen.add(alias)
            assert text.explain(alias) == entry["short"]


def test_glossary_entries_do_not_expose_mutable_dictionary(text):
    before = copy.deepcopy(text.GLOSSARY)
    entries = text.glossary_entries()
    entries[0]["short"] = "바뀐 설명"
    entries[0]["also"].append("새 별칭")
    assert text.GLOSSARY == before
    assert text.glossary_entries()[0]["short"] != "바뀐 설명"


@pytest.mark.parametrize("tag, expected", [
    ("qwen36_35b_runpod", "Qwen3.6 35B (RunPod)"),
    ("qwen3_30b_a3b_rngd", "Qwen3 30B (RNGD)"),
    ("gpt_oss_20b_rngd", "gpt-oss 20B (RNGD)"),
    ("nuextract2_8b_runpod", "NuExtract 2.0 8B (RunPod)"),
    ("qwen3vl4b_rngd", "Qwen3-VL 4B (RNGD)"),
    ("qwen38", "Qwen3.8 27B (vLLM)"),
    ("claude", "Claude (실버 초안)"),
    ("gpt", "GPT"),
    ("future_model", "future_model"),
    (None, ""),
    ("", ""),
])
def test_model_labels(text, tag, expected):
    assert text.model_label(tag) == expected


@pytest.mark.parametrize("name, title", [
    ("20261030_sections_qwen36_35b_runpod_s7_v9_cls_dev10_r2",
     "10/30 Qwen3.6 35B (RunPod) · 안내문 s7 · 입력 version9 · 분류 검사 · 개발 10건 · 2회차"),
    ("20261027_silver_claude_p3_dev",
     "10/27 실버 초안(Claude) · 안내문 p3 · 개발 10건"),
    ("20261029_sections_qwen3_30b_a3b_rngd_s4_cw_optonly_probe",
     "10/29 Qwen3 30B (RNGD) · 안내문 s4 · 입력 chars_wrap · 선택 항목만 · 탐색"),
    ("20261028_sections_qwen3_30b_a3b_rngd_s2_cw_s003_w1_r2",
     "10/28 Qwen3 30B (RNGD) · 안내문 s2 · 입력 chars_wrap · 문서 T21-S003 한 건 · 동시 1개 · 2회차"),
    ("20261028_sections_gpt_oss_20b_rngd_s2_cw_s003_w1_r2",
     "10/28 gpt-oss 20B (RNGD) · 안내문 s2 · 입력 chars_wrap · 문서 T21-S003 한 건 · 동시 1개 · 2회차"),
    ("20261028_sections_nuextract2_8b_runpod_cw_s016_ex",
     "10/28 NuExtract 2.0 8B (RunPod) · 입력 chars_wrap · 문서 T21-S016 한 건 · 예시 포함"),
    ("20261027_silver_claude_p3_eval039",
     "10/27 실버 초안(Claude) · 안내문 p3 · 평가 T21-039 한 건"),
])
def test_real_run_names(text, name, title):
    assert text.run_label({"name": name}) == {
        "title": title, "subtitle": name, "parts": title.split(" · "),
    }


def test_metadata_wins_without_repeating_name_tokens(text):
    info = {"name": "20261030_sections_gpt_oss_20b_rngd_s2_cw_probe",
            "model_tag": "qwen36_35b_runpod", "prompt_version": "s7",
            "pages_dir": "data/pages/version9/", "started_at": "2026-01-02T03:04:05+09:00",
            "docs": ["T21-X01"]}
    before = copy.deepcopy(info)
    result = text.run_label(info)
    assert result["title"] == "10/30 Qwen3.6 35B (RunPod) · 안내문 s7 · 입력 version9 · 탐색"
    assert info == before
    assert text.run_label(info) == result


@pytest.mark.parametrize("info, title", [
    ({}, ""),
    ({"name": "custom_unknown", "started_at": "2026-02-03T12:00:00+09:00"}, "2/3 · custom · unknown"),
    ({"name": "custom", "started_at": "invalid"}, "custom"),
    ({"name": "20260230_sections_gpt_probe", "started_at": "2026-03-01"}, "3/1 GPT · 탐색"),
    ({"name": "20261030_sections_future_model_s8_v13_new", "model_tag": "future_model"},
     "10/30 future_model · 안내문 s8 · 입력 version13 · new"),
    ({"name": "20261030_sections_claude_p3_dev", "prompt_version": "p3"},
     "10/30 Claude (실버 초안) · 안내문 p3 · 개발 10건"),
    ({"name": "manual/20261030_qwen38_s7_v9_probe", "kind": "manual"},
     "[수동] 10/30 Qwen3.8 27B (vLLM) · 안내문 s7 · 입력 version9 · 탐색"),
    ({"name": "20260102_sections_gpt_s7_chars_wrap_dev10"},
     "1/2 GPT · 안내문 s7 · 입력 chars_wrap · 개발 10건"),
    ({"name": "20261028_sections_qwen3_30b_a3b_rngd_s2_version2_diag2"},
     "10/28 Qwen3 30B (RNGD) · 안내문 s2 · 입력 version2 · 진단 2"),
])
def test_partial_metadata_and_unknown_tokens(text, info, title):
    result = text.run_label(info)
    assert result["title"] == title
    assert result["subtitle"] == info.get("name", "")
    assert result["parts"] == title.split(" · ")


@pytest.mark.parametrize("token, expected", [
    ("eval", "평가 10건"), ("probe3", "탐색 3회"), ("diag", "진단"),
    ("none", "안내문 없음"), ("wsonly", "공백 줄임만"),
    ("m013", "문서 T21-M013 한 건"), ("S003", "문서 T21-S003 한 건"),
    ("s12", "안내문 s12"), ("v2", "입력 version2"), ("unknown", "unknown"),
])
def test_condition_tokens(text, token, expected):
    assert text.run_label({"name": f"20261030_sections_gpt_{token}"})["title"] == f"10/30 GPT · {expected}"


@pytest.mark.parametrize("where, raw, message, fix", [
    ("rngd", "Could not resolve hostname ssh: failure",
     "`.env`의 RNGD_SSH 값이 `ssh`로 시작합니다.",
     "`ssh`를 빼고 `-i <키> -p <포트> <사용자>@<호스트>`처럼 인자만 적으세요. 앱은 이제 `ssh`를 빼고 읽습니다."),
    ("rngd", "RNGD_SSH starts with ssh",
     "`.env`의 RNGD_SSH 값이 `ssh`로 시작합니다.",
     "`ssh`를 빼고 `-i <키> -p <포트> <사용자>@<호스트>`처럼 인자만 적으세요. 앱은 이제 `ssh`를 빼고 읽습니다."),
    ("rngd", "RNGD_SSH 없음", "RNGD 접속 정보(RNGD_SSH)가 `.env`에 없습니다.",
     "`.env.example`의 RNGD_SSH 줄을 복사해 값을 채우세요."),
    ("runpod", "RunPod 연결 오류: SSLCertVerificationError",
     "RunPod 주소의 인증서를 확인하지 못했습니다. 파이썬 3.11에 인증서 묶음이 없을 때 생깁니다.",
     "터미널에서 `/Applications/Python 3.11/Install Certificates.command`를 한 번 실행한 뒤 앱을 다시 켜세요."),
    ("runpod", "CERTIFICATE_VERIFY_FAILED",
     "RunPod 주소의 인증서를 확인하지 못했습니다. 파이썬 3.11에 인증서 묶음이 없을 때 생깁니다.",
     "터미널에서 `/Applications/Python 3.11/Install Certificates.command`를 한 번 실행한 뒤 앱을 다시 켜세요."),
    ("runpod", "HTTP 401", "RunPod 관리 키(RUNPOD_API_KEY)가 거절됐습니다.",
     "RunPod 설정 화면에서 키를 다시 만들어 `.env`에 넣으세요."),
    ("runpod", "Unauthorized", "RunPod 관리 키(RUNPOD_API_KEY)가 거절됐습니다.",
     "RunPod 설정 화면에서 키를 다시 만들어 `.env`에 넣으세요."),
    ("model", "request timed out", "서버가 응답하지 않습니다.",
     "SSH 터널이 열려 있는지, 서버가 켜져 있는지 확인하세요."),
    ("rngd", "Connection refused", "서버가 응답하지 않습니다.",
     "SSH 터널이 열려 있는지, 서버가 켜져 있는지 확인하세요."),
    ("model", "새 오류 <unknown>", "서버를 보지 못했습니다.",
     "아래 원문을 보고 .env와 터널을 확인하세요."),
    ("env", "", "서버를 보지 못했습니다.", "아래 원문을 보고 .env와 터널을 확인하세요."),
])
def test_friendly_error_rules(text, where, raw, message, fix):
    assert text.friendly_error(where, raw) == {"message": message, "fix": fix, "raw": raw}


@pytest.mark.parametrize("variable", ["VLLM_BASE_URL", "RNGD_BASE_URL", "RUNPOD_VLLM_BASE_URL"])
def test_friendly_env_uses_config_variable_name(text, variable):
    names = {"api_key": "VLLM_API_KEY", "base_url": variable}
    before = dict(names)
    result = text.friendly_error("env", "주소 설정 없음", names)
    assert result["message"] == f"`.env`에 {variable}가 없습니다."
    assert f"서버 주소를 `.env`의 {variable}에 적으세요." in result["fix"]
    assert "SSH 터널을 거친 내 컴퓨터 쪽 주소" in result["fix"]
    assert result["raw"] == "주소 설정 없음" and names == before


@pytest.mark.parametrize("raw, expected", [
    ("Could not resolve hostname ssh CERTIFICATE_VERIFY_FAILED 401", "RNGD_SSH 값"),
    ("CERTIFICATE_VERIFY_FAILED 401", "인증서를 확인하지 못했습니다"),
    ("Unauthorized timed out", "관리 키"),
    ("timed out", "VLLM_BASE_URL"),
])
def test_friendly_error_first_matching_rule_wins(text, raw, expected):
    assert expected in text.friendly_error("env", raw, {"base_url": "VLLM_BASE_URL"})["message"]


@pytest.mark.parametrize("raw", ["HTTP 401", "HTTP 401: URLError"])
def test_friendly_model_401_is_model_server_key(text, raw):
    result = text.friendly_error("model", raw)
    assert result["message"] == "모델 서버가 키를 거절했습니다."
    assert "RUNPOD_VLLM_API_KEY" in result["fix"] and "RNGD_API_KEY" in result["fix"] and "Pod를 다시 만드세요" in result["fix"]
    assert "관리 키" not in result["message"] and result["raw"] == raw


def test_friendly_runpod_401_unchanged(text):
    raw = "RunPod HTTP 401: 가상 거절"
    assert text.friendly_error("runpod", raw) == {"message": "RunPod 관리 키(RUNPOD_API_KEY)가 거절됐습니다.",
                                                  "fix": "RunPod 설정 화면에서 키를 다시 만들어 `.env`에 넣으세요.",
                                                  "raw": raw}


def test_env_problem_has_line_and_no_value(text):
    item = text.env_problem(4)
    assert item["line"] == 4 and "4번째 줄" in item["message"] and "설정 다시 읽기" in item["fix"]
    assert set(item) == {"line", "message", "fix"}


def test_server_refusal_texts(text):
    assert "RUNPOD_VLLM_API_KEY" in text.SERVER_TEXT["pod_key_missing"]
    assert "할 일:" in text.SERVER_TEXT["pod_key_missing"] and "설정 다시 읽기" in text.SERVER_TEXT["pod_key_missing"]
    assert "만들지 않은 Pod" in text.SERVER_TEXT["pod_not_ours"] and "할 일:" in text.SERVER_TEXT["pod_not_ours"]
    assert text.SERVER_TEXT["env_file_unknown"]


def test_friendly_server_ui_copy(text):
    copy = text.server_ui_text()
    assert copy["guide"]["advanced_off"] == "고급을 켜고 서버 탭에서 모델을 올리세요"
    assert copy["guide"]["advanced_on"] == "서버 탭에서 모델을 올리세요"
    assert copy["action_failure"]["message"] == "서버 변경을 끝내지 못했습니다."
    assert copy["action_failure"]["fix"]
    assert copy["busy"] and copy["unavailable"]
