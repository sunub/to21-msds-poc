# C(전처리) 작업 정리 — 2026-10-29

## 오늘 한 일 요약

1. 로컬 저장소에 이미 구현돼 있던 C(전처리) 담당 코드를 항목별로 전부 확인 (코드 존재 여부만 보던 것에서 실행 검증으로 전환)
2. 테스트 스위트 전체 실행으로 동작 검증 (17개 전부 통과)
3. 모델(B) 쪽에서 보고된 "표 안 공백 문제"의 원인을 찾아 수정
4. TO21 동의어 사전 v0.6을 항목 제목 매칭에 실제로 연결

## 방법: 어떻게 확인했나

- `git log`, `git branch -a`가 비어 있어 커밋된 작업이 하나도 없는 상태였음 → 코드가 "있다"와 "검증됐다"를 구분하기 위해, 파일 존재 확인에 멈추지 않고 실제로 `pytest`를 돌려 동작을 확인함
- `backend/src/msds/preprocess/`, `backend/src/msds/checks/` 아래 각 모듈을 읽고, 대응하는 테스트(`backend/tests/test_c_pipeline.py`, `test_C_checks.py`, `test_validator.py`, `test_c_to_b_contract.py`, `test_preprocess.py`)를 실행
- 과거 작업 정리 문서(공유 아티팩트)에 있던 "`test_preprocess.py`가 `data/pages`를 덮어쓴다"는 경고를 실제 코드로 재확인 → 지금 버전은 `manifest.csv`만 읽는 읽기 전용 테스트로, 해당 경고는 더 이상 유효하지 않음을 확인
- "표 안 공백 문제"는 `to21/v0.6/TO21_MSDS_동의어사전_v0.6.json`을 직접 열어 구조(`sections`, `headings` 등)와 `note` 필드("비교 시 공백·구두점·가운뎃점 제거 후 일치 검사")를 확인한 뒤, 기존 `c_pipeline.py`의 `SECTION_TITLES`가 항목당 변형 1개짜리 하드코딩이라 공백 표기가 다른 문서에서 매칭이 깨졌던 것을 발견

## 확인 결과: 항목별 구현 상태

| 항목 | 상태 | 위치 |
|---|---|---|
| 입력 판별과 형식 변환 | 일부만 — PDF만 처리, HWP·DOCX·XLS 변환 코드 없음 | `backend/src/msds/preprocess/render.py` |
| 글자 만들기 (텍스트층 판별, 표 행 묶기) | 완료, 테스트 통과 | `render.py`, `c_pipeline.py: group_rows` |
| 항목 분할 + 다중 MSDS 분리 | 완료, 테스트 통과 | `c_pipeline.py: split_sections, detect_section_header` |
| 코드 추출기 (H·P코드, CAS, UN번호) | 완료, 테스트 통과 | `c_pipeline.py: extract_codes` |
| 원문 대조 | 완료, 테스트 통과 | `backend/src/msds/checks/source_match.py` |
| TO21 검증기 연결 | 완료, 테스트 통과 | `backend/src/msds/checks/validator.py` |
| TO21 동의어 사전 v0.6 연결 | **오늘 수정** | `c_pipeline.py: SECTION_TITLES` |

## 오늘 수정한 버그: 표 공백 문제

**증상**: 모델(B) 쪽에서 표 안 공백 차이로 문제가 생긴다고 보고됨.

**원인**: `c_pipeline.py`의 `SECTION_TITLES`가 항목(1~16항)마다 한국어 표제 1개 + 영어 표제 1개만 하드코딩돼 있었음. 반면 `to21/v0.6` 동의어 사전에는 항목별로 공백·가운뎃점·표기가 다른 변형이 최대 7개까지 등록돼 있고, 사전 자체 `note`에 "비교 시 공백·구두점·가운뎃점 제거 후 일치 검사"라고 명시돼 있었음. 즉 사전이 있는데도 코드에서 안 쓰고 있어서, 사전에 등록된 변형과 다르게 쓰인 문서(예: "화학제품과 제조회사 정보")는 항목 분할이 실패할 수 있었음.

**수정**: `_load_section_titles()`를 추가해 `to21/v0.6/TO21_MSDS_동의어사전_v0.6.json`의 `sections`를 런타임에 읽어 `SECTION_TITLES`를 구성하도록 변경. 사전을 못 읽을 경우에는 영어 표제 1개로 폴백해서 완전히 깨지지는 않게 함.

**검증**: 사전 로드 후 항목 2(유해성·위험성)에 변형 8개(사전 7개 + 영어 1개)가 들어오는 것, 그리고 "화학제품과 제조회사 정보" 같은 변형 표기도 항목 1로 정상 매칭되는 것을 직접 실행해 확인함.

## 남은 일

- HWP·DOCX·XLS → PDF 변환 코드가 아직 없음 (입력 판별·형식 변환 항목의 핵심 미완 부분)
- 표 안 "필드 라벨" 수준(예: 사전의 `headings` 리스트에 있는 "예방조치문구"/"예방조치 문구")에서도 공백 문제가 나는지는 아직 미확인 — B가 구체적으로 어느 문서·어느 필드에서 깨졌는지 알려주면 추가로 반영 필요
- 실제 20개 문서(`data/manifest.csv`) 전체로 파이프라인을 끝까지 돌려 결과를 검증하는 작업은 아직 안 함
- 지금까지 모든 작업이 로컬에만 있고 커밋된 적이 없음 — 검증이 끝났으니 커밋 여부를 결정해야 함

## 테스트 결과

```
17 passed in 0.91s
```

실행 범위: `backend/tests/` 전체 (`test_C_checks.py`, `test_boundary.py`, `test_c_pipeline.py`, `test_c_to_b_contract.py`, `test_preprocess.py`, `test_validator.py`)
