"""공유 모델 서버에 붙을 수 있는지 확인한다 (팀원용, SSH 필요 없음).

python scripts/model_check.py [--tag qwen36_35b_runpod_48g]

.env의 주소(base_url_env)와 키(api_key_env)로 다음을 본다. 키는 어디에도 찍지 않는다.
  1. 키가 맞는가, 서버에 닿는가 (Pod가 꺼졌거나 바뀌었으면 여기서 걸린다)
  2. 올라온 모델이 태그의 모델과 같은가
  3. 서버의 최대 길이(max_model_len)가 태그의 server 설정과 같은가 (다르면 경고. 시험 조건이 달라진다)
  4. 한 토큰 생성이 되는가
서버를 띄우고 내리는 일은 관리자가 scripts/pod_up.py로 한다 (deploy/runpod/README.md).
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import urllib.error
from dataclasses import dataclass, field
from urllib.parse import urlparse

from dotenv import load_dotenv

from _common import ROOT
from msds.extract.client import load_model_config
from pod_up import _request

DEFAULT_TAG = "qwen36_35b_runpod_48g"
_ASK_ADMIN = "관리자에게 Pod가 켜져 있는지와 지금 주소를 물어 .env의 RUNPOD_VLLM_BASE_URL을 바꾼 뒤 다시 실행하세요."


@dataclass
class CheckResult:
    ok: bool
    model: str | None = None
    max_model_len: int | None = None
    seconds: float | None = None
    problem: str | None = None
    fix: str | None = None
    warnings: list[str] = field(default_factory=list)


def _root(base_url: str) -> str:
    u = urlparse(base_url)
    return f"{u.scheme}://{u.netloc}/v1"


def check(base_url: str, key: str, cfg: dict, *, request=None) -> CheckResult:
    request = request or _request
    root = _root(base_url)
    env_name = cfg.get("base_url_env", "RUNPOD_VLLM_BASE_URL")
    try:
        served = request(f"{root}/models", key)["data"]
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return CheckResult(False, problem="서버가 키를 받지 않습니다 (401).",
                               fix="관리자에게 지금 vLLM 키를 받아 .env의 RUNPOD_VLLM_API_KEY를 바꾸세요.")
        return CheckResult(False, problem=f"서버가 HTTP {e.code}로 답했습니다. Pod가 꺼졌거나 8000 포트가 공개되지 않았을 수 있습니다.",
                           fix=_ASK_ADMIN.replace("RUNPOD_VLLM_BASE_URL", env_name))
    except OSError as e:
        return CheckResult(False, problem=f"{root}에 닿지 않습니다: {e}",
                           fix="주소가 맞는지 확인하세요. Pod를 바꾸면 주소도 바뀝니다. " + _ASK_ADMIN.replace("RUNPOD_VLLM_BASE_URL", env_name))
    want = cfg["model"]
    entry = next((m for m in served if m.get("id") == want), None)
    if entry is None:
        return CheckResult(False, problem=f"다른 모델이 올라와 있습니다: {[m.get('id') for m in served]} (태그 {cfg.get('tag')}의 모델은 {want})",
                           fix="관리자에게 어떤 태그로 서버를 띄웠는지 물어 --tag를 맞추세요.")
    res = CheckResult(True, model=want, max_model_len=entry.get("max_model_len"))
    expected = (cfg.get("server") or {}).get("max_model_len")
    if expected and res.max_model_len and res.max_model_len != expected:
        res.warnings.append(f"서버의 최대 길이 {res.max_model_len}가 태그 설정 {expected}와 다릅니다. 다른 설정으로 떠 있어 시험 조건이 다를 수 있습니다.")
    t = time.perf_counter()
    try:
        request(f"{root}/chat/completions", key, {"model": want, "max_tokens": 1,
                                                  "messages": [{"role": "user", "content": "1"}]}, timeout=120)
    except (OSError, urllib.error.HTTPError) as e:
        return CheckResult(False, model=want, max_model_len=res.max_model_len, warnings=res.warnings,
                           problem=f"모델은 올라와 있지만 생성에 실패했습니다: {e}", fix="잠시 뒤 다시 실행하고, 계속되면 관리자에게 알리세요.")
    res.seconds = round(time.perf_counter() - t, 1)
    return res


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="공유 모델 서버에 붙을 수 있는지 확인한다 (SSH 필요 없음)")
    ap.add_argument("--tag", default=DEFAULT_TAG, help="configs/models.yaml의 모델 태그")
    args = ap.parse_args(argv)
    load_dotenv(ROOT.parent / ".env")
    cfg = load_model_config(args.tag)
    base_url, key = os.getenv(cfg["base_url_env"]), os.getenv(cfg["api_key_env"])
    missing = [name for name, v in ((cfg["base_url_env"], base_url), (cfg["api_key_env"], key)) if not v]
    if missing:
        print(f"실패: .env에 {', '.join(missing)}가 없습니다. 관리자에게 주소와 키를 받아 넣으세요.", file=sys.stderr)
        return 1
    print(f"확인: {base_url} (태그 {args.tag})")
    res = check(base_url, key, cfg)
    for w in res.warnings:
        print(f"주의: {w}")
    if not res.ok:
        print(f"실패: {res.problem}\n할 일: {res.fix}")
        return 1
    print(f"연결됨: {res.model}, 최대 길이 {res.max_model_len}, 한 토큰 생성 {res.seconds}초")
    return 0


if __name__ == "__main__":
    sys.exit(main())
