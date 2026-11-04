# 체험 서버 (RunPod Pod 1대)

발표 때 심사위원이 각자 기기로 접속해 PDF를 올려 보는 서버다. 구성과 근거는 `docs/backend/b/decisions.md` B-45 "배포 구성". 2026-11-04 L40S Pod에서 같은 구성을 손으로 띄워 외부 주소로 시험했고, 그 절차를 이 스크립트로 옮긴 뒤 같은 Pod에서 다시 실행해 확인했다.

```
심사위원 브라우저 ─HTTPS─▶ RunPod 프록시 ─▶ Apache :8080 (Basic 인증) ─▶ 앱 :8020 (화면 + 추출 + 판정)
                                                                         ├▶ vLLM :8000 (Pod 밖으로 열지 않음)
                                                                         └▶ PostgreSQL :5433 (127.0.0.1)
```

## 처음 한 번

| 단계 | 어디서 | 명령 |
|---|---|---|
| 네트워크 볼륨 150GB | RunPod 콘솔 또는 REST `POST /networkvolumes` | GPU 재고가 있는 데이터센터에 만든다(2026-11-04: US-NC-1) |
| Pod 만들기 | 노트북 | `backend/.venv/bin/python deploy/runpod/demo/demo_pod.py create --volume <볼륨 ID> --dc <데이터센터>` (팀 RunPod 키는 `set -a; . <키가 든 .env>; set +a` 뒤) |
| 접속 정보 | 노트북 | `backend/.venv/bin/python deploy/runpod/demo/demo_pod.py status <Pod ID>` |
| 코드·자료 보내기 | 노트북 | `bash deploy/runpod/demo/push_to_pod.sh <포트> <IP>` |
| vLLM과 모델 받기 | Pod | `cd /workspace && bash to21/deploy/runpod/setup_vllm.sh Qwen/Qwen3.6-35B-A3B-FP8` (5~25분, 볼륨에 남음) |
| 앱 가상환경·DB·Apache | Pod | `bash /workspace/to21/deploy/runpod/demo/pod_app_setup.sh` |
| vLLM·앱 켜기 | Pod | `bash /workspace/to21/deploy/runpod/demo/pod_start.sh` (vLLM 첫 기동 약 7분) |
| 끝까지 시험 | 노트북 | `python3 deploy/runpod/demo/smoke_test.py https://<Pod ID>-8080.proxy.runpod.net <PDF> <비밀번호>` |

비밀번호는 Pod의 `/workspace/web_password`(아이디 `to21`). 발표마다 지우고 `pod_app_setup.sh`를 다시 돌리면 새로 만든다.

## Pod를 멈췄다 켜거나 새로 만들 때

컨테이너 디스크(apt로 깐 PostgreSQL·Apache, DB 데이터)는 Pod를 멈추면 지워진다. 볼륨(`/workspace`)의 모델·vLLM·앱 환경·코드·덤프는 남는다. 그래서 켤 때마다 `pod_app_setup.sh`(지식DB를 덤프에서 복원, 몇 분) → `pod_start.sh` → 시험.

코드만 바뀌었으면 `push_to_pod.sh`(Pod의 앱 가상환경·업로드 자료·설정은 지우지 않는다) → Pod에서 `pod_app_setup.sh`(의존성이 바뀌었으면 가상환경을 맞춘다) → `RESTART_APP=1 bash pod_start.sh`.

전처리는 예전 방식(`MSDS_PREPROCESS=legacy`)으로 띄운다. version17(#172)은 OCR 패키지가 있어야 글꼴 깨짐·스캔 PDF를 처리하는데 체험 서버는 OCR 그룹을 깔지 않는다. OCR을 쓰려면 OCR 가중치와 GPU 메모리(vLLM 0.92면 약 4GB만 남음)를 먼저 확인하고 `UV_SYNC_EXTRA="--group ocr" bash pod_app_setup.sh` → `PREPROCESS= RESTART_APP=1 bash pod_start.sh`(앱이 떠 있으면 다시 켜야 반영된다).

## 오늘 확인한 사실 (2026-11-04, L40S 48GB, Qwen3.6-35B-A3B-FP8 원본)

- 문서 1건(S016 9쪽, S014 7쪽): 업로드부터 PDF 리포트까지 90~100초(추출 77~83초, 판정·설명 9~15초). 이 PR을 만들며 `smoke_test.py`로 잰 값이다.
- 3건 동시 업로드(S016·S014·S013): 동시 추출 1개면 마지막 문서 225초, 3개면 169초. `pod_start.sh`는 3개로 띄운다.
- vLLM 첫 기동(모델 올리기·컴파일)은 약 7분.
- vLLM KV 캐시 207,736토큰, 49k 토큰 요청 기준 최대 동시 4.23개(시작 로그). `models.yaml` 48GB 태그 주석의 8개는 낙관적이었다.
- **같은 PDF 재사용은 직전 결과의 검증 상태가 `invalid`가 아닐 때만** 된다(`worker.py` `_reuse_completed`. `needs_review`는 재사용함). 그 밖에 기준일과 모델 태그·설정 해시·프롬프트 해시·스키마·사전 버전·커밋·rows 설정·이미지 입력이 모두 같아야 한다. S016·S013은 검증 오류로 `invalid`라 매번 새로 추출했고, S014는 실행에 따라 됐다 안 됐다 했다(재사용되면 39초). 미리 돌려 두려면 발표 당일에, 최종 커밋으로 한다. 재사용해도 전처리는 다시 돈다.
- 진행 조회가 가끔 502였다: 앱(uvicorn)이 쉬는 연결을 5초 뒤 닫는데 Apache가 재사용했다. `ProxyPass … disablereuse=On`으로 막았다.
- RunPod 프록시(Cloudflare)는 브라우저가 아닌 기본 요청(파이썬 urllib)을 403(오류 1010)으로 막는다. 시험 스크립트는 브라우저 User-Agent를 보낸다.
- 네트워크 볼륨은 파일 소유자·권한 변경이 안 된다(모두 666). 그래서 PostgreSQL 데이터를 둘 수 없어 DB는 컨테이너 디스크에 두고 켤 때마다 덤프에서 복원한다. 볼륨의 비밀값(vLLM 키, 웹 비밀번호, `.env`)도 권한으로 막히지 않으니 체험이 끝나면 볼륨째 지운다.
- 앱 → 모델은 Pod 안(127.0.0.1)이라 프록시 100초 제한과 상관없다. 브라우저 요청은 업로드 뒤 진행 조회라 짧다.
- 원격으로 Pod 프로세스를 띄울 때 `ssh -n`과 `setsid … < /dev/null &`을 쓰지 않으면 ssh가 끝나지 않는다.

## 모델을 바꿀 때

`models.yaml`에 태그가 있으면 코드 수정 없이 바꾼다: Pod에서 vLLM을 그 모델로 다시 띄우고 `TAG=<태그> MODEL=<모델> bash pod_start.sh`. 파인튜닝 LoRA는 `finetune/serve_lora.sh`가 `to21-ft` 이름으로 붙인다.

## 비용 (2026-11-04 조회, 보안 클라우드)

L40S $1.09/시간(RTX PRO 6000 $2.49, H100 $3.99). 네트워크 볼륨 150GB 약 $0.35/일(멈춰도 과금, 지워야 끝남). 멈춘 Pod에는 GPU 요금이 없다. 끝나면 Pod를 지우고(볼륨은 남김), 발표가 끝나면 볼륨도 지운다.
