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

## 태그별 서버 설정 (48GB 시험대)

`configs/models.yaml`의 태그에 `server` 묶음이 있으면 `pod_up.py`가 그 값으로 vLLM을 띄웁니다. 없으면 A100 80GB에서 쓰던 값(컨텍스트 40960, 동시 64, GPU 메모리 0.85)입니다.

| 이름 | 뜻 |
| --- | --- |
| `max_model_len` | 요청 하나의 최대 토큰 (입력+출력) |
| `max_num_seqs` | 서버가 동시에 처리하는 요청 수 |
| `gpu_memory_utilization` | vLLM이 쓰는 GPU 메모리 비율 |
| `batch_invariant` | 결정적 모드. 함께 처리되는 요청에 상관없이 같은 입력이면 같은 출력 (`VLLM_BATCH_INVARIANT=1`, 베타) |
| `prefix_caching` | 이전 요청의 계산 재사용 |

회사 GPU(48GB급으로 추정)를 대신하는 시험대 태그는 두 개입니다.

```bash
uv run python scripts/pod_up.py "<접속 명령어>" --tag qwen36_35b_runpod_48g        # 기본 모드
uv run python scripts/pod_up.py "<접속 명령어>" --tag qwen36_35b_runpod_48g_det --restart   # 결정적 모드
```

- 띄운 설정은 Pod의 `/workspace/serve_settings`에 남습니다. 다른 설정으로 떠 있는 서버에 붙으려 하면 멈추고 `--restart`를 붙이라고 알려 줍니다. 결정적 모드 시험을 기본 모드 서버로 재는 실수를 막습니다.
- 반복 실행 비교는 `scripts/repeat_runs.py`로 합니다 (같은 문서를 N회 돌려 항별 응답이 같은지 비교).

## 팀이 함께 쓰기 (Pod 1대, 관리자 1명)

```
관리자 ──SSH 터널──▶ Pod의 vLLM :8000 ◀──HTTPS 프록시── 팀원 (주소 + vLLM 키만)
```

| | 관리자 (1명) | 팀원 |
| --- | --- | --- |
| 하는 일 | Pod 만들기·멈추기, `pod_up.py`로 서버 띄우기·`--restart`, vLLM 키 정하기 | `model_check.py`로 확인한 뒤 추출·시험 실행 |
| 필요한 것 | SSH 키, `RUNPOD_API_KEY`(콘솔을 쓰면 없어도 됨), vLLM 키 | 팀원용 주소, vLLM 키 |
| `.env` | `RUNPOD_VLLM_BASE_URL=http://127.0.0.1:18000/v1` (터널) | `RUNPOD_VLLM_BASE_URL=https://<Pod 번호>-8000.proxy.runpod.net/v1` |

팀원 `.env`에 넣는 세 줄:

```bash
RUNPOD_VLLM_BASE_URL=https://<Pod 번호>-8000.proxy.runpod.net/v1   # pod_up.py가 '팀원용 주소'로 찍어 준다
RUNPOD_VLLM_API_KEY=<관리자가 1:1로 전한 vLLM 키>
MSDS_SERVICE_MODEL=qwen36_35b_runpod_48g                            # 추출 서비스(8020)가 쓸 태그
```

```bash
cd backend && uv run python scripts/model_check.py --tag qwen36_35b_runpod_48g   # 팀원: 연결 확인
```

- 팀원용 주소는 Pod 설정에서 **HTTP 포트 8000을 공개**해야 열립니다. TCP 22만 공개하면 관리자 터널만 됩니다.
- `RUNPOD_API_KEY`(계정 키)는 팀원에게 주지 않습니다. Pod 만들기·지우기와 요금이 이 키로 됩니다.
- vLLM 키는 저장소·공개 채널에 올리지 않습니다. 바꾸면 관리자가 `--restart`로 다시 띄우고 팀원 `.env`도 바꿉니다.
- `--restart`는 서버를 내렸다 띄워 모두의 작업이 끊깁니다. 관리자만 씁니다.
- `scripts/b_app.py`(작업 화면)는 각자 자기 컴퓨터에서 점수판·비교용으로만 씁니다. 서버 탭의 Pod 만들기는 공유 Pod와 따로 Pod를 만들고(RTX PRO 6000, 80GB 설정), 이름이 `to21-b-`로 시작하는 Pod를 자기 것으로 보고 20분 쉬면 지우므로 공유 Pod에는 쓰지 않습니다.
- 서버는 동시에 `max_num_seqs`개(48GB 태그 8개)를 처리하고 나머지는 기다립니다. 기다리는 시간도 요청 제한 시간(`run.request_timeout`)에 들어갑니다.
- 기본 모드에서는 여러 사람의 요청이 함께 처리되면 같은 입력이라도 답이 달라질 수 있습니다. 같은 답이 필요하면 결정적 모드 태그로 띄웁니다.

## Pod 바꾸기

Pod 정보는 코드에 없습니다. 접속 명령어와 `.env`의 주소만 바꿉니다.

1. 관리자: 새 Pod를 만듭니다 (48GB, TCP 22·HTTP 8000 공개, 디스크 60GB 이상).
2. 관리자: 새 접속 명령어로 `pod_up.py`를 실행합니다. 설치 15~25분. 끝나면 `Pod: <번호>, GPU …`와 `팀원용 주소`가 찍힙니다.
3. 관리자: 팀원에게 새 팀원용 주소를 알립니다. 키는 그대로 두면 됩니다 (`.env`의 키를 새 Pod에 넣습니다).
4. 팀원: `.env`의 `RUNPOD_VLLM_BASE_URL`을 바꾸고 `model_check.py`로 확인합니다.
5. 관리자: 이전 Pod를 콘솔에서 멈추거나 지웁니다 (켜 두면 요금이 계속 나옵니다).

`pod_up.py`는 GPU 이름과 compute capability를 찍습니다. 결정적 모드 시험 결과는 GPU 세대(예: A6000 8.6, RTX 6000 Ada·L40S 8.9)에 따라 다를 수 있으니 결과에 GPU를 함께 적습니다 (`repeat_runs.py --gpu`).
