"""추출 파인튜닝 학습 데이터: 교사 모델(GPT·Claude)의 항목별 추출 결과 → 학생 모델의 학습 예시 (11/03 F).

교사 결과는 두 가지를 받는다.
  TeacherRun  scripts/run_sections.py --model gpt|claude 로 만든 실행 폴더 runs/<실행>/ (항목별 방식)
              run_info.yaml의 pages_dir(교사가 본 쪽 글자 폴더)로 입력을 다시 만들어야 줄 번호가 맞는다
              raw/<문서>_m<i>_s<NN>.json: 항별 응답. 재추출했으면 고른 시도가 맨 위에 있다(section_runner._raw_record)
  SilverSet   묶음 방식 실버·골드 폴더 data/silver/<모델>/, data/gold/ (완성 TO21 문서, 11/03 팀원 p6 실버 59건)
              from_silver.convert_section이 근거 원문 조각으로 줄 번호를 되찾아 항별 중간 형식으로 되돌린다

예시 하나 = 실제 추출 때 학생 모델이 받는 메시지와 같은 system·user + 정답 assistant
  system     section_prompts.build_system(no, rows). 행 형식 여부는 학생 설정의 rows_sections로 정한다.
             JSON 항은 학생 설정의 첫 구조화 방식이 json_object·none이면 ChatClient.call처럼 [응답 형식] 스키마 안내를 붙인다
  user       build_user(no, model_lines(...))의 글. 첫 시도와 같다(재추출 피드백 없음). 글 part 하나라 문자열로 둔다
             (Qwen3 대화 틀은 목록 내용을 빈 글로 읽는다. vLLM도 글 part 하나는 그 글 그대로 넣는다)
  assistant  교사 응답(parsed)을 학생 형식으로 다시 쓴 글
             행 형식 항: rows_text(rows.rows_guide의 형식). 숫자 묶음 열은 원문 표기(raw)를 쓴다
             JSON 항: 공백 없는 JSON. 칸은 스키마 순서, 필수가 아닌 칸의 null·빈 목록은 뺀다(_COMMON 지시와 같다)

버리는 예시와 이유(보고서에 센다)
  교사 실패        교사 항이 ok가 아니거나 검사 문제(check_problems)가 있다
  근거 줄 못 찾음   실버·골드를 되돌릴 때 줄 번호를 못 찾은 행이 있다(그 항 전체를 뺀다)
  MSDS 건수 다름    실버의 MSDS 건수와 쪽 글자로 나눈 건수가 다르다
  줄 번호 다름      정답의 줄 번호가 다시 만든 입력에 없다(쪽 글자가 교사 실행 때와 다르다)
  형식 검사 실패    정답 글을 실제 추출과 같은 방법으로 다시 읽으면(행: parse_rows, JSON: json.loads) 오류·스키마 위반·행 수 차이가 난다
  이미지 항        학생 설정이 2항에 쪽 이미지를 붙이면(image_input) 2항은 뺀다. 이미지 없이 그림문자 정답을 배우면 지어내게 된다
문서 단위로 빼는 것
  manifest의 개발·평가 문서. 학습에 섞이면 같은 문서로 잰 점수가 의미 없어진다 (D-43)

학습 파일에는 명세서에서 만든 안내문과 MSDS 원문이 들어 있다. 저장소에 올리지 않는다(.gitignore data/finetune/, D-47).
"""
from __future__ import annotations

import json
import random
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from msds.common import manifest
from msds.common.paths import DATA, ROOT
from msds.common.schema import to_strict, validate
from msds.extract.client import relax_required
from msds.finetune.from_silver import convert_section
from msds.extract.inputs import EXTRACT_SECTIONS, load_document, model_lines, section_lines
from msds.extract.rows import ROWS_SECTIONS_DEFAULT, _tables, parse_qm, parse_rows
from msds.extract.section_prompts import SECTION_PROMPT_VERSION, build_system, build_user, prompt_hash
from msds.extract.section_runner import IMAGE_SECTION, check_section
from msds.extract.section_specs import response_schema

HELD_OUT_PURPOSES = ("개발", "평가")      # 학습에 넣지 않는 manifest 문서 (D-43)
_RAW_NAME = re.compile(r"^(?P<doc>.+)_m(?P<m>\d+)_s(?P<s>\d{2})\.json$")
# ChatClient.call이 json_object·none 방식일 때 안내문 끝에 붙이는 글 (client.py와 같아야 한다. 시험이 확인한다)
SCHEMA_HINT_HEAD = "\n\n[응답 형식] 아래 JSON 스키마를 지키는 JSON 하나만 출력하세요. 설명이나 코드블록 없이 JSON만.\n"
_FENCE_SAFE = str.maketrans({"|": "/", "\n": " ", "\r": " "})


# ── 학생 설정 ──────────────────────────────────────────

@dataclass(frozen=True)
class Student:
    """학습 예시의 모양을 정하는 학생 모델 설정(configs/models.yaml 태그 하나에서 읽는다)."""
    tag: str | None
    rows_sections: tuple[int, ...]
    json_mode: str                     # JSON 항의 첫 구조화 방식
    image_input: bool
    chat_template_kwargs: dict = field(default_factory=dict)

    @classmethod
    def from_config(cls, cfg: dict | None) -> "Student":
        """cfg가 None이면 지금 RNGD 설정과 같은 기본값(행 형식 3·8·9·11·12·14·15항, 공백 없는 JSON, 이미지 없음)."""
        if cfg is None:
            return cls(None, tuple(ROWS_SECTIONS_DEFAULT), "json_schema_compact", False, {})
        params = cfg.get("params") or {}
        ctk = ((params.get("extra_body") or {}).get("chat_template_kwargs")) or {}
        return cls(cfg.get("tag"), tuple(cfg.get("rows_sections") or ()), (cfg.get("structured") or ["none"])[0],
                   bool(cfg.get("image_input")), dict(ctk))

    def is_rows(self, no: int) -> bool:
        return no in self.rows_sections


def system_prompt(no: int, student: Student) -> str:
    """학생이 실제 추출 때 받는 시스템 안내문."""
    rows = student.is_rows(no)
    text = build_system(no, rows)
    if not rows and student.json_mode not in ("json_schema", "json_schema_compact"):
        schema = response_schema(no)
        text += SCHEMA_HINT_HEAD + json.dumps(relax_required(to_strict(schema), schema), ensure_ascii=False)
    return text


# ── 정답 글: 행 형식 ───────────────────────────────────

def _num(v) -> str:
    return json.dumps(v, ensure_ascii=False) if isinstance(v, (int, float)) and not isinstance(v, bool) else str(v)


_QM_KEYS = ("value", "lower_op", "lower", "upper_op", "upper", "unit", "approx")


def qm_text(q: dict | None) -> str:
    """숫자 묶음 → 행 형식 칸 글. 원문 표기(raw)가 있으면 그대로 쓴다.
    없으면 원문 같은 표기('>= 95 %', '10 ~ <20 %')로 다시 쓰고, parse_qm으로 다시 읽어 같은 값이 안 나오는 모양
    (예: 아래 끝이 '>'인 범위)은 rows.parse_qm이 읽는 칸 이름 쌍('lower_op:>,lower:10,...')으로 쓴다."""
    if not q:
        return ""
    if q.get("raw"):
        return str(q["raw"]).strip()
    want = {k: q[k] for k in _QM_KEYS if q.get(k) is not None}
    if not want:
        return ""
    head = "약 " if q.get("approx") else ""
    if q.get("value") is not None:
        body = _num(q["value"])
    elif q.get("lower") is not None and q.get("upper") is not None:
        body = f"{_num(q['lower'])} ~ {'<' if q.get('upper_op') == '<' else ''}{_num(q['upper'])}"
    elif q.get("lower") is not None:
        body = f"{q.get('lower_op') or '>='} {_num(q['lower'])}"
    elif q.get("upper") is not None:
        body = f"{q.get('upper_op') or '<='} {_num(q['upper'])}"
    else:
        body = ""
    text = (head + body + (f" {q['unit']}" if q.get("unit") and body else "")).strip()
    back = parse_qm(text) or {}
    if text and {k: back[k] for k in _QM_KEYS if back.get(k) is not None} == want:
        return text
    return ",".join(f"{k}:{'true' if v is True else _num(v)}" for k, v in want.items())


def _cell(table, col: str, row: dict) -> str:
    kind = table.kinds[col]
    if table.is_object and col == "line":
        ids = [v for v in (row.get("lines") or {}).values() if v]
        v = Counter(ids).most_common(1)[0][0] if ids else None
    else:
        v = row.get(col)
    if v is None or v == [] or v == {}:
        return ""
    if kind == "qm":
        text = qm_text(v)
    elif kind == "pairs":
        text = "; ".join(f"{k}={'true' if x is True else 'false' if x is False else _num(x)}"
                         for k, x in v.items() if x is not None)
    elif kind == "stmts":
        text = "; ".join(f"{s['key']} : {s['value']}" if s.get("key") else str(s.get("value") or "")
                         for s in v if isinstance(s, dict) and (s.get("value") or s.get("key")))
    elif kind == "list":
        text = "; ".join(str(x) for x in v)
    elif kind == "boolean":
        text = "true" if v else "false"
    elif kind in ("number", "integer"):
        text = _num(v)
    else:
        text = str(v)
    return text.translate(_FENCE_SAFE).strip()


def rows_text(parsed: dict, no: int) -> str:
    """중간 형식 응답 → 행 형식 글(rows.rows_guide). 표마다 '### 표' 줄, 행이 있으면 열 이름 줄과 행들.
    쓸 행이 없는 표는 '### 표' 줄만 쓴다(안내문 규칙)."""
    out: list[str] = []
    for t in _tables(no):
        out.append(f"### {t.name}")
        rows = parsed.get(t.name)
        if t.is_object:
            rows = [rows] if isinstance(rows, dict) and any(v is not None for k, v in rows.items() if k != "lines") else []
        rows = [r for r in rows or [] if isinstance(r, dict)]
        if rows:
            out.append(" | ".join(t.columns))
            out += [" | ".join(_cell(t, c, r) for c in t.columns) for r in rows]
    return "\n".join(out)


# ── 정답 글: JSON ──────────────────────────────────────

def _resolve(node: dict, defs: dict) -> dict:
    while True:
        if "$ref" in node:
            node = defs[node["$ref"].rsplit("/", 1)[1]]
        elif "anyOf" in node:
            node = next((b for b in node["anyOf"] if b.get("type") != "null"), node["anyOf"][0])
        else:
            return node


def canonical(value, node: dict, defs: dict):
    """스키마 순서로 칸을 늘어놓고, 필수가 아닌 칸의 null·빈 목록·빈 객체를 뺀 사본."""
    node = _resolve(node, defs)
    if isinstance(value, dict):
        props, req = node.get("properties"), set(node.get("required") or [])
        if not props:
            return {k: v for k, v in value.items() if v is not None}
        out = {}
        for k, sub in props.items():
            if k not in value:
                continue
            v = value[k]
            if v is None or v == [] or v == {}:
                if k in req:
                    out[k] = v
                continue
            out[k] = canonical(v, sub, defs)
        return out
    if isinstance(value, list):
        items = node.get("items") or {}
        return [canonical(v, items, defs) for v in value]
    return value


def json_text(parsed: dict, no: int) -> str:
    schema = response_schema(no)
    return json.dumps(canonical(parsed, schema, schema.get("$defs", {})), ensure_ascii=False, separators=(",", ":"))


def drop_pictograms(parsed: dict) -> dict:
    """이미지를 받지 않는 학생의 2항 정답에서 그림문자를 뺀다(안내문: 이미지가 없으면 pictograms를 쓰지 않는다)."""
    out = json.loads(json.dumps(parsed))
    out.pop("pictograms", None)
    if isinstance(out.get("hazard"), dict):
        out["hazard"].pop("pictograms", None)
        if isinstance(out["hazard"].get("lines"), dict):
            out["hazard"]["lines"].pop("pictograms", None)
    return out


# ── 정답 확인 ──────────────────────────────────────────

def _row_counts(parsed: dict, no: int) -> dict[str, int]:
    return {t.name: len(parsed.get(t.name) or []) for t in _tables(no) if not t.is_object}


def target_problems(target: str, parsed: dict, no: int, rows: bool, allowed: set[str]) -> list[str]:
    """정답 글을 실제 추출과 같은 방법으로 다시 읽어 문제를 돌려준다. 빈 목록이면 학습에 쓴다."""
    schema = response_schema(no)
    if rows:
        back, errors = parse_rows(target, no)
        problems = [f"행 읽기: {e}" for e in errors[:3]]
        if back:
            problems += [f"스키마: {e}" for e in validate(back, schema)[:3]]
            got, want = _row_counts(back, no), _row_counts(parsed, no)
            problems += [f"행 수 다름 {k}: {want[k]} → {got.get(k)}" for k in want if got.get(k) != want[k]]
        else:
            problems.append("행 읽기 결과 없음")
    else:
        try:
            back = json.loads(target)
        except json.JSONDecodeError as e:
            return [f"JSON 읽기: {e}"]
        problems = [f"스키마: {e}" for e in validate(back, schema)[:3]]
    problems += [f"검사: {p}" for p in check_section(back, allowed, no)[:3]]
    return problems


# ── 교사 실행 읽기 ─────────────────────────────────────

@dataclass
class TeacherRun:
    path: Path
    info: dict
    pages_dir: Path

    @classmethod
    def load(cls, path: Path, pages_dir: Path | None = None) -> "TeacherRun":
        path = Path(path)
        info = yaml.safe_load((path / "run_info.yaml").read_text(encoding="utf-8")) or {}
        if pages_dir is None:
            pages_dir = ROOT / info["pages_dir"] if info.get("pages_dir") else DATA / "pages"
        return cls(path, info, Path(pages_dir))

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def model_tag(self) -> str | None:
        return self.info.get("model_tag")

    def records(self):
        """(문서, MSDS 번호, 항, raw 기록). 파일 이름 순서."""
        for f in sorted((self.path / "raw").glob("*.json")):
            m = _RAW_NAME.match(f.name)
            if m:
                yield m["doc"], int(m["m"]), int(m["s"]), json.loads(f.read_text(encoding="utf-8"))

    def doc_ids(self) -> list[str]:
        return sorted({m["doc"] for f in (self.path / "raw").glob("*.json") if (m := _RAW_NAME.match(f.name))})

    def answers(self, doc_id: str, doc, sections: tuple[int, ...]):
        """(MSDS 번호, 항, 기록). 교사 응답을 그대로 쓴다(doc은 쓰지 않는다)."""
        for d, mi, no, rec in self.records():
            if d == doc_id and no in sections:
                yield mi, no, rec

    def describe(self) -> dict:
        return {"run": self.name, "kind": "항목별 실행", "model_tag": self.model_tag, "model": self.info.get("model"),
                "prompt_version": self.info.get("prompt_version"), "pages_dir": str(self.info.get("pages_dir"))}


@dataclass
class SilverSet:
    """묶음 방식 실버·골드 폴더(<문서>.json, 완성 TO21 문서). 근거 원문 조각으로 줄 번호를 되찾아 항별 정답으로 바꾼다."""
    path: Path
    pages_dir: Path
    tag: str | None = None

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def model_tag(self) -> str | None:
        return self.tag or self.path.name

    def doc_ids(self) -> list[str]:
        return sorted(f.name[:-5] for f in Path(self.path).glob("*.json") if f.name.count(".") == 1)

    def load(self, doc_id: str) -> dict:
        return json.loads((Path(self.path) / f"{doc_id}.json").read_text(encoding="utf-8"))

    def answers(self, doc_id: str, doc, sections: tuple[int, ...]):
        data = self.load(doc_id)
        items = data.get("msds") or []
        for mi, item in enumerate(items):
            for no in sections:
                if isinstance(doc, Exception):
                    yield mi, no, {"ok": False, "reason": "입력 없음(쪽 글자)", "errors": [f"{type(doc).__name__}: {doc}"[:120]]}
                elif len(items) != len(doc.msds):
                    yield mi, no, {"ok": False, "reason": "MSDS 건수 다름",
                                   "errors": [f"실버 {len(items)}건, 쪽 글자로 나눈 {len(doc.msds)}건"]}
                else:
                    parsed, problems, notes = convert_section(item, no, doc, mi)
                    yield mi, no, ({"ok": True, "parsed": parsed, "notes": notes} if not problems else
                                   {"ok": False, "reason": "근거 줄 못 찾음", "errors": problems, "notes": notes})

    def describe(self) -> dict:
        engine = None
        for doc_id in self.doc_ids()[:1]:
            engine = ((self.load(doc_id).get("doc") or {}).get("extraction") or {}).get("engine")
        return {"run": self.name, "kind": "묶음 실버·골드", "model_tag": self.model_tag, "model": engine,
                "prompt_version": None, "pages_dir": str(self.pages_dir)}


@dataclass
class BuildResult:
    examples: list[dict]
    dropped: Counter
    drop_samples: dict[str, list[str]]
    excluded_docs: dict[str, str]
    sections: Counter
    tried: Counter = field(default_factory=Counter)     # 문서별로 바꿔 본 항 수
    made: Counter = field(default_factory=Counter)      # 문서별로 예시가 된 항 수
    notes: Counter = field(default_factory=Counter)     # 예시가 된 항에서 이 항이 볼 수 없어 뺀 행·칸(실버·골드)


def _held_out() -> dict[str, str]:
    try:
        rows = manifest.load()
    except FileNotFoundError:
        return {}
    return {r["doc_id"]: r["purpose"] for r in rows if r.get("purpose") in HELD_OUT_PURPOSES}


def build_examples(runs: list, student: Student, sections_dir: Path = DATA / "sections",
                   codes_dir: Path = DATA / "codes", allow_held_out: bool = False,
                   sections: tuple[int, ...] = EXTRACT_SECTIONS, only_docs: set[str] | None = None) -> BuildResult:
    """교사 실행·실버 폴더들 → 학습 예시. 같은 (문서, MSDS, 항)이 여러 곳에 있으면 앞에 준 것을 쓰고,
    그것이 버려졌으면 다음 것을 쓴다. 버린 수는 곳마다 센다. only_docs를 주면 그 문서만 쓴다."""
    held = {} if allow_held_out else _held_out()
    examples, dropped, samples, excluded, used = [], Counter(), {}, {}, set()
    tried, made, notes = Counter(), Counter(), Counter()
    docs: dict[tuple[str, Path], object] = {}
    systems: dict[int, str] = {}

    def drop(reason: str, key: str, detail: str = "") -> None:
        dropped[reason] += 1
        if len(samples.setdefault(reason, [])) < 5:
            samples[reason].append(f"{key} {detail}".strip())

    for run in runs:
        for doc_id in run.doc_ids():
            if only_docs is not None and doc_id not in only_docs:
                continue
            if doc_id in held:
                excluded[doc_id] = held[doc_id]
                continue
            if (doc_id, run.pages_dir) not in docs:
                try:
                    docs[(doc_id, run.pages_dir)] = load_document(doc_id, run.pages_dir, sections_dir, codes_dir)
                except (FileNotFoundError, KeyError) as e:
                    docs[(doc_id, run.pages_dir)] = e
            doc = docs[(doc_id, run.pages_dir)]
            for mi, no, rec in run.answers(doc_id, doc, sections):
                key = f"{doc_id}_m{mi}_s{no:02d}"
                if (doc_id, mi, no) in used:
                    continue
                if no == IMAGE_SECTION and student.image_input:
                    drop("이미지 항(2항) 제외", key)
                    continue
                tried[doc_id] += 1
                if rec.get("reason"):
                    drop(rec["reason"], key, "; ".join(rec.get("errors") or [])[:160])
                    continue
                if not rec.get("ok") or rec.get("check_problems") or not isinstance(rec.get("parsed"), dict):
                    drop("교사 실패·검사 문제", key, "; ".join((rec.get("errors") or rec.get("check_problems") or [])[:1]))
                    continue
                if isinstance(doc, Exception):
                    drop("입력 없음(쪽 글자)", key, f"{type(doc).__name__}: {doc}"[:120])
                    continue
                if mi >= len(doc.msds):
                    drop("입력 없음(쪽 글자)", key, "MSDS 건수가 교사 실행과 다름")
                    continue
                allowed = {l.id for l in section_lines(doc, mi, no)}
                parsed = rec["parsed"]
                if no == IMAGE_SECTION:
                    parsed = drop_pictograms(parsed)
                rows = student.is_rows(no)
                target = rows_text(parsed, no) if rows else json_text(parsed, no)
                problems = target_problems(target, parsed, no, rows, allowed)
                if problems:
                    reason = "줄 번호 다름" if all("원문에 없는 줄 번호" in p for p in problems) else "형식 검사 실패"
                    drop(reason, key, problems[0][:160])
                    continue
                if no not in systems:
                    systems[no] = system_prompt(no, student)
                user = build_user(no, model_lines(doc, mi, no))
                examples.append({
                    "id": key, "doc_id": doc_id, "msds_index": mi, "section": no, "format": "rows" if rows else "json",
                    "teacher": run.model_tag, "teacher_run": run.name,
                    "messages": [{"role": "system", "content": systems[no]},
                                 {"role": "user", "content": "\n".join(p["text"] for p in user if p.get("type") == "text")},
                                 {"role": "assistant", "content": target}],
                })
                used.add((doc_id, mi, no))
                made[doc_id] += 1
                notes.update(" ".join(n.split(" ")[:-1]) for n in rec.get("notes") or [])
    counts = Counter(e["section"] for e in examples)
    return BuildResult(examples, dropped, samples, excluded, counts, tried, made, notes)


def split_by_doc(examples: list[dict], val_ratio: float = 0.1, seed: int = 2026) -> tuple[list[dict], list[dict], list[str]]:
    """문서 단위로 나눈다(같은 문서의 항이 학습·검증에 나뉘면 검증 손실이 낮게 나온다). 반환: (학습, 검증, 검증 문서)."""
    docs = sorted({e["doc_id"] for e in examples})
    n_val = max(1, round(len(docs) * val_ratio)) if len(docs) >= 2 and val_ratio > 0 else 0
    val_docs = sorted(random.Random(seed).sample(docs, n_val))
    train = [e for e in examples if e["doc_id"] not in val_docs]
    val = [e for e in examples if e["doc_id"] in val_docs]
    return train, val, val_docs


def data_info(runs: list, student: Student, result: BuildResult, val_docs: list[str], val: BuildResult | None = None) -> dict:
    """학습 데이터와 함께 둘 기록. 안내문 글은 넣지 않고 판·해시만 남긴다(D-47)."""
    used = sorted({no for no in result.sections})
    return {
        "student_tag": student.tag, "rows_sections": list(student.rows_sections), "json_mode": student.json_mode,
        "image_input": student.image_input, "chat_template_kwargs": student.chat_template_kwargs,
        "prompt_version": SECTION_PROMPT_VERSION,
        "prompt_hashes": {no: prompt_hash(no, student.is_rows(no)) for no in used},
        "teacher_runs": [r.describe() for r in runs],
        "examples": len(result.examples), "sections": dict(sorted(result.sections.items())),
        "yield": {"tried": sum(result.tried.values()), "made": sum(result.made.values()),
                  "by_doc": {d: [result.made[d], result.tried[d]] for d in sorted(result.tried)}},
        "removed_rows": dict(result.notes),
        "dropped": dict(result.dropped), "excluded_docs": result.excluded_docs, "val_docs": val_docs,
        "val_from": "골드(개발 문서)" if val is not None else "학습 문서에서 문서 단위로 뗌",
        "val_yield": [sum(val.made.values()), sum(val.tried.values())] if val is not None else None,
        "val_dropped": dict(val.dropped) if val is not None else None,
    }


def report_md(info: dict, result: BuildResult, n_train: int, n_val: int) -> str:
    y = info["yield"]
    pct = lambda a, b: f"{a}/{b} ({100 * a / b:.0f}%)" if b else "-"  # noqa: E731
    lines = ["# 추출 파인튜닝 학습 데이터", "",
             f"- 학생 설정: {info['student_tag'] or '기본(RNGD와 같음)'} · 행 형식 항 {info['rows_sections']} · JSON 방식 {info['json_mode']}"
             f" · 이미지 {'있음(2항 제외)' if info['image_input'] else '없음(2항 그림문자 뺌)'}",
             f"- 안내문 판 {info['prompt_version']}",
             "- 교사: " + ", ".join(f"{r['run']}({r['kind']}, {r['model'] or r['model_tag']})" for r in info["teacher_runs"]),
             f"- 학습 예시로 바뀐 항: {pct(y['made'], y['tried'])}",
             f"- 예시 {info['examples']}개 = 학습 {n_train} + 검증 {n_val}. 검증: {info['val_from']}"
             + (f" {len(info['val_docs'])}건({', '.join(info['val_docs'])})" if info["val_docs"] else ""),
             "", "| 항 | 예시 |", "|---|---|", *(f"| {k} | {v} |" for k, v in info["sections"].items())]
    if info.get("val_yield"):
        lines += ["", f"검증(골드) 항: {pct(*info['val_yield'])}, 버린 이유 {info['val_dropped']}"]
    lines += ["", "## 문서별로 학습 예시가 된 항", "", "| 문서 | 예시 / 시도 |", "|---|---|",
              *(f"| {d} | {pct(m, t)} |" for d, (m, t) in y["by_doc"].items())]
    lines += ["", "## 버린 예시(항 단위)", "", "| 이유 | 수 |", "|---|---|", *(f"| {k} | {v} |" for k, v in result.dropped.items())]
    for reason, xs in result.drop_samples.items():
        lines += ["", f"### {reason} (앞 5개)", *(f"- {x}" for x in xs)]
    if result.notes:
        lines += ["", "## 예시 안에서 뺀 행·칸 (이 항 호출이 볼 수 없는 값)", "",
                  "이 항 줄 밖: 16항의 작성일처럼 다른 항에 적힌 값. 근거 글 없는 행: 펼치기가 만드는 '미기재' 행 등", "",
                  "| 종류 | 수 |", "|---|---|", *(f"| {k} | {v} |" for k, v in result.notes.most_common())]
    if result.excluded_docs:
        lines += ["", "## 뺀 문서 (manifest 개발·평가, D-43)", *(f"- {d}: {p}" for d, p in sorted(result.excluded_docs.items()))]
    return "\n".join(lines) + "\n"
