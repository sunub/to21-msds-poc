# RunPod 모델 실습

2026-11-03 작성. 모델을 RunPod에 띄우고 백엔드에서 불러 보는 순서다. 팀 문서 `deploy/runpod/README.md`(브랜치 `b/runpod-48g-determinism`, 아직 main에 없음)를 그대로 쓰고, 여기에는 이 컴퓨터의 환경과 주의점만 적는다.

## 먼저 알아야 할 것

- **`RUNPOD_API_KEY`는 팀 공용 계정 키다.** Pod 만들기·지우기와 요금이 이 키로 된다. 계정의 다른 Pod도 지울 수 있다. 공유하거나 올리지 않는다.
- **`pod.py delete`와 콘솔 삭제는 ID를 두 번 확인한다.** `sunub-*` Pod는 팀원 것이다.
- **`pod.py create` 기본 GPU는 RTX PRO 6000($2.49/시간)이다.** 실습에는 콘솔에서 48GB를 고른다.
- **`pod_up.py`는 Pod를 끄지 않는다.** 실습이 끝나면 콘솔에서 지운다. 켜 두면 요금이 계속 나간다.
- 모델 응답에 TO21 문서를 넣는 실습은 Pod가 우리 계정 안에 있어도 D-47 범위를 팀과 확인한다.

## 이 컴퓨터의 환경

| 항목 | 위치 | 비고 |
|---|---|---|
| 실습 작업 공간 | `~/team/to21-runpod` | `b/runpod-48g-determinism`을 그대로 둔 별도 worktree. B 코드와 안 섞인다 |
| 키 | `~/team/to21-runpod/.env` | 권한 600, git 제외. `RUNPOD_API_KEY`, `RUNPOD_VLLM_API_KEY`(새로 만듦), `RUNPOD_VLLM_BASE_URL`(터널), `MSDS_SERVICE_MODEL` |
| 키 원본 | `C:\Users\Admin\Desktop\runpod_lifecycle_script\.env` | 수업 운영용 도구다. 실습에는 쓰지 않는다 |
| SSH 키 | `~/.ssh/id_ed25519` | **공용 계정에 미등록** (2026-11-03 확인). 계정 설정을 바꾸지 말고 Pod를 만들 때 환경 변수 `PUBLIC_KEY`에 `~/.ssh/id_ed25519.pub` 내용을 넣는다. 이 방법은 아직 실행해 보지 않았다 |
| 파이썬 | `~/team/to21-msds-poc/backend/.venv/bin/python` | `backend/`에서 `PYTHONPATH=src`로 실행 |

## 비용 (2026-11-03 조회)

| GPU | 메모리 | 시간당 (Secure / Community) |
|---|---|---|
| RTX A6000 | 48GB | $0.59 / $0.33 |
| A100 80GB | 80GB | $1.79 / $1.19 |
| RTX PRO 6000 | 96GB | $2.49 (팀원 Pod 기준) |

처음 설치에 15~25분이 걸린다. A6000으로 설치와 1시간 실습이면 약 $1이다. 조회 시점 잔액은 $200, 계정 전체 소비는 시간당 $3.09였다.

## 두 가지 방법

**A. 팀 공유 Pod에 붙기 (비용 추가 없음).** 관리자에게 팀원용 주소와 vLLM 키를 받아 `.env`에 넣는다. 이때 `.env`의 `RUNPOD_VLLM_BASE_URL`은 프록시 주소다.

```bash
cd ~/team/to21-runpod/backend
PYTHONPATH=src ~/team/to21-msds-poc/backend/.venv/bin/python scripts/model_check.py --tag qwen36_35b_runpod_48g
```

**B. 내 Pod를 만들기 (서버 띄우기까지 연습).**

1. 콘솔에서 Pod 생성: RTX A6000 48GB, 이미지 기본, 디스크 60GB 이상, TCP 22와 HTTP 8000 공개.
2. 콘솔의 "SSH over exposed TCP" 명령을 복사해 실행한다.

```bash
cd ~/team/to21-runpod/backend
PYTHONPATH=src ~/team/to21-msds-poc/backend/.venv/bin/python scripts/pod_up.py "<접속 명령어>" --tag qwen36_35b_runpod_48g
```

3. 다른 터미널에서 `model_check.py`로 확인한다.
4. **콘솔에서 내 Pod를 지운다.** 지운 뒤 `scripts/pod.py list`로 내 Pod가 없는지 본다.

## 판정 설명까지 돌려 보기

B2 설명은 `qwen36_35b_runpod` 태그를 쓴다. `.env`에 같은 `RUNPOD_VLLM_*`가 있으면 된다. 실제 호출 전에 건수와 시간을 먼저 정한다. 25번 한 건부터 돌려 검사 통과율과 문장틀 대체율을 잰다 (문제 목록 6번, 22번).

## 확인한 것과 못 한 것

- 확인: `pod.py list`가 이 환경에서 동작한다 (읽기 전용). `model_check.py --help` 실행.
- 못 한 것: Pod 생성, `pod_up.py` 실행, 모델 호출. 비용이 들어 실행하지 않았다.
- 못 한 것: 이 worktree에서 `test_B_pod_up.py` 등 시험. conftest가 저장소 밖 `to21/` 자료를 요구해 시작 전에 멈춘다.

## 사용 기록

| 날짜 | Pod | 시간·비용 | 보낸 것 (D-47) | 정리 |
|---|---|---|---|---|
| 2026-11-04 | `to21-b-e2e-qwen36`, L40S 48GB, 보안 클라우드, 이미지 `vllm/vllm-openai:v0.32.0` | 약 70분, 시간당 $1.09 (약 $1.3). RTX 6000 Ada는 자리가 없었다 | 개발용 T21-S016 PDF의 쪽 글자·쪽 이미지(추출 호출), TO21 25번 예제와 개발용 10건의 판정 설명 요청(판정 줄·원인·계산 과정, MSDS 원문 조각, 지식DB 조문 글). 평가용 10건은 보내지 않았다 | 작업 뒤 Pod 삭제(디스크 포함, 볼륨 없음). 2시간 뒤 스스로 지우는 타이머도 넣었다 |

- 만들기는 `pod.create_pod`과 같은 본문에 GPU 후보 여러 개(`gpuTypeIds`, `gpuTypePriority: custom`)를 넣어 REST로 했다. 서버 설정은 `qwen36_35b_runpod_48g`의 `server` 값과 `serve_vllm.sh`의 문법 강제 설정을 그대로 썼다. 뜨기까지 3분 30초였다.
- Pod는 HTTP 8000만 열고 프록시 주소(`https://<Pod>-8000.proxy.runpod.net/v1`)로 붙었다. SSH 키 등록이 필요 없다.

