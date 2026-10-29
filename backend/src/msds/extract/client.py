"""모델 호출 공통부 (A·B 공용, D-44).

교육원 키(MonoRouter)와 RunPod의 vLLM은 모두 OpenAI 호환 Chat Completions 형식이다.
그래서 같은 코드로 부르고, 모델 이름·주소만 configs/models.yaml에서 바꾼다.

구조화 출력은 설정의 순서대로 시도한다 (기본: json_schema → json_object → none).
- 어떤 방식이 거부되면(400 오류 등) 다음 방식으로 넘어가고, 성공한 방식은 기억해 다음 호출부터 바로 쓴다.
- 어느 방식이든 응답을 JSON으로 읽은 뒤 스키마로 검증하고, 실패하면 오류 내용을 붙여 다시 요청한다.
- structured가 json_schema_compact로 시작하면 처음부터 공백을 막는다. 한도에 걸리면 다음 방식으로 넘어가지 않고 실패로 돌려준다 (ADR-017).
- json_schema 다음이 json_schema_compact이면 json_schema가 출력 한도에 걸릴 때만 압축(공백을 막은 스키마 강제)으로 한 번 더 보낸다 (ADR-017).
- json_schema 다음이 json_object나 none이면 json_schema가 공백 폭주(응답의 절반 이상이 공백)로 한도에 걸릴 때만
  그 방식(문법 강제 없음)으로 한 번 더 보낸다. 넘어간 방식은 기억하지 않는다 (ADR-021).
- request_style: nuextract_template 태그는 시스템 메시지 없이 칸 틀만 보내고, 다시 보내지 않는다 (ADR-010).
- call_text는 표 항목의 행 형식 출력용이다. 구조화 출력 없이 글로 받아 그대로 돌려준다 (ADR-019).
"""
from __future__ import annotations

import base64
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf
import yaml
from dotenv import load_dotenv

from ..common.paths import CONFIGS
from ..common.schema import to_strict, validate
from . import nuextract, nuextract_examples

load_dotenv()


def load_model_config(tag: str) -> dict:
    with open(CONFIGS / "models.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    m = dict(cfg["models"][tag])
    m["tag"] = tag
    m["run"] = cfg.get("run", {})
    return m


@dataclass
class CallResult:
    parsed: dict | None
    raw_text: str
    mode: str | None
    finish_reason: str | None
    usage: dict
    seconds: float
    model: str
    attempts: int
    errors: list[str] = field(default_factory=list)
    requests: list[dict] = field(default_factory=list)   # 받은 응답마다 하나 (_request_record)

    @property
    def ok(self) -> bool:
        return self.parsed is not None and not self.errors


def _shrink_png(data: bytes, max_side: int) -> bytes:
    """긴 변이 max_side 이하가 되게 비율을 지켜 줄인 PNG. 이미 작으면 그대로 돌려준다."""
    pix = pymupdf.Pixmap(data)
    w, h = pix.width, pix.height
    if max(w, h) <= max_side:
        return data
    scale = max_side / max(w, h)
    return pymupdf.Pixmap(pix, max(1, round(w * scale)), max(1, round(h * scale)), None).tobytes("png")


def image_part(path: Path, detail: str = "high", max_side: int | None = None) -> dict:
    """max_side가 있으면 긴 변을 그 값 이하로 줄여 넣는다 (2항 쪽 이미지, ADR-019)."""
    data = Path(path).read_bytes()
    if max_side:
        data = _shrink_png(data, max_side)
    b64 = base64.b64encode(data).decode()
    return {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}", "detail": detail}}


def page_parts(pages: list[dict], input_mode: str, detail: str = "high") -> list[dict]:
    """쪽마다 '=== 쪽 N ===' 표시, 텍스트층 또는 OCR 글(이미지+글자 모드, render.load_pages의 source), 쪽 이미지를 차례로 넣는다."""
    parts: list[dict] = []
    for p in pages:
        header = f"=== 쪽 {p['page']} ==="
        if input_mode == "이미지+글자" and p.get("state") == "정상":
            label = ("[OCR 글: 텍스트층을 믿을 수 없어 쪽 이미지를 OCR로 읽은 글. 오인식이 있을 수 있으니 이미지와 함께 보세요]"
                     if p.get("source") == "OCR" else "[텍스트층]")
            parts.append({"type": "text", "text": f"{header}\n{label}\n{p['text'].strip()}"})
        elif p.get("state") == "정상":   # 이미지만 조건(입력 비교 실험): 읽을 글이 있지만 일부러 뺀 쪽
            parts.append({"type": "text", "text": f"{header}\n[글자 없이 이미지만 보고 읽으세요]"})
        else:
            parts.append({"type": "text", "text": f"{header}\n[텍스트층 없음 또는 깨짐: 이미지만 보고 읽으세요]"})
        parts.append(image_part(p["image"], detail))
    return parts


_TEXT_EDGE = 500   # 요청 기록에 남기는 응답 앞·뒤 글자 수


def _request_record(mode: str, finish: str | None, usage: dict, seconds: float, text: str) -> dict:
    """요청 하나의 기록. 성공해도 앞선 요청이 출력 한도에 걸린 이유(공백 폭주, 진짜 긴 출력)를 볼 수 있게 남긴다."""
    return {"mode": mode, "finish_reason": finish, "usage": usage, "seconds": round(seconds, 3),
            "chars": len(text), "whitespace": sum(c.isspace() for c in text),
            "head": text[:_TEXT_EDGE], "tail": text[_TEXT_EDGE:][-_TEXT_EDGE:]}


def relax_required(strict: dict, schema: dict) -> dict:
    """to_strict(schema)의 결과(strict)에서, properties가 있는 객체마다 required를
    원래 schema의 같은 자리 객체의 required로 되돌린 새 사본.
    원래 객체에 required가 없으면 []. 그 객체의 properties에 없는 이름은 뺀다.
    additionalProperties: false 와 그 밖의 키는 strict 그대로 둔다. $defs 안의 객체도 같다.

    to_strict는 키를 빼기만 하므로, 두 스키마를 같은 키·같은 순번으로 함께 따라가면 같은 자리를 찾는다 (ADR-017)."""
    def walk(s, o):
        if isinstance(s, dict):
            o = o if isinstance(o, dict) else {}
            out = {k: walk(v, o.get(k)) for k, v in s.items()}
            if out.get("type") == "object" and "properties" in out:   # to_strict가 required를 바꾼 객체
                out["required"] = [n for n in o.get("required", []) if n in out["properties"]]
            return out
        if isinstance(s, list):
            o = o if isinstance(o, list) else []
            return [walk(v, o[i] if i < len(o) else None) for i, v in enumerate(s)]
        return s

    return walk(strict, schema)


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.S)


def parse_json(text: str):
    s = _FENCE.sub("", (text or "").strip())
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        # 앞뒤에 설명이 붙은 경우: 가장 바깥 { ... } 만 다시 시도
        a, b = s.find("{"), s.rfind("}")
        if a >= 0 and b > a:
            return json.loads(s[a:b + 1])
        raise


class ChatClient:
    _working_mode: dict[str, str] = {}   # 모델별로 성공한 구조화 출력 방식

    def __init__(self, cfg: dict, model: str | None = None):
        from openai import OpenAI   # 설치 확인을 늦춰, 다른 모듈은 openai 없이도 읽히게 한다

        self.cfg = cfg
        self.model = model or cfg["model"]
        base_url = os.getenv(cfg["base_url_env"])
        api_key = os.getenv(cfg["api_key_env"]) or "EMPTY"
        if not base_url:
            raise RuntimeError(f".env에 {cfg['base_url_env']}가 없습니다.")
        self.client = OpenAI(base_url=base_url, api_key=api_key,
                             timeout=cfg.get("run", {}).get("request_timeout", 600))
        # 출력 길이 한도 이름: 모델에 따라 max_tokens 또는 max_completion_tokens
        self.token_param = cfg.get("token_param", "max_tokens")

    def _request(self, messages, mode, schema_name, strict_schema, max_tokens, template=None, examples=None):
        params = dict(self.cfg.get("params") or {})
        extra_body = params.pop("extra_body", None)
        kw = dict(model=self.model, messages=messages, **params)
        kw[self.token_param] = max_tokens
        if extra_body:
            kw["extra_body"] = extra_body
        if mode == "json_schema":
            kw["response_format"] = {"type": "json_schema",
                                     "json_schema": {"name": schema_name, "schema": strict_schema, "strict": True}}
        elif mode == "json_schema_compact":
            # furiosa-llm은 structured_outputs와 response_format을 함께 받지 않는다 (ADR-017)
            kw["extra_body"] = {**(extra_body or {}),
                                "structured_outputs": {"json": strict_schema, "disable_any_whitespace": True}}
        elif mode == "json_object":
            kw["response_format"] = {"type": "json_object"}
        elif mode == "nuextract_template":
            # NuExtract 2.0은 response_format 대신 대화 틀 인자로 칸 틀을 받는다 (ADR-010)
            eb = extra_body or {}
            ctk = {**(eb.get("chat_template_kwargs") or {}), "template": template}
            if examples:
                ctk["examples"] = examples     # 줄 번호 쓰는 법을 보이는 예시 (ADR-011)
            kw["extra_body"] = {**eb, "chat_template_kwargs": ctk}
        return self.client.chat.completions.create(**kw)

    def call(self, system: str, user_parts: list[dict], schema: dict, schema_name: str,
             max_tokens: int | None = None, require_all: bool = True) -> CallResult:
        """한 묶음 호출. schema는 검증용 원래 스키마(묶음 응답 형식).
        require_all=False면 서버에 보내는 스키마의 필수 칸을 원래 schema의 required로 줄인다.
        모델이 값 없는 칸을 쓰지 않아도 되게 한다 (ADR-017). 검증은 어느 쪽이든 원래 schema로 한다."""
        max_tokens = max_tokens or self.cfg.get("max_tokens", 32000)
        if self.cfg.get("request_style") == "nuextract_template":
            return self._call_nuextract(user_parts, schema, max_tokens, schema_name)
        max_retries = self.cfg.get("run", {}).get("max_retries", 2)
        strict_schema = to_strict(schema)
        if not require_all:
            strict_schema = relax_required(strict_schema, schema)
        modes = list(self.cfg.get("structured") or ["none"])
        known = self._working_mode.get(self.model)
        if known in modes:
            modes = [known] + [m for m in modes if m != known]

        schema_hint = ("\n\n[응답 형식] 아래 JSON 스키마를 지키는 JSON 하나만 출력하세요. 설명이나 코드블록 없이 JSON만.\n"
                       + json.dumps(strict_schema, ensure_ascii=False))
        t0 = time.time()
        errors: list[str] = []
        requests: list[dict] = []
        attempts = 0
        usage: dict = {}
        last_text = ""
        finish = None

        last_parsed = None
        runaway = False    # 공백 폭주로 다음 방식에 넘어왔으면 True. 넘어온 방식은 기억하지 않는다 (ADR-021)
        for i, mode in enumerate(modes):
            sys_text = system if mode in ("json_schema", "json_schema_compact") else system + schema_hint
            messages = [{"role": "system", "content": sys_text},
                        {"role": "user", "content": user_parts}]
            retry = 0
            while retry <= max_retries:
                attempts += 1
                t_req = time.time()
                try:
                    resp = self._call_with_backoff(messages, mode, schema_name, strict_schema, max_tokens)
                except _ModeRejected as e:
                    errors.append(f"[{mode}] 거부됨: {e}")
                    break          # 이 방식은 지원되지 않음 → 다음 방식으로
                if mode != "json_schema_compact" and not runaway:   # 압축 방식은 기억하지 않는다. json_schema 다음에 둔 태그는 한도에 걸린 묶음에만 쓴다 (ADR-017)
                    self._working_mode[self.model] = mode   # 요청이 받아들여진 방식은 기억한다
                choice = resp.choices[0]
                finish = choice.finish_reason
                last_text = choice.message.content or ""
                u = getattr(resp, "usage", None)
                if u is not None:
                    usage = {k: getattr(u, k, None) for k in ("prompt_tokens", "completion_tokens", "total_tokens")}
                requests.append(_request_record(mode, finish, usage if u is not None else {},
                                                time.time() - t_req, last_text))
                if finish == "length":
                    errors.append(f"[{mode}] 출력 길이 한도에 걸려 잘림 (max_tokens={max_tokens})")
                    if mode == "json_schema" and modes[i + 1:i + 2] == ["json_schema_compact"]:
                        break      # 공백을 막아 한 번 더 보낸다 (ADR-017)
                    rec = requests[-1]
                    if (mode == "json_schema" and modes[i + 1:i + 2] in (["json_object"], ["none"])
                            and rec["whitespace"] / max(rec["chars"], 1) >= 0.5):
                        errors.append(f"[{mode}] 공백 폭주로 한도에 걸림 → {modes[i + 1]}으로 다시 보냄")
                        runaway = True
                        break      # 문법 강제 없이 한 번 더 보낸다 (ADR-021)
                    return CallResult(None, last_text, mode, finish, usage, time.time() - t0, self.model, attempts,
                                      errors, requests)
                try:
                    parsed = parse_json(last_text)
                except (json.JSONDecodeError, ValueError) as e:
                    problems = [f"JSON으로 읽을 수 없음: {e}"]
                else:
                    last_parsed = parsed
                    problems = validate(parsed, schema)
                    if not problems:
                        return CallResult(parsed, last_text, mode, finish, usage, time.time() - t0, self.model, attempts,
                                          [], requests)
                retry += 1
                errors.append(f"[{mode}] 검증 실패 {len(problems)}건: " + "; ".join(problems[:5]))
                messages = messages + [
                    {"role": "assistant", "content": last_text},
                    {"role": "user", "content": "응답이 형식에 맞지 않습니다. 아래 문제를 고쳐 JSON 전체를 다시 출력하세요.\n- "
                     + "\n- ".join(problems[:20])},
                ]
            else:
                # 방식은 받아들여졌지만 재시도해도 형식이 맞지 않음: 다른 방식으로 바꿔도 나아지지 않으므로 멈춘다.
                # 읽을 수 있는 JSON이 있으면 넘겨서 쓸 수 있는 부분은 쓰게 한다 (ok=False로 표시됨).
                return CallResult(last_parsed, last_text, mode, finish, usage, time.time() - t0, self.model, attempts,
                                  errors, requests)
        return CallResult(last_parsed, last_text, None, finish, usage, time.time() - t0, self.model, attempts, errors,
                          requests)

    def _call_nuextract(self, user_parts: list[dict], schema: dict, max_tokens: int, schema_name: str) -> CallResult:
        """NuExtract 2.0 호출 (ADR-010). 사용자 글은 뽑을 원문 그대로 보내고, 칸은 틀로만 넘긴다.
        같은 입력·temperature 0이면 같은 응답이 오고 대화 틀이 오류를 붙인 재요청을 받지 않으므로 한 번만 보낸다.
        항 단위 재추출은 실행기가 한다."""
        mode = "nuextract_template"
        messages = [{"role": "user", "content": user_parts}]
        template = json.dumps(nuextract.template(schema), ensure_ascii=False, indent=4)
        m = re.fullmatch(r"sec(\d{2})", schema_name or "")
        no = int(m.group(1)) if m else 0
        examples = [nuextract_examples.example(no)] if 1 <= no <= 16 else None
        t0 = time.time()
        try:
            resp = self._call_with_backoff(messages, mode, None, None, max_tokens, template, examples)
        except _ModeRejected as e:
            return CallResult(None, "", mode, None, {}, time.time() - t0, self.model, 1, [f"[{mode}] 거부됨: {e}"])
        choice = resp.choices[0]
        finish = choice.finish_reason
        text = choice.message.content or ""
        u = getattr(resp, "usage", None)
        usage = ({k: getattr(u, k, None) for k in ("prompt_tokens", "completion_tokens", "total_tokens")}
                 if u is not None else {})
        requests = [_request_record(mode, finish, usage, time.time() - t0, text)]
        parsed, errors = None, []
        if finish == "length":
            errors.append(f"[{mode}] 출력 길이 한도에 걸려 잘림 (max_tokens={max_tokens})")
        else:
            try:
                parsed = nuextract.coerce(parse_json(text), schema)
            except (json.JSONDecodeError, ValueError) as e:
                errors.append(f"[{mode}] JSON으로 읽을 수 없음: {e}")
            else:
                problems = validate(parsed, schema)
                if problems:
                    errors.append(f"[{mode}] 검증 실패 {len(problems)}건: " + "; ".join(problems[:5]))
        return CallResult(parsed, text, mode, finish, usage, time.time() - t0, self.model, 1, errors, requests)

    def call_text(self, system: str, user_parts: list[dict], max_tokens: int | None = None) -> CallResult:
        """구조화 출력 없이 글로 받는다 (행 형식, ADR-019). response_format·structured_outputs를 보내지 않는다.
        응답 글은 raw_text에 두고 parsed는 None이다. 글을 읽고 검증해 다시 보내는 일은 실행기가 한다.
        다시 보내는 것은 연결 오류뿐이고, 그 대기 재시도는 _call_with_backoff가 한다."""
        max_tokens = max_tokens or self.cfg.get("max_tokens", 32000)
        mode = "rows"
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user_parts}]
        t0 = time.time()
        try:
            resp = self._call_with_backoff(messages, mode, None, None, max_tokens)
        except _ModeRejected as e:
            return CallResult(None, "", mode, None, {}, time.time() - t0, self.model, 1, [f"[{mode}] 거부됨: {e}"])
        choice = resp.choices[0]
        finish = choice.finish_reason
        text = choice.message.content or ""
        u = getattr(resp, "usage", None)
        usage = ({k: getattr(u, k, None) for k in ("prompt_tokens", "completion_tokens", "total_tokens")}
                 if u is not None else {})
        requests = [_request_record(mode, finish, usage, time.time() - t0, text)]
        errors = [f"[{mode}] 출력 길이 한도에 걸려 잘림 (max_tokens={max_tokens})"] if finish == "length" else []
        return CallResult(None, text, mode, finish, usage, time.time() - t0, self.model, 1, errors, requests)

    def _call_with_backoff(self, messages, mode, schema_name, strict_schema, max_tokens, template=None, examples=None):
        from openai import APIStatusError, APIConnectionError, RateLimitError

        delay = 5
        for i in range(5):
            try:
                return self._request(messages, mode, schema_name, strict_schema, max_tokens, template, examples)
            except RateLimitError:
                time.sleep(delay); delay *= 2
            except APIConnectionError:
                time.sleep(delay); delay *= 2
            except APIStatusError as e:
                msg = str(e)
                if e.status_code == 400 and "max_tokens" in msg and self.token_param == "max_tokens":
                    self.token_param = "max_completion_tokens"   # 추론 모델은 이름이 다르다
                    continue
                if e.status_code in (400, 404, 422) and mode != "none":
                    raise _ModeRejected(str(e)[:300])
                if e.status_code >= 500:
                    time.sleep(delay); delay *= 2
                    continue
                raise
        raise RuntimeError("API 호출이 계속 실패했습니다 (재시도 5회).")


class _ModeRejected(Exception):
    pass
