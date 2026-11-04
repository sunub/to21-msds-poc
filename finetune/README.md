# 추출 모델 LoRA·QLoRA 파인튜닝

작성 F 김우진 · 2026-11-03(11/04 모델별 설정·메모리 점검) · 대상: 교사 라벨을 만드는 팀원, RunPod에서 학습·평가하는 사람

GPT·Claude(교사)가 새 MSDS를 추출한 결과를, 우리 오픈소스 모델(학생)이 같은 프롬프트로 따라 쓰도록 LoRA(밀집 모델은 4bit QLoRA)로 학습한다. 학생은 실제 추출과 같은 안내문·원문을 받으므로, 학습이 끝나면 설정 파일의 모델 이름만 바꿔 지금 추출 파이프라인에 그대로 쓴다.

교사 결과는 두 가지 모양을 받는다.
- **묶음 방식 실버** (`data/silver/<모델>/<문서>.json`, 11/03 팀원 p6 실버 59건): 완성 TO21 문서라 줄 번호가 없다. 근거의 원문 조각을 쪽 글자에서 찾아 줄 번호를 되찾고 항별 정답으로 바꾼다(`backend/src/msds/finetune/from_silver.py`).
- **항목별 실행** (`runs/<실행>/raw/`, `run_sections.py --model gpt|claude`): 그대로 쓴다.

```
새 MSDS ─(전처리: 실서비스와 같은 판)→ data/pages/<문서>/
  └─ 교사 추출: 묶음 실버(data/silver/<모델>/) 또는 항목별 실행(runs/<실행>/raw/)   [팀원]
       └─ 학습 데이터 (backend/scripts/ft_build_data.py)     → data/finetune/<이름>/   [저장소에 안 올림]
            └─ LoRA 학습 (finetune/train_qlora.py, RunPod)   → finetune/out/<run_name>/adapter/
                 └─ 평가: vLLM + LoRA로 개발 문서 추출 → score.py로 학습 전과 비교
```

검증·평가에 쓰는 문서

| 단계 | 문서 | 비고 |
|---|---|---|
| 학습 | 교사 라벨 문서 79건 전부(A가 준 train·val을 모두 학습에) | manifest '기타'. 개발·평가 문서는 자동으로 빠진다(D-43) |
| 검증 ① 학습 중 손실 | main의 개발셋 골드(`data/gold/`, 개발 10건) | 같은 방법으로 항별 정답으로 바꾼다. 쪽 글자가 있는 문서만(글꼴 깨진 S003 제외) |
| 검증 ② 개발 채점 | 개발 10건 | 실제 파이프라인 + `score.py`로 학습 전후 비교 |
| 평가 | main의 평가셋 11건 | 설정을 고정한 뒤 F가 한 번만 |

## 빠른 실행 안내 (11/04, 학습 담당 팀원용)

이 장만 따라 하면 된다. 자세한 이유와 설정은 0~5장에 있다.

**누가 무엇을**

| 모델 | 담당 | 학습 설정 | 학습 데이터 폴더(F가 전달) | GPU(RunPod) | 비교용 태그 |
|---|---|---|---|---|---|
| Qwen3.6-35B-A3B | 팀원 | `configs/qwen36_35b_a3b.yaml` | `20261104_qwen36_35b_runpod` | H200 141GB × 1 | `ft_base_qwen36`·`ft_lora_qwen36` |
| Qwen3.8-27B | 팀원 | `configs/qwen38_27b.yaml` | `20261104_qwen38` | A100 80GB × 1 | `ft_base_qwen38`·`ft_lora_qwen38` |
| Qwen3.5-122B-A10B | F | `configs/qwen35_122b_a10b.yaml` | `20261104_qwen36_35b_runpod`(35B와 같음) | H200 141GB × 4 | `ft_base_qwen35_122b`·`ft_lora_qwen35_122b` |
| Qwen3-30B-A3B(되면) | F | `configs/qwen3_30b_a3b.yaml` | `20261104_qwen3_30b_a3b_rngd` | A100 80GB × 1 | `ft_base_qwen3_30b`·`ft_lora_qwen3_30b` |

- 디스크(`/workspace` 볼륨): 35B·27B·30B는 200GB, 122B는 700GB.
- 학습 데이터에는 안내문과 MSDS 원문이 들어 있다. 저장소·노션·채팅에 올리지 않는다. Pod에는 학습하는 동안만 두고 끝나면 지운다(D-47).
- 키(W&B, vLLM)는 Pod 터미널과 PC `.env`에만 둔다.

### 가. 학습 데이터 만들기 (F, PC에서 한 번)

```powershell
cd C:\Users\siskw\projects\to21-msds-poc
# A의 to21_ft_data_20261104.zip을 저장소 최상위에 푼다: runs\20261103_sections_claude_cli\, data\pages\T21-0xx(79건)
cd backend
.venv\Scripts\python scripts\preprocess.py --docs T21-M002 T21-M004 T21-S014   # 검증용 개발 문서 쪽 글자 중 없는 것
foreach ($t in "qwen36_35b_runpod", "qwen38", "qwen3_30b_a3b_rngd") {
  .venv\Scripts\python scripts\ft_build_data.py ..\runs\20261103_sections_claude_cli --pages-dir ..\data\pages `
      --student $t --out ..\data\finetune\20261104_$t
}
```

- 학습은 A의 79건 전부다(A 폴더의 train 568 + val 64 = 632개와 같은 예시. 2항을 쓰는 학생은 711개).
- 푼 `runs\20261103_sections_claude_cli\`와 `data\pages\`의 79건은 커밋하지 않는다(MSDS 원문, D-47). `git add`는 늘 경로를 적어서 한다.
- 검증은 main 개발셋 골드다. `report.md`의 '검증: 골드(개발 문서) N건'을 본다. 11/04 시험(개발 쪽 글자 5건): 35B 검증 39개, 27B·30B 44개. M002·M004·S014를 더하면 늘어난다. M005는 원본 PDF가 있어야 들어간다.
- 폴더마다 zip으로 묶어 A와 같은 방법으로 담당자에게 준다.

### 나. Pod 준비 (담당자)

RunPod 콘솔의 SSH 접속 명령어(`ssh root@<주소> -p <포트> -i ~/.ssh/id_ed25519`)를 쓴다. PC(PowerShell, 저장소 최상위)에서 코드와 데이터를 올린다.

```powershell
ssh root@<주소> -p <포트> -i ~/.ssh/id_ed25519 "mkdir -p /workspace/to21/deploy /workspace/to21/data/finetune"
scp -P <포트> -i ~/.ssh/id_ed25519 -r finetune root@<주소>:/workspace/to21/
scp -P <포트> -i ~/.ssh/id_ed25519 -r deploy/runpod root@<주소>:/workspace/to21/deploy/
scp -P <포트> -i ~/.ssh/id_ed25519 -r data/finetune/20261104_qwen36_35b_runpod root@<주소>:/workspace/to21/data/finetune/
```

Pod 터미널에서:

```bash
cd /workspace/to21
sed -i 's/\r$//' finetune/*.sh deploy/runpod/*.sh   # Windows에서 올리면 줄 끝이 CRLF일 수 있어 bash용으로 고친다
bash finetune/pod_setup.sh            # 학습 가상환경. 끝에 '11 passed'와 GPU·디스크가 나오면 된다
source /workspace/venv-train/bin/activate && export HF_HOME=/workspace/hf
```

### 다. 확인하고 학습 (담당자, Pod)

```bash
M=qwen36_35b_a3b; D=data/finetune/20261104_qwen36_35b_runpod      # 27B면 M=qwen38_27b; D=data/finetune/20261104_qwen38
python finetune/train_qlora.py --config finetune/configs/$M.yaml --data $D --check-data     # 길이(몇 분)
python finetune/train_qlora.py --config finetune/configs/$M.yaml --data $D --check-memory   # 모델 받기 + 한 걸음
export WANDB_API_KEY=<본인 키>                                       # W&B를 안 쓰면 이 줄과 아래 --set wandb.enabled=true를 뺀다
nohup python finetune/train_qlora.py --config finetune/configs/$M.yaml --data $D --set wandb.enabled=true > train_$M.log 2>&1 &
tail -f train_$M.log
```

| 볼 것 | 정상 | 아니면 |
|---|---|---|
| `--check-data`의 '정답 자르기' | `template`(27B는 `eos`도 정상) | F에게 알림 |
| `--check-data`의 '뺀 긴 예시' | 몇 개(16,384토큰 넘는 11·15항) | 많으면 `--set max_seq_len=24576`(메모리 더 듦) |
| `--check-memory`의 최대 GPU 메모리 | GPU의 92% 아래 | `--set max_seq_len=12288` 또는 더 큰 GPU |
| `--check-memory`의 'LoRA … N층 중 N층' | 두 수가 같음 | 학습하지 말고 F에게 알림 |
| 학습 로그·W&B의 `eval/loss` | 학습 전보다 내려감 | 다시 오르기 시작하면 그 단계 수를 적어 둔다 |

결과는 `finetune/out/<run_name>/`(`adapter/`, `train_info.yaml`, `check_memory.yaml`, `log_history.json`)에 남는다.

### 라. 개발 10건으로 학습 전후 비교 (담당자)

학습이 끝난 같은 Pod에서 vLLM을 띄운다. 한 서버가 학습 전(원본)과 학습 후(`to21-ft`)를 모두 받는다.

```bash
bash deploy/runpod/setup_vllm.sh Qwen/Qwen3.6-35B-A3B-FP8        # 처음 한 번(15~25분). vLLM 0.32.0과 원본을 받는다
nohup bash finetune/serve_lora.sh Qwen/Qwen3.6-35B-A3B-FP8 finetune/out/to21_lora_qwen36_35b_a3b_v1/adapter > serve.log 2>&1 &
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/v1/models    # 키 없이 401이면 떴고 잠겨 있다
cat /workspace/vllm_api_key                                                  # PC .env에 옮겨 적는다(다른 곳에 적지 않는다)
```

| 모델 | `setup_vllm.sh`·`serve_lora.sh`에 줄 원본 | 덧붙일 것 |
|---|---|---|
| 35B | `Qwen/Qwen3.6-35B-A3B-FP8`(운영과 같은 FP8) | 없음 |
| 27B | `Qwen/Qwen3.8-27B` | 앞에 `MAX_MODEL_LEN=65536` |
| 122B | `Qwen/Qwen3.5-122B-A10B` | 없음(GPU 4장에 자동으로 나눈다) |
| 30B | `Qwen/Qwen3-30B-A3B-Instruct-2507-FP8` | 앞에 `MM_LIMIT=`(글 전용 모델) |

- FP8 원본에 LoRA가 안 붙으면(`serve.log`에 LoRA·양자화 오류) bf16 원본(`Qwen/Qwen3.6-35B-A3B` 등, 학습에 쓴 것)으로 띄우고, PC의 `ft_base_*` 태그 `model`도 그 이름으로 바꾼다. 전후 둘 다 같은 서버에서 돌리면 비교는 그대로 성립한다.

PC에서:

1. 창 하나에 터널을 열어 둔다: `ssh -N -L 18000:127.0.0.1:8000 root@<주소> -p <포트> -i ~/.ssh/id_ed25519`
2. 추출에 쓰는 `.env`(지금 `RUNPOD_VLLM_API_KEY`가 있는 파일)에 두 줄을 더한다: `FT_VLLM_BASE_URL=http://127.0.0.1:18000/v1`, `FT_VLLM_API_KEY=<Pod 키>`
3. `finetune/eval_tags.yaml`에서 맡은 모델의 두 태그를 `backend/configs/models.yaml`의 `models:` 아래에 붙인다(커밋하지 않는다).
4. 개발 10건의 쪽 글자(`data/pages/`)가 있어야 한다. 없으면 `python scripts/preprocess.py --purpose 개발`(원본 PDF 필요).

```powershell
cd backend
.venv\Scripts\python scripts\run_sections.py --model ft_base_qwen36 --purpose 개발
.venv\Scripts\python scripts\run_sections.py --model ft_lora_qwen36 --purpose 개발
cd ..
backend\.venv\Scripts\python backend\scripts\score.py --pred runs\<날짜>_sections_ft_base_qwen36\outputs --title ft_base_qwen36_개발 --purpose 개발
backend\.venv\Scripts\python backend\scripts\score.py --pred runs\<날짜>_sections_ft_lora_qwen36\outputs --title ft_lora_qwen36_개발 --purpose 개발
backend\.venv\Scripts\python backend\scripts\compare_scores.py --title ft_qwen36_전후 base=runs\<날짜>_score_ft_base_qwen36_개발 lora=runs\<날짜>_score_ft_lora_qwen36_개발
```

- bf16 원본으로도 LoRA를 못 붙이면 4장의 합치기 방법으로 바꾸고 F에게 알린다. Qwen3.5 구조의 DeltaNet 층 LoRA를 vLLM이 받는지는 확인이 필요하다.
- 평가셋 11건은 돌리지 않는다. 설정을 고정한 뒤 F가 한 번만 채점한다(D-43).

### 마. 넘기고 정리 (담당자)

- F에게 넘길 것(팀 공유 위치, 저장소 말고): `adapter/` 폴더, `train_info.yaml`, `check_memory.yaml`, `log_history.json`, W&B 주소, `runs/<날짜>_compare_ft_*_전후/compare.md`
- Pod에서 지운다: `rm -rf /workspace/to21/data/finetune`. 다 쓰면 콘솔에서 Pod를 멈춘다(GPU 비용).

### 바. 평가셋 11건 (F, 한 번)

개발 10건 비교로 모델·설정을 고른 뒤, 고른 것만 평가셋으로 한 번 돌린다(D-43). 학습 전도 같은 서버에서 같이 돌린다.

```powershell
cd backend
.venv\Scripts\python scripts\run_sections.py --model ft_lora_<모델> --purpose 평가 --allow-eval
cd ..
backend\.venv\Scripts\python backend\scripts\score.py --pred runs\<날짜>_sections_ft_lora_<모델>\outputs --title ft_lora_<모델>_평가 --purpose 평가
backend\.venv\Scripts\python backend\scripts\score.py --pred runs\<날짜>_sections_ft_lora_<모델>\outputs --title ft_lora_<모델>_25 --docs T21-025 --gold-example25
```

## 0. 먼저 정할 것

| 무엇 | 정하는 사람 | 바꿀 곳 |
|---|---|---|
| 학생 모델 | 모델 담당 | `configs/<모델>.yaml`(아래 표). 새 모델이면 하나를 복사해 `base_model`(bf16 원본 이름), `chat_template_kwargs`, `lora.target_modules`를 바꾼다 |
| 학생 추출 설정 | 모델 담당 | `backend/configs/models.yaml`의 그 모델 태그(행 형식 항, JSON 방식, 이미지 여부). 학습 데이터를 이 태그로 만든다 |

모델을 바꿀 때 확인할 것
- **학습은 원본(bf16) 체크포인트로 한다.** `-FP8`·`-AWQ` 같은 양자화본은 QLoRA로 올릴 수 없다. 예: `Qwen/Qwen3.6-35B-A3B-FP8` → `Qwen/Qwen3.6-35B-A3B`.
- **생각 모드가 있는 모델**은 `chat_template_kwargs: {enable_thinking: false}`처럼 추론 설정과 같게 둔다. 다르면 학습 글과 추론 글의 앞부분이 달라진다.
- **이미지를 받는 설정(`image_input: true`)이면 2항은 학습에서 빠진다.** 이미지 없이 그림문자 정답을 배우면 그림문자를 지어내게 된다. 2항은 원래 모델 그대로 쓴다.
- **MoE 모델은 4bit로 거의 줄지 않는다(11/04 확인).** transformers 5는 MoE 전문가를 층마다 큰 3차원 묶음 하나로 두고, bitsandbytes 4bit는 `nn.Linear`만 바꾼다. 그래서 전문가는 bf16 그대로이고, peft의 4bit 준비 함수는 이것을 fp32로 바꿔 두 배로 만든다(Qwen3-30B-A3B 58GB → 116GB). MoE는 4bit 없이 bf16 LoRA로 돌린다. 학습 스크립트는 큰 bf16 묶음이 남으면 fp32로 바꾸지 않는다(`quantization.upcast_rest: auto`).
- **Qwen3.5·3.6·3.8 계열은 4층 중 3층이 Gated DeltaNet**이라 q/k/v/o가 4층에 1층만 있다. `in_proj_qkv`·`in_proj_z`·`out_proj`를 더해야 모든 층에 LoRA가 붙는다. 학습 스크립트가 붙은 층 수를 보여 주고, 일부 층에만 붙으면 알린다.
- **RNGD에 올리려면** 학습 결과를 원본에 합친 뒤(`merge_adapter.py`) 퓨리오사 형식으로 다시 빌드해야 한다. 가능한지와 걸리는 시간은 확인이 필요하다. RunPod의 vLLM에서는 LoRA를 바로 붙여 쓴다.

### 모델별 설정과 GPU (11/04)

| 설정 파일 | 모델 | 구조 | 방식 | 학습 데이터 `--student` | 예상 메모리(16k 토큰) | GPU |
|---|---|---|---|---|---|---|
| `configs/qwen3_30b_a3b.yaml` | Qwen3-30B-A3B-Instruct-2507 (RNGD 운영 모델 원본) | MoE 128전문가 48층 | bf16 LoRA | `qwen3_30b_a3b_rngd` | 가중치 약 61GB + 학습 중 약 5~10GB | A100 80GB 한 장(먼저 `--check-memory`) |
| `configs/qwen36_35b_a3b.yaml` | Qwen3.6-35B-A3B (RunPod 추론 모델 원본) | MoE 256전문가 40층, DeltaNet 30층 | bf16 LoRA | `qwen36_35b_runpod` | 가중치 약 69GB + 학습 중 약 5~10GB | A100 80GB는 빠듯. H200 141GB 한 장 권장 |
| `configs/qwen38_27b.yaml` | Qwen3.8-27B (기준선) | 밀집 64층, DeltaNet 48층 | 4bit QLoRA | `qwen38` | 4bit 본체 약 13GB + 임베딩·출력층(fp32) 약 10GB + 학습 중 | A100 80GB 한 장이면 넉넉 |
| `configs/qwen35_122b_a10b.yaml` | Qwen3.5-122B-A10B (큰 모델 비교 한 번) | MoE 256전문가 48층, DeltaNet 36층 | bf16 LoRA, GPU 여러 장(`device_map: auto`) | `qwen36_35b_runpod`(35B와 같은 데이터) | 가중치 약 244GB + 학습 중 약 15~20GB | H200 141GB × 4 권장(B200 × 2, 80GB × 4는 빠듯) |

- 예상 메모리는 매개변수 수로 계산한 값이다(확인 필요). 실제 값은 Pod에서 `--check-memory`로 잰다(3.3).
- 122B는 운영 후보가 아니라 '같은 계열에서 모델만 키우면 얼마나 나아지나'를 보는 비교 실험이다. 학습해도 RNGD·온프레미스 서버에 올릴 수 있는지는 확인이 필요하다. 'Qwen3.6-122B'는 11/04 현재 공개되지 않아 같은 구조의 3.5판을 쓴다.
- GPU 여러 장에 나눠 올리면(`device_map: auto`) 한 번에 한 장씩 계산해 속도는 한 장과 비슷하다. 평가용 vLLM도 같은 Pod에서 `--tensor-parallel-size 4`로 띄운다.
- Qwen3.8-2.4T-A95B는 RunPod로도 하지 않는다: bf16 약 4.8TB(4bit도 약 1.3TB)라 GPU 수십 장이 필요하고, 생각 모드를 끌 수 없으며 별도 라이선스다.

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

- Pod: 위 표의 GPU. 디스크는 넉넉히(35B급 bf16 원본 약 70GB + 내려받기 캐시, 합치기까지 하면 그 두 배).
- 코드: `finetune/`과 `deploy/runpod/`만 올린다(빠른 실행 안내 나). 학습 스크립트는 backend 코드를 쓰지 않는다.
- 데이터: `data/finetune/<이름>/`을 Pod의 같은 경로로 올린다.
- 환경은 `bash finetune/pod_setup.sh`로 만든다.
  - uv로 `/workspace/venv-train`을 만들고, Pod의 CUDA 드라이버에 맞는 torch(`--torch-backend=auto`)와 `finetune/requirements.txt`를 깐다.
  - CPU 시험 11개(작은 가짜 모델)를 돌린다. 11 passed면 설치가 맞다.
  - 평가용 vLLM은 `deploy/runpod/setup_vllm.sh`가 `/workspace/venv`에 따로 깐다(vLLM이 자기 torch 판을 깐다).

### 3.2 길이 확인 (GPU 안 씀, 몇 분)

```bash
python finetune/train_qlora.py --config finetune/configs/<모델>.yaml --data data/finetune/<이름> --check-data
```

- 항마다 토큰 수(중앙값·95%·최대)가 나온다. `max_seq_len`(기본 16,384)보다 긴 예시는 자르지 않고 뺀다. 많이 빠지면 `--set max_seq_len=24576`처럼 늘린다(메모리가 더 든다).
- `정답 자르기: {'template': N}`이 정상이다. `eos`가 나오면 대화 틀이 마지막 답을 다르게 감싸는 모델이다. 끝 토큰이 추론 때와 같은지(Qwen 지시형은 `<|im_end|>`) 확인한다.

### 3.3 메모리 확인 (GPU, 모델 내려받기 + 몇 분)

```bash
python finetune/train_qlora.py --config finetune/configs/<모델>.yaml --data data/finetune/<이름> --check-memory
```

- 모델을 올리고 LoRA를 붙인 뒤, 가장 긴 예시 하나로 순전파·역전파를 두 번 해 **최대 GPU 메모리**와 한 걸음 시간을 잰다. 학습·저장은 하지 않는다. 결과는 `finetune/out/<run_name>/check_memory.yaml`.
- 함께 나오는 것: 저장 방식별 매개변수 크기(4bit·bf16·fp32), 4bit가 아닌 큰 묶음(MoE면 `experts.gate_up_proj`), LoRA가 붙은 곳과 층 수, 대략 학습 시간.
- 최대 메모리가 GPU의 92%를 넘으면 경고한다. 그러면 `--set max_seq_len=12288`처럼 줄이거나(긴 예시가 빠진다, `--check-data`로 몇 개인지 본다) 더 큰 GPU를 쓴다. GPU 두 장이면 `--set device_map=auto`.
- LoRA가 일부 층에만 붙었다고 나오면 학습하지 말고 `lora.target_modules`를 고친다.

### 3.4 학습

```bash
nohup python finetune/train_qlora.py --config finetune/configs/<모델>.yaml --data data/finetune/<이름> > train.log 2>&1 &
tail -f train.log
```

- 결과: `finetune/out/<run_name>/adapter/`(LoRA), `train_info.yaml`(설정·데이터·길이·손실·매개변수 크기·LoRA 층·최대 메모리·버전·GPU·시간), `log_history.json`

학습 곡선을 W&B로 보려면

```bash
export WANDB_API_KEY=<본인 키>                  # Pod 터미널에서만. 저장소·채팅·노션에 적지 않는다
nohup python finetune/train_qlora.py --config finetune/configs/<모델>.yaml --data data/finetune/<이름> \
    --set wandb.enabled=true wandb.entity=<팀 조직 이름, 개인이면 빼기> > train.log 2>&1 &
```

- 프로젝트 `to21-msds-qlora`에 `run_name` 이름으로 실행이 생긴다. 실행 주소는 `train.log`와 `train_info.yaml`(`wandb_url`)에 남는다.
- 보이는 것: `train/loss`·`train/learning_rate`·`train/grad_norm`, `eval/loss`(학습 전 0단계부터), GPU 메모리·사용률, 설정, 예시 수와 항별 길이 표(`data/lengths`).
- **보내지 않는 것: 학습 글(안내문·MSDS 원문·정답)과 모델·체크포인트(D-47).** 시험(`finetune/tests`)이 W&B 기록에 학습 글이 없는지 확인한다.
- Pod에서 바깥으로 못 나가면 `WANDB_MODE=offline`으로 돌리고, 끝난 뒤 `wandb sync wandb/offline-run-*`로 올린다.
- 볼 것: `eval/loss`가 학습 전보다 내려가다가 다시 오르기 시작하면 외우기 시작한 것이다. 그 지점의 단계 수로 에폭을 줄인다.
- 걸리는 시간은 모델과 길이에 따라 다르다(확인 필요). 처음 몇 단계 로그의 단계당 시간 × 전체 단계로 계산한다. 전체 단계 ≈ 학습 예시 수 ÷ 8 × 2(에폭).
- 값을 바꿔 다시 돌릴 때는 `--set run_name=to21_lora_qwen3_30b_a3b_v2 train.lr=5e-5`처럼 이름도 바꾼다.

기본값과 이유 (공통 `configs/qlora.yaml`, 모델별 파일이 일부를 덮는다)

| 값 | 기본 | 이유 |
|---|---|---|
| LoRA 위치 | 주의 투영 4개(q·k·v·o). Qwen3.5·3.6·3.8 계열은 DeltaNet 투영 3개(in_proj_qkv·in_proj_z·out_proj)를 더한다 | MoE 전문가 층까지 넣으면 메모리·시간이 크게 늘고 vLLM LoRA 지원도 모델마다 다르다 |
| r / alpha | 16 / 32 | 예시 수백 개에 흔히 쓰는 크기. 형식·규칙을 맞추는 데는 충분하다 |
| 학습률·에폭 | 1e-4, 2에폭 | 예시가 적어 오래 돌리면 외운다. 검증 손실이 다시 오르면 에폭을 줄인다 |
| 한 번에 반영 | 8개(1 × 8) | 긴 예시라 묶음 크기 1, 누적 8 |
| 4bit | 밀집 모델만 NF4, 이중 양자화. MoE는 bf16 | MoE 전문가는 4bit로 줄지 않아 4bit의 이득이 주의 층 1~2GB뿐이다 |
| 4bit 아닌 부분 fp32 | auto(늘어나는 크기 16GB 이하일 때만) | peft 기본은 모두 fp32로 바꾸는데, 큰 bf16 묶음이 있으면 두 배가 되어 넘친다 |
| 정답 자리 logits만 | 켬 | 어휘가 15만~25만이라 16k 토큰 전체 logits는 fp32로 10~16GB다. 손실은 정답 토큰에만 걸리므로 값은 같다(시험으로 확인) |

## 4. 평가

학습 전 모델과 학습 후 모델을 **같은 서버·같은 정밀도·같은 설정**으로 같은 문서에 돌려 `score.py`로 비교한다.

명령은 빠른 실행 안내 라에 있다. 정리하면:

- 서버: `finetune/serve_lora.sh`가 팀 서버(`deploy/runpod/serve_vllm.sh`)와 같은 설정(vLLM 0.32.0, 공백 금지 구조화 출력 ADR-017, 이미지 2장)에 LoRA만 더해 띄운다. `127.0.0.1`에만 열고 키는 환경변수로 넘긴다(ps에 보이지 않게). PC는 ssh 터널로 붙는다.
- 학습 전은 같은 서버의 원본 이름, 학습 후는 LoRA 이름 `to21-ft`다. 35B·30B는 운영과 같은 FP8 원본에 LoRA를 붙인다(학습은 bf16 원본으로 했다). 같은 서버·같은 정밀도라 전후 차이가 LoRA 효과다.
- 태그: `finetune/eval_tags.yaml`. 요청 방식(행 형식 항·구조화 방식·이미지·출력 한도·생각 모드)은 학습 데이터를 만든 학생 태그와 같고, 주소·키(`FT_VLLM_*`)와 모델 이름만 다르다. 팀 RunPod 서버 설정(`RUNPOD_VLLM_*`)과 겹치지 않는다.

- 팀원은 개발 10건으로 본다. 평가 11건(manifest 평가)은 설정을 고정한 뒤 F가 한 번만 채점한다(D-43).
- Qwen3.5·3.6·3.8 계열은 학습 때 글 모델만 올린다(`Qwen3_5*ForCausalLM`). vLLM이 이 LoRA 이름(`model.layers.N...`)과 DeltaNet 층 LoRA를 그대로 받는지는 확인이 필요하다.
- vLLM이 이 모델·양자화에서 LoRA를 못 붙이면, `merge_adapter.py`로 합친 체크포인트를 `vllm serve <merged> --quantization fp8`처럼 띄우고 원본도 같은 옵션으로 띄워 비교한다.
- 항별 성공률·재추출 수는 각 실행의 `checks/`, 시간은 `timing.jsonl`에 있다.

## 5. 끝나면

- Pod의 `data/finetune/`과 쪽 글자를 지운다(D-47). LoRA(`adapter/`, 수백 MB)만 팀 공유 위치로 옮긴다.
- `train_info.yaml`, `report.md`, 성적표 비교를 작업기록에 남긴다.

## 알려진 한계

- 교사 답이 정답은 아니다. 교사가 틀린 칸은 학생도 따라 틀린다. 그래서 평가는 교사가 아니라 사람이 검수한 골드로 한다.
- 예시 수가 수백 개라 새 지식보다 형식·작성 규칙(행 나누기, 코드표, 숫자 묶음)을 맞추는 효과가 주로 난다.
- 2항 그림문자(이미지)는 학습하지 않는다.
- bitsandbytes 4bit 경로는 GPU에서만 돈다. 이 저장소의 시험은 CPU에서 4bit 없이 같은 코드를 확인한다. 메모리 수치는 CPU 시험으로 확인할 수 없어 Pod에서 `--check-memory`로 잰다.
- MoE 전문가까지 4bit로 줄이려면 MoE 전용 도구(예: experts4bit-qlora, Unsloth)가 필요하다. 11/6까지는 쓰지 않는다.
