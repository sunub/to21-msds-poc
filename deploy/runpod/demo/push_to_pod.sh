#!/bin/bash
# 노트북 → Pod: 코드(git 이력), 화면 빌드, TO21 자료, DB 접속 설정, 지식DB 덤프를 /workspace 로 보낸다. 다시 실행해도 된다.
#   bash deploy/runpod/demo/push_to_pod.sh <포트> <IP>          (demo_pod.py status 가 알려 준다)
# - git 이력은 git bundle 로 보낸다. 같은 PDF 재사용과 판정 넘김이 커밋을 읽어서 없으면 둘 다 실패한다.
#   worktree 체크아웃(.git 이 파일)에서도 된다.
# - Pod 쪽 /workspace/to21 을 지우지 않는다. git reset 은 추적 파일만 바꾸므로 앱 가상환경(backend/.venv), 업로드 자료(data/service),
#   모델 설정(.env)은 그대로 남는다.
# - 함께 보내는 to21/v0.6, deploy/htodb/.env, 지식DB 덤프는 TO21 자료·비밀값이다(D-47). 체험 서버 Pod에만 보낸다.
#   네트워크 볼륨은 chmod·chown 이 듣지 않는다(파일이 666으로 남는다). 체험이 끝나면 볼륨째 지운다.
set -euo pipefail
PORT="$1"; IP="$2"; H="root@$IP"
SSH=(ssh -n -p "$PORT" -o ConnectTimeout=20 "$H"); SCP=(scp -q -P "$PORT")
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"; T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT

echo "[1] 화면 빌드 (Node 24, 같은 출처 API)"
# shellcheck disable=SC1091
[ -s "$HOME/.nvm/nvm.sh" ] && { . "$HOME/.nvm/nvm.sh"; nvm use 24 >/dev/null; }
( cd "$ROOT" && make build > "$T/build.log" 2>&1 ) || { tail -20 "$T/build.log" >&2; exit 1; }

echo "[2] 묶기: git 이력(bundle), 화면·TO21 자료·DB 설정(추적하지 않는 파일)"
git -C "$ROOT" bundle create -q "$T/repo.bundle" HEAD
tar -C "$ROOT" --dereference -czf "$T/extras.tgz" frontend/out to21/v0.6 deploy/htodb/.env   # .env 는 링크일 수 있어 실제 파일을 담는다

echo "[3] 지식DB 덤프 (로컬 to21-htodb-pg-1)"
docker exec to21-htodb-pg-1 pg_dumpall -U kdb --globals-only > "$T/globals.sql"
docker exec to21-htodb-pg-1 pg_dump -U kdb -Fc kdb > "$T/kdb.dump"

echo "[4] 보내고 풀기"
"${SCP[@]}" "$T/repo.bundle" "$T/extras.tgz" "$T/globals.sql" "$T/kdb.dump" "$H:/workspace/" < /dev/null
"${SSH[@]}" 'set -euo pipefail; cd /workspace
  git config --global --add safe.directory /workspace/to21
  if [ -d to21/.git ]; then git -C to21 fetch -q /workspace/repo.bundle HEAD; git -C to21 reset -q --hard FETCH_HEAD
  else git clone -q /workspace/repo.bundle to21; fi
  git -C to21 config core.fileMode false
  tar -xzf extras.tgz -C to21 --no-same-owner
  rm -f repo.bundle extras.tgz
  echo "Pod 코드: $(git -C to21 log --oneline -1), 변경 $(git -C to21 status --short | wc -l)건"'
echo "다음(Pod 안): 처음이면 setup_vllm.sh → pod_app_setup.sh → pod_start.sh / 코드만 바뀌었으면 pod_start.sh RESTART_APP=1"
