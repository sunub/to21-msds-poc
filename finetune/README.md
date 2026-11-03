# 추출 모델 QLoRA 파인튜닝

작성 F 김우진 · 2026-11-03 · 대상: 교사 라벨을 만드는 팀원, RunPod에서 학습·평가하는 사람

GPT·Claude(교사)가 새 MSDS 80건을 항목별로 추출한 결과를, 우리 오픈소스 모델(학생)이 같은 프롬프트로 따라 쓰도록 QLoRA로 학습한다. 학생은 실제 추출과 같은 안내문·원문을 받으므로, 학습이 끝나면 설정 파일의 모델 이름만 바꿔 지금 추출 파이프라인에 그대로 쓴다.

```
새 MSDS 80건 ─(전처리)→ data/pages/<문서>/
  └─ 교사 추출 (run_sections.py --model gpt|claude)         → runs/<교사 실행>/raw/   [팀원]
       └─ 학습 데이터 (backend/scripts/ft_build_data.py)     → data/finetune/<이름>/   [저장소에 안 올림]
            └─ QLoRA 학습 (finetune/train_qlora.py, RunPod)  → finetune/out/<run_name>/adapter/
                 └─ 평가: vLLM + LoRA로 개발 문서 추출 → score.py로 학습 전과 비교
```

## 0. 먼저 정할 것

| 무엇 | 정하는 사람 | 바꿀 곳 |
|---|---|---|
| 학생 모델 | 모델 담당 | `configs/qlora.yaml`의 `base_model`(bf16 원본 이름), `chat_template_kwargs` |
| 학생 추출 설정 | 모델 담당 | `backend/configs/models.yaml`의 그 모델 태그(행 형식 항, JSON 방식, 이미지 여부). 학습 데이터를 이 태그로 만든다 |

모델을 바꿀 때 확인할 것
- **학습은 원본(bf16) 체크포인트로 한다.** `-FP8`·`-AWQ` 같은 양자화본은 QLoRA로 올릴 수 없다. 예: `Qwen/Qwen3.6-35B-A3B-FP8` → `Qwen/Qwen3.6-35B-A3B`.
- **생각 모드가 있는 모델**은 `chat_template_kwargs: {enable_thinking: false}`처럼 추론 설정과 같게 둔다. 다르면 학습 글과 추론 글의 앞부분이 달라진다.
- **이미지를 받는 설정(`image_input: true`)이면 2항은 학습에서 빠진다.** 이미지 없이 그림문자 정답을 배우면 그림문자를 지어내게 된다. 2항은 원래 모델 그대로 쓴다.
- **RNGD에 올리려면** 학습 결과를 원본에 합친 뒤(`merge_adapter.py`) 퓨리오사 형식으로 다시 빌드해야 한다. 가능한지와 걸리는 시간은 확인이 필요하다. RunPod의 vLLM에서는 LoRA를 바로 붙여 쓴다.

## 1. 교사 라벨 만들기 (팀원)

새 문서의 쪽 글자(`data/pages/<문서>/`)를 지금 추출과 같은 전처리로 먼저 만든다. 그다음 **지금 추출과 같은 항목별 방식**으로 교사 추출을 돌린다. 예전 실버 방식(`run_silver.py`)은 묶음 단위라 학습 데이터로 바꿀 수 없다.

```bash
cd backend
python scripts/run_sections.py --model gpt --all-in-pages-dir --pages-dir ../data/pages/<새 문서 폴더>
python scripts/run_sections.py --model claude --docs <문서 번호들> --pages-dir ../data/pages/<새 문서 폴더>
```

- 결과는 `runs/<날짜>_sections_<태그>/raw/`에 항별로 남는다. 이 폴더가 학습 데이터의 재료다.
- **개발·평가 20건은 넣지 않는다.** 넣어도 3단계에서 자동으로 빠지지만, 비용만 든다.
- 같은 문서를 GPT·Claude 둘 다 돌렸으면 3단계에서 앞에 적은 실행을 우선한다.
- 교사 실행의 안내문 판(`run_info.yaml`의 `prompt_version`)이 학습 때 판과 같아야 좋다. 안내문을 고치면 교사 추출을 다시 돌릴지 정한다.

## 2. 학습 데이터 만들기

```bash
cd backend
python scripts/ft_build_data.py ../runs/<Claude 실행> ../runs/<GPT 실행> --student <학생 태그> --out ../data/finetune/<이름>
```

- 예시 하나 = (문서, MSDS, 항) 하나. 학생이 실제 추출 때 받는 system·user 글과, 교사 답을 학생 형식(행 형식 또는 공백 없는 JSON)으로 다시 쓴 정답이다.
- 결과: `train.jsonl`, `val.jsonl`(문서 단위로 10%), `data_info.yaml`, `report.md`
- **`report.md`의 '버린 예시'를 먼저 본다.**

| 버린 이유 | 뜻 | 많으면 |
|---|---|---|
| 교사 실패·검사 문제 | 교사 항이 실패했거나 줄 번호·코드 검사에 걸림 | 교사 실행의 `checks/` 확인 |
| 줄 번호 다름 | 교사가 본 쪽 글자와 지금 쪽 글자가 다름 | `--pages-dir`로 교사가 본 폴더를 지정 |
| 형식 검사 실패 | 정답을 실제 추출처럼 다시 읽으면 오류·행 수 차이 | 앞 5개 예를 보고 F에게 알림 |
| 이미지 항(2항) 제외 | 학생이 2항에 이미지를 받음 | 정상 |

- **학습 데이터에는 명세서로 만든 안내문과 MSDS 원문이 들어 있다.** 저장소에 올리지 않는다(`.gitignore`의 `data/finetune/`, D-47). RunPod에는 학습하는 동안만 두고 끝나면 지운다.

## 3. RunPod에서 학습

### 3.1 준비

- Pod: A100 80GB 한 장. 디스크는 넉넉히(35B급 bf16 원본 약 70GB + 내려받기 캐시, 합치기까지 하면 그 두 배).
- 코드: 저장소를 받거나 `finetune/` 폴더만 올린다. 학습 스크립트는 backend 코드를 쓰지 않는다.
- 데이터: `data/finetune/<이름>/`을 Pod의 같은 경로로 올린다.

```bash
cd /workspace/to21-msds-poc
python -m venv /workspace/venv-train && source /workspace/venv-train/bin/activate
pip install -r finetune/requirements.txt        # torch는 Pod 이미지의 것을 쓴다. 없으면 CUDA 판 torch를 먼저 깐다
python -m pytest finetune/tests -q              # CPU 시험 4개(작은 가짜 모델). 4 passed면 설치가 맞다
```

### 3.2 길이 확인 (GPU 안 씀, 몇 분)

```bash
python finetune/train_qlora.py --config finetune/configs/qlora.yaml --data data/finetune/<이름> --check-data
```

- 항마다 토큰 수(중앙값·95%·최대)가 나온다. `max_seq_len`(기본 16,384)보다 긴 예시는 자르지 않고 뺀다. 많이 빠지면 `--set max_seq_len=24576`처럼 늘린다(메모리가 더 든다).
- `정답 자르기: {'template': N}`이 정상이다. `eos`가 나오면 대화 틀이 마지막 답을 다르게 감싸는 모델이다. 끝 토큰이 추론 때와 같은지(Qwen 지시형은 `<|im_end|>`) 확인한다.

### 3.3 학습

```bash
nohup python finetune/train_qlora.py --config finetune/configs/qlora.yaml --data data/finetune/<이름> > train.log 2>&1 &
tail -f train.log
```

- 결과: `finetune/out/<run_name>/adapter/`(LoRA), `train_info.yaml`(설정·데이터·길이·손실·버전·GPU·시간), `log_history.json`
- 걸리는 시간은 모델과 길이에 따라 다르다(확인 필요). 처음 몇 단계 로그의 단계당 시간 × 전체 단계로 계산한다. 전체 단계 ≈ 학습 예시 수 ÷ 8 × 2(에폭).
- 값을 바꿔 다시 돌릴 때는 `--set run_name=to21_qlora_v2 train.lr=5e-5`처럼 이름도 바꾼다.

기본값과 이유 (`configs/qlora.yaml`)

| 값 | 기본 | 이유 |
|---|---|---|
| LoRA 위치 | 주의 투영 4개(q·k·v·o) | 밀집·MoE 모델 모두 이름이 같다. MoE 전문가 층까지 넣으면 메모리·시간이 크게 늘고 vLLM LoRA 지원도 모델마다 다르다 |
| r / alpha | 16 / 32 | 예시 수백 개에 흔히 쓰는 크기. 형식·규칙을 맞추는 데는 충분하다 |
| 학습률·에폭 | 1e-4, 2에폭 | 예시가 적어 오래 돌리면 외운다. 검증 손실이 다시 오르면 에폭을 줄인다 |
| 한 번에 반영 | 8개(1 × 8) | 긴 예시라 묶음 크기 1, 누적 8 |
| 4bit | NF4, 이중 양자화 | QLoRA 표준 설정 |

## 4. 평가

학습 전 모델과 학습 후 모델을 **같은 서버·같은 정밀도·같은 설정**으로 같은 문서에 돌려 `score.py`로 비교한다.

```bash
# vLLM은 학습과 다른 가상환경에 깐다(vLLM이 자기 torch 판을 깐다)
python -m venv /workspace/venv-vllm && source /workspace/venv-vllm/bin/activate && pip install vllm
vllm serve <base_model> --enable-lora --lora-modules to21-ft=finetune/out/<run_name>/adapter \
    --max-lora-rank 16 --max-model-len 32768 --port 8000
```

`backend/configs/models.yaml`에 학생 태그를 복사해 두 개를 더한다. 바꾸는 것은 `model`과 주소뿐이고, 행 형식 항·구조화 방식·이미지 여부는 학습 데이터를 만든 학생 태그와 같게 둔다.

```yaml
  ft_base_runpod:                 # 학습 전 (같은 서버의 원본)
    model: <base_model>
    base_url_env: RUNPOD_VLLM_BASE_URL
    # 나머지는 학생 태그 그대로
  ft_lora_runpod:                 # 학습 후 (같은 서버의 LoRA)
    model: to21-ft                # --lora-modules의 이름
    base_url_env: RUNPOD_VLLM_BASE_URL
    # 나머지는 학생 태그 그대로
```

```bash
cd backend
python scripts/run_sections.py --model ft_base_runpod --purpose 개발
python scripts/run_sections.py --model ft_lora_runpod --purpose 개발
cd ..
python backend/scripts/score.py --pred runs/<ft_base 실행>/outputs --title ft_base_개발 --purpose 개발
python backend/scripts/score.py --pred runs/<ft_lora 실행>/outputs --title ft_lora_개발 --purpose 개발
python backend/scripts/compare_scores.py --title ft_전후 base=runs/<날짜>_score_ft_base_개발 lora=runs/<날짜>_score_ft_lora_개발
```

- 팀원은 개발 10건으로 본다. 평가 10건은 설정을 고정한 뒤 F가 한 번만 채점한다(D-43).
- vLLM이 이 모델·양자화에서 LoRA를 못 붙이면, `merge_adapter.py`로 합친 체크포인트를 `vllm serve <merged> --quantization fp8`처럼 띄우고 원본도 같은 옵션으로 띄워 비교한다.
- 항별 성공률·재추출 수는 각 실행의 `checks/`, 시간은 `timing.jsonl`에 있다.

## 5. 끝나면

- Pod의 `data/finetune/`과 쪽 글자를 지운다(D-47). LoRA(`adapter/`, 수백 MB)만 팀 공유 위치로 옮긴다.
- `train_info.yaml`, `report.md`, 성적표 비교를 작업기록에 남긴다.

## 알려진 한계

- 교사 답이 정답은 아니다. 교사가 틀린 칸은 학생도 따라 틀린다. 그래서 평가는 교사가 아니라 사람이 검수한 골드로 한다.
- 예시 수가 수백 개라 새 지식보다 형식·작성 규칙(행 나누기, 코드표, 숫자 묶음)을 맞추는 효과가 주로 난다.
- 2항 그림문자(이미지)는 학습하지 않는다.
- bitsandbytes 4bit 경로는 GPU에서만 돈다. 이 저장소의 시험은 CPU에서 4bit 없이 같은 코드를 확인한다.
