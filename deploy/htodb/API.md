# HTODB 조회 API

TO21 지식DB를 읽기만 하는 API입니다. 추출한 코드·CAS 번호를 HTODB 원본과 맞대어 볼 때 씁니다. 테이블 구조는 [ERD.md](ERD.md)를 보세요.

```bash
cd backend && .venv/bin/uvicorn --app-dir src msds.api.htodb_app:app --port 8010   # http://127.0.0.1:8010
```

## 한눈에 보기

| 경로 | 하는 일 |
|---|---|
| `GET /health` | 서버·DB 상태와 적재 버전 |
| `GET /chemicals?cas=` · `?ke=` · `?un=` | 번호로 물질 찾기 |
| `GET /chemicals/{chem_id}` | 물질 한 건 |
| `GET /chemicals/{chem_id}/{part}` | 물질의 분류·독성·물성·규제·노출기준 |
| `GET /codes/{종류}/{code}` | HTODB 코드의 이름·설명 |
| `GET /mapping/hazard?class_code=&category=` | 추출 분류 코드 → HTODB 분류 코드 |
| `GET /mapping/{종류}/{code}` | 그 밖의 추출 코드 → HTODB 코드 |
| `POST /lookup` | 추출 JSON 한 건을 통째로 대조 |

## 공통 규칙

- **응답 모양:** `/health`를 빼면 모두 `{"knowledge_version": "...", "map_version": "...", "data": ...}`입니다. 두 버전은 어느 적재본으로 답했는지 나타내므로, 결과를 저장할 때 함께 남기세요.
- **값:** DB 원본 그대로입니다. 행에는 테이블의 모든 컬럼이 들어 있고, 숫자 컬럼(numeric)은 자릿수를 지키려고 문자열(`"1.000"`)로 옵니다.
- **없는 것:** 없는 물질은 404, 없는 코드는 200에 빈 결과입니다. 번역표에 대응이 없으면 `[]`이고, 비슷한 코드를 골라 주지 않습니다.
- **오류:** `{"detail": "..."}` 형식입니다. 매개변수 형식 오류(필수 값 없음 등)는 `detail`이 목록으로 옵니다.

> 아래 예시 값은 지어낸 것입니다(D-47).

## 물질

### `GET /chemicals`

`cas`, `ke`, `un` 중 **하나만** 줍니다. `limit`은 1~500이고 기본 50입니다.

- CAS: 공백과 특수 하이픈만 정리해서 비교합니다.
- UN: `UN` 접두어와 공백을 무시합니다. `UN1203`, `un 1203`, `1203`은 같은 값입니다.

```json
"data": {"total": 1, "rows": [{"chem_id": "C0000001", "cas_no": "0000-00-0", "chem_name_ko": "예시물질", "...": "..."}]}
```

CAS는 물질마다 하나라서 `cas` 조회는 0건 아니면 1건입니다. `total`이 2 이상인 경우는 `ke`·`un` 조회에서 나옵니다(같은 KE 번호가 여러 물질에 걸린 값 584개, UN 번호 289개). 어느 물질인지는 호출하는 쪽에서 골라야 합니다.

오류: 키를 0개나 2개 이상 주면 422.

### `GET /chemicals/{chem_id}`

`data`는 물질 행 하나(객체)입니다. 없으면 404.

### `GET /chemicals/{chem_id}/{part}`

원본 행(`rows`)과, 그 행들이 쓰는 코드의 이름 사전(`codes`)을 따로 돌려줍니다.

| `part` | `data` |
|---|---|
| `classifications` | `rows`(환경부·고용노동부 분류 모두), `codes{class_result_code: {class_master, hcode_phrase, hcode_phrase_lang}}` |
| `toxicity` | `rows`, `codes{div_code: [...]}`, `parsed`(선택) |
| `physical-properties` | `rows`, `codes{property_id: [...]}`, `parsed`(선택) |
| `regulations` | `rows`(해당 규제 항목), `notice_std`(수치), `notice_content`(글), `notices`(고시), `codes{regulate_item_id: {regulate_item, regulate}}` |
| `exposure-limits` | `rows`(MSDS 8항 노출기준) |

`?parsed=true`는 `toxicity`와 `physical-properties`에만 쓸 수 있습니다. 원본 문장에서 뽑은 숫자를 `rows`와 같은 순서의 `parsed` 목록으로 덧붙입니다(맨 아래 [parsed](#parsed) 참고).

오류:
- 모르는 `part`: 404
- 다른 `part`에 `parsed=true`: 422 (물질이 없어도 이 검사가 먼저입니다)
- 없는 물질: 404

## 코드 이름 찾기 `GET /codes/{종류}/{code}`

| 종류 | `code` 예 | `data` |
|---|---|---|
| `ghs-class` | 분류 결과 코드 | `{class_master, hcode_phrase, hcode_phrase_lang}`: 분류 이름, H코드·신호어·그림문자, H문구 |
| `h` | `H302` | `{hcode_phrase, hcode_phrase_lang, class_master}`: 이 H코드를 쓰는 분류 전부 |
| `div` | `GHS0201` | 독성 구분 행 목록 |
| `property` | `G0907000000` | 물성 항목 행 목록 |
| `regulate-item` | 규제 항목 ID | `{regulate_item, regulate}`: 항목 이름과 그 항목이 속한 법 |

## 추출 코드 번역 `GET /mapping/...`

명세서 `13_TO21DB매핑` 시트를 근거로 번역합니다. 결과는 목록이고, 원소마다 근거 시트 행이 붙습니다.

```json
"data": [{"sheet_row": 20, "sheet_cells": ["ACUTE_TOX", "4", "경구", "", "GHS000000", "", ""], "class_result_code": "GHS000000"}]
```

| 경로 | 입력 (추출 JSON 쪽) | 결과에 붙는 값 |
|---|---|---|
| `/mapping/hazard?class_code=&category=&route_form=&effect=` | `hazard.classes[]` | `class_result_code` |
| `/mapping/pictogram/{code}` | `GHS07` 등 | `symbol` |
| `/mapping/signal-word/{code}` | `위험`, `경고` | `sign_word` |
| `/mapping/property/{code}` | `physchem[].prop_code` | `property_id` |
| `/mapping/endpoint/{code}` | `toxicity[]`·`ecotox[]`의 `endpoint` | `div_codes` (후보 여러 개) |
| `/mapping/regulation/{code}` | `regulations[].item_code` | `regulate_item_id` |

`hazard`를 쓸 때 주의할 점:
- `category`는 시트 값과 정확히 같아야 합니다. 구분이 있는 분류는 `category`를 꼭 줘야 결과가 나옵니다.
- 시트가 `route_form`이나 `effect`로 나눈 분류는 그 값까지 같아야 합니다.
- 분류 결과가 없는 경우는 `class_code=(hazard.classified = false)`로 찾습니다.

오류: `class_code`가 없으면 422, 모르는 종류면 404.

## 일괄 대조 `POST /lookup`

추출 JSON(TO21 스키마) 한 건을 그대로 보내면, 그 안의 코드마다 번역 결과와 HTODB 원본을 돌려줍니다.

```json
"data": [
  {"path": "msds[0].components[0].cas_no", "kind": "cas", "value": "0000-00-0", "seq": 1,
   "lookup_key": "0000-00-0", "chemicals": {"total": 1, "rows": ["..."]}, "details": {"classifications": "...", "...": "..."}},
  {"path": "msds[0].regulations[0].item_code", "kind": "regulation", "value": "NO_SUCH", "comp_ref": "1",
   "mapping": [], "reference": {}}
]
```

| 찾는 위치 (`msds[i]` 안) | `kind` | 붙는 결과 |
|---|---|---|
| `components[].cas_no`, `.ke_no`, `transport[].un_no` | `cas`, `ke`, `un` | `lookup_key`, `chemicals`(`rows`는 앞 50행만 담고 따로 알리지 않습니다. 전체 수는 `total`로 보세요. UN 번호 하나에 2,135개 물질이 걸린 경우도 있습니다). CAS로 물질이 **딱 하나** 찾아지면 `details`(그 물질의 분류·독성·물성·규제·노출기준 전부) |
| `hazard.classes[]`, `hazard.classified=false` | `hazard_class` | `mapping`, `reference`(분류 코드 이름) |
| `hazard.pictograms[].code`, `hazard.signal_word` | `pictogram`, `signal_word` | `mapping` |
| `hazard.h_statements[].code` | `h_code` | `reference` |
| `physchem[].prop_code` | `property` | `mapping`, `reference` |
| `toxicity[].endpoint`, `ecotox[].endpoint` | `endpoint` | `mapping`, `reference` |
| `regulations[].item_code` | `regulation` | `mapping`, `reference` |

- 빈 칸은 건너뜁니다.
- `mapping: []`이면 시트에 대응이 없다는 뜻입니다.

오류: JSON 모양이 틀리면 422이고, 틀린 경로를 알려 줍니다. 예: `"추출 JSON 형식 오류: msds[0].hazard는 객체여야 함"`.

## parsed

`parsed` 목록의 각 원소는 셋 중 하나입니다.
- `null`: 그 행에는 적용할 규칙이 없습니다.
- `{"rule": ..., "result": null}`: 규칙은 있지만 값을 뽑지 못했습니다(자료 부족).
- `{"rule": ..., "result": {...}}`: 뽑은 값입니다.

| `rule` | 대상 | `result` |
|---|---|---|
| `acute` | 급성독성 GHS0201~0205 | `{descriptor, sign, value, value_max, unit, species, basis}`. 범위면 `value`가 최소값. 단위가 맞지 않으면 `sign: "?"` |
| `aquatic_acute` | GHS0311~0314 | `{sign, value, unit: "mg/L"}` |
| `aquatic_chronic_noec` | GHS0325~0328 | `{value, unit: "mg/L"}` ('=' NOEC 중 최소값) |
| `rapid_degradability` | GHS0331 | `{rapidly_degradable: true/false}` |
| `STATE` · `PH` · `BOILING_POINT` · `FLASH_POINT` · `VISCOSITY_40` | 물성 항목 | `{value}`. 성상은 `"기체"`·`"액체"`·`"고체"`, 인화점은 최소값, 점도는 40℃ 동점도만 |

규칙의 세부 내용은 `backend/src/msds/compliance/htodb/parsers.py`에 있습니다.
