"""추출값 확인(2.2)의 검수 기록: 칸별 확인·수정, 항 확인, 화면용 보기 (서비스 API).

추출 결과(outputs)는 고치지 않는다. 사람이 고친 값은 검수 기록에 원래 값·근거·검토자·시각과 함께 따로 두고,
재생성할 때만 apply_edits로 얹는다. 파일을 읽거나 쓰지 않는 순수 함수만 둔다. 저장은 store다.

칸 경로는 msds 한 건 기준이다: components[0].cas_no. 값이 있는 스칼라 칸만 보여 주고 고칠 수 있다.
"""
from __future__ import annotations

import copy
import re

from msds.extract.inputs import EXTRACT_SECTIONS
from msds.service.code_names import code_name, display_value

SECTION_OF_ROOT = {"meta": 1, "product": 1, "companies": 1, "hazard": 2, "composition": 3, "components": 3,
                   "exposure_limits": 8, "physchem": 9, "toxicity": 11, "cmr": 11, "ecotox": 12, "waste": 15,
                   "transport": 14, "dangerous_goods": 15, "regulations": 15, "intl_class": 15}
SECTIONS = EXTRACT_SECTIONS    # 추출·검수 대상 항
# 코드가 채우는 칸, 원문 그대로의 칸, 근거 줄
_HIDDEN = {"seq", "comp_ref", "parent_seq", "dp", "status", "note", "raw", "text", "refs", "std_code", "match_score",
           "line", "lines", "page", "section_no", "after_item", "reason", "suggested_code", "item_code", "title_raw",
           "key", "data_source"}
_LABEL = {"msds_no": "MSDS 번호", "doc_code": "문서 코드", "revision_no": "개정 차수", "revision_label": "개정 표기",
          "header_product_name": "머리글 제품명", "source_note": "출처 표기", "first_issue_date": "최초 작성일",
          "last_revision_date": "최종 개정일", "name": "이름", "name_en": "영문명", "code": "코드", "synonyms": "이명",
          "uses": "용도", "restrictions": "사용상의 제한", "address": "주소", "tel": "전화", "role": "구분",
          "cas_no": "CAS 번호", "ke_no": "KE 번호", "ec_no": "EC 번호", "other_id": "기타 식별번호",
          "other_id_type": "식별번호 종류", "lower": "하한", "upper": "상한", "lower_op": "하한 부등호",
          "upper_op": "상한 부등호", "value": "값", "unit": "단위", "approx": "약", "cond": "조건",
          "text_value": "값", "prop_code": "항목", "type": "종류", "signal_word": "신호어", "content_note": "함유량 비고",
          "content_basis": "함유량 기준", "trade_secret": "영업비밀", "approval_no": "승인번호",
          "approval_expiry": "승인 기한", "read_across_cas": "유사물질 참조 CAS",
          # 이름은 TO21 추출스키마 v0.6 의 칸 설명을 따른다. 스키마 키가 화면에 그대로 보이지 않게 한다
          "department": "담당부서", "postcode": "우편번호", "site": "사업장명", "hours": "운영시간",
          "use_category_code": "용도분류 코드", "classified": "분류 해당 여부", "group": "유해성 구분",
          "class_code": "분류", "category": "구분", "effect": "영향 구분", "route_form": "노출 형태",
          "target_organs": "표적장기", "other_hazards": "기타 유해성", "health": "NFPA 보건", "fire": "NFPA 화재",
          "reactivity": "NFPA 반응성", "special": "NFPA 특수", "no_hazardous_component": "유해성분 미함유 표기",
          "standard": "기준 출처", "limit_type": "기준 종류", "kr_basis": "국내 기준 구분", "form": "입자 형태",
          "notations": "표기", "bio_determinant": "지표 물질", "bio_medium": "시료 매체", "bio_timing": "채취 시기",
          "temp": "측정 온도", "temp_unit": "온도 단위", "method": "측정 방법", "reference": "기준 물질",
          "pressure": "압력", "pressure_unit": "압력 단위", "conc_value": "농도", "conc_unit": "농도 단위",
          "descriptor": "지표", "species": "시험종", "sex": "성별", "duration_value": "노출 시간",
          "duration_unit": "노출 시간 단위", "physical_form": "흡입 형태", "guideline": "시험 지침",
          "exposure_type": "노출 형태", "classification": "분류 결과", "converted": "환산값",
          "mode": "운송 규정", "regulated": "운송 규제 해당", "un_no": "유엔 번호", "shipping_name": "적정 선적명",
          "hazard_class": "위험성 등급", "sub_risk": "부위험성", "packing_group": "용기등급",
          "marine_pollutant": "해양오염물질", "ems_fire": "화재 비상조치(EmS)", "ems_spill": "유출 비상조치(EmS)",
          "basis_raw": "적용 규정 원문", "law": "법령", "item_raw": "규제 항목", "applicable": "해당 여부",
          "remark": "부가 표기", "country": "국가", "sub_class": "세부 구분", "value_raw": "값 원문",
          "item": "품명", "water_soluble": "수용성 구분", "grade": "위험등급", "designated": "지정폐기물",
          "waste_type": "폐기물 종류", "class_raw": "분류 표기", "h_code": "H 코드", "agency": "분류 기관·법령",
          "mark": "각주 기호", "page_start": "시작 페이지", "page_end": "끝 페이지"}
# 같은 키라도 놓인 자리(바로 위 키)에 따라 이름이 다르다
_CONTEXT_LABEL = {("contacts", "type"): "연락처 종류", ("contacts", "value"): "연락처", ("composition", "type"): "물질 구분",
                  ("p_statements", "type"): "P 유형", ("h_statements", "code"): "H 코드", ("p_statements", "code"): "P 코드",
                  ("pictograms", "code"): "그림문자 코드", ("product", "code"): "제품 코드", ("h_statements", "system"): "코드 체계",
                  ("intl_class", "system"): "분류 체계", ("toxicity", "endpoint"): "독성 항목", ("ecotox", "endpoint"): "생태 항목",
                  ("dangerous_goods", "class"): "위험물 류별", ("cmr", "class"): "분류 등급", ("cmr", "hazard"): "유해성",
                  ("companies", "role"): "회사 구분"}
# 값 묶음: 묶음 이름을 앞에 붙인다. 값 자체는 묶음 이름으로
_BLOCK_LABEL = {"content": "함유량", "cycle": "측정·진단 주기", "qty": "규제 수량", "qty_alt": "규제 수량(병기)",
                "threshold": "기준 농도", "designated_qty": "지정수량"}
_BULLET = re.compile(r"^[\s○〇●•·ㆍ\-*]+")
_ROOT_TITLE = {"meta": "문서 정보", "product": "제품", "companies": "회사", "hazard": "분류와 표지", "composition": "구성",
               "components": "성분", "exposure_limits": "노출 기준", "physchem": "물리화학적 특성", "toxicity": "독성",
               "cmr": "발암성 등", "ecotox": "환경 영향", "waste": "폐기", "transport": "운송",
               "dangerous_goods": "위험물", "regulations": "규제", "intl_class": "국제 분류",
               "narratives": "서술", "extras": "기타 항목"}
_GROUP_KEYS = ("title_raw", "name", "prop_code", "item_code", "law_code", "item", "code")
_TOKEN = re.compile(r"([^.\[\]]+)|\[(\d+)\]")


def empty() -> dict:
    return {"fields": {}, "sections": {}, "log": []}


def _parts(path: str) -> list:
    return [name or int(index) for name, index in _TOKEN.findall(path)]


def _get(root, path: str):
    node = root
    for p in _parts(path):
        node = node[p]
    return node


def _field_key(msds_index: int, path: str) -> str:
    return f"{msds_index}:{path}"


def _section_key(msds_index: int, section: int) -> str:
    return f"{msds_index}:{section}"


def _section_of(msds: dict, root: str, index: int | None) -> int | None:
    if root in SECTION_OF_ROOT:
        return SECTION_OF_ROOT[root]
    item = msds[root][index] if index is not None and isinstance(msds.get(root), list) else None
    if root == "narratives" and item:
        m = re.match(r"S(\d+)_", item.get("item_code") or "")
        return int(m.group(1)) if m else None
    if root == "extras" and item:
        return item.get("section_no")
    return None


def _coerce(original, value):
    """원래 칸의 형식에 맞춘다. 빈 값은 값 없음(None)이다."""
    text = "" if value is None else str(value).strip()
    if text == "":
        return None
    if isinstance(original, bool):
        if text.lower() in ("true", "참"):
            return True
        if text.lower() in ("false", "거짓"):
            return False
        raise ValueError("참 또는 거짓으로 적어 주세요")
    if isinstance(original, (int, float)):
        try:
            number = float(text)
        except ValueError:
            raise ValueError("숫자로 적어 주세요") from None
        return int(number) if number.is_integer() and isinstance(original, int) else number
    return text


def set_field(record: dict, doc: dict, msds_index: int, path: str, action: str, value, reviewer: str, at: str) -> None:
    """action: confirm(확인함) | edit(수정) | reset(되돌림). 없는 칸이면 KeyError, 형식이 틀리면 ValueError."""
    try:
        msds = doc["msds"][msds_index]
        original = _get(msds, path)
    except (IndexError, KeyError, TypeError):
        raise KeyError(path) from None
    if isinstance(original, (dict, list)) or original is None:
        raise KeyError(path)
    key = _field_key(msds_index, path)
    entry = {"msds_index": msds_index, "path": path, "action": action, "reviewer": reviewer, "at": at}
    if action == "edit":
        new = _coerce(original, value)
        record["fields"][key] = {"state": "edited", "value": new, "original": original, "reviewer": reviewer, "at": at}
        entry.update(value=new, original=original)
    elif action == "confirm":
        record["fields"][key] = {"state": "confirmed", "reviewer": reviewer, "at": at}
    else:
        record["fields"].pop(key, None)
    record["log"].append(entry)


def set_section(record: dict, msds_index: int, section: int, confirmed: bool, reviewer: str, at: str) -> None:
    if section not in SECTIONS or msds_index < 0:
        raise KeyError(section)
    key = _section_key(msds_index, section)
    if confirmed:
        record["sections"][key] = {"reviewer": reviewer, "at": at}
    else:
        record["sections"].pop(key, None)
    record["log"].append({"msds_index": msds_index, "section": section, "action": "section_confirm" if confirmed
                          else "section_unconfirm", "reviewer": reviewer, "at": at})


def apply_edits(doc: dict, record: dict) -> dict:
    """고친 값을 얹은 복사본. 원본은 그대로다."""
    out = copy.deepcopy(doc)
    for key, f in record["fields"].items():
        if f["state"] == "edited":
            index, path = key.split(":", 1)
            parts = _parts(path)
            node = out["msds"][int(index)]
            for p in parts[:-1]:
                node = node[p]
            node[parts[-1]] = f["value"]
    return out


def _walk(value, path: str):
    """보여 줄 스칼라 칸 (경로, 값, 옆 칸들)."""
    if isinstance(value, dict):
        for k, v in value.items():
            if k not in _HIDDEN:
                yield from _walk(v, f"{path}.{k}" if path else k)
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from _walk(v, f"{path}[{i}]")
    elif value is not None and value != "":
        yield path, value


def _statement_key(key) -> str | None:
    """원문 '〇 | 금지물질 | :' 같은 키에서 표 칸 구분·글머리를 뺀 이름."""
    text = " ".join(re.sub(r"[|:]", " ", key or "").split())
    return _BULLET.sub("", text) or None


def _label(msds: dict, path: str) -> str:
    leaf = _parts(path)
    if len(leaf) >= 3 and leaf[-1] == "value" and leaf[-3] == "statements":
        statement = _get(msds, path.rsplit(".", 1)[0])
        return _statement_key(statement.get("key")) or "문장"
    names = [p for p in leaf if isinstance(p, str)]
    name = names[-1] if names else path
    container = names[-2] if len(names) >= 2 else None
    if (container, name) in _CONTEXT_LABEL:
        return _CONTEXT_LABEL[(container, name)]
    if container in _BLOCK_LABEL:
        block = _BLOCK_LABEL[container]
        return block if name == "value" else f"{block} {_LABEL.get(name, name)}"
    return _LABEL.get(name, name)


def _group_title(root: str, item, fallback: str) -> str:
    if isinstance(item, dict):
        if root in ("toxicity", "ecotox") and item.get("endpoint"):
            title = code_name(item["endpoint"]) or str(item["endpoint"])
            return f"{title} · {item['descriptor']}" if item.get("descriptor") else title
        for k in _GROUP_KEYS:
            if item.get(k):
                return code_name(item[k]) or str(item[k])
    return fallback


def _evidence_index(msds: dict) -> dict:
    return {e["field"]: e for e in msds.get("evidence") or []}


def _evidence_for(index: dict, path: str):
    """가장 긴 앞부분이 맞는 근거."""
    while path:
        if path in index:
            return index[path]
        m = re.match(r"(.*)(\.[^.\[\]]+|\[\d+\])$", path)
        path = m.group(1) if m else ""
    return None


def build_view(doc: dict, checks: dict, state_sections: list[dict], record: dict) -> dict:
    """{summary, msds: [{msds_index, info, sections: [{section, title, status, pages, needs_review, problems,
    confirmed, field_count, checked_count, groups: [{path, title, fields: [...]}]}]}]}"""
    review_set = {(r["msds_index"], r["section"]) for r in checks.get("needs_review", [])}
    state = {(s["msds_index"], s["section"]): s for s in state_sections}
    section_problems: dict[tuple[int, int], list[str]] = {}
    for c in checks.get("sections", []):
        section_problems.setdefault((c["msds_index"], c["section"]), []).extend(
            list(c.get("errors") or []) + list(c.get("check_problems") or []))
    for p in checks.get("expand_problems", []):
        section_problems.setdefault((p["msds_index"], p["section"]), []).append(f"{p['kind']}: {p.get('detail')}")
    validator: list[tuple[str, str]] = [(v["field"], f"{v.get('rule') or ''} {v['message']}".strip())
                                        for v in checks.get("to21_validator", []) if v.get("field")]
    out, total_fields, checked_fields, edited = [], 0, 0, 0
    for i, msds in enumerate(doc["msds"]):
        evidence = _evidence_index(msds)
        sections = {no: {"groups": {}} for no in SECTIONS}
        for root, node in msds.items():
            if root in ("evidence", "validation"):
                continue
            items = list(enumerate(node)) if isinstance(node, list) else [(None, node)]
            for index, item in items:
                no = _section_of(msds, root, index)
                if no not in sections:
                    continue
                base = f"{root}[{index}]" if index is not None else root
                group = sections[no]["groups"].setdefault(base, {"path": base, "title": _group_title(root, item, _ROOT_TITLE.get(root, root)), "fields": []})
                for path, value in _walk(item, base):
                    rec = record["fields"].get(_field_key(i, path), {})
                    ev = _evidence_for(evidence, path) or {}
                    full = f"msds[{i}].{path}"
                    shown = rec["value"] if rec.get("state") == "edited" else value
                    group["fields"].append({
                        "path": path, "label": _label(msds, path), "value": shown,
                        "display": display_value(path.rsplit(".", 1)[-1], shown),
                        "original": rec.get("original"), "state": rec.get("state", "unchecked"),
                        "reviewer": rec.get("reviewer"), "at": rec.get("at"),
                        "page": ev.get("page"), "source_text": ev.get("source_text"),
                        "problems": [m for f, m in validator if f == full]})
        rows = []
        for no in SECTIONS:
            groups = [g for g in sections[no]["groups"].values() if g["fields"]]
            fields = [f for g in groups for f in g["fields"]]
            confirmed = record["sections"].get(_section_key(i, no))
            s = state.get((i, no), {})
            group_problems = [m for f, m in validator if any(f == f"msds[{i}].{g['path']}" for g in groups)]
            total_fields += len(fields)
            checked = sum(f["state"] != "unchecked" for f in fields)
            checked_fields += checked if not confirmed else len(fields)
            edited += sum(f["state"] == "edited" for f in fields)
            rows.append({"section": no, "title": s.get("title"), "status": s.get("status", "done"),
                         "pages": s.get("pages", []), "needs_review": (i, no) in review_set,
                         "problems": section_problems.get((i, no), []) + group_problems,
                         "confirmed": confirmed, "field_count": len(fields), "checked_count": checked,
                         "groups": groups})
        meta = msds.get("meta") or {}
        comp = msds.get("composition") or {}
        out.append({"msds_index": i, "info": {"product_name": (msds.get("product") or {}).get("name"),
                                              "last_revision_date": meta.get("last_revision_date"),
                                              "composition_type": comp.get("type"),
                                              "component_count": len(msds.get("components") or [])},
                    "sections": rows})
    total = sum(len(m["sections"]) for m in out)
    return {"msds": out, "summary": {"sections_total": total, "sections_confirmed": len(record["sections"]),
                                     "fields_total": total_fields, "fields_checked": checked_fields,
                                     "fields_edited": edited}}


_COMPOSITION_TYPES = {"단일물질": "단일물질", "혼합물": "혼합물"}


def document_extras(doc: dict, checks: dict, state_sections: list[dict], record: dict) -> dict:
    """[A2] 목록·머리줄 칸 (contracts/5-api document_extras). 첫 MSDS 기준이고 사람이 고친 값을 얹는다.

    values_review.state: 미검수(확인한 칸·항 0) / 일부 / 완료(모든 항 확인 완료)."""
    summary = build_view(doc, checks, state_sections, record)["summary"]
    started = summary["fields_checked"] > 0 or summary["sections_confirmed"] > 0
    finished = summary["sections_total"] > 0 and summary["sections_confirmed"] >= summary["sections_total"]
    values_review = {"state": "완료" if finished else "일부" if started else "미검수", **summary}
    msds_list = apply_edits(doc, record)["msds"]
    if not msds_list:
        return {"product_name": None, "doc_code": None, "msds_revision_date": None, "composition": None,
                "values_review": values_review}
    first = msds_list[0]
    meta = first.get("meta") or {}
    return {"product_name": (first.get("product") or {}).get("name"),
            "doc_code": meta.get("doc_code"),
            "msds_revision_date": meta.get("last_revision_date") or meta.get("first_issue_date"),
            # 검수에서 이 칸을 자유 글로 고칠 수 있다. 계약(단일물질·혼합물·null) 밖 값은 내리지 않는다
            "composition": {"type": _COMPOSITION_TYPES.get((first.get("composition") or {}).get("type")),
                            "component_count": len(first.get("components") or [])},
            "values_review": values_review}


def review_stage(status: str, record: dict, *, handed_off: bool) -> str | None:
    """[A2] 사람 구간 상태 (contracts/5-api queue_fields.review_stage). 화면이 어디서 이어 열지 정한다.

    추출이 끝나지 않았으면 None. 판정으로 넘긴 기록이 있으면 '판정으로 넘김', 검수 기록이 하나라도 있으면
    '추출값 확인 중'(되돌림도 확인을 시작한 것이다), 아니면 '검수 대기'."""
    if status != "done":
        return None
    if handed_off:
        return "판정으로 넘김"
    return "추출값 확인 중" if record.get("log") else "검수 대기"
