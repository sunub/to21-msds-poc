"""RunPod REST 도구 (Pod 목록·조회·만들기·지우기). 키는 .env의 RUNPOD_API_KEY에서만 읽고 출력하지 않는다.

python scripts/pod.py list | volumes | get <id> | delete <id> | create --start-cmd-file <파일> --vllm-key-file <파일> [--name to21-b-qwen36]
"""
import argparse
import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Mapping

from dotenv import load_dotenv

import _common  # noqa: F401  src 경로 등록

load_dotenv()

API = "https://rest.runpod.io/v1"
USER_AGENT = "to21-b-pod/1.0"   # 없으면 403이 난다 (10/28 확인)
POD_FIELDS = ("id", "name", "desiredStatus", "costPerHr", "imageName", "gpuCount", "lastStatusChange", "lastStartedAt")
# lastStatusChange의 JS 날짜 글. 예: "Rented by User: Fri Jul 12 2024 15:14:40 GMT-0400 (Eastern Daylight Time)"
_JS_DATE = re.compile(r"\b[A-Z][a-z]{2} ([A-Z][a-z]{2}) (\d{1,2}) (\d{4}) (\d{2}):(\d{2}):(\d{2}) GMT([+-]\d{4})")
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def api_key(env: Mapping[str, str] | None = None) -> str:
    key = (os.environ if env is None else env).get("RUNPOD_API_KEY")
    if not key:
        raise SystemExit("RUNPOD_API_KEY 없음")
    return key


def request(method: str, path: str, body=None, *, opener=None, env: Mapping[str, str] | None = None):
    headers = {"Authorization": f"Bearer {api_key(env)}", "Content-Type": "application/json", "User-Agent": USER_AGENT}
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data, method=method, headers=headers)
    try:
        with (opener or urllib.request.urlopen)(req, timeout=30) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8", "replace")[:200] if hasattr(e, "read") else ""
        raise RuntimeError(f"RunPod HTTP {e.code}: {text}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"RunPod 연결 오류: {type(e.reason).__name__}") from None
    return json.loads(raw) if raw else None


def list_pods(*, opener=None, env=None) -> list[dict]:
    pods = request("GET", "/pods", opener=opener, env=env) or []
    return [{k: p.get(k) for k in POD_FIELDS} for p in pods]


def get_pod(pod_id, *, opener=None, env=None) -> dict:
    return request("GET", f"/pods/{pod_id}", opener=opener, env=env)


def delete_pod(pod_id, *, opener=None, env=None) -> None:
    request("DELETE", f"/pods/{pod_id}", opener=opener, env=env)


def list_volumes(*, opener=None, env=None) -> list[dict]:
    vols = request("GET", "/networkvolumes", opener=opener, env=env) or []
    return [{k: v.get(k) for k in ("id", "name", "size")} for v in vols]


def create_pod(start_cmd: str, vllm_key: str, *, name="to21-b-qwen36",
               gpu="NVIDIA RTX PRO 6000 Blackwell Server Edition", image="vllm/vllm-openai:v0.32.0",
               disk_gb=100, opener=None, env=None) -> str:
    body = {"name": name, "imageName": image, "cloudType": "SECURE", "gpuCount": 1, "gpuTypeIds": [gpu],
            "containerDiskInGb": disk_gb, "volumeInGb": 0, "ports": ["8000/http"],
            "env": {"VLLM_API_KEY": vllm_key}, "dockerEntrypoint": ["bash", "-c"], "dockerStartCmd": [start_cmd]}
    return request("POST", "/pods", body, opener=opener, env=env)["id"]


def pod_url(pod_id) -> str:
    return f"https://{pod_id}-8000.proxy.runpod.net/v1"


def _parse_time(s) -> datetime | None:
    """ISO(끝의 Z 포함), "2024-07-12 19:14:40 +0000 UTC", JS 날짜 글(앞말 있어도 됨)을 받는다. 못 읽으면 None."""
    if not s:
        return None
    s = str(s).strip()
    m = _JS_DATE.search(s)
    if m and m[1] in _MONTHS:                         # 달 이름은 영어 고정이라 strptime(%b, 로캘을 탄다)을 쓰지 않는다
        mon, day, year, hh, mm, ss, tz = m.groups()
        try:
            return datetime(int(year), _MONTHS.index(mon) + 1, int(day), int(hh), int(mm), int(ss),
                            tzinfo=datetime.strptime(tz, "%z").tzinfo)
        except ValueError:
            return None
    if s.endswith(" UTC"):
        s = s[:-4]
    for fmt in ("%Y-%m-%d %H:%M:%S.%f %z", "%Y-%m-%d %H:%M:%S %z"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    try:
        t = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _cost(v) -> float | None:
    """costPerHr는 숫자나 글자("0.74")로 온다."""
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def brief(pod: dict, *, now: datetime | None = None) -> dict:
    """Pod 요약. 켜진 시각은 lastStartedAt을 먼저, 못 읽으면 lastStatusChange. uptime_s(초)·cost_est(=est_cost)는 시각을 못 읽으면 None."""
    now = now or datetime.now(timezone.utc)
    cost = _cost(pod.get("costPerHr"))
    raw = next((pod.get(k) for k in ("lastStartedAt", "lastStatusChange") if _parse_time(pod.get(k))), None)
    started = _parse_time(raw)
    uptime = max(0, int((now - started).total_seconds())) if started else None
    minutes = round((now - started).total_seconds() / 60, 1) if started else None
    est = round(cost * minutes / 60, 2) if cost is not None and minutes is not None else None
    return {"id": pod.get("id"), "name": pod.get("name"), "status": pod.get("desiredStatus"), "cost_per_hr": cost,
            "started": raw if started else pod.get("lastStatusChange"), "minutes": minutes, "est_cost": est,
            "uptime_s": uptime, "cost_est": est}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="RunPod REST 도구")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="Pod 목록")
    sub.add_parser("volumes", help="네트워크 볼륨 목록")
    sub.add_parser("get", help="Pod 하나").add_argument("id")
    sub.add_parser("delete", help="Pod 지우기").add_argument("id")
    c = sub.add_parser("create", help="Pod 만들기 (과금 시작)")
    c.add_argument("--start-cmd-file", required=True)
    c.add_argument("--vllm-key-file", required=True)
    c.add_argument("--name", default="to21-b-qwen36")
    a = ap.parse_args(argv)
    if a.cmd == "list":
        print(json.dumps(list_pods(), ensure_ascii=False))
    elif a.cmd == "volumes":
        print(json.dumps(list_volumes(), ensure_ascii=False))
    elif a.cmd == "get":
        print(json.dumps(brief(get_pod(a.id)), ensure_ascii=False))
    elif a.cmd == "delete":
        delete_pod(a.id)
        print(f"deleted {a.id}")
    elif a.cmd == "create":
        with open(a.start_cmd_file, encoding="utf-8") as f:
            start_cmd = f.read().strip()
        with open(a.vllm_key_file, encoding="utf-8") as f:
            key = f.read().strip()
        print(create_pod(start_cmd, key, name=a.name))


if __name__ == "__main__":
    main()
