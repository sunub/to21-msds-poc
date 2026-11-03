# A2 단일 PDF: 추출 결과 저장과 판정 전달

이 단계는 A1의 PostgreSQL 작업자 위에서 실행된다. 추출 결과가 나오면 원본 추출 JSON과 검사 JSON을 `extract.results`에 각각 불변 기록으로 저장한다. PDF 원본과 출력 파일은 그대로 두며, 모델 값이나 오류를 임의로 수정하지 않는다.

## 준비

- A1의 PostgreSQL 설정은 [A1 실행 안내](A1_작업_흐름_실행.md)를 따른다. DB 모드로 켤 때 `extract.jobs`와 `extract.results` 테이블을 확인한다. 대상 DB에 이미 테이블이 있는 경우 기존 내용을 삭제하거나 최초 생성 SQL을 재실행하지 않는다.
- 신규 DB에서는 `backend/migrations/a1_0001_extract_jobs.sql`, `a2_0002_extract_results_reviews_artifacts.sql`, `a2_0003_extract_handoff.sql`을 순서대로 적용한다. 공통 마이그레이션과 권한 설정을 적용하는 환경에서는 팀의 배포 절차를 따른다.
- `docs/contracts/1-handoff.schema.json`과 `common.schema.json` 및 별도로 받은 TO21 v0.6 추출 스키마가 있어야 전달 계약을 검증할 수 있다. TO21 원본과 비밀번호는 Git에 올리지 않는다.

## 추출 결과와 검사

DB 모드에서는 새 PDF의 추출 완료 시 추출 결과와 검사 결과를 함께 저장한다. 같은 실행의 반복 저장은 멱등이며, 실행 토큰이 만료되거나 교체된 작업자의 결과는 게시하지 않는다. 이전 결과는 유지된다.

기존에 완료된 DB 작업은 추출 및 검사 파일이 모두 남아 있다면 다음 API로 저장할 수 있다.

```bash
curl -X POST http://127.0.0.1:8020/api/documents/<작업번호>/results/persist
```

`GET /api/documents/<작업번호>/result`의 `validation`은 스키마 오류, TO21 오류·경고·검증기 예외, 실패 항목과 누락된 항목을 요약한다. `invalid`는 검증 오류 또는 검사 기록 누락이 있다는 뜻이다. 작업의 `done`은 추출 작업 종료를 뜻하며 검증 통과를 의미하지 않는다. 공식 검증 오류는 해당 항목을 식별할 수 있을 때 검수 목록에도 포함한다. 위치를 알 수 없으면 `unmapped_findings`에 보존한다. 기존 결과를 별도로 저장할 때 추출 JSON과 기록된 검증 결과를 재검증해 불일치하면 저장을 거부한다.

`GET /api/documents/<작업번호>/results/stored`는 PostgreSQL에 저장된 현재 실행의 추출·검사 기록을 해시 확인 후 조회한다.

## 판정 전달

결과 저장이 끝난 뒤 아래 API는 현재 완료된 실행의 추출 결과와 검증 기록, 검수 수정분을 `handoff/1` 계약으로 검사하고 `extract.handoff`에 새 불변 전달본을 만든다.

```bash
curl -X POST http://127.0.0.1:8020/api/documents/<작업번호>/handoffs
```

넘김 계약 전체는 `extract.handoff.payload_json`에 저장한다. B2는 이 JSON을 읽어 담당자의 `b2_001`·`judge.judgment` 구현에 연결한다. A의 설치 절차는 B의 판정 테이블을 만들지 않으며, B2 설치와 서비스 시험은 B 담당자의 코드가 올라온 뒤 해당 안내를 따른다.

`fields_total`은 `payload_json` 최상위의 필수 정수이며, A2 검수 보기의 `summary.fields_total`과 같은 기준으로 계산한다. 모든 MSDS의 검수 가능한 칸을 합산하고, 사람이 값을 비운 칸도 총개수에 남긴다. B는 이 값과 `field_status`를 검수 여부·골드 판정에 사용한다. 이전에 발행한 불변 넘김 기록은 수정하지 않으므로, 이 칸이 없는 기록은 위 API로 새 순번을 발행해야 한다.

판정 기준일은 저장된 **실제 추출 완료 시각**의 한국 날짜다. 시각, 모델 설정 해시, 코드 버전, 원문·항별 실행 기록 또는 필요한 계약 파일을 확인할 수 없으면 전달하지 않고 오류를 반환한다. 업로드 때 지정한 기준일이 실제 추출 날짜와 다르면 임의로 바꾸지 않고 전달을 거부한다. 과거에 실행해 모델 설정 해시를 기록하지 않은 결과도 추측하여 전달하지 않는다. 새 추출에는 실제 모델 설정의 해시가 실행 기록에 남는다. 실행 코드를 수정한 상태에서는 기록된 Git 커밋만으로 실제 코드가 일치한다고 보장할 수 없으므로 커밋한 코드에서 서버를 다시 켜고 실행한다.

검증기 오류와 경고는 기록에 남으며, 정합성 판정은 B의 별도 단계다. `source_mismatch`에는 확인된 불일치만 들어가므로 목록이 비어 있어도 모든 근거가 확인됐다고 해석하지 않는다. 이 API는 HTODB 기준 판정을 수행하거나 `judge` 결과를 저장하지 않는다. PostgreSQL 모드에서 저장된 추출 결과를 검수하면 변경 전후 기록이 `extract.reviews`에 남는다. 검수 화면과 넘김은 현재 추출 결과에 연결된 최신 DB 검수 기록을 읽는다. 기존 파일 검수 기록은 첫 DB 검수 때 함께 보존하며, 재실행 전 기록은 이전 결과에 연결된 이력으로 남는다. 파일 모드 검수는 계속 사용한다. 최종 오류 항의 자동 재추출은 아직 연결되지 않았다.

## 검증

`backend/tests/test_a2_final_validation.py`, `test_a2_provenance.py`, `test_a2_results.py`, `test_a2_handoff.py`를 실행한다. PostgreSQL 통합 시험은 `MSDS_TEST_DATABASE_URL`에 별도의 폐기 가능한 테스트 DB를 지정해야 한다. 실제 PDF와 모델을 사용하는 시험은 자동 테스트와 별도로 확인한다.
