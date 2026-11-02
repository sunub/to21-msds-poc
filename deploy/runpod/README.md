# RunPod에 vLLM 띄우기

RunPod 콘솔의 SSH 접속 명령어(`SSH over exposed TCP`)를 넣으면 설치, 서버 기동, 터널, 응답 확인까지 합니다. `backend/`에서 실행합니다.

```bash
uv run python scripts/pod_up.py "ssh root@<주소> -p <포트> -i ~/.ssh/id_ed25519"
```

되풀이해 실행해도 됩니다. Pod 상태를 보고 필요한 단계만 합니다.

| Pod 상태 | 하는 일 |
| --- | --- |
| 아무것도 없음 | 설치(15~25분) → 서버 기동 → 터널 → 응답 확인 |
| 설치됨, 서버 꺼짐 | 서버 기동 → 터널 → 응답 확인 |
| 설치 또는 기동 중 | 끝나기를 기다림 → 터널 → 응답 확인 |
| 서버 응답함 | 터널 → 응답 확인 |

- 터널이 끊겼거나 Pod 포트가 바뀌면 같은 명령을 새 접속 명령어로 다시 실행합니다.
- `.env`의 키나 모델을 바꿨으면 `--restart`를 붙입니다.
- 모델은 `--tag`로 고릅니다. 기본은 `qwen36_35b_runpod`이고 이름은 `configs/models.yaml`에서 읽습니다.
- `.env`에 `RUNPOD_VLLM_API_KEY`와 `RUNPOD_VLLM_BASE_URL`(예: `http://127.0.0.1:18000/v1`)이 있어야 합니다.
- Pod를 끄거나 지우지 않습니다. 쓰지 않을 때는 콘솔에서 멈춰야 GPU 비용이 멈춥니다.

`setup_vllm.sh`와 `serve_vllm.sh`는 Pod 안에서 도는 스크립트이고, `pod_up.py`가 올려서 실행합니다.
