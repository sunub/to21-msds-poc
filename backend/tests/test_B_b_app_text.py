"""표시 이름 규칙 시험. 실제 실행의 이름만 쓰며 문서 내용이나 서버는 읽지 않는다."""
import copy
import importlib
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from test_B_compare_models import SCRIPTS


def approved_copy(key):
    source = (Path(__file__).parents[1] / 'scripts/b_app_static/design/COPY.md').read_text()
    return next(line.split('|')[1] for line in source.splitlines() if line.startswith(key + '|'))


def test_server_copy_uses_approved_diagnoses_controls_and_visible_management(text):
    for diagnosis, name in [('ok', 'ready'), ('no_model', 'no_model'), ('tunnel_closed', 'tunnel_closed')]:
        result = text.rngd_diagnosis(diagnosis, None, NOW_LOCAL)
        assert result == {'message': approved_copy(f'servers.diagnosis.{name}.fact'),
                          'fix': approved_copy(f'servers.diagnosis.{name}.todo')}
    result = text.server_controls(running=True, runpod_ok=True, rngd_ok=True)
    assert result['why']['pod_create'] == approved_copy('servers.controls.busy')
    for value in text.server_ui_text()['guide'].values():
        assert value == approved_copy('servers.status.guide')
    for state in text.connection_notes('가짜 모델').values():
        for note in state.values():
            assert approved_copy('context.model.action') in note['text']
            assert '고급' not in note['text'] and '④' not in note['text']


def test_server_friendly_errors_and_env_problem_follow_copy_without_address_examples(text):
    result = text.friendly_error('env', 'No setting', {'base_url': 'RNGD_BASE_URL'})
    assert result['message'] == approved_copy('errors.env.missing').format(variable='RNGD_BASE_URL')
    assert result['fix'] == approved_copy('errors.env.company_url')
    result = text.env_problem(17)
    assert result['message'] == approved_copy('errors.env.line').format(line=17)
    assert result['fix'] == approved_copy('errors.env.line_todo')
    for value in text.SERVER_TEXT.values():
        assert 'http' not in value and 'API_KEY=' not in value


@pytest.mark.parametrize("connected, level, state", [
    (["가짜 모델"], "ok", "ready"), (["다른 모델"], "hint", "off"), (None, "error", "failed"),
])
def test_connection_note_facts_and_offline_reading(text, connected, level, state):
    note = text.connection_note("가짜 모델", connected, "고급을 켜고 서버 탭에서 모델을 올리세요.")
    assert note["level"] == level
    assert approved_copy(f"context.model.{state}").format(model="가짜 모델") in note["text"]
    assert approved_copy("context.model.reading") in note["text"]
    assert approved_copy("context.model.action") in note["text"]
    assert "고급" not in note["text"] and "④ 작업" not in note["text"]


def test_connection_notes_cover_loading_and_both_advanced_states(text):
    notes = text.connection_notes("가짜 모델")
    for state in ("ok", "hint", "error", "loading"):
        assert set(notes[state]) == {"advanced_on", "advanced_off"}
        assert all("가짜 모델" in note["text"] for note in notes[state].values())
        assert notes[state]["advanced_on"] == notes[state]["advanced_off"]
    assert notes["loading"]["advanced_off"]["level"] == "hint"
    assert approved_copy("context.model.checking").format(model="가짜 모델") in notes["loading"]["advanced_off"]["text"]
    assert "None" not in text.connection_note(None, [], "서버 탭에서 올리세요.")["text"]


def test_value_tip_lines_translate_and_keep_unknown_nonempty_values(text):
    value = {"seq": 1, "value": "직접 만든 값", "text": "가짜 원문", "refs": ["p5:L25", "p5:L26"],
             "cond": None, "key": "", "empty": [], "std_code": None, "match_score": 0,
             "unknown": False, "nested": {"value": "두\n줄", "cond": None}}
    before = copy.deepcopy(value)
    lines = text.value_tip_lines(value, text.VALUE_FIELD_LABELS)
    assert lines == ["순서: 1", "값: 직접 만든 값", "원문 글: 가짜 원문", "근거 줄: p5:L25, p5:L26",
                     "맞춤 점수: 0", "unknown: 아니요", "nested: 값: 두 줄"]
    assert value == before
    assert text.value_tip_lines({"value": "", "refs": [], "cond": None}, text.VALUE_FIELD_LABELS) == []
    assert text.value_tip_lines([{"value": "가짜"}, "둘"], text.VALUE_FIELD_LABELS) == ["값: 가짜, 둘"]


def test_start_text_contract(text):
    start = text.START_TEXT
    assert start is text.UI_TEXT["journey"]
    assert set(start["tracks"]) == {"t1", "t2"}
    assert len(start["tracks"]["t1"]["steps"]) == 3
    assert len(start["tracks"]["t2"]["steps"]) == 4
    def nonempty(node):
        if isinstance(node, dict):
            assert node
            for value in node.values():
                nonempty(value)
        elif isinstance(node, list):
            assert node
            for value in node:
                nonempty(value)
        elif isinstance(node, str):
            assert node.strip()
    nonempty(start)


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


@pytest.mark.parametrize("delta, phrase", [(-.5, "0.5점 낮습니다"),
                                          (.5, "0.5점 높습니다"), (0, "같습니다")])
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
    assert all(text.UI_TEXT["compare"]["conditions"]["changed"].format(condition=c) in result["headline"] for c in ["모델", "입력 판", text.UI_TEXT["compare"]["conditions"]["prompt_text"]])


def test_diff_headline_commit_only_is_not_same(text, diff_info):
    diff_info["conditions"][-1]["changed"] = True
    result = text.diff_headline(diff_info, "A", "B")
    assert result["same_conditions"] is False
    assert text.UI_TEXT["compare"]["conditions"]["changed"].format(condition="코드 커밋") in result["headline"]


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
        "headline": text.UI_TEXT["compare"]["headline"]["none"], "biggest": None, "same_conditions": True}


FLUTTER = "같은 조건을 반복할 때 생긴 차이일 수 있습니다."


def test_diff_headline_adds_flutter_only_when_same_conditions(text, diff_info):
    diff_info["same_conditions"] = True
    result = text.diff_headline(diff_info, "A", "B")
    assert result["headline"].endswith(text.UI_TEXT["compare"]["conditions"]["same"] + " " + FLUTTER)
    assert set(result) == {"headline", "biggest", "same_conditions"} and result["same_conditions"] is True
    diff_info["same_conditions"] = False                                  # 조건은 같아도 채점 문서가 다르다
    assert FLUTTER not in text.diff_headline(diff_info, "A", "B")["headline"]
    assert text.diff_headline(diff_info, "A", "B")["same_conditions"] is False
    diff_info["same_conditions"] = True
    diff_info["conditions"][0]["changed"] = True
    result = text.diff_headline(diff_info, "A", "B")
    assert FLUTTER not in result["headline"] and text.UI_TEXT["compare"]["conditions"]["changed"].format(condition="모델") in result["headline"]


def test_diff_headline_unscored_total_does_not_claim_equal(text, diff_info):
    diff_info["weighted"]["delta"] = None
    headline = text.diff_headline(diff_info, "A", "B")["headline"]
    assert text.UI_TEXT["compare"]["headline"]["unscored"].format(a="A", b="B") in headline


def test_diff_ui_text_counts_hidden_items_including_unscored(text, diff_info):
    diff_info["items"].append({"name": "미채점", "delta": None})
    result = text.diff_ui_text(diff_info)
    assert result["hidden"] == text.UI_TEXT["compare"]["items"]["hidden"].format(count=2)
    assert result["candidate"] == text.UI_TEXT["compare"]["items"]["candidate"]
    assert result["empty"] == text.UI_TEXT["compare"]["items"]["empty"]


def test_doc_legend_gives_color_only_to_the_selection_and_returns_fresh_values(text):
    expected = [("same", text.UI_TEXT["source"]["legend"]["same"], None),
                ("diff", text.UI_TEXT["source"]["legend"]["different"], None),
                ("silver_only", text.UI_TEXT["source"]["legend"]["missing"], None),
                ("picked", text.UI_TEXT["source"]["legend"]["selected"], "#fff3c6")]
    legend = text.doc_legend()
    assert [(v["key"], v["label"], v["color"]) for v in legend] == expected
    css = (SCRIPTS / "b_app_static" / "app.css").read_text()
    assert "#fff3c6" in css
    legend[3]["color"] = "changed"
    assert text.doc_legend()[3]["color"] == "#fff3c6"


def test_doc_ui_text_summaries_count_values_and_missing_cells_separately(text):
    view = {"values": [{"section": 3, "silver": {"same": True}},
                       {"section": 3, "silver": {"same": False}}],
            "silver_only": [{"section": 3}, {"section": None}]}
    before = copy.deepcopy(view)
    result = text.doc_ui_text(view)
    assert result["sections"] == {
        "3": text.UI_TEXT["source"]["doc"]["counts"].format(total=2, different=1, missing=1),
        "?": text.UI_TEXT["source"]["doc"]["counts"].format(total=0, different=0, missing=1)}
    assert result["howto"] == text.UI_TEXT["source"]["doc"]["howto"]
    assert view == before


def test_doc_ui_text_silver_line_guess_and_missing(text):
    """정답 초안 값의 줄은 글자 맞춤 추정이라고 밝히고, 못 찾으면 그 항의 구간을 연다고 알린다."""
    result = text.doc_ui_text({"values": [], "silver_only": []})
    guess, missing = result["silver_line_guess"], result["silver_line_missing"]
    assert guess == text.UI_TEXT["source"]["doc"]["guess"]
    assert missing == text.UI_TEXT["source"]["doc"]["no_guess"]
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
    suffix = {state: approved_copy(f"context.model.state_{key}")
              for state, key in ((True, "ready"), (None, "unknown"), (False, "off"))}
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
    expected = approved_copy("jobs.try_hint.ready" if count else "jobs.try_hint.off").format(count=count)
    assert text.try_hint(models, advanced) == {"dry_run_forced": not count, "note": expected}


def test_field_help_and_try_stage_help_are_complete(text):
    assert set(text.FIELD_HELP) == {"model", "doc", "pages", "scope", "prompt", "base_run",
                                    "dry_run", "repeat", "run_name", "compare_label"}
    assert all(isinstance(v, str) and v.strip() for v in text.FIELD_HELP.values())
    assert len(text.TRY_STAGE_HELP) == 6
    for key, value in text.FIELD_HELP.items():
        assert value == approved_copy("jobs.fields." + key)
    stage_keys = ["input", "prompt", "raw_answer", "parsed", "to21", "score"]
    assert list(text.TRY_STAGE_HELP.values()) == [approved_copy("jobs.stages." + key) for key in stage_keys]
    for key, value in text.JOB_UI_TEXT.items():
        assert value == approved_copy("jobs.actions." + key)



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
    for phrase in ("72.7점", "90점", "17.3점", "17개가 필수 기준입니다. 5개가 각자의 목표를 채웠습니다."):
        assert phrase in result["headline"]
    drops = result["top_drops"]
    assert [d["name"] for d in drops] == ["8항 노출기준", "11항 기타 독성", "9항 기타 물성"]
    assert [d["cause"] for d in drops] == ["빠뜨림", "틀림", "지어냄"]
    assert [d["weight"] for d in drops] == [3, 2, 1]
    assert drops[0]["score"] == pytest.approx(40.3)
    assert drops[0]["target"] == 95
    assert drops[0]["gap"] == pytest.approx(54.7)
    assert drops[0]["sentence"] == "8항 노출기준은 40.3점입니다. 목표는 95점입니다. 가장 많은 문제 유형은 빠뜨림 47건입니다."
    assert drops[0]["section"] == 8
    assert score_info == before


@pytest.mark.parametrize("connected", [None, False, True])
def test_status_next_action_uses_last_known_connection(text, score_info, connected):
    result = text.score_status(score_info, {"pass_score": 90}, connected=connected)
    expected = (text.UI_TEXT["score"]["summary"]["next_trial"].format(section=11) if connected else
                text.UI_TEXT["score"]["summary"]["next_source"].format(item="11항 기타 독성"))
    assert result["next_action"] == expected


def test_status_section_from_help_or_falls_back_to_source(text, score_info):
    score_info["items"] = [{**score_info["items"][0], "name": "가짜 검사"}]
    c = {"pass_score": 90, "items": [{"name": "가짜 검사", "help": "3항의 가짜 값을 비교합니다."}]}
    result = text.score_status(score_info, c, connected=True)
    assert result["top_drops"][0]["section"] == 3
    assert result["next_action"] == text.UI_TEXT["score"]["summary"]["next_trial"].format(section=3)
    result = text.score_status(score_info, {"pass_score": 90}, connected=True)
    assert result["top_drops"][0]["section"] is None
    assert result["next_action"] == text.UI_TEXT["score"]["summary"]["next_source"].format(item="가짜 검사")


def test_status_pass_none_and_weighted_pass_with_required_failure(text):
    c = {"pass_score": 90, "items": [{"level": "필수"}, {"level": "필수"}]}
    good = text.score_status({"weighted": 90, "must_passed": 2, "items": []}, c)
    assert good["verdict"] == "pass"
    assert "필수 기준 2개가 모두 각자의 목표에 닿았습니다" in good["headline"]
    assert good["top_drops"] == []
    assert good["next_action"] == text.UI_TEXT["score"]["summary"]["next_compare"]
    missing = text.score_status({"weighted": None}, c)
    assert missing["verdict"] == "none"
    assert missing["headline"] == text.UI_TEXT["score"]["summary"]["unscored"]
    assert missing["top_drops"] == [] and "합격" not in missing["next_action"]
    failed = text.score_status({"weighted": 93, "must_passed": 1}, c)
    assert failed["verdict"] == "fail" and "2개가 필수 기준입니다. 1개가 각자의 목표를 채웠습니다." in failed["headline"]
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
    assert text.card_summary("history", {"runs": runs}) == "저장된 결과 2개 중 최고점은 81.2점입니다. 해당 결과는 가짜 실행입니다."
    assert text.card_summary("history", {"runs": runs[:1]}) == "저장된 결과 1개 중 최고점은 0.0점입니다. 해당 결과는 a입니다."


def test_summary_history_skips_silver_runs_and_prefers_comparable(text):
    runs = [{"kind": "run", "name": "silver", "weighted": 93.4, "run_kind": "silver", "comparable": False},
            {"kind": "run", "name": "probe", "weighted": 80.0, "run_kind": "probe", "comparable": False},
            {"kind": "run", "name": "dev", "weighted": 72.7, "run_kind": "dev10", "comparable": True,
             "label": {"title": "가짜 본 실행"}}]
    assert text.card_summary("history", {"runs": runs}) == "저장된 결과 2개 중 최고점은 72.7점입니다. 해당 결과는 가짜 본 실행입니다."
    assert text.card_summary("history", {"runs": runs[:2]}) == "저장된 결과 1개 중 최고점은 80.0점입니다. 해당 결과는 probe입니다."
    assert text.card_summary("history", {"runs": runs[:1]}) == "자료 없음"


def test_run_kind_labels(text):
    assert text.RUN_KIND_LABELS == {
        "dev10": "개발용 10건 시험", "single": "문서 한 건 시험", "probe": "일부 문서 시험", "silver": "AI 정답 초안 만들기",
        "eval": "평가용 기록 · 열람 제한", "outside": "새 문서 시험 · 점수 없음", "models": "비교표"}
    for kind, label in text.RUN_KIND_LABELS.items():
        assert text.run_kind_label(kind) == label
    assert text.run_kind_label(None) == ""


TWO_MUST = {"pass_score": 90, "items": [{"level": "필수"}, {"level": "필수"}]}


def test_status_shows_two_targets(text):
    result = text.score_status({"weighted": 72.66, "must_passed": 1, "items": []}, TWO_MUST)
    assert result["headline"] == ("전체 점수는 72.7점입니다. 목표 점수 90점보다 17.3점 낮습니다. "
                                  "23개 점수 기준 중 꼭 맞아야 하는 2개가 필수 기준입니다. 1개가 각자의 목표를 채웠습니다.")
    assert result["targets"] == {"weighted": {"line": 90, "value": 72.66, "met": False},
                                 "must": {"total": 2, "met_count": 1, "met": False}}
    assert result["verdict"] == "fail"
    mixed = text.score_status({"weighted": 93, "must_passed": 1, "items": []}, TWO_MUST)
    assert mixed["headline"] == "전체 점수는 93.0점입니다. 목표 점수 90점에 도달했습니다. 23개 점수 기준 중 꼭 맞아야 하는 2개가 필수 기준입니다. 1개가 각자의 목표를 채웠습니다."
    assert mixed["targets"]["weighted"]["met"] is True and mixed["targets"]["must"]["met"] is False


def test_status_both_targets_met(text):
    result = text.score_status({"weighted": 90, "must_passed": 2, "items": []}, TWO_MUST)
    assert result["headline"] == "전체 점수는 90.0점입니다. 목표 점수 90점에 도달했습니다. 필수 기준 2개가 모두 각자의 목표에 닿았습니다."
    assert result["targets"] == {"weighted": {"line": 90, "value": 90, "met": True},
                                 "must": {"total": 2, "met_count": 2, "met": True}}
    assert result["next_action"] == text.UI_TEXT["score"]["summary"]["next_compare"]
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
    assert "합격" not in text.START_TEXT["start"]["no_problem"] + text.explain("필수")


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
    assert text.card_summary("docs", info) == "문서 2건입니다. 가장 낮은 점수는 T21-X01의 0.0점입니다. 가장 오래 걸린 문서는 T21-X02입니다. 84초 걸렸습니다."
    info["per_doc"]["T21-X02"]["seconds"] = None
    assert "가장 오래 걸린 문서는 T21-X01입니다. 15초 걸렸습니다." in text.card_summary("docs", info)
    info["per_doc"]["T21-X01"]["seconds"] = None
    assert "문서별 시간 기록이 없습니다." in text.card_summary("docs", info)


def test_summary_grid_matches_cell_priority_including_multi_msds(text):
    info = {"grid": {"T21-X01": {"1": {"ok": True}, "2": {"ok": True, "reextracted": True}},
                     "T21-X02": {"m0:1": {"ok": True, "reextracted": True, "limit_kind": "긴출력"},
                                 "m1:1": {"ok": False, "reextracted": True, "limit_kind": "공백폭주"}}}}
    assert text.card_summary("grid", info) == "AI 요청 4개의 상태입니다. 성공 1개, 다시 뽑아 성공 1개, 길이 제한 뒤 성공 1개, 실패 1개"


def test_summary_rows_includes_all_nine_and_largest_absolute_shortfall(text):
    keys = ("components", "exposure_limits", "physchem", "toxicity", "cmr", "ecotox", "regulations", "intl_class", "extras")
    info = {"rows": {key: {"pred": 2, "gold": 2} for key in keys}}
    info["rows"]["toxicity"] = {"pred": 3, "gold": 12}
    info["rows"]["cmr"] = {"pred": 0, "gold": 2}
    assert text.card_summary("rows", info) == "표 9개 중 정답보다 행이 적은 표는 2개입니다. 행이 가장 부족한 표는 독성 (11번 부분)입니다. AI 결과는 3행입니다. 정답은 12행입니다."
    for row in info["rows"].values():
        row["pred"] = row["gold"]
    assert text.card_summary("rows", info) == "표 9개 중 정답보다 행이 적은 표는 0개입니다."


@pytest.mark.parametrize("kind", ["history", "docs", "grid", "rows"])
def test_summary_empty(text, kind):
    assert text.card_summary(kind, {}) == "자료 없음"


def test_glossary_has_required_terms_and_safe_examples(text):
    required = {
        approved_copy(f"glossary.{key}.term") for key in (
            "silver", "gold", "weighted", "must_count", "must", "important", "ordinary", "section", "item",
            "prompt", "prompt_version", "input", "page_text", "line", "base_run", "practice", "try", "batch",
            "comparison", "missing", "invented", "wrong", "empty_row", "calls", "reextract", "output_limit",
            "whitespace", "repetition", "model_tag", "runpod", "rngd", "pod", "repeat", "extras", "key_gap",
            "concurrency", "rows", "variation", "exposure", "concentration_unit",
        )
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
    ("qwen36_35b_runpod", "Qwen3.6 35B · 빌린 서버"),
    ("qwen3_30b_a3b_rngd", "Qwen3 30B · 회사 서버"),
    ("gpt_oss_20b_rngd", "gpt-oss 20B · 회사 서버"),
    ("nuextract2_8b_runpod", "NuExtract 2.0 8B · 빌린 서버"),
    ("qwen3vl4b_rngd", "Qwen3-VL 4B · 회사 서버"),
    ("qwen38", "Qwen3.8 27B (vLLM)"),
    ("claude", "Claude · AI 정답 초안"),
    ("gpt", "GPT · AI 정답 초안"),
    ("future_model", "future_model"),
    (None, ""),
    ("", ""),
])
def test_model_labels(text, tag, expected):
    assert text.model_label(tag) == expected


@pytest.mark.parametrize("name, title", [
    ("20261030_sections_qwen36_35b_runpod_s7_v9_cls_dev10_r2",
     "10/30 Qwen3.6 35B · 빌린 서버 · AI에게 시킨 일 7번째 판 · 원문 자료 9판 · 분류 검사 · 개발 10건 · 2회차"),
    ("20261027_silver_claude_p3_dev",
     "10/27 Claude · AI 정답 초안 · AI에게 시킬 일 p3 · 개발 10건"),
    ("20261029_sections_qwen3_30b_a3b_rngd_s4_cw_optonly_probe",
     "10/29 Qwen3 30B · 회사 서버 · AI에게 시킨 일 4번째 판 · 원문 자료 임시판 · 선택 항목만 · 일부 시험"),
    ("20261028_sections_qwen3_30b_a3b_rngd_s2_cw_s003_w1_r2",
     "10/28 Qwen3 30B · 회사 서버 · AI에게 시킨 일 2번째 판 · 원문 자료 임시판 · 문서 T21-S003 한 건 · 동시 1개 · 2회차"),
    ("20261028_sections_gpt_oss_20b_rngd_s2_cw_s003_w1_r2",
     "10/28 gpt-oss 20B · 회사 서버 · AI에게 시킨 일 2번째 판 · 원문 자료 임시판 · 문서 T21-S003 한 건 · 동시 1개 · 2회차"),
    ("20261028_sections_nuextract2_8b_runpod_cw_s016_ex",
     "10/28 NuExtract 2.0 8B · 빌린 서버 · 원문 자료 임시판 · 문서 T21-S016 한 건 · 예시 포함"),
    ("20261027_silver_claude_p3_eval039",
     "10/27 Claude · AI 정답 초안 · AI에게 시킬 일 p3 · 평가용 문서 한 건 · 열람 제한"),
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
    assert result["title"] == "10/30 Qwen3.6 35B · 빌린 서버 · AI에게 시킨 일 7번째 판 · 원문 자료 9판 · 일부 시험"
    assert info == before
    assert text.run_label(info) == result


@pytest.mark.parametrize("info, title", [
    ({}, ""),
    ({"name": "custom_unknown", "started_at": "2026-02-03T12:00:00+09:00"}, "2/3 · custom · unknown"),
    ({"name": "custom", "started_at": "invalid"}, "custom"),
    ({"name": "20260230_sections_gpt_probe", "started_at": "2026-03-01"}, "3/1 GPT · AI 정답 초안 · 일부 시험"),
    ({"name": "20261030_sections_future_model_s8_v13_new", "model_tag": "future_model"},
     "10/30 future_model · AI에게 시킨 일 8번째 판 · 원문 자료 13판 · new"),
    ({"name": "20261030_sections_claude_p3_dev", "prompt_version": "p3"},
     "10/30 Claude · AI 정답 초안 · AI에게 시킨 일 p3 · 개발 10건"),
    ({"name": "manual/20261030_qwen38_s7_v9_probe", "kind": "manual"},
     "앱에서 시작 · 10/30 Qwen3.8 27B (vLLM) · AI에게 시킨 일 7번째 판 · 원문 자료 9판 · 일부 시험"),
    ({"name": "20260102_sections_gpt_s7_chars_wrap_dev10"},
     "1/2 GPT · AI 정답 초안 · AI에게 시킨 일 7번째 판 · 원문 자료 임시판 · 개발 10건"),
    ({"name": "20261028_sections_qwen3_30b_a3b_rngd_s2_version2_diag2"},
     "10/28 Qwen3 30B · 회사 서버 · AI에게 시킨 일 2번째 판 · 원문 자료 2판 · 문제 확인 2"),
])
def test_partial_metadata_and_unknown_tokens(text, info, title):
    result = text.run_label(info)
    assert result["title"] == title
    assert result["subtitle"] == info.get("name", "")
    assert result["parts"] == title.split(" · ")


@pytest.mark.parametrize("token, expected", [
    ("eval", "평가 10건"), ("probe3", "일부 문서 시험 3회"), ("diag", "문제 확인"),
    ("none", "AI에게 시킬 일 없음"), ("wsonly", "빈칸 줄이기만"),
    ("m013", "문서 T21-M013 한 건"), ("S003", "문서 T21-S003 한 건"),
    ("s12", "AI에게 시킨 일 12번째 판"), ("v2", "원문 자료 2판"), ("unknown", "unknown"),
])
def test_condition_tokens(text, token, expected):
    assert text.run_label({"name": f"20261030_sections_gpt_{token}"})["title"] == f"10/30 GPT · AI 정답 초안 · {expected}"


@pytest.mark.parametrize("where,raw,kind", [
    ("rngd", "Could not resolve hostname ssh: failure", "ssh_prefix"),
    ("rngd", "RNGD_SSH starts with ssh", "ssh_prefix"),
    ("rngd", "RNGD_SSH 없음", "ssh_missing"),
    ("runpod", "RunPod 연결 오류: SSLCertVerificationError", "certificate"),
    ("runpod", "CERTIFICATE_VERIFY_FAILED", "certificate"),
    ("runpod", "HTTP 401", "account_key"), ("runpod", "Unauthorized", "account_key"),
    ("model", "request timed out", "no_response"), ("rngd", "Connection refused", "no_response"),
    ("model", "새 오류 <unknown>", "other"), ("env", "", "other"),
])
def test_friendly_error_rules(text, where, raw, kind):
    assert text.friendly_error(where, raw) == {"message": approved_copy(f"errors.connection.{kind}.fact"),
        "fix": approved_copy(f"errors.connection.{kind}.todo"), "raw": raw}


@pytest.mark.parametrize("variable,key", [("VLLM_BASE_URL", "unknown_url"), ("RNGD_BASE_URL", "company_url"),
                                           ("RUNPOD_VLLM_BASE_URL", "runpod_url")])
def test_friendly_env_uses_config_variable_name(text, variable, key):
    names = {"api_key": "VLLM_API_KEY", "base_url": variable}
    before = dict(names)
    result = text.friendly_error("env", "주소 설정 없음", names)
    assert result["message"] == approved_copy("errors.env.missing").format(variable=variable)
    assert result["fix"] == approved_copy(f"errors.env.{key}").format(variable=variable)
    assert "http" not in result["fix"]
    assert result["raw"] == "주소 설정 없음" and names == before


@pytest.mark.parametrize("raw,expected", [
    ("Could not resolve hostname ssh CERTIFICATE_VERIFY_FAILED 401", "RNGD_SSH 설정"),
    ("CERTIFICATE_VERIFY_FAILED 401", "인증서를 확인하지 못했습니다"),
    ("Unauthorized timed out", "관리 키"), ("timed out", "VLLM_BASE_URL"),
])
def test_friendly_error_first_matching_rule_wins(text, raw, expected):
    assert expected in text.friendly_error("env", raw, {"base_url": "VLLM_BASE_URL"})["message"]


@pytest.mark.parametrize("raw", ["HTTP 401", "HTTP 401: URLError"])
def test_friendly_model_401_is_model_server_key(text, raw):
    result = text.friendly_error("model", raw)
    assert result["message"] == approved_copy("errors.connection.model_key.fact")
    assert result["fix"] == " ".join([approved_copy("errors.connection.model_key.todo"), approved_copy("errors.connection.model_key_changed")])
    assert "관리 키" not in result["message"] and result["raw"] == raw


def test_friendly_runpod_401_unchanged(text):
    raw = "RunPod HTTP 401: 가상 거절"
    assert text.friendly_error("runpod", raw) == {"message": approved_copy("errors.connection.account_key.fact"),
        "fix": approved_copy("errors.connection.account_key.todo"), "raw": raw}


def test_env_problem_has_line_and_no_value(text):
    item = text.env_problem(4)
    assert item["line"] == 4 and "4번째 줄" in item["message"] and "설정 다시 읽기" in item["fix"]
    assert set(item) == {"line", "message", "fix"}


def test_server_refusal_texts(text):
    assert "RUNPOD_VLLM_API_KEY" in text.SERVER_TEXT["pod_key_missing"]
    assert "할 일:" in text.SERVER_TEXT["pod_key_missing"] and "설정 다시 읽기" in text.SERVER_TEXT["pod_key_missing"]
    assert text.SERVER_TEXT["pod_not_ours"] == approved_copy("servers.messages.pod_not_ours")
    assert text.SERVER_TEXT["env_file_unknown"]


def test_timed_out_does_not_assume_tunnel(text):
    fix = text.friendly_error("model", "URLError: TimeoutError")["fix"]
    assert fix == approved_copy("errors.connection.no_response.todo") and "SSH 터널이 열려 있는지" not in fix          # 모델이 안 떠 있어도 터널을 탓하던 문장 (step 6)


NOW_LOCAL = datetime(2026, 10, 30, 21, 0, tzinfo=timezone(timedelta(hours=9)))


def ago(minutes: float) -> str:
    return (NOW_LOCAL - timedelta(minutes=minutes)).isoformat(timespec="seconds")


def test_rngd_diagnosis_texts(text):
    for diagnosis, name in [("ok", "ready"), ("no_model", "no_model"), ("tunnel_closed", "tunnel_closed")]:
        item = text.rngd_diagnosis(diagnosis, None, NOW_LOCAL)
        assert item == {"message": approved_copy(f"servers.diagnosis.{name}.fact"),
                        "fix": approved_copy(f"servers.diagnosis.{name}.todo")}
    no_model = text.rngd_diagnosis("no_model", None, NOW_LOCAL)
    assert "터널" not in no_model["message"] + no_model["fix"]
    assert text.rngd_diagnosis(None, None, NOW_LOCAL) is None
    assert text.rngd_diagnosis("모르는 값", None, NOW_LOCAL) is None


@pytest.mark.parametrize("since, minutes, late", [(ago(7.5), 7, False), (ago(25), 25, False), (ago(26), 26, True)])
def test_rngd_diagnosis_loading_minutes(text, since, minutes, late):
    item = text.rngd_diagnosis("loading", since, NOW_LOCAL)
    assert item["message"] == approved_copy("servers.diagnosis.loading.elapsed").format(minutes=minutes)
    assert item["fix"].startswith(approved_copy("servers.diagnosis.loading.todo"))
    assert ("서버 기록을 확인하세요" in item["fix"]) is late


def test_rngd_diagnosis_loading_other_timezone_and_unknown(text):
    utc = (NOW_LOCAL - timedelta(minutes=3)).astimezone(timezone.utc).isoformat()
    assert text.rngd_diagnosis("loading", utc, NOW_LOCAL)["message"] == approved_copy("servers.diagnosis.loading.elapsed").format(minutes=3)
    for since in (None, "", "시각 아님"):
        item = text.rngd_diagnosis("loading", since, NOW_LOCAL)
        assert item["message"] == approved_copy("servers.diagnosis.loading.unknown") and "서버 기록" not in item["fix"]


def test_tunnel_refusal_texts(text):
    for key in ("tunnel_no_port", "tunnel_already_open", "tunnel_closed", "tunnel_not_ours", "tunnel_exited",
                "tunnel_timeout", "tunnel_spawn_failed", "tunnel_still_open"):
        assert "할 일:" in text.SERVER_TEXT[key], key
    assert text.SERVER_TEXT["tunnel_not_ours"] == approved_copy("servers.messages.tunnel_not_ours")
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
    assert (o, c) == (False, False) and why["tunnel_close"] == approved_copy("servers.controls.busy")
    o, c, why = can(tunnel={**opened, "owned": False})
    assert (o, c) == (False, False) and why["tunnel_close"] == approved_copy("servers.controls.not_owned")
    o, c, why = can(ssh_set=False)
    assert o is False and "RNGD_SSH" in why["tunnel_open"]
    o, c, why = can(tunnel={**opened, "port": None, "open": False, "owned": False})
    assert o is False and "RNGD_BASE_URL" in why["tunnel_open"]


def test_friendly_server_ui_copy(text):
    copy = text.server_ui_text()
    assert copy["guide"]["advanced_off"] == approved_copy("servers.status.guide")
    assert copy["guide"]["advanced_on"] == approved_copy("servers.status.guide")
    assert copy["action_failure"]["message"] == approved_copy("servers.status.failure.fact")
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
    assert err["message"] == approved_copy("errors.job.pages.message")
    assert err["fix"] == approved_copy("errors.job.pages.fix")
    assert err["raw"] == last and err["warnings"] == []


def test_job_error_outside_doc(text):
    err = text.job_error(fake_traceback("KeyError: 'manifest에 없는 문서 번호: RAW-90'"))
    assert err["message"] == approved_copy("errors.job.outside.message")
    assert err["fix"] == approved_copy("errors.job.outside.fix")
    assert err["fix"] in text.SET_TEXT["outside_wait"]


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
        assert err["fix"] == approved_copy("errors.job.key.fix")
    if "연결" in part:
        assert err["fix"] == approved_copy("errors.job.connect.fix")


def test_job_error_first_rule_wins_and_401_needs_a_number_of_its_own(text):
    # 쪽 글자 갈래가 연결 갈래보다 먼저다. 문서 번호 안의 401은 키 오류가 아니다
    path_err = text.job_error("FileNotFoundError: ../data/pages/가짜판/T21-401 timed out\n")
    assert path_err["message"] == approved_copy("errors.job.pages.message")
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
    assert text.problem("unknown_key", id="x")["error"] == "없는 정답지입니다: x. 정답지 목록에서 고르세요."
    assert text.problem("unusable_key", reason="r")["error"] == "고를 수 없는 정답지입니다: r"
    assert text.problem("missing_pages", where="v/T21-X01")["error"] == "쪽 글자가 없습니다: v/T21-X01"
    assert text.problem("doc_not_in_run", doc="T21-X01")["error"] == "이 실행에 없는 문서: T21-X01"
    assert text.problem("doc_not_in_set", doc="T21-X01")["error"] == "이 묶음에 없는 문서: T21-X01"
    bad = text.problem("bad_query", detail="가짜 {중괄호} 글")
    assert bad["error"] == bad["message"] == "가짜 {중괄호} 글" and bad["fix"] == approved_copy("errors.request.bad_query.fix")


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


def test_ui_text_contains_shell_keys_and_is_the_injected_contract(text):
    assert {'nav', 'context', 'common', 'errors'} <= text.UI_TEXT.keys()
    assert text.POLISH_TEXT is text.UI_TEXT
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


@pytest.mark.parametrize('counts,cause', [(None, None), ({'빠뜨림': 6, '틀림': 2, '지어냄': 1}, '빠뜨림'),
                                         ({'빠뜨림': 0, '틀림': 0, '지어냄': 0}, None)])
def test_problem_loss_counts_preserves_missing_zero_and_input(text, counts, cause):
    info = loss_info(('8항 노출기준', '필수', .6, .95))
    if counts is not None:
        info['items'][0].update(counts)
    before = copy.deepcopy(info)
    result = text.score_losses(info, LOSS_CRITERIA)
    assert result['losses'][0]['counts'] == counts
    assert result['losses'][0]['cause'] == cause
    assert result['top_problem']['counts'] == counts
    assert info == before
    assert '기록 없음' in text.UI_TEXT['score']['problem']['unrecorded']


def test_losses_use_field_counts_when_given_and_keep_scorer_counts(text):
    """S01 문제 건수는 S02와 같은 칸 단위 수다 (사용자 결정 10/31). 점수 프로그램의 행 단위 수는 scorer_counts에 둔다.
    S02처럼 항목 이름과 항(section)으로 거른다. 항을 모르는 항목은 모든 항의 칸을 센다."""
    from collections import Counter
    info = loss_info(('8항 노출기준', '필수', .6, .95), ('가짜 일반', '일반', .9, .8))
    info['items'][0].update({'빠뜨림': 47, '틀림': 0, '지어냄': 27})
    per_doc = {'T21-X01': {'items': {'8항 노출기준': .5, '가짜 일반': .9}},
               'T21-X02': {'items': {'8항 노출기준': .7, '가짜 일반': .9}},
               'T21-X03': {'items': {'8항 노출기준': .6, '가짜 일반': .9}}}
    field = {'T21-X01': Counter({('8항 노출기준', 8, 'wrong'): 5, ('8항 노출기준', 8, 'made'): 8,
                                 ('8항 노출기준', 8, 'missing'): 10, ('8항 노출기준', 3, 'missing'): 4,
                                 ('가짜 일반', None, 'made'): 2, ('가짜 일반', 5, 'made'): 1}),
             'T21-X02': Counter({('8항 노출기준', 8, 'missing'): 1})}            # T21-X03은 셀 수 없었다(정답 없음)
    before = copy.deepcopy(info)
    result = text.score_losses(info, LOSS_CRITERIA, per_doc, field_counts=field)
    row, other = result['losses']
    assert (row['name'], row['section']) == ('8항 노출기준', 8)
    assert row['counts'] == {'빠뜨림': 11, '틀림': 5, '지어냄': 8}             # 3항의 칸 4개는 세지 않는다
    assert row['scorer_counts'] == {'빠뜨림': 47, '틀림': 0, '지어냄': 27}
    assert row['counts_basis'] == 'field' and row['cause'] == '빠뜨림'
    assert other['counts'] == {'빠뜨림': 0, '틀림': 0, '지어냄': 3} and other['scorer_counts'] is None
    docs = {d['doc_id']: d for d in result['top_problem']['docs']}
    assert docs['T21-X01']['counts'] == {'빠뜨림': 10, '틀림': 5, '지어냄': 8}
    assert docs['T21-X02']['counts'] == {'빠뜨림': 1, '틀림': 0, '지어냄': 0}
    assert docs['T21-X03']['counts'] is None
    assert result['top_problem']['counts'] == row['counts']
    assert info == before
    status = text.score_status(info, LOSS_CRITERIA, per_doc=per_doc, field_counts=field)
    assert {k: status[k] for k in ('losses', 'top_problem', 'loss_basis')} == result


def test_problem_loss_counts_partial_and_ties(text):
    info = loss_info(('8항 노출기준', '필수', .6, .95))
    info['items'][0].update({'틀림': 4, '지어냄': 4})
    row = text.score_losses(info, LOSS_CRITERIA)['losses'][0]
    assert row['counts'] == {'빠뜨림': 0, '틀림': 4, '지어냄': 4}
    assert row['cause'] == '틀림'


def test_problem_status_copy_contract_has_no_pass_judgement(text, score_info):
    result = text.score_status(score_info, {'pass_score': 87})
    assert {'headline', 'verdict', 'top_drops', 'next_action'} <= result.keys()
    for name in ['headline', 'next_action', 'losses', 'top_problem', 'loss_basis']:
        assert '합격' not in str(result[name])
    assert text.UI_TEXT['score']['summary']['headline_below'].format(line=87, gap='14.3') in result['headline']


def test_diff_same_conditions_copy_is_cautious_and_uses_api_flag(text, diff_info):
    diff_info["same_conditions"] = True
    phrase = text.UI_TEXT["compare"]["conditions"]["variation"]
    assert phrase in text.diff_headline(diff_info, "A", "B")["headline"]
    diff_info["same_conditions"] = False
    diff_info["docs"] = {"common": ["T21-X01"], "only_a": ["T21-X02"], "only_b": []}
    result = text.diff_headline(diff_info, "A", "B")
    assert phrase not in result["headline"]
    assert text.UI_TEXT["compare"]["different"]["title"] in result["headline"]
    assert result["same_conditions"] is False


def test_glossary_definitions_are_exact_approved_copy(text):
    import html
    for key, entry in text.UI_TEXT["glossary"].items():
        assert entry["term"] == html.unescape(approved_copy(f"glossary.{key}.term"))
        meaning = html.unescape(approved_copy(f"glossary.{key}.meaning"))
        actual = text.GLOSSARY[entry["term"]]
        assert actual["short"] + " " + actual["example"] == meaning
        assert text.explain(key) == actual["short"]


def test_copy_exceptions_do_not_keep_already_approved_text(text):
    import html
    import re
    rows = (Path(__file__).parents[1] / 'scripts/b_app_static/design/COPY.md').read_text().splitlines()
    approved = {html.unescape(row.split('|')[1]).replace('<br>', '\n') for row in rows
                if re.match(r'^[a-z][a-z0-9_.]+\|', row)}
    leaves = dict(_ui_leaves(text.UI_TEXT))
    for key, reason in text.COPY_EXCEPTIONS.items():
        assert reason.strip()
        assert leaves[key] not in approved, key


def test_run_label_human_words_follow_approved_copy(text):
    info = {"name": "manual/20261031_sections_fake_s8_v9_probe2_r2", "kind": "manual", "model_tag": "fake"}
    label = text.run_label(info)
    assert approved_copy("common.run.prompt").format(version=approved_copy("common.run.prompt_round").format(round="8")) in label["title"]
    assert approved_copy("common.run.input").format(version=approved_copy("common.run.input_round").format(round="9")) in label["title"]
    assert approved_copy("common.run.probe").format(round="2") in label["title"]
    assert label["title"].startswith(approved_copy("common.run.manual").split("{title}")[0])
    assert label["subtitle"] == info["name"]


def test_remaining_server_generated_labels_follow_copy(text, score_info):
    for tag in text.MODEL_LABELS:
        # 11/1 polish: GPT 용도 이름만 사용자 지정 예외이며 나머지 COPY 대조는 유지한다.
        expected = "GPT · AI 정답 초안" if tag == "gpt" else approved_copy(f"context.models.{tag}")
        assert text.model_label(tag) == expected
        if tag == "gpt":
            assert text.COPY_EXCEPTIONS["context.models.gpt"] == "⑤ 수락 11/1 뒤 작은 문제: 정답 초안용 모델 이름"
    for kind in text.RUN_KIND_LABELS:
        assert text.run_kind_label(kind) == approved_copy(f"jobs.kinds.{kind}")
    result = text.score_status(score_info, {"pass_score": 90})
    for row in result["top_drops"]:
        item = next(i for i in score_info["items"] if i["name"] == row["name"])
        assert row["sentence"] == approved_copy("score.summary.drop").format(
            item=row["name"], score=f'{row["score"]:.1f}', goal=f'{row["target"]:g}',
            cause=row["cause"], count=item.get(row["cause"]) or 0)


def test_api_explanations_use_same_approved_copy_as_screens(text):
    for group, prefix in [(text.SET_TEXT, 'context.set_reason'), (text.KEY_TEXT, 'context.key_reason')]:
        for key, value in group.items():
            assert value == approved_copy(f'{prefix}.{key}')
    for kind, values in text.PROBLEM_TEXT.items():
        for key in ('message', 'fix'):
            if kind == 'bad_query' and key == 'message':
                continue  # API가 준 상세 글은 바꾸지 않는다.
            assert values[key] == approved_copy(f'errors.request.{kind}.{key}')
    for group, values in text.JOURNEY_TEXT.items():
        for key, value in values.items():
            if group == 'errors':
                for field in ('message', 'fix'):
                    if key == 'bad_body' and field == 'message':
                        continue
                    assert value[field] == approved_copy(f'journey.record.errors.{key}.{field}')
            elif f'journey.record.{group}.{key}' in text.COPY_EXCEPTIONS:
                # 승인 문구 밖의 새 검사 문장(progress.guide, 10/31)은 이유와 함께 예외 목록에 있다. 화면 글과 같은지만 본다
                assert value == text.UI_TEXT['journey']['record'][group][key]
            else:
                assert value == approved_copy(f'journey.record.{group}.{key}')


def test_job_error_messages_share_screen_copy(text):
    for kind, entry in text.JOB_ERROR_TEXT.items():
        for field in ("message", "fix"):
            key = "other" if kind == "no_line" and field == "message" else kind
            assert entry[field] == approved_copy(f"errors.job.{key}.{field}")


def test_problem_rows_count_per_item_and_doc_without_touching_the_status(text):
    """문제 행 수는 항목 이름과 항으로 거른다. 손실 순서와 status_text는 그대로이고 문서별 값에 행 수만 더한다."""
    from collections import Counter
    info = loss_info(('8항 노출기준', '필수', .6, .95), ('가짜 일반', '일반', .9, .8))
    per_doc = {'T21-X01': {'items': {'8항 노출기준': .5, '가짜 일반': .9}},
               'T21-X02': {'items': {'8항 노출기준': .7, '가짜 일반': .9}},
               'T21-X03': {'items': {'8항 노출기준': .6, '가짜 일반': .9}}}
    field = {'T21-X01': Counter({('8항 노출기준', 8, 'wrong'): 5}), 'T21-X02': Counter({('8항 노출기준', 8, 'missing'): 1})}
    rows = {'T21-X01': Counter({('8항 노출기준', 8): 3, ('8항 노출기준', 3): 7, ('가짜 일반', None): 2, ('가짜 일반', 5): 1}),
            'T21-X02': Counter({('8항 노출기준', 8): 1})}                       # T21-X03은 셀 수 없었다(정답 없음)
    status = text.score_status(info, LOSS_CRITERIA, per_doc=per_doc, field_counts=field)
    before = copy.deepcopy(status)
    got = text.problem_rows(status, per_doc, field, rows)
    assert status == before
    assert list(got) == [row['name'] for row in status['losses']]               # 손실 순서 그대로
    assert got['8항 노출기준']['row_count'] == 4 and got['가짜 일반']['row_count'] == 3   # 항을 모르면 모든 항을 센다
    docs = got['8항 노출기준']['docs']
    assert {d['doc_id']: d['row_count'] for d in docs} == {'T21-X01': 3, 'T21-X02': 1, 'T21-X03': None}
    assert [{k: v for k, v in d.items() if k != 'row_count'} for d in docs] == status['top_problem']['docs']


def test_problem_rows_are_empty_when_nothing_could_be_counted(text):
    from collections import Counter
    status = text.score_status(loss_info(('8항 노출기준', '필수', .6, .95)), LOSS_CRITERIA)
    assert text.problem_rows(status, {}, {}, {}) == {}
    assert text.problem_rows({'losses': [], 'loss_basis': None}, {}, {}, {'T21-X01': Counter()}) == {}


def test_row_title_uses_labels_and_keeps_unknown_codes_as_written(text):
    title = text.row_title
    assert title('exposure_limits', {'standard': '국내', 'limit_type': 'TWA'}, {}, '가짜성분A', 0) == '가짜성분A / 국내기준 / TWA'
    assert title('exposure_limits', {'standard': 'ACGIH', 'limit_type': 'STEL'}, {}, None, 2) == '3행 / ACGIH / STEL'
    assert title('physchem', {'prop_code': 'FLASH_POINT'}, {}, '제품 전체', 0) == '제품 전체 / 인화점'
    assert title('physchem', {'prop_code': 'NEW_CODE'}, {}, '제품 전체', 0) == '제품 전체 / NEW_CODE'
    assert title('toxicity', {'endpoint': 'TX_ORAL'}, {'descriptor': 'LD50'}, '가짜성분B', 0) == '가짜성분B / 급성 독성(경구) / LD50'
    assert title('toxicity', {}, {'endpoint': 'TX_ORAL'}, None, 4, gold_only=True) == '정답 5행 / 급성 독성(경구)'
    assert title('regulations', {'law': 'OSH', 'item_raw': '가짜 대상', 'item_code': 'OSH_MEASURE'}, {}, '제품 전체', 0) \
        == '제품 전체 / 산업안전보건법 / 가짜 대상'
    assert title('regulations', {'law': 'OSH', 'item_code': 'OSH_MEASURE'}, {}, '제품 전체', 0) \
        == '제품 전체 / 산업안전보건법 / OSH_MEASURE'
    assert title('hazard.classes', {'raw': '가짜 분류 : 구분 2', 'class_code': 'HH_X'}, {}, None, 0) == '가짜 분류 : 구분 2'
    assert title('transport', {'mode': '해상'}, {}, None, 0) == '해상'
    assert title('hazard.h_statements', {}, {}, None, 1) == '2행'                # 구분 값이 없으면 행 번호
    assert title('없는표', {'x': 1}, {}, None, 0) == '1행'


def test_value_title_names_the_field_or_falls_back_to_the_table(text):
    assert text.value_title('hazard', 'signal_word') == '신호어'
    assert text.value_title('meta', 'msds_no') == '제출번호'
    assert text.value_title('hazard', 'nfpa.fire') == 'NFPA 화재 위험'
    assert text.value_title('product', 'name') == '제품명'
    assert text.value_title('meta', '새칸') == '관리정보'
    assert text.value_title('없는표', '새칸') == '없는표'


def test_row_labels_cover_the_schema_codes(text):
    from msds.common.schema import msds_item_schema
    from msds.extract.expand import _resolve
    props = msds_item_schema()['properties']
    def codes(table, column):
        node = _resolve(props[table]['items'])['properties'][column]
        return set(next(b for b in node['anyOf'] if b.get('type') == 'string')['enum'])
    labels = text.UI_TEXT['source']['row_parts']
    assert codes('physchem', 'prop_code') == set(labels['prop_code'])
    assert codes('toxicity', 'endpoint') == codes('ecotox', 'endpoint') == set(labels['endpoint'])
    assert codes('regulations', 'law') == set(labels['law'])
    assert set(labels['agency']) <= codes('cmr', 'agency')
    assert set(labels['standard']) <= codes('exposure_limits', 'standard')
    assert set(labels['system']) <= codes('intl_class', 'system')


def test_every_row_field_of_the_schema_has_a_plain_name(text):
    # 값 칸의 이름이 표 이름으로 대체되면 같은 이름이 여러 칸에 겹친다. 예: 12번 부분의 세 칸이 모두 '환경에 미치는 영향'.
    from msds.common.schema import msds_item_schema
    schema = msds_item_schema()
    defs = schema.get("$defs", {})

    def resolve(node):
        while True:
            if "$ref" in node:
                node = defs.get(node["$ref"].split("/")[-1], {})
            elif "anyOf" in node:
                rest = [x for x in node["anyOf"] if x.get("type") != "null"]
                if len(rest) != 1:
                    return node
                node = rest[0]
            else:
                return node

    source = text.UI_TEXT["source"]
    missing = []
    for table in ("exposure_limits", "physchem", "toxicity", "cmr", "ecotox", "regulations", "components", "companies",
                  "transport", "dangerous_goods", "waste", "intl_class", "extras", "narratives"):
        node = resolve(schema["properties"][table])
        node = resolve(node["items"]) if node.get("type") == "array" else node
        for field in node["properties"]:
            if not any(field in names for names in (text.VALUE_FIELD_LABELS, source["field_names"], source["fields"])):
                missing.append((table, field))
    assert missing == []


def _copy_rows_any_key(text):
    """COPY.md의 `키|글|쓰는 곳` 행. 키에 한글·대문자가 들어가는 행(코드 이름표)도 읽는다."""
    import html
    leaves = dict(_ui_leaves(text.UI_TEXT))
    rows = {}
    for row in (Path(__file__).parents[1] / 'scripts/b_app_static/design/COPY.md').read_text().splitlines():
        if '|' in row and row.split('|')[0] in leaves:
            rows[row.split('|')[0]] = html.unescape(row.split('|')[1]).replace('<br>', '\n')
    return leaves, rows


def test_every_ui_text_key_has_its_own_copy_row_with_the_same_text(text):
    leaves, rows = _copy_rows_any_key(text)
    missing = [key for key in leaves if key not in rows and key not in text.COPY_EXCEPTIONS]
    assert not missing, (len(missing), missing[:20])
    different = [key for key in leaves if key in rows and key not in text.COPY_EXCEPTIONS and rows[key] != leaves[key]]
    assert not different, different[:20]


# 옛 관문에서 이유와 함께 승인한 예외의 수. 이번 phase는 예외를 늘리지 않는다.
OLD_COPY_EXCEPTIONS = 729


def test_this_phase_left_no_copy_exception(text):
    new_groups = ('steps.', 'source.rows.', 'source.row_parts.', 'source.value_titles.', 'nav.group_',
                  'swap.context.', 'guide.ai.steps', 'guide.ai.return_order', 'guide.trial.steps_note', 'guide.source.image_note',
                  'help.source.step_', 'help.servers.step_', 'help.servers.order', 'common.run.prompt_round', 'common.run.input_', 'common.run.dev_docs')
    assert not [key for key in text.COPY_EXCEPTIONS if key.startswith(new_groups)]
    assert len(text.COPY_EXCEPTIONS) <= OLD_COPY_EXCEPTIONS


def _approval_rows():
    source = (Path(__file__).parents[1] / 'scripts/b_app_static/design/STEPS.md').read_text()
    section = source.split('## 12. 문구 승인표', 1)[1].split('\n## ', 1)[0]
    import html
    rows = {}
    for line in section.splitlines():
        match = re.match(r'^\| `([^`]+)` \| (.*?) \| (.*?) \| (.*?) \|$', line)
        if match:
            rows[match[1]] = {'before': match[2], 'after': html.unescape(match[3]).replace('<br>', '\n').replace('\\|', '|'), 'where': match[4]}
    return rows


def test_approval_table_shows_the_current_text_for_every_key_of_this_phase(text):
    rows = _approval_rows()
    leaves = dict(_ui_leaves(text.UI_TEXT))
    assert rows
    for key in leaves:
        if key.startswith(('steps.', 'source.row_parts.', 'source.value_titles.')):
            assert key in rows, key
    for key, row in rows.items():
        if row['after'] == '(지움)':
            assert key not in leaves, key
        else:
            assert leaves[key] == row['after'], key
        assert row['where'].strip(), key
    for key in ('guide.source.image_note', 'guide.ai.steps', 'help.source.kinds', 'help.servers.order', 'glossary.twa.term',
                'context.model.wrong_reply', 'compare.values.expand', 'jobs.form.focus_line', 'journey.trial.parse_todo'):
        assert key in rows, key


@pytest.mark.parametrize('name,gone', [
    ('20261101_sections_qwen36_35b_runpod_s9_v17_dev3_r1', ('s9', 'v17', 'version17', 'dev3')),
    ('20261102_sections_qwen36_35b_runpod_s10h_v17_dev10_r2', ('s10h', 'v17', 'dev10')),
])
def test_run_title_has_plain_names_and_keeps_the_folder_name_as_subtitle(text, name, gone):
    label = text.run_label({'name': name, 'model_tag': 'qwen36_35b_runpod'})
    assert label['subtitle'] == name
    words = re.split(r'[\s·]+', label['title'])
    for word in gone:
        assert word not in words, (word, label['title'])
    assert '번째 판' in label['title']
    assert '판' in label['title'].split('원문 자료')[1]
    assert '개발 ' in label['title']


def test_run_title_keeps_a_token_it_does_not_know_and_does_not_guess(text):
    label = text.run_label({'name': '20261101_sections_mystery7', 'model_tag': ''})
    assert 'mystery7' in label['title']
    assert text.UI_TEXT['common']['run']['input'].format(version=text.UI_TEXT['common']['run']['input_temp']) in text.run_label({'name': '20261101_sections_x_chars_wrap'})['title']
    assert text.UI_TEXT['common']['run']['input_new'] in text.run_label({'name': '20261101_sections_x', 'pages_dir': 'data/pages'})['title']


def test_ui_text_has_no_internal_set_names_or_model_reply_jargon(text):
    for key, value in _ui_leaves(text.UI_TEXT):
        assert 'prev/version' not in value, key
        assert '다른 모델 응답' not in value, key


def test_no_text_repeats_an_action_word(text):
    action = r'(펼치기|접기|보기|닫기|열기|고르기|바꾸기)'
    for key, value in _ui_leaves(text.UI_TEXT):
        assert not re.search(action + r'\s+\1', value), (key, value)


def test_run_title_does_not_repeat_the_short_model_name_of_the_folder(text):
    # 폴더 이름의 qwen36은 이미 앞에 쓴 모델 이름이다. 뜻을 모르는 조각은 그대로 둔다.
    info = {"name": "20261101_sections_qwen36_s9_v17_dev10_r1", "model_tag": "qwen36_35b_runpod",
            "prompt_version": "s9", "pages_dir": "data/pages/version17"}
    assert "qwen36" not in text.run_label(info)["parts"]
    assert text.run_label(info)["title"].startswith("11/1 Qwen3.6 35B")
    assert "qwen" in text.run_label({**info, "model_tag": "other_tag"})["title"]
