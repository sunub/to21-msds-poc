"""Restore metadata.json for already-rendered page directories without rerendering."""
from __future__ import annotations
import csv, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
ids = ["T21-002","T21-005","T21-006","T21-010","T21-014","T21-023","T21-025","T21-039","T21-043","T21-045","T21-M001","T21-M002","T21-M004","T21-M005","T21-M013","T21-S001","T21-S003","T21-S013","T21-S014","T21-S016"]
with (ROOT/"data/manifest.csv").open(encoding="utf-8-sig", newline="") as f: manifest={r["doc_id"]:r for r in csv.DictReader(f)}
for doc_id in ids:
 d=ROOT/"data/pages"/doc_id
 if not d.is_dir(): continue
 m=manifest.get(doc_id,{})
 pages=sorted(d.glob("p[0-9][0-9][0-9].txt"))
 states=["정상"]*len(pages)
 expected=m.get("text_layer","")
 if expected in {"없음","글꼴깨짐"}: states=[expected]*len(pages)
 data={"doc_id":doc_id,"source_file":m.get("source_file",""),"dpi":200,"schema_version":"TO21-MSDS-EXT v0.5","dictionary_version":"v0.5","extraction":{"engine":"PyMuPDF"},"expected_text_layer":expected,"input_mode":m.get("input_mode",""),"language":m.get("language",""),"msds_count":m.get("msds_count",""),"actual_page_states":states,"ocr_required_pages":list(range(1,len(pages)+1)) if expected in {"없음","글꼴깨짐"} else [],"page_count":len(pages)}
 (d/"metadata.json").write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
 print(doc_id)
