# 추출 모델 QLoRA 파인튜닝

작성 F 김우진 · 2026-11-03 · 대상: 교사 라벨을 만드는 팀원, RunPod에서 학습·평가하는 사람

GPT·Claude(교사)가 새 MSDS를 추출한 결과를, 우리 오픈소스 모델(학생)이 같은 프롬프트로 따라 쓰도록 QLoRA로 학습한다. 학생은 실제 추출과 같은 안내문·원문을 받으므로, 학습이 끝나면 설정 파일의 모델 이름만 바꿔 지금 추출 파이프라인에 그대로 쓴다.

교사 결과는 두 가지 모양을 받는다.
- **묶음 방식 실버** (`data/silver/<모델>/<문서>.json`, 11/03 팀원 p6 실버 59건): 완성 TO21 문서라 줄 번호가 없다. 근거의 원문 조각을 쪽 글자에서 찾아 줄 번호를 되찾고 항별 정답으로 바꾼다(`backend/src/msds/finetune/from_silver.py`).
- **항목별 실행** (`runs/<실행>/raw/`, `run_sections.py --model gpt|claude`): 그대로 쓴다.

```
새 MSDS ─(전처리: 실서비스와 같은 판)→ data/pages/<문서>/
  └─ 교사 추출: 묶음 실버(data/silver/<모델>/) 또는 항목별 실행(runs/<실행>/raw/)   [팀원]
       └─ 학습 데이터 (backend/scripts/ft_build_data.py)     → data/finetune/<이름>/   [저장소에 안 올림]
            └─ QLoRA 학습 (finetune/train_qlora.py, RunPod)  → finetune/out/<run_name>/adapter/
                 └─ 평가: vLLM + LoRA로 개발 문서 추출 → score.py로 학습 전과 비교
```

검증·평가에 쓰는 문서

| 단계 | 문서 | 비고 |
|---|---|---|
| 학습 | 교사 라벨 문서(manifest '기타') | 개발·평가 문서는 자동으로 빠진다(D-43) |
| 학습 중 검증 손실 | 개발 문서의 골드(`data/gold/`) | 같은 방법으로 항별 정답으로 바꾼다 |
| 개발 채점 | 개발 10건 | 실제 파이프라인 + `score.py` |
| 최종 평가 | 평가 11건 | 설정을 고정한 뒤 F가 한 번 |

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

## 1. 교사 라벨과 쪽 글자 (팀원)

**11/04 받은 학습 데이터 (A)**: 새 문서 79건을 항목별 방식(`claude -p`, Opus 5.5, 안내문 s10)으로 다시 추출한 `runs/20261103_sections_claude_cli/`와 쪽 글자(전처리 2026-10-29판)가 팀 공유 zip(`to21_ft_data_20261104.zip`)에 있다. 이것이 학습 데이터의 재료다. 아래 묶음 실버 경로는 예비로 둔다(개발 골드를 검증용으로 바꿀 때도 같은 변환기를 쓴다).

**묶음 실버를 쓰는 경우 (예비)**
- 실버는 이미 브랜치에 있다: `a/silver1`(cli_opus 20건), `b/silver4`(api_opus 20건), `silver/damdang3-p6-20261103`(cli_codex 19건).
- **쪽 글자 폴더(`data/pages/<문서>/`)가 필요하다.** git에 올리지 않는 폴더라 공유 위치로 받는다(D-47). 실서비스(RNGD 추출)와 같은 전처리 판이 좋다. 학생이 학습 때 보는 원문이 추론 때 보는 원문과 같아야 하기 때문이다.
- 근거 조각(`evidence`의 `source_text`)이 쪽 글자에 있어야 줄 번호를 찾는다. 글꼴이 깨진 문서는 글자가 맞지 않아 대부분 버려진다.

**항목별 방식으로 새로 만드는 경우**

```bash
cd backend
python scripts/run_sections.py --model gpt --all-in-pages-dir --pages-dir ../data/pages/<새 문서 폴더>
python scripts/run_sections.py --model claude --docs <문서 번호들> --pages-dir ../data/pages/<새 문서 폴더>
```

- 결과는 `runs/<날짜>_sections_<태그>/raw/`에 항별로 남는다. 줄 번호가 이미 있어 그대로 학습 데이터가 된다.
- 교사 실행의 안내문 판(`run_info.yaml`의 `prompt_version`)이 학습 때 판과 같아야 좋다.

## 2. 학습 데이터 만들기

실버 브랜치의 `data/silver/<모델>/` 폴더가 작업 폴더에 있어야 한다. 브랜치가 main에 합쳐졌으면 main을 받는다. 그 전이면 작업 폴더에만 꺼낸다(스테이지에 올리지 않으니 커밋하지 않는다).

```powershell
git restore --source=origin/a/silver1 --worktree -- data/silver/cli_opus
git restore --source=origin/b/silver4 --worktree -- data/silver/api_opus
git restore --source=origin/silver/damdang3-p6-20261103 --worktree -- data/silver/cli_codex
```

그다음 backend에서:

```bash
cd backend
python scripts/ft_build_data.py --silver ../data/silver/api_opus ../data/silver/cli_opus ../data/silver/cli_codex \
    --pages-dir ../data/pages --student <학생 태그> --out ../data/finetune/<이름>
# 항목별 실행도 있으면 앞에 함께 적는다: python scripts/ft_build_data.py ../runs/<실행> --silver ... 
```

- 예시 하나 = (문서, MSDS, 항) 하나. 학생이 실제 추출 때 받는 system·user 글과, 교사 답을 학생 형식(행 형식 또는 공백 없는 JSON)으로 다시 쓴 정답이다.
- 결과: `train.jsonl`, `val.jsonl`(개발 문서 골드), `data_info.yaml`, `report.md`
- 검증은 기본으로 개발 문서의 골드(`--val-gold ../data/gold`)를 쓴다. 개발 문서의 쪽 글자가 `--pages-dir`에 없으면 `--val-pages-dir`로 따로 준다. `--val-gold none`이면 학습 문서의 10%를 문서 단위로 뗀다.
- **`report.md`를 먼저 본다.** 맨 위의 '학습 예시로 바뀐 항'이 살아남은 비율이다(실버 1건 = 항 9개). 문서별 표에서 0%인 문서는 쪽 글자가 없거나 글자가 깨진 문서다.

| 버린 이유 | 뜻 | 많으면 |
|---|---|---|
| 입력 없음(쪽 글자) | 그 문서의 쪽 글자 폴더가 없음 | 쪽 글자를 받아 `--pages-dir`에 둔다 |
| 근거 줄 못 찾음 | 실버의 근거 조각을 그 항 원문에서 못 찾은 행이 있음(항 전체를 뺀다) | 앞 5개 예를 보고 F에게 알림. 쪽 글자 판이 실버 때와 다른지 확인 |
| MSDS 건수 다름 | 실버의 MSDS 건수와 쪽 글자로 나눈 건수가 다름 | 다중 MSDS 문서. 그 문서만 빼도 된다 |
| 교사 실패·검사 문제 | (항목별 실행) 교사 항이 실패했거나 검사에 걸림 | 교사 실행의 `checks/` 확인 |
| 줄 번호 다름 | (항목별 실행) 교사가 본 쪽 글자와 지금 쪽 글자가 다름 | `--pages-dir`로 교사가 본 폴더를 지정 |
| 형식 검사 실패 | 정답을 실제 추출처럼 다시 읽으면 오류·행 수 차이 | 앞 5개 예를 보고 F에게 알림 |
| 이미지 항(2항) 제외 | 학생이 2항에 이미지를 받음 | 정상 |

- '예시 안에서 뺀 행·칸'은 그 항 호출이 볼 수 없는 값이다. 예를 들어 16항에 적힌 작성일은 1항 호출에 보이지 않으므로 1항 정답에서 뺀다(그 값은 실서비스에서도 16항 호출과 펼치기가 채운다).
- 11/03 확인: 개발 문서 5건(글꼴이 깨진 S003 제외)의 골드 → 45개 항 중 44개, 같은 문서의 예전 묶음 실버(p3) → 45개 중 45개가 학습 예시가 됐다. 정답 행의 93~95%는 고른 줄에 그 행의 값이 그대로 있다(나머지는 '● 생분해성'처럼 제목 줄을 고른 경우).
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
python -m pytest finetune/tests -q              # CPU 시험 5개(작은 가짜 모델). 5 passed면 설치가 맞다
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

학습 곡선을 W&B로 보려면

```bash
export WANDB_API_KEY=<본인 키>                  # Pod 터미널에서만. 저장소·채팅·노션에 적지 않는다
nohup python finetune/train_qlora.py --config finetune/configs/qlora.yaml --data data/finetune/<이름> \
    --set wandb.enabled=true wandb.entity=<팀 조직 이름, 개인이면 빼기> > train.log 2>&1 &
```

- 프로젝트 `to21-msds-qlora`에 `run_name` 이름으로 실행이 생긴다. 실행 주소는 `train.log`와 `train_info.yaml`(`wandb_url`)에 남는다.
- 보이는 것: `train/loss`·`train/learning_rate`·`train/grad_norm`, `eval/loss`(학습 전 0단계부터), GPU 메모리·사용률, 설정, 예시 수와 항별 길이 표(`data/lengths`).
- **보내지 않는 것: 학습 글(안내문·MSDS 원문·정답)과 모델·체크포인트(D-47).** 시험(`finetune/tests`)이 W&B 기록에 학습 글이 없는지 확인한다.
- Pod에서 바깥으로 못 나가면 `WANDB_MODE=offline`으로 돌리고, 끝난 뒤 `wandb sync wandb/offline-run-*`로 올린다.
- 볼 것: `eval/loss`가 학습 전보다 내려가다가 다시 오르기 시작하면 외우기 시작한 것이다. 그 지점의 단계 수로 에폭을 줄인다.
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

- 팀원은 개발 10건으로 본다. 평가 11건(manifest 평가)은 설정을 고정한 뒤 F가 한 번만 채점한다(D-43).
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
