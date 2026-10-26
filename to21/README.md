# TO21 제공 자료

TO21이 준 스키마·명세서·도구 원본을 두는 폴더다. 코드는 `src/msds/common/paths.py`의 `to21_file()`로만 이 파일들을 읽는다.

## 이 폴더의 파일은 저장소에 올리지 않는다 (결정 D-47, 임시)

TO21 명세서와 스키마에 외부 공유 금지가 표기되어 있다. TO21에 비공개 GitHub 저장소·노션에 두어도 되는지 확인을 요청했고,
답을 받을 때까지는 이 README만 올린다. `.gitignore`가 나머지 파일을 막는다.

- 각자 팀 공유 위치(노션)에서 받아 `to21/v0.5/`에 **원래 파일 이름 그대로** 둔다.
- 파일이 없으면 코드가 이 안내와 함께 멈춘다.
- 허용되면 이 폴더를 저장소에 올리고 이 안내를 지운다.

## 받아 둘 파일 (`to21/v0.5/`)

| 파일 | 쓰는 곳 |
|---|---|
| `TO21_MSDS_추출스키마_v0.5.json` | 모든 결과의 형식 검증 (`common/schema.py`) |
| `TO21_MSDS_추출명세서_v0.5.xlsx` | 프롬프트 생성 (`extract/prompt_builder.py`), 검수 판단 기준 |
| `TO21_MSDS_동의어사전_v0.5.json` | 프롬프트 생성, 정규화 |
| `TO21_MSDS_검증기_v0.5.py` | 자동 검사 (`checks/validator.py`) |
| `TO21_MSDS_채점기_v0.5.py` | 채점 (`evaluate/score.py`) |
| `TO21_MSDS_추출예제_25_황산_v0.5.json` | 25번 정답, 형식 시험 (프롬프트 조정에 쓰지 않음, D-43) |
| `TO21_MSDS_DB적재_재생성_v0.5.py` | 평가 2단계 (2주차 이후) |
| `TO21_MSDS_커버리지점검_v0.5.py` | 평가 3단계 (2주차 이후) |
| `TO21_MSDS_PoC_작업가이드_v0.5.pptx`, `TO21_MSDS_PoC_작업기록_20261022.md`, `T21-025_재생성MSDS_예시_v0.5.html` | 참고 자료 |

## 규칙

- TO21 원본은 고치지 않는다. 공식 채점 기준이기 때문이다.
- 새 버전이 오면 `to21/v0.6/`처럼 폴더를 추가하고, `paths.py`의 `TO21`과 `TO21_FILES`만 바꾼다.

확인 방법: `python -c "import sys; sys.path.insert(0,'src'); from msds.common.paths import TO21_FILES, to21_file; [to21_file(k) for k in TO21_FILES]; print('ok')"`
