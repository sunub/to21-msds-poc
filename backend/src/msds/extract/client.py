"""모델 호출 공통부 (A·B 공용, D-44).

교육원 키(MonoRouter)와 RunPod의 vLLM은 모두 OpenAI 호환 Chat Completions 형식이다.
그래서 같은 코드로 부르고, 모델 이름·주소만 configs/models.yaml에서 바꾼다.

구조화 출력은 설정의 순서대로 시도한다 (기본: json_schema → json_object → none).
- 어떤 방식이 거부되면(400 오류 등) 다음 방식으로 넘어가고, 성공한 방식은 기억해 다음 호출부터 바로 쓴다.
- 어느 방식이든 응답을 JSON으로 읽은 뒤 스키마로 검증하고, 실패하면 오류 내용을 붙여 다시 요청한다.
- RNGD 태그는 json_schema가 출력 한도에 걸리면 json_schema_compact(공백을 막은 스키마 강제)로 한 번 더 보낸다 (ADR-016).
"""
from __future__ import annotations

import base64
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

from ..common.paths import CONFIGS
from ..common.schema import to_strict, validate

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


def image_part(path: Path, detail: str = "high") -> dict:
    b64 = base64.b64encode(Path(path).read_bytes()).decode()
    return {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}", "detail": detail}}


def page_parts(pages: list[dict], input_mode: str, detail: str = "high") -> list[dict]:
    """쪽마다 '=== 쪽 N ===' 표시, 텍스트층(이미지+글자 모드), 쪽 이미지를 차례로 넣는다."""
    parts: list[dict] = []
    for p in pages:
        header = f"=== 쪽 {p['page']} ==="
        if input_mode == "이미지+글자" and p.get("state") == "정상":
            parts.append({"type": "text", "text": f"{header}\n[텍스트층]\n{p['text'].strip()}"})
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

    def _request(self, messages, mode, schema_name, strict_schema, max_tokens):
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
            # furiosa-llm은 structured_outputs와 response_format을 함께 받지 않는다 (ADR-016)
            kw["extra_body"] = {**(extra_body or {}),
                                "structured_outputs": {"json": strict_schema, "disable_any_whitespace": True}}
        elif mode == "json_object":
            kw["response_format"] = {"type": "json_object"}
        return self.client.chat.completions.create(**kw)

    def call(self, system: str, user_parts: list[dict], schema: dict, schema_name: str,
             max_tokens: int | None = None) -> CallResult:
        """한 묶음 호출. schema는 검증용 원래 스키마(묶음 응답 형식)."""
        max_tokens = max_tokens or self.cfg.get("max_tokens", 32000)
        max_retries = self.cfg.get("run", {}).get("max_retries", 2)
        strict_schema = to_strict(schema)
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
                if mode != "json_schema_compact":   # 공백 막기는 출력 한도에 걸린 묶음에만 쓴다 (ADR-016)
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
                        break      # 공백을 막아 한 번 더 보낸다 (ADR-016)
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

    def _call_with_backoff(self, messages, mode, schema_name, strict_schema, max_tokens):
        from openai import APIStatusError, APIConnectionError, RateLimitError

        delay = 5
        for i in range(5):
            try:
                return self._request(messages, mode, schema_name, strict_schema, max_tokens)
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
