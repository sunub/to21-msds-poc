"""Build version3 by comparing page image, PDF/Paddle text, and Qwen3-VL-4B."""
from __future__ import annotations

import csv, json, shutil, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGES = ROOT / "data/pages"
MODEL = "Qwen/Qwen3-VL-4B-Instruct"

PROMPT = """원본 MSDS 페이지 이미지와 두 텍스트 후보를 대조하여 최종 원문을 전사하라.
이미지가 최종 기준이다. 요약·번역·임의 보완을 하지 마라.
읽기 순서, 띄어쓰기, 숫자, 코드, 단위와 표의 행 관계를 보존하라.
PDF 후보의 정확한 문자를 우선 참고하고 Paddle 후보로 이미지 문자와 읽기 순서를 확인하라.
2. 유해성·위험성에서는 분류 항목과 구분값을 같은 행에 두고 H/P 코드와 해당 문장을 짝지어라.
그림문자는 보이는 순서대로 [그림문자 GHSxx]로 기록하고 신호어 값을 누락하지 마라.
머리글과 푸터도 보이는 문자라면 포함하라. 설명 없이 최종 전사만 출력하라.

[PDF 텍스트 후보]
{pdf}

[PDF+Paddle 후보]
{paddle}
"""

PICTOGRAM_PROMPT = """이 MSDS 페이지에서 GHS 그림문자와 신호어만 판독하라.
그림문자의 개수와 왼쪽부터의 순서를 원본 이미지로 직접 확인하라.
대응: 폭발=GHS01, 불꽃=GHS02, 원위의 불꽃=GHS03, 가스용기=GHS04, 부식=GHS05,
해골=GHS06, 느낌표=GHS07, 사람 가슴 별모양=GHS08, 죽은 나무와 물고기=GHS09.
그림문자가 없으면 '[그림문자 0개]'라고 써라. 다음 형식 외에는 출력하지 마라.
[그림문자 N개: GHSxx, GHSxx]
[신호어: 위험/경고/없음]"""

def main() -> int:
    import torch
    from transformers import BitsAndBytesConfig, pipeline
    with (ROOT / "data/manifest.csv").open(encoding="utf-8-sig", newline="") as f:
        docs = list(csv.DictReader(f))
    quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_compute_dtype=torch.float16,
                               bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True)
    pipe = pipeline("image-text-to-text", model=MODEL, device_map="auto", dtype=torch.float16,
                    model_kwargs={"quantization_config": quant})
    overall = []
    for row in docs:
        doc = row["doc_id"]
        v1, v2, out = PAGES/"version1"/doc, PAGES/"version2"/doc, PAGES/"version3"/doc
        out.mkdir(parents=True, exist_ok=True); candidates = out/"candidates"; candidates.mkdir(exist_ok=True)
        images = sorted(v2.glob("p[0-9][0-9][0-9].png"))
        completed = 0
        for image in images:
            stem = image.stem; final = out/f"{stem}.txt"; qwen = candidates/f"{stem}_qwen4b.txt"
            shutil.copy2(image, out/image.name)
            pdf_src, paddle_src = v1/f"{stem}.txt", v2/f"{stem}.txt"
            if pdf_src.exists(): shutil.copy2(pdf_src, candidates/f"{stem}_pdf.txt")
            if paddle_src.exists(): shutil.copy2(paddle_src, candidates/f"{stem}_pdf_paddle.txt")
            reference = ""
            if pdf_src.exists(): reference += pdf_src.read_text(encoding="utf-8", errors="replace")
            if paddle_src.exists(): reference += paddle_src.read_text(encoding="utf-8", errors="replace")
            needs_pictogram = "그림문자" in reference or "pictogram" in reference.lower()
            pictogram = candidates/f"{stem}_pictograms.txt"
            if final.exists() and qwen.exists() and (not needs_pictogram or pictogram.exists()):
                completed += 1; print(f"[{doc} {stem}] skipped", flush=True); continue
            started=time.perf_counter()
            if not qwen.exists():
                pdf = pdf_src.read_text(encoding="utf-8", errors="replace") if pdf_src.exists() else ""
                paddle = paddle_src.read_text(encoding="utf-8", errors="replace") if paddle_src.exists() else ""
                prompt = PROMPT.format(pdf=pdf[:14000], paddle=paddle[:14000])
                messages = [{"role":"user","content":[{"type":"image","path":str(image)}, {"type":"text","text":prompt}]}]
                result=pipe(text=messages,max_new_tokens=8192,do_sample=False)
                generated=result[0].get("generated_text","")
                if isinstance(generated,list): generated=generated[-1].get("content","")
                qwen.write_text(str(generated).rstrip()+"\n",encoding="utf-8")
            text=qwen.read_text(encoding="utf-8")
            if needs_pictogram and not pictogram.exists():
                messages = [{"role":"user","content":[{"type":"image","path":str(image)}, {"type":"text","text":PICTOGRAM_PROMPT}]}]
                result=pipe(text=messages,max_new_tokens=128,do_sample=False)
                value=result[0].get("generated_text","")
                if isinstance(value,list): value=value[-1].get("content","")
                pictogram.write_text(str(value).strip()+"\n",encoding="utf-8")
            if needs_pictogram:
                text=text.rstrip()+"\n\n[그림문자·신호어 전용 판독]\n"+pictogram.read_text(encoding="utf-8")
            final.write_text(text.rstrip()+"\n",encoding="utf-8")
            (candidates/f"{stem}_meta.json").write_text(json.dumps({"seconds":round(time.perf_counter()-started,3),"model":MODEL},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
            completed += 1; print(f"[{doc} {stem}] {completed}/{len(images)}",flush=True)
        (out/"config.json").write_text(json.dumps({"doc_id":doc,"version":"version3","dpi":200,"model":MODEL,"quantization":"NF4 4-bit","method":"image + PDF + Paddle candidates -> Qwen final transcription","pages":len(images)},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        (out/"report.md").write_text(f"# {doc} version3\n\n- 페이지: {len(images)}\n- 방식: PDF + PaddleOCR + Qwen3-VL-4B 비교 전사\n- 입력: 200 DPI\n",encoding="utf-8")
        overall.append({"doc_id":doc,"pages":len(images)})
    (PAGES/"version3"/"summary.json").write_text(json.dumps(overall,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return 0

if __name__ == "__main__": raise SystemExit(main())
