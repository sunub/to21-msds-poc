# 파트 사이 계약 (JSON Schema)

작성 2026-11-02 · 상태: 승인 전 · 나누기: `../2026-11-02-work-split-design.md`

추출 데이터는 모두 **TO21 추출스키마 v0.6**(`$id https://to21.co.kr/schema/msds-extraction/v0.6`)을 `$ref`로 그대로 쓴다. 정합성검증 설계서 v0.4가 입력을 "추출 JSON v0.5"로 적은 곳도 v0.6으로 읽는다 (v0.6은 v0.5와 하위 호환, 작업기록 2026-10-26). 판정 결과 모양은 설계서 v0.4를 따른다.

## 1. 파일과 주인

| 파일 | 약속 (나누기 문서 3절) | 쓰는 쪽 → 읽는 쪽 | 주인 |
|---|---|---|---|
| `common.schema.json` | 공용 정의 (작업 번호, 칸 경로, 판정·심각도·원인 코드, 지식 버전, TO21 Q·class_code 참조) | 모두 | 네 명 같이 |
| `1-handoff.schema.json` | ① 넘김 기록 | A2 → B2 | A2 |
| `2-job-event.schema.json` | ② 단계 함수의 진행 이벤트 | A2 → A1 | A1 |
| `3-consistency.schema.json` | ③ `judge()` 결과 (판정 + trace) | B1 → B2 | B1 |
| `4-explanation.schema.json` | 설명 요청·모델 응답·저장 (B2 안쪽, 설계서 v0.4 안전장치) | B2 ↔ 모델 | B2 |
| `5-api.schema.json` | ⑤ 화면 API에 새로 생기는 모양 | A1·A2·B2 → 화면 | 칸마다 `[A1]`·`[A2]`·`[B2]` 표시 |
| `6-screens.md` | 화면별로 필요한 데이터 → 경로 → 스키마 칸 대응표, 화면 쪽 zod 고칠 것, 미결 | 화면 | A2·B2 같이 |
| (5절) | ④ 모델 호출 창구 — JSON이 아니라 파이썬 모양 | A1 → A2·B2 | A1 |

계약을 바꾸려면 쓰는 쪽과 읽는 쪽이 같이 바꾸고, 계약 시험(4절)을 함께 고친다. 바꿀 때는 `contract` 값의 번호를 올린다 (`handoff/1` → `handoff/2`).

## 2. 공통 규칙

- **해시**: 모든 `*_sha256`은 JSON을 `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`로 직렬화한 UTF-8 바이트의 SHA-256이다. 판정 재사용(B)과 추출 재사용(A)이 이 규칙에 기댄다.
- **시각**: ISO 8601 `+09:00`. 날짜는 `YYYY-MM-DD`.
- **칸 경로**: msds 한 건 기준, 추출스키마 `evidence[].field` 표기 (`components[0].content`). msds 자리는 `msds_index`로 따로 둔다.
- **같은 입력이면 같은 출력**: `judge()` 결과는 `findings`를 `id` 오름차순으로, `traces`는 키 정렬로 낸다. trace 번호(`T-0001`…)는 정렬된 findings 순서대로 붙인다. 그래야 결과를 해시로 비교할 수 있다.
- **TO21 스키마 등록**: TO21 파일은 저장소에 올리지 않는다(D-47). 검증할 때는 `msds.common.paths.to21_file()`로 `TO21_MSDS_추출스키마_v0.6.json`을 읽어 `referencing.Registry`에 그 `$id`로 등록한다.

## 3. 판정 항목 ID (finding_id) 규칙

판정 버전이 바뀌어도 같은 항목이면 같은 ID여야 판정 검토 이력이 이어진다. 그래서 **추출 순서(seq)가 아니라 내용**으로 만든다.

```
m<msds_index>/<종류>:<키>
```

| 종류 | 키 | 예 |
|---|---|---|
| `F2` 2항 유해성 분류 | `<class_code>:<route_form 또는 ->` | `m0/F2:HH_ACUTE_INHAL:분진·미스트`, `m0/F2:HH_SKIN_CORR:-` |
| `F2L` 2항 표시 요소 | `H:<H코드>` / `PIC:<그림문자 코드>` / `SIGNAL` | `m0/F2L:H:H314`, `m0/F2L:SIGNAL` |
| `F15` 15항 규제 | `<성분 키>:<law>.<item_code>` | `m0/F15:7664-93-9:OSH.OSH_MEASURE` |
| `F15DG` 15항 위험물 | `<성분 키 또는 MIX>` | `m0/F15DG:MIX` |
| `FPT` 단일·혼합 판별 | `TYPE` | `m0/FPT:TYPE` |

- **성분 키**: CAS가 있으면 CAS, 없으면 `name:<성분명 원문>`, 제품 전체면 `MIX`. 공백은 `_`로 바꾼다.
- **흡입 형태**: `F2`의 route_form은 기준 쪽(expected) 형태를 쓴다. MSDS가 형태를 다르게 적은 경우도 같은 항목으로 묶어 "형태·세부 표기" 불일치로 낸다.
- 같은 키가 둘 생기면(같은 CAS가 두 번 적힌 MSDS 등) 뒤에 `#2`, `#3`을 붙인다. 번호는 성분 순번이 아니라 내용(함량·이름·기재값) 순서로 준다.
- CAS도 이름도 없는 성분은 `seq:<성분 번호>`를 쓴다. 원문에 다른 키가 없어 생기는 예외다.

## 4. 계약 시험과 견본

- 각 주인은 `backend/tests/contracts/`에 자기 계약의 시험을 둔다. 쓰는 쪽은 "내 출력이 스키마를 통과한다", 읽는 쪽은 "견본을 넣으면 내 코드가 돈다"를 시험한다.
- 화면용 견본은 `contracts/samples/*.json`(TO21 원문 없음, 파일 이름 = `$defs` 이름)이다. 가짜는 `backend/tests/contracts/fakes.py`(`make_handoff`, `fake_process`, `FakeGate`)에 있다.
- **넘김 기록 견본은 저장소에 JSON 파일로 올리지 않는다.** 넘김 기록 견본은 TO21 정답 예제(`TO21_MSDS_추출예제_25_황산_v0.6.json`)를 통째로 담기 때문이다(D-47). 대신 시험 픽스처 함수가 `to21_file()`로 예제를 읽어 그 자리에서 견본을 만든다. 다른 견본(판정 결과·설명·API)은 TO21 원문을 담지 않는 손으로 만든 값만 쓴다.
- 이 스키마들은 2026-11-02에 25번 황산으로 만든 견본(통과 기대)과 틀린 견본(걸림 기대)으로 한 번 점검했다: 메타스키마 6개 통과, 견본 24건 통과, 틀린 견본 7건 모두 걸림 (화면 칸 보강 뒤 다시 점검).

## 5. 약속 ④ 모델 호출 창구 (파이썬)

JSON을 주고받지 않으므로 모양만 정한다. 주인은 A1, 위치는 `backend/src/msds/common/model_gate.py`.

```python
class ModelGate(Protocol):
    def slot(self, kind: Literal["extract", "reextract", "explain"]) -> AsyncContextManager[None]:
        """빈자리를 기다렸다가 들어간다. 서버 전체 동시 호출 상한(설정 MSDS_MODEL_MAX_INFLIGHT)을 지킨다.
        빈자리가 나면 extract·reextract가 explain보다 먼저 들어간다. 같은 종류끼리는 먼저 온 순서."""

# 쓰는 쪽
async with gate.slot("explain"):
    response = await client.chat(...)
```

- A1 구현(`get_model_gate()`)은 `extract/client.py`의 `ChatClient`가 호출마다 잡는다. 이 클라이언트를 쓰는 쪽은 바깥에서 다시 잡지 않는다 (B-35).
- 가짜 창구: `asyncio.Semaphore`만 쓰는 구현. A2·B2는 A1의 창구가 나오기 전까지 이것으로 개발한다.
- 동기 코드에서 쓸 `slot_sync(kind)`도 같은 뜻으로 둔다 (지금 `extract/client.py`는 스레드에서 돈다).

## 6. 이 계약에서 Claude가 정한 것 (검토 부탁)

| 결정 | 이유 |
|---|---|
| 넘김 기록에 evidence·검증기 결과를 따로 두지 않음 | 추출스키마 v0.6 안에 `msds[].evidence`, `msds[].validation`이 이미 있다. 같은 것을 두 곳에 두면 어긋난다 |
| 넘김 기록에 `failed_sections`를 둠 | 추출에 실패한 항은 "자료없음"과 다르다. B가 근거부족(추출 실패)으로 다뤄야 한다 |
| `judge()` 결과를 msds별 `results[]`로 | 설계서 v0.4 예시는 msds 한 건 기준이지만 한 PDF에 MSDS가 여러 건일 수 있다 (추출스키마 `msds[]`) |
| 판정에 `참고`·`범위 외`를 더함 | 설계서 v0.4 D-18(구분5는 '참고')과 검증 범위("제외 항목은 '범위 외'로 표시") |
| finding ID를 내용(CAS·class_code)으로 | seq는 다시 추출하면 바뀐다 |
| 판정 결과에 `review`·`explanation`을 넣지 않음 | 다시 판정해도 검토 이력이 지워지지 않게. 화면 응답(`judgment_view`)에서만 옆에 붙인다 |
| 검토 상태에 `stale` | 검토 뒤 판정이 바뀌면 화면이 다시 확인을 요청할 수 있게 |
| 검토·저장 요청에 `seen_version` | 보던 버전보다 새 판정이 있으면 409로 막아, 옛 화면을 보고 확정하는 일을 막는다 |
| 검토 동작에 `확인`(일치 확인)·`되돌리기` | 화면 2.3·2.4의 "처리"에 일치 항목 확인과 실수 되돌리기가 필요하다고 봄 |

## 7. 구현하며 바꾼 것 (B1·B2, 2026-11-02)

쓰는 쪽과 읽는 쪽이 모두 B라 1절 규칙대로 번호를 올렸다 (`consistency/1` → `/2`). 화면 쪽은 `contract` 상수 하나와 아래 칸을 맞추면 된다.

| 계약 | 변경 | 이유 |
|---|---|---|
| ③ | `trace`의 칸 강제 해제, `cause_texts`·`basis_lines`·`calc_lines` 추가 | 엔진 trace는 계산 종류마다 칸이 다르다. 우진 실측에서 원인 문장과 근거 묶음이 설명 품질을 좌우했다 |
| ③ | finding에 `reason` 추가 | trace 없는 줄(범위 외·참고)의 근거. 문서 전체 가정은 trace `assumptions`에 넣는다 |
| 공용 | `cause_code`에 엔진 코드 추가, `law_label`에 `해외`, `out_of_scope_reason`에 `구버전 제외`·`해외 규제` 추가 | 엔진이 이미 쓰는 코드. 설계서의 "제외 항목은 범위 외로 표시" |
| 설명 | 요청에 `causes`와 요약 trace, `finding`에 `kind`·`item_name`, 근거는 `{page,text,field}`, 응답에서 `finding_id`·`used_numbers`와 길이 제한 제거 | 우진 측정 2~7차 |
| ⑤ 동작 | 확인은 일치·참고·범위 외에만, 확정·승인은 처리 대상에만 (422). 최신 넘김 판정 전 검토·저장 409. 글이 빠진 PDF 422. `stale`·`changed_findings`에 msds 포함. 골드는 저장 뒤 바뀌면 실버 | 저장본의 추출값과 판정이 어긋나지 않게, 거짓 골드 방지 (6-screens 미결 2보다 좁다) |
| ⑤ | `judgment_status.unreviewed`, `review_state.last_event_id`, `review_event_request.seen_event_id`, `conflict_response`, `report_document` 추가 | 6-screens 0절 미검토 수, 동시 처리 충돌, 409 모양, JSON 리포트 모양 |

`mismatch_type`에 `내부 불일치`를 더했다. 단일물질의 11·12항 수치와 2항 구분이 다를 때의 경고다 (설계서 19장). id는 `m0/F2:CROSS:<class_code>:<route_form 또는 ->`.

`judgment_status`의 `판정 실패`에 연결 장애도 포함된다. 이 경우 `error`가 자동 재시도를 알리고, 복구되면 새 넘김 없이 `판정 있음`이 된다.

`4-explanation` 요청의 `finding.type`·`severity`는 값이 없으면 보내지 않으므로 필수에서 뺐다 (측정된 프롬프트 유지).

3절의 `#n` 번호 순서·`seq:` 키와 4절의 `samples/`도 이때 더했다.

`extract.handoff` 표 (약속 ①): `job_id text, handoff_seq integer, body jsonb, created_at timestamptz, PRIMARY KEY (job_id, handoff_seq)`. `body`가 `1-handoff.schema.json` 한 건이다. B 계정 `judge_writer`는 이 표만 읽는다.
