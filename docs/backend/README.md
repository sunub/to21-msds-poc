# 백엔드 재설계 문서 색인

세션을 시작할 때 이 파일부터 읽는다. 진행 상태, 문서 우선순위, 남은 일이 여기 있다.

## 문서 우선순위

충돌하면 위가 이긴다. 2026-11-02 사용자 결정. 기준 문서는 팀 공유본인 main의 `docs/superpowers/specs/`에 있다.

1. `docs/superpowers/specs/2026-11-02-backend-pipeline-design.md` (개요), `contracts/6-screens.md` (화면별 데이터)
2. `docs/superpowers/specs/contracts/` (약속 ①~⑤, 구현하며 바꾼 것은 README 7절)
3. `2026-11-02-work-split-design.md` (역할 나누기), `2026-11-02-part-b-judgment-save-design.md` (파트 B 설계)
4. 프론트 목업 (미확정, 화면 참고용. 링크는 사용자에게 받은 것)

기업 기준은 개요 1절의 최신본이다. 정합성은 설계서 v0.4 → 규칙표 v0.3 순이다. GitHub에 새로 올라온 것을 먼저 확인한다 (`git fetch`, PR 목록). 겹치면 비교해 판단하고 `b/decisions.md`에 남긴다.

| 문서 | 내용 | 갱신 규칙 |
|---|---|---|
| `b/open-issues.md` | **우선 해결할 문제** (순위, 상태, 담당) | 해결하면 빼고 결과를 기록 |
| `b/mentoring-followups.md` | 멘토링 전에 우리가 정한 결정과 근거, 법령 대조 결과 | 답이 다르면 고치고 기록 |
| `b/runpod-practice.md` | RunPod 모델 실습 순서, 이 컴퓨터의 환경, 비용, 주의점 | 환경이 바뀌면 고침 |
| `b/handoffs.md` | **다른 역할에 전달할 것** (담당별 목록, 보낼 문구, 상태) | 전달하면 날짜, 끝나면 삭제 |
| `b/troubleshooting.md` | 겪은 문제와 조사 과정 (틀린 가설 포함) | 고칠 때마다 함께 |
| `b/decisions.md` | 결정·미결 기록 (번호, 근거, 정한 사람) | 결정이 생기면 바로 한 줄 |
| `b/traceability.md` | 요구 → 코드 → 시험 추적표 | 작업을 끝낼 때 상태를 고친다 |
| `docs/superpowers/specs/contracts/README.md` | 계약 규칙과 변경 이력 (7절) | 계약을 바꾸면 함께 |

개요 `fcac3a4188fb`, 나누기 `7fa6d03ccd33`, 화면 `b6a427e2da29`. 팀 공유가 끝나면 저장소 사본이 기준이 된다.

## 진행 상태 (2026-11-03)

| 부분 | 상태 |
|---|---|
| 약속 ①~⑤ 스키마 | main 공유본 기준으로 맞춤. 구현하며 바꾼 칸은 README 7절 |
| B1 엔진 | main (#143). 우진(F) 작업은 main에서 합쳐진다. 결정과 남은 차이는 `b/decisions.md` |
| B1 `judge()` | 완료. `compliance/judge.py` |
| B2 판정 서비스 | main (#143, #145). A2 `extract.handoff`(#142)를 읽고, 추출 앱에 붙는다(#144) |
| 화면 연결 | 판정 탭 main (#138). "판정으로 넘기기" 경로만 어긋남 (`b/handoffs.md` 화면) |

작업 공간 `~/team/to21-b`. 작업마다 최신 main에서 새 브랜치를 만든다.

## 시험

```
cd backend && <python> -m pytest -q tests/contracts
```

`<python>`은 `backend/.venv/bin/python`이다. worktree에는 `.venv`가 없으니 `~/team/to21-msds-poc/backend/.venv/bin/python`을 쓴다. worktree에는 `to21/v0.6` 파일과 `deploy/htodb/.env`도 잇는다.

- 계약만: `tests/contracts/test_contract_schemas.py` (DB·구현 불필요, TO21 추출스키마 필요). 견본 `docs/superpowers/specs/contracts/samples/`, 가짜 `tests/contracts/fakes.py`
- `judge()`: `test_3_consistency.py`. 샘플 CSV `to21/v0.4/to21_sample`이 필요하다 (`Msds-test_v0.4/data/to21_sample`을 잇는다). 없으면 건너뛴다.
- B2: `test_b2_service.py`. 로컬 PostgreSQL의 시험 전용 DB `judge_test`를 쓴다.

## 실행

```
python scripts/b2_migrate.py --dev      # judge 스키마와 개발용 extract.handoff
uvicorn --app-dir src msds.api.judge_app:app --port 8011
```

**팀 DB에 judge 설치:** `deploy/htodb/TEAM_SETUP.md` 6절(A 실행기)을 마친 뒤 `backend/`에서 실행한다.

```
python scripts/b2_migrate.py            # judge 스키마, judge_writer 계정, 넘김 읽기 권한
```

- 순서가 중요하다. A 설치 전이거나 A 실행기가 0007(권한 단계)에서 멈춘 DB면 "A 설치가 끝나지 않았습니다"라며 아무것도 바꾸지 않고 멈춘다. A 실행기를 끝까지 마친 뒤 다시 돌린다. 없는 DB는 만들지 않는다(`--dev`만 만든다).
- 넘김 읽기 권한은 A가 만든 `to21_judge` 그룹에 `judge_writer`를 넣어 받는다. `extract`에 직접 권한을 주면 A 실행기가 "스키마가 이력과 다르다"며 멈추기 때문이다(2026-11-03).
- 다시 돌려도 된다. A 실행기도 B 설치 뒤에 다시 돌릴 수 있다. 예전 방식으로 직접 권한이 들어간 DB는 이 명령이 되돌린다.
- `JUDGE_PG_PASSWORD`가 `deploy/htodb/.env`에 없으면 만들어 적는다. 값은 출력하지 않는다.
- 시험: `tests/contracts/test_b2_install.py`가 빈 DB에 이 순서를 그대로 돌린다.

시험용 넘김 API는 `MSDS_JUDGE_TEST_API=1`일 때만 켜진다. 설명 모델은 `MSDS_EXPLAIN_MODEL`의 서버 주소 환경 변수가 있을 때만 호출한다. 없으면 문장틀을 쓴다. 호출 동시 수는 `MSDS_MODEL_MAX_INFLIGHT`.
