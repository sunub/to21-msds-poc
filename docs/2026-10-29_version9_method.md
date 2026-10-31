# version9 추출 방법

## 요약

`version2`(PDF 텍스트 + PaddleOCR 하이브리드) 방식에, 그동안 빠져 있던 두 옵션(표 행 묶기, 줄번호)을 켜서 20개 문서 전체를 다시 추출했다.

## 시도한 방법

1. **기반 방법은 `version2`와 동일** — PDF 좌표 텍스트(`pymupdf`, 신뢰도 1.0)를 우선 쓰고, 텍스트층이 정상인 페이지는 PaddleOCR 결과 중 PDF와 안 겹치는 부분만 보강, 텍스트층이 없거나 깨진 페이지는 PaddleOCR만으로 전체 처리.
2. **문제 발견**: `version2`/`version7` 실행 때 `pipe_rows`, `line_numbers` 옵션을 켜지 않아서 표가 `|`로 안 묶이고, 줄번호(`L001` 등)도 안 들어갔음. `version6`은 이 옵션을 켠 상태로 실행된 버전이었음을 코드(`ocr_batch_version6.py`)에서 확인.
3. **`version8` 시도**: `pipe_rows=True`만 켜서 T21-025(황산) 1건으로 먼저 테스트 → 표 묶기 정상 확인.
4. **줄번호 옵션 추가**: `line_numbers=True`도 추가로 켜서 T21-025에서 `L001`, `L002`... 형식이 실제로 파일에 들어가는지 재검증.
5. **재현 가능한 스크립트로 고정**: 인라인으로 돌렸던 호출을 `backend/scripts/ocr_batch_version8.py`에 `pipe_rows=True`, `line_numbers=True`로 박아 넣고, `--output-version` 인자를 추가해 출력 폴더를 바꿔가며 재사용할 수 있게 함.
6. **`version9` 전체 실행**: 같은 스크립트로 `--output-version version9 --force`를 줘서 manifest의 20개 문서 전체를 재추출.

## version2 대비 바뀐 점

| 옵션 | version2 / version7 | version8 (T21-025만) | version9 (전체 20건) |
|---|---|---|---|
| `pipe_rows` (표 `\|` 묶기) | False | True | True |
| `line_numbers` (`L001` 줄번호) | False | True | True |
| OCR·중복제거·좌표재정렬 로직 | 동일 | 동일 | 동일 |

추출 로직 자체(PDF 텍스트 우선, PaddleOCR 보강, 중복제거, 좌표 재정렬)는 전부 동일하고, **출력 형식 옵션만 켠 것**이 `version9`의 전부다.

## 실행 스크립트

```bash
python scripts/ocr_batch_version8.py --output-version version9 --force
```

## 타이밍·결과 기록

문서별/페이지별 소요시간은 `data/pages/version9/timing_report.md`에 별도로 정리했다.
