"""교육원 키(MonoRouter)·vLLM 서버 점검 (역할 B, 10/25 아침 첫 작업, D-44)

모델마다 아래가 되는지 한 번씩 호출해 표로 보여 준다.
  1) 글자 호출         기본 연결
  2) 이미지 입력       쪽 이미지를 보고 제품명을 읽는지
  3) json_schema      스키마 강제 출력이 받아들여지는지 (안 되면 실버는 json_object 또는 none으로 자동 전환)
  4) json_object      JSON 응답 강제가 받아들여지는지
그리고 남은 크레딧을 조회한다.

사용법
  python scripts/check_router.py                       # gpt, claude
  python scripts/check_router.py --models qwen38       # RunPod vLLM
  python scripts/check_router.py --image data/pages/T21-S016/p001.png
"""
import argparse
import json
import os

import requests

import _common  # noqa: F401
from msds.extract.client import image_part, load_model_config

TINY_SCHEMA = {"type": "object", "additionalProperties": False,
               "properties": {"product_name": {"anyOf": [{"type": "string"}, {"type": "null"}]}},
               "required": ["product_name"]}


def try_call(client, model, cfg, **kw):
    params = dict(cfg.get("params") or {})
    extra = params.pop("extra_body", None)
    tok = cfg.get("token_param", "max_tokens")
    args = dict(model=model, **params, **kw)
    args[tok] = 2000
    if extra:
        args["extra_body"] = extra
    try:
        r = client.chat.completions.create(**args)
        return "성공", (r.choices[0].message.content or "")[:80].replace("\n", " ")
    except Exception as e:  # noqa: BLE001
        return "실패", str(e)[:160]


if __name__ == "__main__":
    from openai import OpenAI

    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="*", default=["gpt", "claude"])
    ap.add_argument("--image", default="data/pages/T21-S016/p001.png")
    a = ap.parse_args()

    key, base = os.getenv("LLM_API_KEY"), os.getenv("LLM_BASE_URL")
    if key and base and "monogpt" in base:
        try:
            r = requests.get(base.rstrip("/") + "/credits", headers={"Authorization": f"Bearer {key}"}, timeout=20)
            print("남은 크레딧:", json.dumps(r.json(), ensure_ascii=False))
        except Exception as e:  # noqa: BLE001
            print("크레딧 조회 실패:", e)

    for tag in a.models:
        cfg = load_model_config(tag)
        client = OpenAI(base_url=os.getenv(cfg["base_url_env"]), api_key=os.getenv(cfg["api_key_env"]) or "EMPTY")
        m = cfg["model"]
        print(f"\n== {tag}: {m}")
        tests = {
            "1) 글자": dict(messages=[{"role": "user", "content": "OK라고만 답하세요."}]),
            "2) 이미지": dict(messages=[{"role": "user", "content": [
                {"type": "text", "text": "이 MSDS 쪽에 적힌 제품명만 답하세요."}, image_part(a.image)]}]),
            "3) json_schema": dict(messages=[{"role": "user", "content": [
                {"type": "text", "text": "이 MSDS 쪽의 제품명을 JSON으로."}, image_part(a.image)]}],
                response_format={"type": "json_schema", "json_schema": {"name": "t", "schema": TINY_SCHEMA, "strict": True}}),
            "4) json_object": dict(messages=[{"role": "user", "content": [
                {"type": "text", "text": '이 MSDS 쪽의 제품명을 {"product_name": ...} JSON으로.'}, image_part(a.image)]}],
                response_format={"type": "json_object"}),
        }
        for name, kw in tests.items():
            status, msg = try_call(client, m, cfg, **kw)
            print(f"  {name:<16} {status}  {msg}")
    print("\n결과를 디스코드에 공유하세요. 3)이 실패해도 실버는 4) 또는 프롬프트 방식으로 자동 전환됩니다.")
