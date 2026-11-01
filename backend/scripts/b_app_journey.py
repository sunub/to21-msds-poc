"""첫 사용 안내의 기록 journey v2 (역할 B, 개발 전용, ADR-028). 모양은 STRUCTURE '저장 형태 — journey v2'다.

파일은 runs/manual/journey.json 하나다(체크아웃 하나에 기록 하나, 사용자 구분 없음). 길(GET·PUT /api/journey)은 b_app이 열고,
이 모듈은 읽기(load)·검사(validate)·합치기(merge)·쓰기(save)만 한다. 잠금은 b_app이 잡는다.
- 저장하지 않는 것: 문서 번호, 실행 이름, 항 번호, 값, 지시문, 묶음·정답지 id, 모델, 경로, 키. 모르는 칸은 validate가 거부한다.
  작업 번호(last_job, pending.job)와 시도 번호(pending.attempt)만 예외다.
- 시각은 브라우저 toISOString() 모양(UTC, 밀리초, Z)만 받는다. 그래서 글자 비교가 곧 이르고 늦음이다.
- merge는 성공 기록(outcomes)을 줄이지 않는다. 들어온 값이 null이어도, count가 작아도, first_at이 늦어도 저장된 값이 남는다.
  count는 '적어도 이만큼'이라는 뜻이다. 두 탭이 같은 저장 값 1을 읽고 각자 2로 올려 보내면 3이 아니라 2로 남는다.
- progress·pending은 들어온 값으로 바꾼다(마지막 PUT이 이긴다). migrated_from은 한 번 1이면 1로 남는다.
- progress.guide는 처음 사용 안내(Wispr 구조, 승인 10/31)의 진행이다. 선택 칸이라 없으면 시작 전이다. 화면 이름(G01~G15),
  고른 일(GUIDE_CHOICES), 건너뛴 직접 해 보기(GUIDE_PRACTICES)처럼 정해진 이름만 받는다.
"""
import copy
import json
import os
import re
import tempfile
from pathlib import Path

import _common  # noqa: F401  src 경로 등록 (b_app_text가 msds를 부른다)
import b_app_text as bt

TEXT = bt.JOURNEY_TEXT
MAX_BODY = 16 * 1024                                   # PUT 본문 한도
KEYS = ("version", "progress", "outcomes", "pending", "migrated_from")
STATES = ("not_started", "in_progress", "skipped", "completed")
MODES = ("real", "practice")
TOP_STEP = {"t1": 3, "t2": 4}                          # 갈래마다 마지막 단계. 0은 시작 전
GUIDE_CHOICES = ("score", "source", "retest", "ai")             # G02에서 고르는 일
GUIDE_PRACTICES = ("p1", "p2", "p3")                            # 직접 해 보기 세 개
_GUIDE_SCREEN = re.compile(r"G(0[1-9]|1[0-5])", re.ASCII)
OUTCOME_KINDS = {"t1": ("real",), "t2": ("real", "practice")}
_OUTCOME_KEYS = {"t1": ("first_at", "last_at", "count"), "t2": ("first_at", "last_at", "count", "last_job")}
_TIME = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z", re.ASCII)
_ID = re.compile(r"[\w-]{1,64}", re.ASCII)


def default() -> dict:
    """기본 기록. 두 갈래는 시작 전, 성공 기록·판정 전 시도·옮김 표시는 null. 부를 때마다 새 dict다."""
    return {"version": 2,
            "progress": {"active": None, "dismissed_at": None,
                         **{t: {"state": "not_started", "step": 0, "updated_at": None} for t in TOP_STEP}},
            "outcomes": {t: {kind: None for kind in kinds} for t, kinds in OUTCOME_KINDS.items()},
            "pending": None, "migrated_from": None}


# ── 검사 ───────────────────────────────────────────────

def _bad(where: str, expect: str, **facts) -> ValueError:
    return ValueError(TEXT["invalid"]["bad_value"].format(where=where, expect=TEXT["expect"][expect].format(**facts)))


def _fields(obj, keys, where: str) -> None:
    """obj가 정확히 keys 칸만 가진 객체인지."""
    if not isinstance(obj, dict):
        raise _bad(where, "object")
    extra = [k for k in obj if k not in keys]
    if extra:
        raise ValueError(TEXT["invalid"]["unknown_key"].format(where=f"{where}.{extra[0]}"))
    missing = [k for k in keys if k not in obj]
    if missing:
        raise ValueError(TEXT["invalid"]["missing_key"].format(where=f"{where}.{missing[0]}"))


def _time(v, where: str, *, nullable: bool) -> None:
    if v is None and nullable:
        return
    if not (isinstance(v, str) and _TIME.fullmatch(v)):
        raise _bad(where, "time_or_null" if nullable else "time")


def _id(v, where: str, *, nullable: bool) -> None:
    if v is None and nullable:
        return
    if not (isinstance(v, str) and _ID.fullmatch(v)):
        raise _bad(where, "id_or_null" if nullable else "id")


def _int(v, low: int, high: int | None) -> bool:
    return type(v) is int and v >= low and (high is None or v <= high)   # 참거짓(bool)은 정수로 치지 않는다


def _names(v, allowed: tuple, where: str, expect: str) -> None:
    if not (isinstance(v, list) and len(set(v)) == len(v) and all(isinstance(x, str) and x in allowed for x in v)):
        raise _bad(where, expect)


def _check_guide(g) -> None:
    _fields(g, ("state", "screen", "choices", "skipped", "updated_at"), "progress.guide")
    if not (isinstance(g["state"], str) and g["state"] in STATES):
        raise _bad("progress.guide.state", "state")
    if not (g["screen"] is None or (isinstance(g["screen"], str) and _GUIDE_SCREEN.fullmatch(g["screen"]))):
        raise _bad("progress.guide.screen", "screen")
    _names(g["choices"], GUIDE_CHOICES, "progress.guide.choices", "choices")
    _names(g["skipped"], GUIDE_PRACTICES, "progress.guide.skipped", "practices")
    _time(g["updated_at"], "progress.guide.updated_at", nullable=True)


def _check_progress(p) -> None:
    _fields(p, ("active", "dismissed_at", *TOP_STEP, *(("guide",) if isinstance(p, dict) and "guide" in p else ())),
            "progress")
    if "guide" in p:
        _check_guide(p["guide"])
    if not (p["active"] is None or (isinstance(p["active"], str) and p["active"] in TOP_STEP)):
        raise _bad("progress.active", "active")
    _time(p["dismissed_at"], "progress.dismissed_at", nullable=True)
    for t, top in TOP_STEP.items():
        where = f"progress.{t}"
        _fields(p[t], ("state", "step", "updated_at"), where)
        if not (isinstance(p[t]["state"], str) and p[t]["state"] in STATES):
            raise _bad(f"{where}.state", "state")
        if not _int(p[t]["step"], 0, top):
            raise _bad(f"{where}.step", "step", top=top)
        _time(p[t]["updated_at"], f"{where}.updated_at", nullable=True)


def _check_outcomes(o) -> None:
    _fields(o, tuple(OUTCOME_KINDS), "outcomes")
    for t, kinds in OUTCOME_KINDS.items():
        _fields(o[t], kinds, f"outcomes.{t}")
        for kind in kinds:
            e, where = o[t][kind], f"outcomes.{t}.{kind}"
            if e is None:
                continue
            _fields(e, _OUTCOME_KEYS[t], where)
            _time(e["first_at"], f"{where}.first_at", nullable=False)
            _time(e["last_at"], f"{where}.last_at", nullable=False)
            if not _int(e["count"], 1, None):
                raise _bad(f"{where}.count", "count")
            if "last_job" in e:
                _id(e["last_job"], f"{where}.last_job", nullable=True)


def _check_pending(p) -> None:
    if p is None:
        return
    _fields(p, ("attempt", "job", "mode", "started_at"), "pending")
    _id(p["attempt"], "pending.attempt", nullable=False)
    _id(p["job"], "pending.job", nullable=True)          # 작업 번호를 받기 전이면 null
    if not (isinstance(p["mode"], str) and p["mode"] in MODES):
        raise _bad("pending.mode", "mode")
    _time(p["started_at"], "pending.started_at", nullable=False)


def _check_migrated(v) -> None:
    if not (v is None or (type(v) is int and v == 1)):
        raise _bad("migrated_from", "migrated_from")


_PARTS = {"progress": _check_progress, "outcomes": _check_outcomes, "pending": _check_pending,
          "migrated_from": _check_migrated}


def _is_v2(obj) -> bool:
    return isinstance(obj, dict) and type(obj.get("version")) is int and obj["version"] == 2


def validate(obj) -> dict:
    """journey v2인지 본다. 틀리면 한국어 ValueError. 맞으면 받은 dict를 그대로 돌려준다."""
    if not isinstance(obj, dict):
        raise _bad("journey", "object")
    extra = [k for k in obj if k not in KEYS]
    if extra:
        raise ValueError(TEXT["invalid"]["unknown_key"].format(where=extra[0]))
    missing = [k for k in KEYS if k not in obj]
    if missing:
        raise ValueError(TEXT["invalid"]["missing_key"].format(where=missing[0]))
    if not _is_v2(obj):
        raise ValueError(TEXT["invalid"]["version"])
    for part, check in _PARTS.items():
        check(obj[part])
    return obj


# ── 읽기·합치기·쓰기 ────────────────────────────────────

def load(path: Path) -> tuple[dict, list[dict]]:
    """(기록, problems). 파일이 없으면 기본값이고 파일을 만들지 않는다. JSON이 아니거나 형식 번호가 2가 아니면 통째로 기본값과
    {"part": "file"}. 그 밖에는 칸(progress·outcomes·pending·migrated_from)마다 따로 보고 틀린 칸만 기본값으로 돌린다.
    파일을 열지 못하면(권한 등) OSError를 그대로 올린다. 그 기록을 기본값으로 덮어쓰지 않기 위해서다."""
    try:
        raw = Path(path).read_bytes()
    except FileNotFoundError:
        return default(), []
    try:
        data = json.loads(raw.decode("utf-8"))
    except ValueError:                                  # JSON 오류와 UTF-8 오류 모두
        return default(), [{"part": "file", "message": TEXT["parts"]["file_json"]}]
    if not _is_v2(data):
        return default(), [{"part": "file", "message": TEXT["parts"]["file_version"]}]
    journey, problems = default(), []
    for part, check in _PARTS.items():
        try:
            if part not in data:
                raise ValueError(part)
            check(data[part])
        except ValueError:
            problems.append({"part": part, "message": TEXT["parts"][part]})
        else:
            journey[part] = data[part]
    return journey, problems


def _merge_outcome(stored: dict | None, incoming: dict | None) -> dict | None:
    if stored is None or incoming is None:
        return copy.deepcopy(incoming if stored is None else stored)
    out = {"first_at": min(stored["first_at"], incoming["first_at"]),
           "last_at": max(stored["last_at"], incoming["last_at"]),
           "count": max(stored["count"], incoming["count"])}
    if "last_job" in stored:
        # last_at이 늦은 쪽의 작업 번호. 같으면 저장된 쪽
        out["last_job"] = (incoming if incoming["last_at"] > stored["last_at"] else stored)["last_job"]
    return out


def merge(stored: dict, incoming: dict) -> dict:
    """저장된 기록과 들어온 기록을 합친 새 dict. 둘 다 검사를 지난 v2여야 한다. 받은 dict는 바꾸지 않는다."""
    return {"version": 2,
            "progress": copy.deepcopy(incoming["progress"]),
            "outcomes": {t: {kind: _merge_outcome(stored["outcomes"][t][kind], incoming["outcomes"][t][kind])
                             for kind in kinds} for t, kinds in OUTCOME_KINDS.items()},
            "pending": copy.deepcopy(incoming["pending"]),
            "migrated_from": 1 if 1 in (stored["migrated_from"], incoming["migrated_from"]) else None}


def save(path: Path, journey: dict) -> None:
    """같은 폴더의 임시 파일에 다 쓴 뒤 이름을 바꿔 한 번에 갈아 끼운다. 폴더가 없으면 만든다. 실패하면 임시 파일을 지운다."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(journey, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
