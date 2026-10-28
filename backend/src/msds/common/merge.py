"""묶음별 모델 응답을 하나의 TO21 문서로 합친다 (D-35).

입력: {묶음 id: 응답(dict)} — 응답 형식은 schema.bundle_response_schema 참고
출력: (TO21 문서, 검수 정보 목록)

- MSDS 건수는 묶음 ①의 msds 길이로 정한다.
- 다른 묶음은 같은 순서(msds_index)로 합친다. 건수가 다르면 경고를 남기고 앞에서부터 맞춘다.
- 근거(evidence)는 TO21 형식의 msds[].evidence로 옮긴다.
- 실버 모드의 rules·note는 TO21 형식에 칸이 없으므로 검수 정보 목록으로 따로 돌려준다 (D-33).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
SCHEMA_VERSION = "TO21-MSDS-EXT v0.6"
DICTIONARY_VERSION = "v0.6"


def now_kst() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


def merge_bundles(responses: dict[str, dict], manifest_row: dict, engine: str,
                  evidence_method: str = "vLM") -> tuple[dict, list[dict], list[str]]:
    warnings: list[str] = []
    if "b1" not in responses or not responses["b1"]:
        raise ValueError("묶음 ①(b1) 결과가 없어 문서를 합칠 수 없습니다.")

    b1 = responses["b1"]
    msds = [dict(m) for m in b1.get("msds") or []]
    n = len(msds)
    if n == 0:
        raise ValueError("묶음 ①이 MSDS를 하나도 돌려주지 않았습니다.")

    for bid, resp in responses.items():
        if bid == "b1" or not resp:
            continue
        items = resp.get("msds") or []
        if len(items) != n:
            warnings.append(f"{bid}: MSDS 건수 {len(items)} ≠ 묶음 ① {n}. 앞에서부터 맞춥니다.")
        for i in range(min(n, len(items))):
            for k, v in items[i].items():
                msds[i][k] = v

    review_items: list[dict] = []
    for m in msds:
        m.setdefault("evidence", [])
        m.setdefault("validation", [])
        m.setdefault("extras", m.get("extras") or [])
    for bid, resp in responses.items():
        for e in (resp or {}).get("evidence") or []:
            idx = e.get("msds_index", 0)
            if not isinstance(idx, int) or not 0 <= idx < n:
                warnings.append(f"{bid}: 근거의 msds_index {idx}가 범위를 벗어나 0으로 둡니다.")
                idx = 0
            msds[idx]["evidence"].append({
                "field": e.get("field"),
                "page": e.get("page"),
                "bbox": None,
                "source_text": (e.get("source_text") or None) and e["source_text"][:200],
                "confidence": None,
                "method": evidence_method,
                "needs_review": None,
            })
            if "rules" in e or "note" in e:
                review_items.append({
                    "bundle": bid,
                    "msds_index": idx,
                    "field": e.get("field"),
                    "page": e.get("page"),
                    "source_text": e.get("source_text"),
                    "rules": e.get("rules") or [],
                    "note": e.get("note"),
                })

    b1doc = b1.get("doc") or {}
    doc = {
        "doc_id": manifest_row["doc_id"],
        "source_file": manifest_row["source_file"],
        "page_count": int(manifest_row["pages"]) if manifest_row.get("pages") else None,
        "text_layer": manifest_row.get("text_layer") or None,
        "language": b1doc.get("language") or manifest_row.get("language") or None,
        "msds_count": n,
        "schema_version": SCHEMA_VERSION,
        "dictionary_version": DICTIONARY_VERSION,
        "extraction": {"engine": engine, "extracted_at": now_kst()},
    }
    if b1doc.get("msds_count") not in (None, n):
        warnings.append(f"b1이 적은 msds_count {b1doc.get('msds_count')} ≠ 실제 msds 건수 {n}. 실제 건수를 씁니다.")
    return {"doc": doc, "msds": msds}, review_items, warnings


def components_summary(b1_response: dict) -> str:
    """묶음 ①의 성분 목록을 다른 묶음 프롬프트에 넘길 글로 만든다 (comp_ref를 맞추기 위함)."""
    lines = []
    for i, m in enumerate(b1_response.get("msds") or []):
        name = ((m.get("product") or {}).get("name")) or "(제품명 없음)"
        lines.append(f"- MSDS {i} (msds_index={i}): {name}")
        comps = m.get("components") or []
        if not comps:
            lines.append("    성분 없음 → 제품 전체 값은 comp_ref='MIX'")
        for c in comps:
            ids = ", ".join(x for x in [c.get("cas_no") and f"CAS {c['cas_no']}",
                                        c.get("ke_no") and f"KE {c['ke_no']}"] if x)
            lines.append(f"    comp_ref='{c.get('seq')}': {c.get('name')}" + (f" ({ids})" if ids else ""))
        lines.append("    제품 전체(혼합물 전체) 값은 comp_ref='MIX'")
    return "\n".join(lines)
