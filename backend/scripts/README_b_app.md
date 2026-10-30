# B 작업 화면 (개발 전용)

모델 실행의 점수·비교·원문 대조·시험·서버 관리를 한 화면에서 하는 작은 웹 앱이다.
ADR-025 참고. 쓰는 법은 앱의 "도움말" 탭(`b_app_static/guide.html`)에 있다.

## 켜기
```
(cd backend && .venv/bin/python scripts/b_app.py)   # 127.0.0.1 에서만 열린다
```

## 파일
- `b_app.py`: 서버(표준 `http.server`)와 라우트. 탭 5개의 API와 정적 파일을 준다.
- `b_app_runs.py`: `runs/` 읽기·채점(F의 `score_set`)·호출 격자·한도 분류·값 없는 행 뺀 점수·합격 기준.
- `b_app_diff.py`: 두 실행 비교, 하락 원인 문장, 안내문 버전 차이.
- `b_app_doc.py`: 쪽 글자 줄·그림 좌표, 결과 값↔줄↔실버 맞추기.
- `b_app_jobs.py`: 시험·본 실행·비교표를 하위 프로세스로 시작·중단하고 로그를 읽는다.
- `b_app_servers.py`: 모델 서버 상태, RunPod Pod·RNGD 모델 올리기·내리기(확인 토큰 2단계).
- `pod.py`: RunPod REST 도구(list·get·create·delete). 명령줄로도 쓴다.
- `try_section.py`: 항 하나·여러 개·문서 전체를 모델에 보내 단계별로 보여 준다.
- `b_app_static/`: `index.html`, `app.js`, `app.css`, `guide.html`(외부 주소 없음).

## 시험
```
(cd backend && .venv/bin/python -m pytest -q --ignore=tests/test_preprocess.py)
```
시험은 모델 서버·네트워크를 부르지 않는다. `test_preprocess.py`는 실제 `data/pages/`를 덮어쓰므로 뺀다.

## 보안 규칙
- 서버는 127.0.0.1에만 묶고 다른 Host·Origin 요청은 거부한다.
- 키(`.env`의 RUNPOD_API_KEY, 모델 서버 키 등)는 화면·로그·기록에 쓰지 않는다. 변수 이름만 문서에 적는다.
- 쪽 그림·쪽 글자·안내문은 요청 때 읽어 보여 줄 뿐 파일로 저장하지 않는다(D-47). 평가용 문서는 받지 않는다(D-43).
