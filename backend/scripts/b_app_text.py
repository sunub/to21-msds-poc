"""작업 화면의 표시 이름 (역할 B, 개발 전용, ADR-027).

파일이나 서버를 읽지 않는 순수 함수다. 실행 정보가 이름보다 우선하며,
모르는 조건은 그대로 남겨 표시 이름에서 실행 조건을 잃지 않는다.
"""
import re
from datetime import datetime
from pathlib import PurePosixPath


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
