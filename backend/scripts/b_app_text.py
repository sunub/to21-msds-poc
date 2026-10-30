"""작업 화면의 표시 이름 (역할 B, 개발 전용, ADR-027).

파일이나 서버를 읽지 않는 순수 함수다. 실행 정보가 이름보다 우선하며,
모르는 조건은 그대로 남겨 표시 이름에서 실행 조건을 잃지 않는다.
"""
import re
from datetime import datetime
from math import isfinite
from pathlib import PurePosixPath


START_TEXT: dict = {
    "intro": [
        "안전보건자료(MSDS)에서 정보를 뽑는 모델의 결과를 점수로 봅니다.",
        "틀린 값을 원문과 맞춰 봅니다.",
        "고칠 항 하나만 다시 시험할 수 있습니다.",
    ],
    "steps": [
        {"no": 1, "title": "점수를 먼저 봅니다.",
         "why": "어느 항목이 깎였는지 알아야 고칠 곳을 정할 수 있어요.",
         "button": "최근 실행 점수 보기", "tab": "score"},
        {"no": 2, "title": "깎인 항목을 고릅니다.",
         "why": "지금 상태 카드에서 ‘원문 대조로 →’를 누르면 그 항목으로 이동해요.",
         "button": "깎인 항목 고르기", "tab": "score"},
        {"no": 3, "title": "틀린 값의 원문을 확인합니다.",
         "why": "오른쪽에서 실버와 다른 값을 누르면 왼쪽 근거 줄이 노랗게 켜져요.",
         "button": "원문에서 값 고르기", "tab": "doc"},
    ],
    "later": [
        {"title": "두 실행 비교", "line": "바꾼 뒤 점수가 나아졌는지 확인합니다.",
         "button": "두 실행 비교하기", "tab": "diff"},
        {"title": "항 하나 시험", "line": "고칠 항 하나만 모델에 다시 보냅니다.",
         "button": "시험 준비하기", "tab": "jobs"},
        {"title": "서버 올리기(고급)", "line": "모델을 새로 부를 때 준비합니다.",
         "button": "고급 켜고 서버 보기", "tab": "servers"},
    ],
    "empty_runs": "runs/에 실행이 없습니다. 터미널에서 run_sections.py를 돌리거나 ④ 작업 탭을 보세요.",
    "no_drops": "합격 기준을 넘었습니다. ② 두 실행 비교에서 이전 실행과 비교해 보세요.",
    "no_line": "이 값은 원문 줄을 못 찾았습니다. 다른 값을 눌러 보세요.",
    "heading": "지금 할 일",
    "later_title": "다음에 할 수 있는 것",
    "offline": "모델 서버 없이 저장된 실제 실행 결과로 시작할 수 있습니다.",
    "loading": "실행 목록을 불러오는 중입니다.",
    "unscored": "아직 점수를 낸 실행이 없습니다. ① 점수판에서 실행 상태를 보세요.",
    "no_candidates": "원문으로 연결할 미달 항목이 없습니다. ① 점수판에서 전체 항목을 보세요.",
    "resume": "지금 상태 카드에서 원문으로 볼 항목을 다시 골라 주세요.",
    "success": "틀린 값의 원문 줄을 확인했습니다. 첫 안내를 마쳤습니다.",
    "done": "✓ 끝남", "current": "현재 단계", "skipped": "건너뜀",
    "dismiss": "이 안내 닫기", "replay": "처음부터 다시 보기",
    "compare_button": "두 실행 비교하기",
}


FIELD_HELP: dict[str, str] = {
    "model": "문서에서 값을 뽑을 모델입니다. 연결된 모델부터 보여 줍니다.",
    "doc": "시험할 개발용 문서입니다. 평가용 문서는 고를 수 없습니다.",
    "pages": "전처리한 쪽 글자가 있는 폴더입니다. 현재 실행 입력은 version9입니다.",
    "scope": "시험할 항을 고릅니다. 문서 전체는 16개 항을 보냅니다.",
    "prompt": "모델에게 줄 지시문입니다. 항을 하나만 고르면 고쳐 쓸 수 있습니다.",
    "base_run": "시험한 항의 답을 끼워 넣을 기준 실행입니다. 자동이면 같은 모델의 가장 최근 개발 10건 실행을 씁니다.",
    "dry_run": "서버를 부르지 않고 입력과 안내문 정보를 확인합니다.",
    "repeat": "같은 조건으로 실행할 횟수입니다. 1~10회로 정합니다.",
    "run_name": "결과를 모아 둘 폴더 이름입니다. 회차마다 _r1, _r2가 붙습니다.",
    "compare_label": "비교표에서 실행을 부를 이름입니다. 비우면 실행 이름을 씁니다.",
}

# 도움말 5장의 여섯 단계와 같은 설명이다.
TRY_STAGE_HELP: dict[str, str] = {
    "① 보낸 입력": "모델에게 준 줄 글자. 줄 번호(p2:L23 모양)가 앞에 붙어 있습니다.",
    "② 안내문": "모델에게 준 지시문. 화면에만 보이고 파일로 저장하지 않습니다.",
    "③ 모델 원문 답": "모델이 쓴 글 그대로입니다.",
    "④ 읽은 결과": "원문 답을 중간 형식으로 바꾼 것. 행 형식에서 버린 줄 수도 나옵니다.",
    "⑤ 펼친 TO21 칸": "중간 형식을 최종 JSON 칸으로 펼친 것입니다.",
    "⑥ 점수 전 → 후": "기준 실행의 해당 항 답을 새 답으로 바꿔 끼워 다시 채점한 점수입니다.",
}

JOB_UI_TEXT = {
    "send": "모델에 보내기",
    "preview": "입력·안내문 보기",
    "run_unavailable": "연결된 모델을 고르면 본 실행을 시작할 수 있습니다.",
    "more_summary": "본 실행과 비교표 만들기는 여기서 펼칩니다.",
}


def order_models(models: list[dict]) -> list[dict]:
    """같은 연결 상태의 순서는 유지하고, 원래 모델 정보에 선택지 글만 더한다."""
    rank = {True: 0, None: 1, False: 2}
    labels = {True: "연결됨", None: "연결 모름", False: "연결 안 됨"}
    return [{**m, "option_label": f"{m['label']} — {labels[m.get('connected')]}"}
            for m in sorted(models, key=lambda m: rank[m.get("connected")])]


def try_hint(models: list[dict], advanced: bool) -> dict:
    """연결을 확인한 모델이 없으면 서버 없는 시험만 안내한다."""
    count = sum(m.get("connected") is True for m in models)
    guide = "" if advanced else "고급을 켜고 "
    note = (f"연결된 모델 {count}개. 모델을 고르고 돌리기를 누르세요." if count else
            "연결된 모델이 없어 서버 없이 입력·안내문만 봅니다(dry-run). "
            f"모델을 쓰려면 {guide}서버 탭에서 먼저 올리세요.")
    return {"dry_run_forced": not count, "note": note}


# 용어만 맡는다. 채점 항목 23개의 설명은 b_app_runs.ITEM_HELP에 둔다.
# 예의 근거: guide.html 9장, b_app_runs.criteria/limit_kind, models.yaml,
# section_prompts.SECTION_PROMPT_VERSION, try_section의 옵션, app.js의 표시·조작.
# 문서 내용이나 실행 점수는 넣지 않는다.
GLOSSARY: dict[str, dict] = {
    "실버": {
        "short": "Claude가 만든 정답 초안으로, 틀린 곳이 있을 수 있습니다.",
        "example": "비교표는 data/silver/claude의 파일을 정답 자리에 놓습니다.",
        "also": ["정답 초안", "정답 초안(실버)", "silver"],
    },
    "골드": {
        "short": "사람이 내용을 확인한 정답입니다.",
        "example": "도움말의 ‘정답(골드)’는 Claude가 만든 초안과 구분됩니다.",
        "also": ["정답(골드)", "gold"],
    },
    "가중 종합": {
        "short": "각 항목 점수에 중요도별 무게를 곱해 평균 낸 점수입니다.",
        "example": "무게는 필수 3, 중요 2, 일반 1입니다.",
        "also": ["가중 종합 점수", "weighted"],
    },
    "필수 통과": {
        "short": "필수 항목 중 각자의 목표 점수 이상인 항목 수입니다.",
        "example": "17/17은 필수 17개가 모두 목표 이상이라는 표시입니다.",
        "also": ["must_passed"],
    },
    "필수": {
        "short": "합격하려면 빠짐없이 목표를 충족해야 하는 등급입니다.",
        "example": "신호어는 필수 등급이며 점수 무게는 3입니다.",
        "also": ["필수 등급"],
    },
    "중요": {
        "short": "가중 종합에서 일반 항목보다 무게가 큰 등급입니다.",
        "example": "중요 등급의 점수 무게는 2입니다.",
        "also": ["중요 등급"],
    },
    "일반": {
        "short": "가중 종합에서 점수 무게가 가장 작은 등급입니다.",
        "example": "일반 등급의 점수 무게는 1입니다.",
        "also": ["일반 등급"],
    },
    "항": {
        "short": "안전보건자료를 나눈 법정 16개 구역 중 하나입니다.",
        "example": "3항은 구성성분, 14항은 운송에 관한 구역입니다.",
        "also": ["법정 항"],
    },
    "항목": {
        "short": "점수판에서 각각 점수를 매기는 검사 단위입니다.",
        "example": "점수판은 그림문자와 H 코드 등을 23개 항목으로 채점합니다.",
        "also": ["채점 항목"],
    },
    "안내문": {
        "short": "어떤 값을 어떻게 뽑을지 모델에게 알려 주는 지시문입니다.",
        "example": "작업 탭의 ‘고쳐 쓰기’는 항 하나의 안내문을 바꿔 시험합니다.",
        "also": ["프롬프트", "prompt"],
    },
    "안내문 버전": {
        "short": "안내문 내용이 바뀐 판을 구분하는 번호입니다.",
        "example": "s7은 16항 관리정보와 결과 칸의 대응을 더한 판입니다.",
        "also": ["prompt_version"],
    },
    "입력 판": {
        "short": "모델에게 보낼 쪽 글자 묶음을 구분하는 판입니다.",
        "example": "version9는 줄 앞에 L001처럼 번호를 붙이고 표 칸을 |로 나눕니다.",
        "also": ["입력판", "쪽 폴더", "쪽 글자 폴더"],
    },
    "쪽 글자": {
        "short": "PDF의 각 쪽에서 읽어 모델 입력으로 쓰는 글입니다.",
        "example": "원문 대조의 왼쪽에서 쪽 그림과 쪽 글자를 함께 봅니다.",
        "also": ["쪽 텍스트"],
    },
    "줄 번호": {
        "short": "결과 값의 근거가 원문 몇 쪽의 어느 줄인지 가리키는 표시입니다.",
        "example": "p2:L23은 2쪽의 23번 줄을 가리킵니다.",
        "also": ["근거 줄 번호"],
    },
    "기준 실행": {
        "short": "새로 뽑은 항의 답을 끼워 넣어 점수 변화를 볼 기존 실행입니다.",
        "example": "시험 결과의 ‘전’은 기준 실행, ‘후’는 새 답을 끼운 점수입니다.",
        "also": ["base_run"],
    },
    "dry-run": {
        "short": "모델 서버를 부르지 않고 입력과 안내문만 확인하는 방식입니다.",
        "example": "--dry-run은 ‘① 보낸 입력’과 ‘② 안내문’까지만 보여 줍니다.",
        "also": ["서버 없이 확인"],
    },
    "시험": {
        "short": "항 하나나 문서 하나를 다시 뽑아 변경 효과를 확인하는 작업입니다.",
        "example": "작업 탭의 ‘시험하기’는 처음에 11항이 선택되어 있습니다.",
        "also": ["수동 시험"],
    },
    "본 실행": {
        "short": "고른 개발용 문서들을 정한 횟수만큼 모두 추출하는 작업입니다.",
        "example": "작업 탭의 본 실행은 기본 반복 횟수가 2회입니다.",
        "also": ["전체 실행"],
    },
    "비교표": {
        "short": "여러 실행의 점수와 시간을 같은 기준으로 모은 표입니다.",
        "example": "작업 탭에서 만든 비교표의 파일 이름은 compare.md입니다.",
        "also": ["compare.md"],
    },
    "빠뜨림": {
        "short": "정답에는 있지만 추출 결과에는 없는 값입니다.",
        "example": "항목 신호등의 ‘빠뜨림’ 수를 보고 줄을 누르면 해당 값 목록이 열립니다.",
        "also": ["누락"],
    },
    "지어냄": {
        "short": "추출 결과에는 있지만 비교 기준인 정답에는 없는 값입니다.",
        "example": "항목 신호등의 ‘지어냄’은 ‘결과에는 있는데 정답에 없음’으로 표시합니다.",
        "also": ["과추출"],
    },
    "틀림": {
        "short": "정답과 추출 결과 양쪽에 있으나 내용이 다른 값입니다.",
        "example": "항목 신호등의 ‘틀림’은 ‘둘 다 있지만 값이 다름’으로 표시합니다.",
        "also": ["값 불일치"],
    },
    "값 없는 행": {
        "short": "자료없음이나 해당없음처럼 실제 값 대신 상태만 적힌 행입니다.",
        "example": "‘값 없는 행을 뺀 점수’는 자료없음·해당없음·비해당·미기재 행을 양쪽에서 뺍니다.",
        "also": ["무값 행"],
    },
    "호출 격자": {
        "short": "문서와 항별로 모델 요청의 상태를 보여 주는 표입니다.",
        "example": "호출 격자의 열은 1항부터 16항까지입니다.",
        "also": [],
    },
    "재추출": {
        "short": "검사에 걸린 항에 문제 설명을 붙여 한 번 더 뽑는 작업입니다.",
        "example": "둘째 답이 첫째 답보다 나을 때만 둘째 답을 채택합니다.",
        "also": ["다시 추출"],
    },
    "출력 한도": {
        "short": "모델이 한 번의 요청에서 답할 수 있는 최대 길이입니다.",
        "example": "Qwen3.6 설정은 일반 답 8,192토큰, 행 형식 답 16,384토큰까지 받습니다.",
        "also": ["한도 걸림", "출력 길이 한도"],
    },
    "공백폭주": {
        "short": "답 대신 공백이 길게 이어져 출력 한도를 소모한 상태입니다.",
        "example": "한도에 걸린 답의 공백 비율이 50%를 넘으면 공백폭주로 분류합니다.",
        "also": ["공백 폭주"],
    },
    "반복": {
        "short": "모델이 같은 글을 계속 되풀이하다 출력 한도에 걸린 상태입니다.",
        "example": "답 끝에서 20자 이상인 같은 글이 4번 이상 이어지면 반복으로 분류합니다.",
        "also": ["반복 출력"],
    },
    "모델 태그": {
        "short": "모델과 호출 설정을 고르는 짧은 식별 이름입니다.",
        "example": "qwen36_35b_runpod는 Qwen3.6의 RunPod 설정을 고르는 태그입니다.",
        "also": ["model_tag"],
    },
    "RunPod": {
        "short": "모델을 띄울 장비를 시간당 요금을 내고 빌리는 서비스입니다.",
        "example": "서버 탭의 RunPod 카드에서 ‘Pod 만들기(Qwen3.6)’를 고릅니다.",
        "also": [],
    },
    "RNGD": {
        "short": "이 프로젝트에서 모델을 띄우는 사내 연산 장비입니다.",
        "example": "서버 탭의 RNGD 카드는 장비 카드 4장을 안내합니다.",
        "also": ["사내 장비"],
    },
    "Pod": {
        "short": "RunPod에서 만들어 모델을 실행하는 서버 한 대입니다.",
        "example": "이 도구가 만든 Pod의 이름은 to21-b-로 시작합니다.",
        "also": ["팟"],
    },
    "회차": {
        "short": "같은 조건의 실행을 몇 번째로 돌렸는지 나타내는 번호입니다.",
        "example": "실행 이름 끝의 r2는 2회차를 뜻합니다.",
        "also": [],
    },
    "extras": {
        "short": "정해진 결과 칸에 들어가지 않아 따로 모은 남는 값입니다.",
        "example": "점수판의 ‘표 행 수’는 남는 값 extras의 행 수도 셉니다.",
        "also": ["남는 값", "extras(남는 값)"],
    },
    "실버 빈 곳": {
        "short": "정답 초안 자체에 빠졌거나 확인이 필요한 부분을 적어 둔 메모입니다.",
        "example": "항목 신호등의 노란 점에 실버 빈 곳의 메모와 출처가 나옵니다.",
        "also": [],
    },
    "동시 호출": {
        "short": "여러 항의 모델 요청을 한꺼번에 보내는 방식입니다.",
        "example": "Qwen3.6 설정의 concurrency: 16은 최대 16개 요청을 함께 보냅니다.",
        "also": ["동시 요청", "동시 수", "concurrency"],
    },
    "행 형식": {
        "short": "모델이 표의 값들을 정해진 열 순서로 한 줄에 한 행씩 쓰는 방식입니다.",
        "example": "3·8·9·11·12·14·15항은 행 형식으로 받는 표 항목입니다.",
        "also": [],
    },
    "흔들림": {
        "short": "같은 조건으로 여러 번 실행했을 때 결과 점수가 달라지는 현상입니다.",
        "example": "본 실행의 r1과 r2는 같은 조건의 회차별 결과를 비교하는 데 씁니다.",
        "also": [],
    },
}


def glossary_entries() -> list[dict]:
    """가나다 순의 사전 사본. 화면과 도움말이 같은 API를 쓴다."""
    return [{"term": term, **entry, "also": list(entry["also"])}
            for term, entry in sorted(GLOSSARY.items())]


def explain(term: str) -> str | None:
    """용어 또는 같은 뜻의 표기에 해당하는 쉬운 설명을 돌려준다."""
    for name, entry in GLOSSARY.items():
        if term == name or term in entry["also"]:
            return entry["short"]
    return None


_SCORE_WEIGHTS = {"필수": 3, "중요": 2, "일반": 1}
_ROW_LABELS = {
    "components": "성분 (3항)", "exposure_limits": "노출기준 (8항)", "physchem": "물리·화학 성질 (9항)",
    "toxicity": "독성 (11항)", "cmr": "발암성 등 CMR (11항)", "ecotox": "생태 독성 (12항)",
    "regulations": "규제 (15항)", "intl_class": "국제 분류 (15항)", "extras": "남는 값 extras (자리가 없는 값)",
}


def _number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)


def diff_headline(diff: dict, label_a: str, label_b: str) -> dict:
    """B − A 점수 차를 요약한다. 변화 크기가 같으면 내려간 항목을 먼저 고른다."""
    changed = [c["what"] for c in diff.get("conditions", []) if c.get("changed")]
    if diff.get("prompt_changed_sections"):
        changed.append("안내문 글")
    same = not changed
    items = [i for i in diff.get("items", []) if _number(i.get("delta"))]
    if not items:
        return {"headline": "비교할 항목이 없습니다.", "biggest": None, "same_conditions": same}
    item = max(items, key=lambda i: (abs(i["delta"]), i["delta"] < 0))
    biggest = {"name": item["name"], "delta": item["delta"]}
    delta = (diff.get("weighted") or {}).get("delta")
    labels = f"B({label_b})와 A({label_a})"
    if not _number(delta):
        headline = f"{labels}의 종합 점수를 비교할 수 없습니다."
    elif delta == 0:
        headline = f"{labels}의 종합 점수가 같습니다."
    else:
        direction = "내려갔습니다" if delta < 0 else "올랐습니다"
        headline = f"B({label_b})가 A({label_a})보다 {abs(delta):.1f}점 {direction}."
    if item["delta"]:
        sign = "−" if item["delta"] < 0 else "+"
        headline += f" 가장 큰 변화 항목은 {item['name']}({sign}{abs(item['delta']):.1f}점)입니다."
    headline += (" 조건(모델·안내문·입력 판·동시 호출·코드 커밋)은 모두 같습니다." if same
                 else f" 조건이 다릅니다: {', '.join(changed)}.")
    return {"headline": headline, "biggest": biggest, "same_conditions": same}


def diff_ui_text(diff: dict) -> dict:
    """표시 범위와 원인 후보의 안내. 원인 판정은 b_app_diff에 그대로 둔다."""
    hidden = sum(not _number(i.get("delta")) or i["delta"] >= 0 for i in diff.get("items", []))
    return {"hidden": f"내려가지 않았거나 점수가 없는 항목 {hidden}개 숨김",
            "empty": "내려간 항목이 없습니다. 모두 보기에서 전체 항목을 볼 수 있습니다.",
            "candidate": "후보입니다. 확정은 ③ 원문 대조에서 눈으로 합니다."}


def doc_legend() -> list[dict]:
    """app.css의 기존 원문 대조 색을 그대로 쓴다."""
    return [{"key": key, "label": label, "color": color} for key, label, color in [
        ("same", "실버와 같음", "#8c959f"),
        ("diff", "실버와 다르거나 실버에 없음", "#bc4c00"),
        ("silver_only", "실버에만 있음(결과가 빠뜨림)", "#cf222e"),
        ("picked", "고른 값·줄", "#fff8c5"),
    ]]


def doc_ui_text(view: dict) -> dict:
    """원문 대조 사용법과 항별 값 수를 설명한다. 빠뜨린 칸은 결과 수와 따로 센다."""
    counts = {}
    for only, values in [(False, view.get("values", [])), (True, view.get("silver_only", []))]:
        for value in values:
            key = str(value["section"]) if value.get("section") is not None else "?"
            count = counts.setdefault(key, [0, 0, 0])
            if only:
                count[2] += 1
            else:
                count[0] += 1
                count[1] += not value.get("silver", {}).get("same", False)
    return {"howto": "오른쪽에서 값을 누르면 왼쪽 원문 줄이 노랗게 켜집니다. "
                     "줄을 누르면 그 줄을 근거로 쓴 값이 켜집니다.",
            "sections": {key: f"값 {total}개 중 실버와 다른 것 {different}개, 결과가 빠뜨린 것 {missing}개"
                         for key, (total, different, missing) in counts.items()}}


def _item_section(item: dict, criteria: dict) -> int | None:
    """항목 이름 또는 ITEM_HELP에서 온 설명에 적힌 항만 쓴다. 추측하지 않는다."""
    match = re.match(r"^(1[0-6]|[1-9])항", item["name"])
    if not match:
        help_text = next((i.get("help", "") for i in criteria.get("items", []) if i.get("name") == item["name"]), "")
        match = re.search(r"(?<!\d)(1[0-6]|[1-9])항", help_text)
    return int(match[1]) if match else None


def score_status(info: dict, criteria: dict, *, connected: bool | None = None) -> dict:
    """채점 값은 그대로 두고 100점 단위의 요약과 확인 순서를 만든다."""
    weighted = info.get("weighted")
    if not _number(weighted):
        return {"headline": "점수가 없는 실행입니다.", "verdict": "none", "top_drops": [],
                "next_action": "실행에 채점할 결과와 정답 초안(실버)이 있는지 확인하세요."}
    target = criteria["pass_score"]
    must_total = info.get("must_total")
    if must_total is None:
        must_total = sum(i.get("level") == "필수" for i in criteria.get("items", []))
    must_passed = info.get("must_passed") or 0
    missing = max(0, must_total - must_passed)
    passed = weighted >= target and missing == 0
    headline = f"{weighted:.1f}점입니다. 합격 기준은 가중 종합 {target:g}점과 필수 {must_total}/{must_total}입니다."
    if passed:
        headline += " 합격 기준을 넘었습니다."
    else:
        if weighted < target:
            headline += f" 점수는 {target - weighted:.1f}점 부족합니다."
        headline += f" 필수 {missing}개가 목표 아래입니다."

    drops = []
    for item in info.get("items", []):
        if item.get("pass") is not False or not all(_number(item.get(k)) for k in ("score", "target")):
            continue
        # max는 같은 수일 때 앞의 값을 택한다: 빠뜨림 > 틀림 > 지어냄.
        cause = max(("빠뜨림", "틀림", "지어냄"), key=lambda k: item.get(k) or 0)
        score, goal = item["score"] * 100, item["target"] * 100
        drops.append({"name": item["name"], "score": score, "target": goal,
                      "gap": round(goal - score, 10), "weight": _SCORE_WEIGHTS[item["level"]], "cause": cause,
                      "section": _item_section(item, criteria),
                      "sentence": f"{item['name']} {score:.1f}점(목표 {goal:g}). 주원인은 {cause} {item.get(cause) or 0}개입니다."})
    drops.sort(key=lambda d: d["gap"] * d["weight"], reverse=True)
    drops = drops[:3]
    if drops:
        top = drops[0]
        next_action = (f"④ 작업 탭에서 {top['section']}항만 다시 시험해 보세요."
                       if connected is True and top["section"] is not None else
                       f"③ 원문 대조에서 {top['name']}의 틀린 값이 원문 어디서 왔는지 확인하세요.")
    elif passed:
        next_action = "합격 기준을 넘었습니다. ② 두 실행 비교로 흔들림을 확인하세요."
    else:
        next_action = "항목 신호등에서 모두 보기를 눌러 점수와 목표를 확인하세요."
    return {"headline": headline, "verdict": "pass" if passed else "fail", "top_drops": drops,
            "next_action": next_action}


def card_summary(kind: str, info: dict) -> str:
    """접힌 카드의 요약. 격자는 화면과 같이 실패 > 한도 > 재추출 > 성공으로 한 번씩 센다."""
    if kind == "history":
        runs = [r for r in info.get("runs", [])
                if r.get("kind", "run") == "run" and not r.get("error") and _number(r.get("weighted"))]
        if runs:
            best = max(runs, key=lambda r: r["weighted"])
            title = (best.get("label") or {}).get("title") or best.get("name", "")
            return f"실행 {len(runs)}개, 최고 {best['weighted']:.1f}점({title})"
    elif kind == "docs":
        docs = info.get("per_doc") or {}
        scored = [(d, p["weighted"]) for d, p in docs.items() if _number(p.get("weighted"))]
        timed = [(d, p["seconds"]) for d, p in docs.items() if _number(p.get("seconds"))]
        if docs and (scored or timed):
            low = min(scored, key=lambda x: x[1]) if scored else None
            slow = max(timed, key=lambda x: x[1]) if timed else None
            score_text = f"가장 낮은 {low[0]} {low[1]:.1f}점" if low else "점수 자료 없음"
            time_text = f"가장 오래 걸린 {slow[0]} {slow[1]:.0f}초" if slow else "시간 자료 없음"
            return f"문서 {len(docs)}건, {score_text}, {time_text}"
    elif kind == "grid":
        cells = [c for cells in (info.get("grid") or {}).values() for c in cells.values() if c]
        if cells:
            counts = {k: 0 for k in ("성공", "재추출", "한도 걸림", "실패")}
            for c in cells:
                key = "실패" if not c.get("ok") else "한도 걸림" if c.get("limit_kind") else "재추출" if c.get("reextracted") else "성공"
                counts[key] += 1
            return f"호출 {len(cells)}개 중 " + ", ".join(f"{k} {v}" for k, v in counts.items())
    elif kind == "rows":
        rows = {k: v for k, v in (info.get("rows") or {}).items()
                if k in _ROW_LABELS and all(_number(v.get(f)) for f in ("pred", "gold"))}
        if rows and (info.get("docs") or any(v["pred"] or v["gold"] for v in rows.values())):
            short = [(k, v) for k, v in rows.items() if v["pred"] < v["gold"]]
            result = f"표 {len(rows)}개 중 정답보다 적은 표 {len(short)}개"
            if short:
                key, row = max(short, key=lambda kv: kv[1]["gold"] - kv[1]["pred"])
                result += f"(가장 모자란 {_ROW_LABELS[key]} {row['pred']}/{row['gold']})"
            return result
    return "자료 없음"


MODEL_LABELS: dict[str, str] = {
    "qwen36_35b_runpod": "Qwen3.6 35B (RunPod)",
    "qwen3_30b_a3b_rngd": "Qwen3 30B (RNGD)",
    "gpt_oss_20b_rngd": "gpt-oss 20B (RNGD)",
    "nuextract2_8b_runpod": "NuExtract 2.0 8B (RunPod)",
    "qwen3vl4b_rngd": "Qwen3-VL 4B (RNGD)",
    "qwen38": "Qwen3.8 27B (vLLM)",
    "claude": "Claude (실버 초안)",
    "gpt": "GPT",
}
_CONDITIONS = {
    "dev10": "개발 10건", "dev": "개발 10건", "eval": "평가 10건",
    "probe": "탐색", "cls": "분류 검사", "optonly": "선택 항목만",
    "wsonly": "공백 줄임만", "diag": "진단", "none": "안내문 없음",
    "ex": "예시 포함", "w1": "동시 1개", "p3": "안내문 p3",
}


def model_label(tag: str | None) -> str:
    """알려진 모델은 표시 이름으로, 모르는 모델은 태그 그대로 돌려준다."""
    return MODEL_LABELS.get(tag, tag or "")


def friendly_error(where: str, raw: str, env_names: dict[str, str] | None = None) -> dict:
    """오류를 안내로 바꾼다. 원문은 호출자가 비밀값을 가린 뒤 넘긴다."""
    if "Could not resolve hostname ssh" in raw or "RNGD_SSH starts with ssh" in raw:
        message = "`.env`의 RNGD_SSH 값이 `ssh`로 시작합니다."
        fix = "`ssh`를 빼고 `-i <키> -p <포트> <사용자>@<호스트>`처럼 인자만 적으세요. 앱은 이제 `ssh`를 빼고 읽습니다."
    elif raw == "RNGD_SSH 없음":
        message = "RNGD 접속 정보(RNGD_SSH)가 `.env`에 없습니다."
        fix = "`.env.example`의 RNGD_SSH 줄을 복사해 값을 채우세요."
    elif "SSLCertVerificationError" in raw or "CERTIFICATE_VERIFY_FAILED" in raw:
        message = "RunPod 주소의 인증서를 확인하지 못했습니다. 파이썬 3.11에 인증서 묶음이 없을 때 생깁니다."
        fix = "터미널에서 `/Applications/Python 3.11/Install Certificates.command`를 한 번 실행한 뒤 앱을 다시 켜세요."
    elif "401" in raw or "Unauthorized" in raw:
        message = "RunPod 관리 키(RUNPOD_API_KEY)가 거절됐습니다."
        fix = "RunPod 설정 화면에서 키를 다시 만들어 `.env`에 넣으세요."
    elif where == "env" and env_names:
        variable = env_names.get("base_url") or next(iter(env_names.values()))
        message = f"`.env`에 {variable}가 없습니다."
        fix = (f"서버 주소를 `.env`의 {variable}에 적으세요. 예: http://127.0.0.1:8000/v1 "
               "(SSH 터널을 거친 내 컴퓨터 쪽 주소)")
    elif any(token in raw for token in ("timed out", "Connection refused", "TimeoutError",
                                        "ConnectionRefusedError", "TimeoutExpired")):
        # 기존 연결 검사는 비밀값 보호를 위해 예외의 종류만 남긴다.
        message = "서버가 응답하지 않습니다."
        fix = "SSH 터널이 열려 있는지, 서버가 켜져 있는지 확인하세요."
    else:
        message = "서버를 보지 못했습니다."
        fix = "아래 원문을 보고 .env와 터널을 확인하세요."
    return {"message": message, "fix": fix, "raw": raw}


def server_controls(*, running: bool, runpod_ok: bool, rngd_ok: bool) -> dict:
    """모델 연결과 별개로 관리 서버를 볼 수 있어야 변경 단추를 연다."""
    reasons = {}
    for action, ready, offline in (
        ("pod_create", runpod_ok, "RunPod를 보지 못해 Pod를 만들 수 없습니다."),
        ("pod_delete", runpod_ok, "RunPod를 보지 못해 Pod를 지울 수 없습니다."),
        ("rngd_up", rngd_ok, "RNGD를 보지 못해 모델을 올릴 수 없습니다."),
        ("rngd_down", rngd_ok, "RNGD를 보지 못해 모델을 내릴 수 없습니다."),
    ):
        reasons[action] = ("실행이나 시험이 돌고 있어 서버를 바꿀 수 없습니다." if running
                           else offline if not ready else "")
    return {"can": {action: not reason for action, reason in reasons.items()}, "why": reasons}


def server_ui_text() -> dict:
    """브라우저 상태에 따라 고를 안내문. 화면에서는 받은 글만 표시한다."""
    return {
        "guide": {"advanced_on": "서버 탭에서 모델을 올리세요",
                  "advanced_off": "고급을 켜고 서버 탭에서 모델을 올리세요"},
        "busy": "서버 변경이 진행 중입니다. 끝날 때까지 기다리세요.",
        "unavailable": "서버 상태를 확인하지 못해 동작을 잠갔습니다. 지금 다시 보기를 누르세요.",
        "action_failure": {"message": "서버 변경을 끝내지 못했습니다.",
                           "fix": "아래 원문을 보고 서버 연결과 실행 상태를 확인하세요."},
    }


def _date(name: str, started_at) -> str:
    candidates = []
    if re.match(r"^\d{8}(?:_|$)", name):
        candidates.append((name[:8], "%Y%m%d"))
    if started_at:
        candidates.append((str(started_at)[:10], "%Y-%m-%d"))
    for value, fmt in candidates:
        try:
            day = datetime.strptime(value, fmt)
            return f"{day.month}/{day.day}"
        except ValueError:
            continue
    return ""


def _prompt(token: str) -> bool:
    # 세 자리 s003은 안내문이 아니라 문서 번호다.
    return bool(re.fullmatch(r"s\d+", token) and not re.fullmatch(r"s\d{3}", token))


def _input_version(token: str) -> str:
    if token in ("cw", "chars_wrap"):
        return "chars_wrap"
    if re.fullmatch(r"v\d+", token):
        return "version" + token[1:]
    return token if re.fullmatch(r"version\d+", token) else ""


def _condition(token: str) -> str:
    if token in _CONDITIONS:
        return _CONDITIONS[token]
    doc = re.fullmatch(r"([smSM])(\d{3})", token)
    if doc:
        return f"문서 T21-{doc[1].upper()}{doc[2]} 한 건"
    match = re.fullmatch(r"(eval|probe|diag|r)(\d+)", token)
    if match:
        prefix, number = match.groups()
        return {"eval": f"평가 T21-{number} 한 건", "probe": f"탐색 {number}회",
                "diag": f"진단 {number}", "r": f"{number}회차"}[prefix]
    return token


def run_label(info: dict) -> dict:
    """summarize_run 결과(일부 키만 있어도 됨)를 제목·원래 이름·구성 글로 바꾼다."""
    name = info.get("name") or ""
    base = name.removeprefix("manual/")
    date = _date(base, info.get("started_at"))
    inferred = next((tag for tag in sorted(MODEL_LABELS, key=lambda t: (-len(t), t))
                     if re.search(rf"(?:^|_){re.escape(tag)}(?:_|$)", base)), "")
    tag = info.get("model_tag") or inferred
    model = "실버 초안(Claude)" if "_silver_" in name else model_label(tag)

    rest = re.sub(r"^\d{8}(?:_|$)", "", base)
    for known in dict.fromkeys((inferred, tag)):
        if known:
            rest = re.sub(rf"(^|_){re.escape(known)}(?=_|$)", r"\1", rest)
    # 두 토큰으로 나뉘는 입력 판도 한 조건으로 읽는다.
    tokens = re.findall(r"chars_wrap|[^_]+", rest)
    prompt = info.get("prompt_version") or next((t for t in tokens if _prompt(t)), "")
    pages_dir = info.get("pages_dir")
    version = PurePosixPath(str(pages_dir)).name if pages_dir else ""
    version = version or next((_input_version(t) for t in tokens if _input_version(t)), "")

    parts = [" ".join(v for v in (date, model) if v)]
    if prompt:
        parts.append(f"안내문 {prompt}")
    if version:
        parts.append(f"입력 {version}")
    parts.extend(_condition(t) for t in tokens
                 if t not in ("sections", "silver", prompt) and not _prompt(t) and not _input_version(t))
    title = " · ".join(p for p in parts if p)
    if info.get("kind") == "manual":
        title = "[수동] " + title
    return {"title": title, "subtitle": name, "parts": title.split(" · ")}
