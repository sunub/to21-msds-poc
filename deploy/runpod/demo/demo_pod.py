"""체험 서버 Pod 만들기·상태·지우기 (노트북에서, RunPod REST). 키는 저장소 최상위 .env 의 RUNPOD_API_KEY 에서만 읽고 출력하지 않는다.

  backend/.venv/bin/python deploy/runpod/demo/demo_pod.py stock                         # 볼륨 데이터센터의 GPU 재고
  backend/.venv/bin/python deploy/runpod/demo/demo_pod.py create --volume <볼륨 ID>      # Pod 만들기(과금 시작)
  backend/.venv/bin/python deploy/runpod/demo/demo_pod.py status <Pod ID>               # SSH 주소·외부 주소
  backend/.venv/bin/python deploy/runpod/demo/demo_pod.py delete <Pod ID>               # Pod 지우기(볼륨은 남음)

- 네트워크 볼륨에 모델·환경·코드를 둔다. Pod를 지워도 남고, 같은 데이터센터의 아무 GPU Pod에 다시 붙인다(2026-11-04 B-45).
- 포트는 만들 때 정한다(켜진 Pod를 고치면 초기화된다): 8080/http(Apache, 심사위원), 22/tcp(SSH).
- GPU는 후보 순서대로 시도한다(gpuTypePriority custom). 재고는 수시로 바뀐다.
"""
import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend" / "scripts"))
import pod  # noqa: E402  (REST 요청·키 처리 재사용)

GPUS = ["NVIDIA L40S", "NVIDIA RTX 6000 Ada Generation", "NVIDIA H100 80GB HBM3", "NVIDIA A100-SXM4-80GB", "NVIDIA A100 80GB PCIe"]
IMAGE = "runpod/pytorch:1.5.0-cu1281-torch280-ubuntu2404"


def env():
    from dotenv import dotenv_values
    # 셸에 export 한 값이 먼저다. 팀 RunPod 키를 다른 .env 에 둔 경우 `set -a; . <그 .env>; set +a` 뒤에 실행한다
    return {**dotenv_values(Path(__file__).resolve().parents[3] / ".env"), **os.environ}


def stock(e, dc):
    q = json.dumps({"query": "query { dataCenters { id gpuAvailability { gpuTypeId available } } }"}).encode()
    req = urllib.request.Request("https://api.runpod.io/graphql", q, {"Content-Type": "application/json", "Authorization": f"Bearer {e['RUNPOD_API_KEY']}", "User-Agent": pod.USER_AGENT})
    for d in json.load(urllib.request.urlopen(req, timeout=30))["data"]["dataCenters"]:
        if d["id"] == dc:
            return [x["gpuTypeId"] for x in d.get("gpuAvailability") or [] if x.get("available") and x["gpuTypeId"] in GPUS]
    return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["stock", "create", "status", "delete"])
    ap.add_argument("pod_id", nargs="?")
    ap.add_argument("--volume", help="네트워크 볼륨 ID")
    ap.add_argument("--dc", default="US-NC-1", help="볼륨이 있는 데이터센터")
    ap.add_argument("--name", default="to21-b-demo")
    a = ap.parse_args()
    e = env()
    if a.cmd == "stock":
        print(a.dc, stock(e, a.dc) or "재고 없음")
    elif a.cmd == "create":
        if not a.volume:
            sys.exit("--volume 이 필요하다")
        body = {"name": a.name, "imageName": IMAGE, "cloudType": "SECURE", "gpuCount": 1, "gpuTypeIds": GPUS,
                "gpuTypePriority": "custom", "dataCenterIds": [a.dc], "networkVolumeId": a.volume, "volumeMountPath": "/workspace",
                "containerDiskInGb": 50, "ports": ["8080/http", "22/tcp"], "supportPublicIp": True,
                "env": {"PUBLIC_KEY": Path("~/.ssh/id_ed25519.pub").expanduser().read_text().strip()}}
        p = pod.request("POST", "/pods", body, env=e)
        print(f"Pod {p['id']} 시간당 ${p.get('costPerHr')} — status 로 SSH 주소를 본다")
    elif a.cmd == "status":
        g = pod.request("GET", f"/pods/{a.pod_id}", env=e)
        ssh = (g.get("portMappings") or {}).get("22")  # 막 만든 Pod는 null
        print(f"{g.get('desiredStatus')} 시간당 ${g.get('costPerHr')}")
        print(f"SSH: ssh -p {ssh} root@{g.get('publicIp')}" if ssh else "SSH: 아직 없음")
        print(f"외부: https://{a.pod_id}-8080.proxy.runpod.net")
    else:
        g = pod.request("GET", f"/pods/{a.pod_id}", env=e)
        if not (g.get("name") or "").startswith("to21-b-demo"):
            sys.exit(f"체험 서버 Pod가 아니라 지우지 않는다: {g.get('name')}")
        pod.request("DELETE", f"/pods/{a.pod_id}", env=e)
        print(f"Pod {a.pod_id} 삭제 (볼륨은 남음)")


if __name__ == "__main__":
    main()
