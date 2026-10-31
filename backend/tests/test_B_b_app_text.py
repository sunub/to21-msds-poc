"""표시 이름 규칙 시험. 실제 실행의 이름만 쓰며 문서 내용이나 서버는 읽지 않는다."""
import copy
import importlib
from datetime import datetime, timedelta, timezone
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
    expected = [("same", "실버와 같음", "#53645e"),
                ("diff", "실버와 다르거나 실버에 없음", "#bc4c00"),
                ("silver_only", "실버에만 있음(결과가 빠뜨림)", "#a52f35"),
                ("picked", "고른 값·줄", "#fff3c6")]
    legend = text.doc_legend()
    assert [(v["key"], v["label"], v["color"]) for v in legend] == expected
    css = (SCRIPTS / "b_app_static" / "app.css").read_text()
    assert all(color in css for _, _, color in expected)
    legend[0]["color"] = "changed"
    assert text.doc_legend()[0]["color"] == "#53645e"


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


def test_doc_ui_text_silver_line_guess_and_missing(text):
    """정답 초안 값의 줄은 글자 맞춤 추정이라고 밝히고, 못 찾으면 그 항의 구간을 연다고 알린다."""
    result = text.doc_ui_text({"values": [], "silver_only": []})
    guess, missing = result["silver_line_guess"], result["silver_line_missing"]
    assert "(추정)" in guess and "정답 초안" in guess
    assert "찾지 못했습니다" in missing and "구간" in missing
    assert "합격" not in guess + missing


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


# ── 총점 손실 순서 (사용자 결정 10/31) ─────────────────

LOSS_CRITERIA = {"pass_score": 90, "items": [
    {"name": "가짜 필수", "level": "필수"}, {"name": "가짜 필수2", "level": "필수"},
    {"name": "가짜 중요", "level": "중요"}, {"name": "가짜 일반", "level": "일반"}]}


def loss_info(*items):
    """(이름, 중요도, 점수, 목표) → 채점기와 같은 식으로 가중 종합을 낸 가짜 실행."""
    from msds.evaluate.score import _weighted
    rows = [{"name": n, "level": lv, "score": s, "target": t, "pass": s >= t} for n, lv, s, t in items]
    return {"weighted": _weighted(rows), "must_passed": 0, "items": rows}


def test_losses_follow_scorer_formula_and_sum_to_weighted_gap(text):
    from msds.evaluate.score import WEIGHTS, _weighted
    info = loss_info(("가짜 필수", "필수", .5, .95), ("가짜 중요", "중요", 1.0, .9), ("가짜 일반", "일반", .8, .8))
    before = copy.deepcopy(info)
    result = text.score_losses(info, LOSS_CRITERIA)
    total = WEIGHTS["필수"] + WEIGHTS["중요"] + WEIGHTS["일반"]
    by = {r["name"]: r for r in result["losses"]}
    for item in info["items"]:
        expected = WEIGHTS[item["level"]] * (1 - item["score"]) / total * 100
        assert by[item["name"]]["loss"] == pytest.approx(expected)
    assert sum(r["loss"] for r in result["losses"]) == pytest.approx(100 - _weighted(info["items"]))
    assert result["loss_basis"] == {"weight_total": total, "loss_total": pytest.approx(100 - info["weighted"])}
    first = result["losses"][0]
    assert [r["name"] for r in result["losses"]] == ["가짜 필수", "가짜 일반", "가짜 중요"]
    assert [r["rank"] for r in result["losses"]] == [1, 2, 3]
    assert (first["level"], first["weight"], first["section"], first["below_target"]) == ("필수", 3, None, True)
    assert first["score"] == pytest.approx(50) and first["target"] == pytest.approx(95)
    assert by["가짜 일반"]["below_target"] is False                      # 목표와 같으면 아래가 아니다
    assert info == before


def test_loss_counts_items_above_target_and_keeps_top_drops(text):
    info = loss_info(("가짜 필수", "필수", .96, .95), ("가짜 일반", "일반", .9, .95))
    status = text.score_status(info, LOSS_CRITERIA)
    first, second = status["losses"]
    assert (first["name"], first["below_target"]) == ("가짜 필수", False)  # 3×0.04 > 1×0.1
    assert (second["name"], second["below_target"]) == ("가짜 일반", True)
    assert status["top_problem"]["name"] == "가짜 필수"
    assert [d["name"] for d in status["top_drops"]] == ["가짜 일반"]      # 옛 키는 목표 아래 항목만 그대로 센다


def test_loss_ties_follow_criteria_order_and_no_loss_has_no_top_problem(text):
    # 3×(1−0.9)와 1×(1−0.7)은 같은 손실이지만 소수 계산은 끝자리가 다르다
    info = loss_info(("가짜 일반", "일반", .7, .8), ("가짜 필수2", "필수", .9, .95), ("가짜 필수", "필수", .9, .95))
    names = [r["name"] for r in text.score_losses(info, LOSS_CRITERIA)["losses"]]
    assert names == ["가짜 필수", "가짜 필수2", "가짜 일반"]
    perfect = loss_info(("가짜 일반", "일반", 1.0, .8), ("가짜 필수", "필수", 1.0, .95))
    result = text.score_losses(perfect, LOSS_CRITERIA)
    assert result["top_problem"] is None
    assert [r["name"] for r in result["losses"]] == ["가짜 필수", "가짜 일반"]
    assert all(r["loss"] == 0 for r in result["losses"])
    assert result["loss_basis"] == {"weight_total": 4, "loss_total": 0}


def test_top_problem_docs_split_the_item_loss(text):
    info = loss_info(("가짜 필수", "필수", .4, .95), ("가짜 일반", "일반", .9, .8))
    per_doc = {"T21-X01": {"items": {"가짜 필수": .6, "가짜 일반": .8}},
               "T21-X02": {"items": {"가짜 필수": .2, "가짜 일반": 1.0}}}
    top = text.score_losses(info, LOSS_CRITERIA, per_doc)["top_problem"]
    assert top["name"] == "가짜 필수" and top["rank"] == 1
    assert [d["doc_id"] for d in top["docs"]] == ["T21-X02", "T21-X01"]
    assert [d["score"] for d in top["docs"]] == [pytest.approx(20), pytest.approx(60)]
    assert top["docs"][0]["loss"] == pytest.approx(3 * .8 / (2 * 4) * 100)
    assert sum(d["loss"] for d in top["docs"]) == pytest.approx(top["loss"])
    assert text.score_losses(info, LOSS_CRITERIA)["top_problem"]["docs"] == []


def test_losses_without_score_or_unscored_items(text, score_info):
    assert text.score_losses({"weighted": None}, LOSS_CRITERIA) == {
        "losses": [], "top_problem": None, "loss_basis": None}
    score_info["items"].append({**score_info["items"][0], "name": "미채점", "score": None})
    result = text.score_losses(score_info, {"pass_score": 90})
    # 2×(1−0.1) = 1.8이 3×(1−0.403) = 1.791보다 크다. 목표 차 순서(top_drops)와 다르다
    assert [r["name"] for r in result["losses"]] == ["11항 기타 독성", "8항 노출기준", "9항 기타 물성", "14항 운송"]
    assert result["loss_basis"]["weight_total"] == 3 + 2 + 1 + 3


def test_status_adds_loss_keys_and_passes_per_doc(text, score_info):
    per_doc = {"T21-X01": {"items": {"11항 기타 독성": .1}}}
    status = text.score_status(score_info, {"pass_score": 90}, per_doc=per_doc)
    losses = text.score_losses(score_info, {"pass_score": 90}, per_doc)
    assert {k: status[k] for k in ("losses", "top_problem", "loss_basis")} == losses
    top = status["top_problem"]
    assert top["section"] == 11 and top["docs"] == [{"doc_id": "T21-X01", "score": pytest.approx(10),
                                                     "loss": pytest.approx(top["loss"])}]
    assert status["top_drops"][0]["name"] == "8항 노출기준"
    none = text.score_status({"weighted": None}, {"pass_score": 90})
    assert (none["losses"], none["top_problem"], none["loss_basis"]) == ([], None, None)


def test_item_section_names_table_and_help(text):
    c = {"items": [{"name": "관리정보(가짜 네 칸)"}, {"name": "제품명·가짜"}, {"name": "MSDS 건수(가짜)"},
                   {"name": "8항 가짜 기준", "help": "3항 성분과 맞춘 가짜 값"}, {"name": "가짜 검사", "help": "12항의 가짜 값"}]}
    sections = [text.item_section(i, c) for i in c["items"]]
    assert sections == [16, 1, None, 8, 12]
    assert text.ITEM_SECTION["관리정보"] == 16 and text.ITEM_SECTION["MSDS 건수"] is None
    assert text.item_section({"name": "서술형 가짜"}, {}) is None
    for prefix in ("H 코드", "P 코드", "그림문자", "신호어", "유해성 분류"):
        assert text.item_section({"name": prefix + "(가짜)"}, {}) == 2
    for prefix in ("구성성분", "구성성분 필드", "함유량"):
        assert text.item_section({"name": prefix + "(가짜)"}, {}) == 3


def test_item_section_matches_doc_section_map(text, monkeypatch):
    """채점 항목 → 최상위 키(채점기 TOP_TO_ITEMS) → 항(b_app_doc.SECTION_OF)과 같은 규칙이다."""
    from msds.evaluate.score import TOP_TO_ITEMS
    monkeypatch.syspath_prepend(str(SCRIPTS))
    doc = importlib.import_module("b_app_doc")
    diff = importlib.import_module("b_app_diff")
    for top, prefixes in TOP_TO_ITEMS.items():
        for prefix in prefixes:
            section = text.item_section({"name": prefix + "(가짜)"}, {})
            if top in doc.SECTION_OF:
                assert section == doc.SECTION_OF[top], (top, prefix)
            if section is not None:
                assert section in diff.sections_of(prefix), prefix


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
     "서버 상태 칸의 진단을 보세요. 터널이 닫혔거나 모델이 아직 뜨는 중일 수 있습니다."),
    ("rngd", "Connection refused", "서버가 응답하지 않습니다.",
     "서버 상태 칸의 진단을 보세요. 터널이 닫혔거나 모델이 아직 뜨는 중일 수 있습니다."),
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


def test_timed_out_does_not_assume_tunnel(text):
    fix = text.friendly_error("model", "URLError: TimeoutError")["fix"]
    assert "진단" in fix and "SSH 터널이 열려 있는지" not in fix          # 모델이 안 떠 있어도 터널을 탓하던 문장 (step 6)


NOW_LOCAL = datetime(2026, 10, 30, 21, 0, tzinfo=timezone(timedelta(hours=9)))


def ago(minutes: float) -> str:
    return (NOW_LOCAL - timedelta(minutes=minutes)).isoformat(timespec="seconds")


def test_rngd_diagnosis_texts(text):
    ok = text.rngd_diagnosis("ok", None, NOW_LOCAL)
    assert ok["message"] == "RNGD 모델이 응답합니다." and set(ok) == {"message", "fix"}
    no_model = text.rngd_diagnosis("no_model", None, NOW_LOCAL)
    assert no_model["message"] == "RNGD에 떠 있는 모델이 없습니다."
    assert no_model["fix"] == "모델 올리기를 누르세요. 15~25분 걸립니다."
    assert "터널" not in no_model["message"] + no_model["fix"]
    closed = text.rngd_diagnosis("tunnel_closed", None, NOW_LOCAL)
    assert closed == {"message": "내 컴퓨터와 RNGD를 잇는 통로(SSH 터널)가 닫혀 있습니다.", "fix": "터널 열기를 누르세요."}
    assert text.rngd_diagnosis(None, None, NOW_LOCAL) is None
    assert text.rngd_diagnosis("모르는 값", None, NOW_LOCAL) is None


@pytest.mark.parametrize("since, minutes, late", [(ago(7.5), 7, False), (ago(25), 25, False), (ago(26), 26, True)])
def test_rngd_diagnosis_loading_minutes(text, since, minutes, late):
    item = text.rngd_diagnosis("loading", since, NOW_LOCAL)
    assert item["message"] == f"모델을 올리는 중입니다({minutes}분 지남)."
    assert item["fix"].startswith("보통 15~25분 걸립니다. 기다린 뒤 다시 보세요.")
    assert ("서버 기록을 확인하세요" in item["fix"]) is late


def test_rngd_diagnosis_loading_other_timezone_and_unknown(text):
    utc = (NOW_LOCAL - timedelta(minutes=3)).astimezone(timezone.utc).isoformat()
    assert "3분 지남" in text.rngd_diagnosis("loading", utc, NOW_LOCAL)["message"]
    for since in (None, "", "시각 아님"):
        item = text.rngd_diagnosis("loading", since, NOW_LOCAL)
        assert item["message"] == "모델을 올리는 중입니다." and "서버 기록" not in item["fix"]


def test_tunnel_refusal_texts(text):
    for key in ("tunnel_no_port", "tunnel_already_open", "tunnel_closed", "tunnel_not_ours", "tunnel_exited",
                "tunnel_timeout", "tunnel_spawn_failed", "tunnel_still_open"):
        assert "할 일:" in text.SERVER_TEXT[key], key
    assert "앱이 연 터널이 아닙니다" in text.SERVER_TEXT["tunnel_not_ours"]
    assert "연 터미널에서 닫으세요" in text.SERVER_TEXT["tunnel_not_ours"]


def test_server_controls_tunnel(text):
    def can(**kw):
        base = {"running": False, "runpod_ok": True, "rngd_ok": True, "ssh_set": True,
                "tunnel": {"port": 18000, "open": False, "owned": False, "pid": None, "since": None}}
        c = text.server_controls(**{**base, **kw})
        return c["can"]["tunnel_open"], c["can"]["tunnel_close"], c["why"]
    assert can()[:2] == (True, False)
    assert can(running=True)[:2] == (True, False)                         # 여는 것은 실행 중에도 된다
    opened = {"port": 18000, "open": True, "owned": True, "pid": 1, "since": None}
    assert can(tunnel=opened)[:2] == (False, True)
    o, c, why = can(tunnel=opened, running=True)
    assert (o, c) == (False, False) and "실행" in why["tunnel_close"]
    o, c, why = can(tunnel={**opened, "owned": False})
    assert (o, c) == (False, False) and "앱이 연 터널이 아닙니다" in why["tunnel_close"]
    o, c, why = can(ssh_set=False)
    assert o is False and "RNGD_SSH" in why["tunnel_open"]
    o, c, why = can(tunnel={**opened, "port": None, "open": False, "owned": False})
    assert o is False and "RNGD_BASE_URL" in why["tunnel_open"]


def test_friendly_server_ui_copy(text):
    copy = text.server_ui_text()
    assert copy["guide"]["advanced_off"] == "고급을 켜고 서버 탭에서 모델을 올리세요"
    assert copy["guide"]["advanced_on"] == "서버 탭에서 모델을 올리세요"
    assert copy["action_failure"]["message"] == "서버 변경을 끝내지 못했습니다."
    assert copy["action_failure"]["fix"]
    assert copy["busy"] and copy["unavailable"]


# ── 작업 실패 글과 라우트 오류 글 (step 7) ─────────────────
# 가짜 로그만 쓴다. 실제 작업 로그(runs/manual/jobs)의 글은 옮기지 않는다.

def fake_traceback(last: str, *, before: str = "") -> str:
    return (before + "Traceback (most recent call last):\n"
            '  File "scripts/try_section.py", line 9, in <module>\n'
            "    raise SomeError(\"가짜\")\n" + last + "\n")


@pytest.mark.parametrize("last", [
    "FileNotFoundError: T21-X01: 쪽 글자 파일(pNNN.txt)이 없습니다: ../data/pages/가짜판/T21-X01",
    "FileNotFoundError: [Errno 2] No such file or directory: '../data/pages/가짜판/T21-X01/p001.txt'",
])
def test_job_error_missing_pages(text, last):
    err = text.job_error(fake_traceback(last))
    assert err["message"] == "쪽 글자 폴더나 파일이 없습니다."
    assert "문서 묶음" in err["fix"] and "prev/version9" in err["fix"]
    assert err["raw"] == last and err["warnings"] == []


def test_job_error_outside_doc(text):
    err = text.job_error(fake_traceback("KeyError: 'manifest에 없는 문서 번호: RAW-90'"))
    assert "manifest" in err["message"] and "돌릴 수 없습니다" in err["message"]
    assert "format40" in err["fix"] and err["fix"] in text.SET_TEXT["outside_wait"]


@pytest.mark.parametrize("last, part", [
    ("openai.APIConnectionError: Connection error.", "연결하지 못했습니다"),
    ("ConnectionRefusedError: [Errno 61] Connection refused", "연결하지 못했습니다"),
    ("httpx.ConnectTimeout: timed out", "연결하지 못했습니다"),
    ("httpx.ReadTimeout: 가짜 읽기 시간 초과", "연결하지 못했습니다"),
    ("openai.AuthenticationError: Error code: 401 - {'error': '가짜'}", "키를 거절했습니다"),
    ("httpx.HTTPStatusError: Client error '401 Unauthorized' for url 'http://127.0.0.1:9/v1'", "키를 거절했습니다"),
    ("ValueError: 평가용 문서가 들어 있습니다(T21-X09).", "평가용"),
    ("ValueError: 가짜 다른 오류", "오류로 끝났습니다"),
    ("SystemExit: 가짜 끝", "오류로 끝났습니다"),
])
def test_job_error_branches(text, last, part):
    err = text.job_error(fake_traceback(last))
    assert part in err["message"] and err["raw"] == last
    if "키를" in part:
        assert "RUNPOD_VLLM_API_KEY" in err["fix"] and "RNGD_API_KEY" in err["fix"]
    if "연결" in part:
        assert "진단" in err["fix"]


def test_job_error_first_rule_wins_and_401_needs_a_number_of_its_own(text):
    # 쪽 글자 갈래가 연결 갈래보다 먼저다. 문서 번호 안의 401은 키 오류가 아니다
    path_err = text.job_error("FileNotFoundError: ../data/pages/가짜판/T21-401 timed out\n")
    assert path_err["message"] == "쪽 글자 폴더나 파일이 없습니다."
    assert "키" not in text.job_error("ValueError: 가짜 문서 T21-401 오류\n")["message"]


def test_job_error_takes_last_exception_line_not_source_lines(text):
    log = ("KeyError: 'manifest에 없는 문서 번호: RAW-90'\n"            # 앞 실행의 오류
           + fake_traceback("ValueError: 가짜 마지막 오류")
           + "    raise FileNotFoundError(f\"쪽 글자 파일(pNNN.txt)이 없습니다\")\n")   # 들여 쓴 소스 줄은 예외 줄이 아니다
    err = text.job_error(log)
    assert err["raw"] == "ValueError: 가짜 마지막 오류" and err["message"] == "작업이 오류로 끝났습니다."


def test_job_error_reads_only_last_200_lines_for_the_exception(text):
    log = "ValueError: 오래된 가짜 오류\n" + "가짜 진행 줄\n" * 200
    assert text.job_error(log) is None


def test_job_error_dotenv_warnings(text):
    log = ("python-dotenv could not parse statement starting at line 7\n"
           "Python-dotenv could not parse statement starting at line 7\n"
           "python-dotenv could not parse statement starting at line 12\n"
           + fake_traceback("ValueError: 가짜"))
    err = text.job_error(log)
    assert err["warnings"] == [text.env_problem(7), text.env_problem(12)]
    only = text.job_error("python-dotenv could not parse statement starting at line 3\n가짜 진행 줄\n")
    assert only["raw"] is None and only["warnings"] == [text.env_problem(3)]
    assert only["message"] and only["fix"]


@pytest.mark.parametrize("log", ["", "가짜 진행 줄\n끝\n", "Traceback (most recent call last):\n"])
def test_job_error_none_without_exception_or_warning(text, log):
    assert text.job_error(log) is None


def test_job_error_texts_are_filled_and_have_no_pass_word(text):
    logs = ["FileNotFoundError: ../data/pages/x", "KeyError: 'manifest에 없는 문서 번호: RAW-90'",
            "openai.APIConnectionError: x", "openai.AuthenticationError: 401", "ValueError: 평가용",
            "ValueError: x", "python-dotenv could not parse statement starting at line 1"]
    for log in logs:
        err = text.job_error(log + "\n")
        assert err["message"].strip() and err["fix"].strip(), log
        assert "합격" not in err["message"] + err["fix"]
        assert set(err) == {"message", "fix", "raw", "warnings"}


PROBLEM_FACTS = {"unknown_set": {"id": "가짜묶음"}, "unusable_set": {"reason": "가짜 이유."},
                 "unknown_key": {"id": "gold/가짜"}, "unusable_key": {"reason": "가짜 이유."},
                 "missing_pages": {"where": "가짜판/T21-X01"}, "missing_run": {"name": "가짜실행"},
                 "doc_not_in_run": {"doc": "T21-X01"}, "doc_not_in_set": {"doc": "T21-X01"},
                 "bad_query": {"detail": "no는 1~16 항 번호여야 합니다 (받은 값: 0)"}}


@pytest.mark.parametrize("kind", sorted(PROBLEM_FACTS))
def test_problem_kinds(text, kind):
    p = text.problem(kind, **PROBLEM_FACTS[kind])
    assert set(p) == {"error", "message", "fix"}
    assert all(isinstance(v, str) and v.strip() for v in p.values())
    assert "합격" not in "".join(p.values())
    assert set(text.PROBLEM_TEXT) == set(PROBLEM_FACTS)


def test_problem_keeps_old_error_texts(text):
    # 지금 화면과 기존 시험이 쓰는 error 글은 그대로다
    assert text.problem("unknown_set", id="x")["error"] == "없는 문서 묶음: x"
    assert text.problem("missing_run", name="a, b")["error"] == "없는 실행: a, b"
    assert text.problem("unknown_key", id="x")["error"] == text.KEY_TEXT["unknown_key"].format(id="x")
    assert text.problem("unusable_key", reason="r")["error"] == text.KEY_TEXT["unusable_key"].format(reason="r")
    assert text.problem("missing_pages", where="v/T21-X01")["error"] == "쪽 글자가 없습니다: v/T21-X01"
    assert text.problem("doc_not_in_run", doc="T21-X01")["error"] == "이 실행에 없는 문서: T21-X01"
    assert text.problem("doc_not_in_set", doc="T21-X01")["error"] == "이 묶음에 없는 문서: T21-X01"
    bad = text.problem("bad_query", detail="가짜 {중괄호} 글")
    assert bad["error"] == bad["message"] == "가짜 {중괄호} 글" and bad["fix"] == "입력을 고친 뒤 다시 보내세요."


def test_problem_for_hidden_docs_does_not_say_why(text):
    for kind in ("doc_not_in_run", "doc_not_in_set", "missing_pages"):
        p = text.problem(kind, **PROBLEM_FACTS[kind])
        assert "평가" not in "".join(p.values()) and "잠" not in "".join(p.values())


def _ui_leaves(value, prefix=''):
    for key, item in value.items():
        path = f'{prefix}.{key}' if prefix else key
        if isinstance(item, dict):
            yield from _ui_leaves(item, path)
        else:
            yield path, item


def test_ui_text_contains_shell_keys_and_legacy_keys_without_collision(text):
    assert {'nav', 'context', 'common', 'errors'} <= text.UI_TEXT.keys()
    assert not (text.UI_TEXT.keys() & text._LEGACY_POLISH_TEXT.keys())
    assert text.POLISH_TEXT == {**text._LEGACY_POLISH_TEXT, **text.UI_TEXT}
    assert all(isinstance(v, str) and v.strip() for _, v in _ui_leaves(text.UI_TEXT))
    for key in ['app_name', 'recent', 'source', 'retest', 'compare', 'jobs', 'servers', 'help', 'open_guide']:
        assert text.UI_TEXT['nav'][key]


def test_ui_text_matches_copy_md(text):
    import html
    import re
    from pathlib import Path
    copy = (Path(__file__).parents[1] / 'scripts/b_app_static/design/COPY.md').read_text()
    def normalize(s):
        return re.sub(r'\s+', ' ', html.unescape(s).replace('**', '').replace('`', '')).strip()
    copy = normalize(copy)
    leaves = dict(_ui_leaves(text.UI_TEXT))
    for key, value in leaves.items():
        if key in text.COPY_EXCEPTIONS:
            assert text.COPY_EXCEPTIONS[key].strip(), key
            continue
        for part in re.split(r'\{[^{}]+\}', value):
            part = normalize(part)
            if len(part) >= 2:
                assert part in copy, (key, part)
    assert set(text.COPY_EXCEPTIONS) <= leaves.keys()
    assert all(isinstance(v, str) and v.strip() for v in text.COPY_EXCEPTIONS.values())
