"""작업 화면(ADR-025)의 바탕 (역할 B, 개발 전용): runs/ 아래 실행 폴더를 모두 읽어 점수·호출 상태·행 수·진행률을 한 구조로 돌려준다.

- 점수는 F의 msds.evaluate.score(score_set, score_pair)만 쓴다. "값 없는 행 제외" 점수는 채점 전에 정답·결과 양쪽에서
  값 없는 행(자료없음·해당없음·비해당·미기재)을 거른 뒤 같은 score_set을 부른 것이다.
- 평가용 문서는 실행 폴더에 있어도 채점·목록에서 빼고 excluded에 문서 번호만 남긴다 (D-43).
- 캐시는 저장소 밖(임시 폴더)에 쓴다. runs/는 git에 올라가고, 하네스는 깨끗한 작업 트리를 바란다.
- 비밀값은 읽지 않는다. run_info.yaml에 있는 것만 쓴다.
"""
import copy
import json
import os
import re
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import yaml

import _common  # noqa: F401  src 경로 등록
from compare_models import ROW_KEYS, load_run, row_counts
from msds.common import manifest
from msds.evaluate.score import LEVEL_ORDER, PASS_SCORE, WEIGHTS, score_pair, score_set

NO_VALUE = ("자료없음", "해당없음", "비해당", "미기재")
VERSION = 1   # 계산 규칙이 바뀌면 올린다. 캐시 키에 들어간다
CACHE_DIR = Path(tempfile.gettempdir()) / "to21_b_app_cache"   # 기본 캐시 폴더. cache_dir=None이면 캐시를 쓰지 않는다
RUNNING_HOURS = 6

# 값 없는 행을 거르는 표. 성분(components)은 다른 표의 comp_ref가 가리키는 행이라 지우지 않는다(지우면 채점기의 성분 짝이 깨진다)
_STRIP_KEYS = tuple(k for k in ROW_KEYS if k != "components")
_MARKS = ("status", "text_value", "applicable", "value_raw")    # 행에서 상태 글이 들어가는 칸
_QS = ("q", "content", "threshold", "qty", "qty_alt")          # 숫자 묶음(TO21 Q) 칸
_NUMS = ("value", "lower", "upper")
_REPEAT = re.compile(r"(.{20,}?)\1{3,}", re.S)                  # 20자 넘는 글이 3번 넘게 이어 반복

ITEM_HELP: dict[str, str] = {
    "MSDS 건수": "한 파일에 든 MSDS가 몇 건인지 정답과 같은 수로 나눴는가",
    "관리정보": "MSDS 번호·최초 작성일·최종 개정일·개정 횟수 네 칸이 정답과 같은가",
    "제품명": "제품 이름, 회사 이름, 긴급 전화번호가 정답과 같은가",
    "신호어": "'위험'이나 '경고' 같은 신호어가 정답과 같은가",
    "그림문자": "위험을 나타내는 빨간 마름모 그림(GHS01~09)을 문서와 똑같이 골랐는가",
    "H 코드": "유해·위험 문구 번호(예: H315 피부 자극)를 빠뜨리거나 더하지 않고 뽑았는가",
    "P 코드": "예방조치 문구 번호(예: P280 보호장갑 착용)를 빠뜨리거나 더하지 않고 뽑았는가",
    "유해성 분류": "유해성 분류와 구분의 짝(예: 심한 눈 자극성 구분 2)이 정답과 같은가",
    "구성성분(CAS": "성분 목록이 정답과 같은가 (성분은 CAS 번호로 맞춰 본다)",
    "구성성분 필드": "맞춘 성분마다 성분 이름과 KE 번호(국내 기존화학물질 번호)가 정답과 같은가",
    "함유량": "성분마다 함유량의 부등호·값·단위가 정답과 같은가 (예: '10 ~ 20 %')",
    "8항 노출기준": "8항 노출기준 행(성분·기준 출처·TWA 같은 종류·값)이 정답과 같은가",
    "9항 필수 물성": "외관·pH·끓는점·인화점·폭발 한계·증기압·비중·자연발화점 값이 정답과 같은가",
    "9항 기타 물성": "필수가 아닌 나머지 물성(색·냄새·녹는점 등) 행이 정답과 같은가",
    "11항 급성독성": "경구·경피·흡입 급성독성 행(예: 경구 LD50 > 2000 mg/kg)이 정답과 같은가",
    "11항 기타 독성": "피부 자극·눈 손상·과민성 같은 나머지 독성 행이 정답과 같은가",
    "11항 CMR": "발암성·생식세포 변이원성·생식독성 행(예: IARC 3군)이 정답과 같은가",
    "12항 생태": "물고기·물벼룩 독성, 분해성, 생물농축성 같은 환경 영향 행이 정답과 같은가",
    "15항 국내 규제": "산업안전보건법·화평법·화관법·위험물·폐기물 규제 행의 항목과 해당 여부가 정답과 같은가",
    "15항 국내 규제 기준농도": "국내 규제 행 가운데 기준 농도(예: 1% 이상 함유)가 적힌 행이 정답과 같은가",
    "15항 해외": "미국·EU 같은 해외·기타 규제 행의 항목과 해당 여부가 정답과 같은가",
    "14항 운송": "UN 번호·운송 위험 등급·용기 등급이 정답과 같은가",
    "서술형": "응급조치·취급 방법 같은 문장 항목이 정답 글과 얼마나 비슷한가 (글자 유사도)",
}


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


# ── 값 없는 행 ─────────────────────────────────────────

def _blank(text) -> str:
    return re.sub(r"\s+", "", text) if isinstance(text, str) else ""


def _no_value_row(row: dict) -> bool:
    qs = [row[k] for k in _QS if isinstance(row.get(k), dict)]
    if any(q.get(n) is not None for q in qs for n in _NUMS):
        return False
    marks = [row.get(k) for k in _MARKS] + [q.get(k) for q in qs for k in ("raw", "status")]
    return any(_blank(v) in NO_VALUE for v in marks)


def strip_no_value_rows(doc: dict) -> dict:
    """값 없는 행을 뺀 사본. 값 없는 행 = 상태 칸(status·text_value·applicable·value_raw, Q의 raw·status) 중 하나라도
    NO_VALUE이고 숫자 값(Q의 value·lower·upper)이 없는 행. 원본은 바꾸지 않는다."""
    out = copy.deepcopy(doc)
    for m in out.get("msds") or []:
        for k in _STRIP_KEYS:
            if isinstance(m.get(k), list):
                m[k] = [r for r in m[k] if not (isinstance(r, dict) and _no_value_row(r))]
    return out


# ── 한도 걸림 분류 ─────────────────────────────────────

def limit_kind(request: dict) -> str | None:
    """출력 한도에 걸린 요청(raw의 requests 원소)의 원인. docs/plan/도구/diag_runs.py의 kind()와 같은 규칙."""
    if request.get("finish_reason") != "length":
        return None
    tail = request.get("tail") or ""
    ws = (request.get("whitespace") or 0) / max(request.get("chars") or 0, 1)
    if ws > 0.5 or len(tail) - len(tail.rstrip()) > 200:
        return "공백폭주"
    if _REPEAT.search(tail):
        return "반복"
    return "긴출력"


def _section_limit(path: Path) -> str | None:
    """항 하나의 raw 기록에서 처음으로 한도에 걸린 요청의 분류. 시도 순서: first_attempt → 채택 → reextract_attempt."""
    if not path.exists():
        return None
    raw = _read_json(path)
    for attempt in (raw.get("first_attempt") or {}, raw, raw.get("reextract_attempt") or {}):
        for r in attempt.get("requests") or []:
            kind = limit_kind(r)
            if kind:
                return kind
    return None


def _grid_doc(run: Path, doc_id: str, checks: dict) -> dict:
    out = {}
    for s in checks.get("sections") or []:
        i, no = s.get("msds_index") or 0, s["section"]
        out[str(no) if i == 0 else f"m{i}:{no}"] = {
            "ok": s.get("ok"), "mode": s.get("mode"), "reextracted": s.get("reextracted"),
            "attempts": s.get("attempts"), "seconds": s.get("seconds"),
            "limit_kind": _section_limit(run / "raw" / f"{doc_id}_m{i}_s{no:02d}.json")}
    return out


# ── 합격 기준 ──────────────────────────────────────────

def _help(name: str) -> str:
    key = max((k for k in ITEM_HELP if name.startswith(k)), key=len, default=None)
    return ITEM_HELP[key] if key else ""


def criteria() -> dict:
    empty = {"msds": [{"product": {"name": None}}]}
    items = sorted(score_pair(empty, empty)["items"], key=lambda i: LEVEL_ORDER[i["level"]])
    must = sum(i["level"] == "필수" for i in items)
    return {"pass_score": PASS_SCORE, "weights": dict(WEIGHTS),
            "rule": f"필수 {must}개가 모두 목표 이상이고 가중 종합 {PASS_SCORE:.0f}점 이상",
            "items": [{"name": i["name"], "level": i["level"], "metric": i["metric"], "target": i["target"],
                       "help": _help(i["name"])} for i in items]}


# ── 실행 폴더 ──────────────────────────────────────────

def _kind(run: Path) -> str:
    if run.parent.name == "manual":
        return "manual"
    return "run" if (run / "run_info.yaml").exists() else "models"


def _name(run: Path) -> str:
    return f"manual/{run.name}" if _kind(run) == "manual" else run.name


def list_runs(runs_dir: Path) -> list[Path]:
    """run_info.yaml이 있는 실행 폴더(runs/manual/<이름>/ 포함)와 비교표 폴더(compare.md만 있음)."""
    runs_dir = Path(runs_dir)
    out: list[Path] = []
    for p in sorted(runs_dir.iterdir()) if runs_dir.exists() else []:
        if not p.is_dir():
            continue
        if p.name == "manual":
            out += [q for q in sorted(p.iterdir()) if q.is_dir() and (q / "run_info.yaml").exists()]
        elif (p / "run_info.yaml").exists() or (p / "compare.md").exists():
            out.append(p)
    return out


def _recent(started_at) -> bool:
    try:
        t = datetime.fromisoformat(str(started_at))
    except (TypeError, ValueError):
        return False
    return datetime.now().astimezone() - t.astimezone() < timedelta(hours=RUNNING_HOURS)


def _summarize(run: Path, gold_dir: Path) -> dict:
    r = load_run(run)
    info = yaml.safe_load((run / "run_info.yaml").read_text(encoding="utf-8")) or {}
    purposes = {row["doc_id"]: row["purpose"] for row in manifest.load()}
    seen = set(r["outputs"]) | set(r["seconds"]) | set(r["checks"])
    # 평가용과 manifest에 없는 문서(용도를 확인할 수 없음)는 문서 번호만 남긴다 (D-43)
    excluded = sorted(d for d in seen if purposes.get(d) in (None, "평가"))
    targets = seen - set(excluded)
    outputs = {d: doc for d, doc in r["outputs"].items() if d in targets}
    docs = [d for d in sorted(outputs) if (gold_dir / f"{d}.json").exists()]
    golds = {d: _read_json(gold_dir / f"{d}.json") for d in docs}
    pairs = [(d, golds[d], outputs[d]) for d in docs]

    out = {"name": _name(run), "kind": _kind(run), "model_tag": info.get("model_tag"), "model": info.get("model"),
           "prompt_version": info.get("prompt_version"), "prompt_hashes": info.get("prompt_hashes"),
           "pages_dir": info.get("pages_dir"), "concurrency": info.get("concurrency"),
           "git_commit": info.get("git_commit"), "started_at": info.get("started_at"),
           "docs": docs, "excluded": excluded, "no_gold": sorted(set(outputs) - set(docs)),
           "weighted": None, "must_passed": None, "must_total": None, "passed": None,
           "items": [], "items_na_excluded": [], "weighted_na_excluded": None, "details": [], "per_doc": {}}
    if pairs:
        ss = score_set(pairs)
        na = score_set([(d, strip_no_value_rows(g), strip_no_value_rows(p)) for d, g, p in pairs])
        out.update({
            "weighted": ss["weighted"], "must_passed": ss["must_passed_count"], "must_total": ss["must_total"],
            "passed": ss["passed"], "items": ss["items"], "items_na_excluded": na["items"],
            "weighted_na_excluded": na["weighted"], "details": ss["details"],
            "per_doc": {d: {"weighted": ss["docs"][d]["weighted"], "failed_must": ss["docs"][d]["failed_must"],
                            "seconds": r["seconds"].get(d),
                            "items": {i["name"]: i["score"] for i in score_pair(golds[d], outputs[d])["items"]}}
                        for d in docs}})
    pred_rows = {d: row_counts(outputs[d]) for d in docs}
    gold_rows = {d: row_counts(golds[d]) for d in docs}
    out["rows"] = {k: {"pred": sum(pred_rows[d][k] for d in docs), "gold": sum(gold_rows[d][k] for d in docs)}
                   for k in ROW_KEYS}
    out["grid"] = {d: _grid_doc(run, d, c) for d, c in sorted(r["checks"].items()) if d in targets}
    done = sum(1 for d in targets if d in r["seconds"])
    out["progress"] = {"done": done, "total": len(targets),
                       "running": done < len(targets) and _recent(info.get("started_at"))}
    # 캐시(JSON)에서 읽은 결과와 같은 모양으로 맞춘다 (예: prompt_hashes의 키 1 → "1", 날짜 → 글자)
    return json.loads(json.dumps(out, ensure_ascii=False, default=str))


def _max_mtime(folder: Path) -> int | None:
    times = [p.stat().st_mtime_ns for p in folder.glob("*.json")] if folder.exists() else []
    return max(times, default=None)


def summarize_run(run: Path, gold_dir: Path, *, cache_dir: Path | None = CACHE_DIR) -> dict:
    """실행 하나의 요약. 비교표 폴더(kind="models")는 채점하지 않는다.
    cache_dir가 있으면 <cache_dir>/<실행 이름>.json에 저장하고, outputs·정답 폴더의 최대 수정 시각과 VERSION이
    같으면 그것을 읽는다."""
    run, gold_dir = Path(run), Path(gold_dir)
    if _kind(run) == "models":
        return {"name": _name(run), "kind": "models", "started_at": None}
    key = [_max_mtime(run / "outputs"), _max_mtime(gold_dir), VERSION, str(gold_dir)]
    cache = Path(cache_dir) / f"{_name(run)}.json" if cache_dir else None
    if cache and cache.exists():
        try:
            saved = _read_json(cache)
            if saved.get("key") == key:
                return saved["result"]
        except (OSError, ValueError):
            pass                                    # 쓰다 만 캐시는 다시 계산한다
    result = _summarize(run, gold_dir)
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache.with_name(cache.name + ".tmp")
        tmp.write_text(json.dumps({"key": key, "result": result}, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, cache)
    return result


def _order(summary: dict) -> tuple:
    """started_at 순. 없으면 폴더 이름 앞의 날짜(20261029 → 2026-10-29), 그것도 없으면 폴더 이름."""
    name = summary["name"]
    m = re.match(r"(?:manual/)?(\d{4})(\d{2})(\d{2})", name)
    return (summary.get("started_at") or (f"{m[1]}-{m[2]}-{m[3]}" if m else name), name)


def load_all(runs_dir: Path, gold_dir: Path, *, cache_dir: Path | None = CACHE_DIR) -> dict:
    runs = []
    for run in list_runs(runs_dir):
        try:
            runs.append(summarize_run(run, gold_dir, cache_dir=cache_dir))
        except Exception as e:                      # 쓰는 중인 파일 등. 실행 하나 때문에 화면 전체가 멈추지 않게 한다
            runs.append({"name": _name(run), "kind": _kind(run), "started_at": None,
                         "error": f"{type(e).__name__}: {e}"})
    return {"criteria": criteria(), "runs": sorted(runs, key=_order), "gold_dir": str(gold_dir)}
