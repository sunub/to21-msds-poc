# S003 OCR 원문 대조 시험 (2026-10-26, 역할 C)

S003은 텍스트층이 완전히 깨져(글꼴깨짐) 원문 대조가 모두 "대조불가"다.
쪽 이미지를 PaddleOCR로 읽은 글자로 대조하면 얼마나 "일치"가 나오는지 본다.

- OCR: paddleocr 3.7.0 (PP-OCRv5_server_det + korean_PP-OCRv5_mobile_rec), 300dpi, CPU
- 원문 조각: `fragments.json` 52개. S003 실버가 없어 쪽 이미지를 보고 직접 옮겨 적었다(OCR 글자를 보지 않음).
  실제 조각 44개 + 대조군 8개(쪽 틀림 2, 지어냄 5, 다듬음 1, `expect`에 기대 결과)
- 원문 대조: `backend/src/msds/checks/source_match.py` 그대로

## 결과

| 글자 | 일치 | 다른 쪽에서 일치 | 불일치 | 대조불가 |
|---|---|---|---|---|
| 현재 (깨진 텍스트층, 쪽 상태 글꼴깨짐) | 0 | 0 | 0 | 52 |
| OCR (OCR 글자를 '정상'으로) | 42 | 2 | 8 | 0 |

- 실제 조각 44개 중 42개 일치. 틀린 2개는 OCR의 ℃ 오인식: `-196 ℃`→`-196 C`, `(25℃)`→`(25°c)`.
  소문자 c는 D-9(대소문자 엄격) 때문에 정규화로 맞추지 않는다.
- 대조군 8개는 모두 기대대로 (쪽 틀림 → 실제 쪽에서 일치, 지어냄·다듬음 → 불일치).

## 한계

- 조각을 사람이 만들었다. 모델 실버는 원문을 다듬어 적는 일이 있어 일치율이 더 낮을 수 있다. S003 실버가 나오면 다시 잰다.
- 한 문서, 52개 조각이다.
- 지금 `match`는 쪽 상태가 '정상'이 아니면 대조불가다. OCR 쪽을 쓰려면 쪽 상태·결과 표시를 A와 맞춰야 한다.

## 다시 돌리기 (backend/에서, PaddleOCR 설치 환경)

```
python scripts/preprocess.py --docs T21-S003
python scripts/ocr_pages.py --docs T21-S003
python scripts/check_ocr_match.py T21-S003 ../runs/20261026_s003_ocr_source_match/fragments.json
```
