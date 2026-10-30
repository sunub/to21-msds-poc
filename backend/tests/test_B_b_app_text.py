"""표시 이름 규칙 시험. 실제 실행의 이름만 쓰며 문서 내용이나 서버는 읽지 않는다."""
import copy
import importlib

import pytest

from test_B_compare_models import SCRIPTS


@pytest.fixture
def text(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    return importlib.import_module("b_app_text")


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
    for phrase in ("72.7점", "90점", "17/17", "17.3점", "필수 12개"):
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
    assert "2/2" in good["headline"]
    assert good["top_drops"] == []
    assert good["next_action"] == "합격 기준을 넘었습니다. ② 두 실행 비교로 흔들림을 확인하세요."
    missing = text.score_status({"weighted": None}, c)
    assert missing["verdict"] == "none"
    assert missing["headline"] == "점수가 없는 실행입니다."
    assert missing["top_drops"] == [] and "합격" not in missing["next_action"]
    failed = text.score_status({"weighted": 93, "must_passed": 1}, c)
    assert failed["verdict"] == "fail" and "필수 1개" in failed["headline"]
    assert "-3" not in failed["headline"] and "합격 기준을 넘었습니다" not in failed["next_action"]


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


def test_friendly_server_ui_copy(text):
    copy = text.server_ui_text()
    assert copy["guide"]["advanced_off"] == "고급을 켜고 서버 탭에서 모델을 올리세요"
    assert copy["guide"]["advanced_on"] == "서버 탭에서 모델을 올리세요"
    assert copy["action_failure"]["message"] == "서버 변경을 끝내지 못했습니다."
    assert copy["action_failure"]["fix"]
    assert copy["busy"] and copy["unavailable"]
