"""물리적 위험성 항목 판정: transport 방식(14개)은 UN 번호 → 대표 성분 → 9항 물성, compare 방식(2개)은 MSDS 기재값 대조만.

규칙표(mixture_rules.yaml)의 정의를 그대로 따르며, 규칙표가 참조하지만 저장소에 없는 것(un_class_map.csv, flam_liquid.yaml)은
쓰지 않고 assumptions 에 남긴다. 결과는 classify_item 과 같은 모양(class_code, result, rule, inputs, calc, thresholds, assumptions,
knowledge_version)이다. 판정 안 함(대조만)은 status "대조", 판정 대상이 아님은 status "해당 없음"으로 둔다.
"""
from .class_inputs import build_class_inputs
from .evaluate_item import build_props
from .rule_eval import evaluate_rules, evaluate_rules_trace

_STATE_BY_SUFFIX = {"_GAS": "가스", "_LIQ": "액체", "_SOL": "고체"}  # 항목 이름 끝으로 정하는 성상 제한 (규칙표 representative.state_filter)
_STATE_ALIAS = {"기체": "가스", "가스": "가스", "액체": "액체", "고체": "고체"}
_NO_CLASS = "분류안됨"


def physical_inputs(msds_item) -> dict:
    """추출 JSON msds[i]에서 이 모듈이 쓰는 입력만 꺼낸다: 13항 transport, 2항 hazard.classes."""
    return {"transport": msds_item.get("transport") or [],
            "msds_classes": (msds_item.get("hazard") or {}).get("classes") or []}


def _result(status, low=None, high=None, reason=None):
    r = {"low": low, "high": high, "status": status}
    if reason:
        r["reason"] = reason
    return r


def _out(item_id, rules, result, rule_id, formula, inputs, assumptions, calc=None, thresholds=None, extra=None):
    out = {"class_code": item_id, "form": None, "result": result,
           "rule": {"id": rule_id, "basis": rules["meta"]["source"], "formula": formula},
           "inputs": inputs, "calc": calc or {}, "thresholds": thresholds or [], "assumptions": assumptions,
           "knowledge_version": rules["meta"]["version"]}
    if extra:
        out["extra"] = extra
    return out


def _state(mixture_props, state):
    s = (mixture_props or {}).get("STATE") or state
    return _STATE_ALIAS.get(s) if s else None


def _needed_state(item_id):
    return next((v for k, v in _STATE_BY_SUFFIX.items() if item_id.endswith(k)), None)


def _representative(components):
    """함량(상한)이 가장 큰 성분. 상한이 없는 성분은 후보에서 뺀다. 동률이면 앞선 성분."""
    cands = [c for c in components if c.get("high") is not None]
    return max(cands, key=lambda c: c["high"]) if cands else None


def _un(transport):
    return [t for t in transport if t.get("un_no") and t.get("regulated") is not False]


def _comp_row(c, role, **kw):
    return {"role": role, "cas": c.get("cas"), "name": c.get("name"), "content": {"low": c.get("low"), "high": c.get("high")}, **kw}


def _transport(item_id, item, components, mixture_props, physical, state, rules):
    asm = ["대표성분: 함량(상한)이 가장 큰 성분 한 개(규칙표 미결 4, 정의 확인 필요). 동률이면 입력 순서가 앞선 성분",
           "대표성분의 분류는 class_rows(지식DB)에서 찾고 출처 우선순위는 build_class_inputs 를 따름",
           "UN 번호는 운송 규제 여부(해당·비위험물) 확인에만 쓰고 UN→분류 변환은 하지 않음: 규칙표가 가리키는 un_class_map.csv 가 저장소에 없음"]
    if item_id == "PH_FLAM_LIQ":
        asm.append("flam_liquid.yaml(인화점·끓는점 판정)이 저장소에 없어 인화성 액체의 물성 단계는 계산하지 않음")
    rule_id = f"PHY-{item_id.removeprefix('PH_')}"
    need = _needed_state(item_id)
    st = _state(mixture_props, state)
    if need and st and st != need:
        return _out(item_id, rules, _result("해당 없음", _NO_CLASS, _NO_CLASS, f"성상 불일치: 이 항목은 {need}용, 제품 성상 {st}"),
                    "PHY-STATE", "성상별 가능한 항목만 판정", [{"role": "성상", "STATE": st, "required": need}], asm)
    if need and not st:
        asm.append(f"제품 성상을 몰라 성상 제한({need})을 적용하지 못함")
    un = _un(physical.get("transport") or [])
    un_in = [{"role": "UN", "un_no": t.get("un_no"), "hazard_class": t.get("hazard_class"), "packing_group": t.get("packing_group"),
              "mode": t.get("mode"), "source": "13항 transport"} for t in un]
    if not un:
        why = "13항 운송정보 없음" if not physical.get("transport") else "UN 번호 없음 또는 운송 비위험물"
        asm.append("운송 규제에 해당하지 않으면 물리적 위험성 판정 대상이 아닌 것으로 봄(규제 밖 위험성은 놓칠 수 있음)")
        return _out(item_id, rules, _result("해당 없음", _NO_CLASS, _NO_CLASS, why), "PHY-UN", "UN 운송정보 우선", un_in, asm)
    rep = _representative(components)
    if rep is None:
        return _out(item_id, rules, _result("근거부족", reason="대표성분을 정할 함량(상한)이 없음"), rule_id, "대표성분 분류", un_in, asm)
    inputs = un_in + [_comp_row(rep, "대표성분", source="2항 구성성분 함량(상한 최대)", class_rows=len(rep.get("class_rows") or []),
                                excluded=None)]
    cats = {}
    if rep.get("class_rows"):
        built = build_class_inputs([rep], mode="high")
        cats = built["by_class"].get(item_id, {})
    if cats:
        keys = sorted(cats)  # 구분 이름 정렬순으로 앞이 더 위험하다고 가정
        if len(keys) > 1:
            asm.append(f"대표성분에 같은 항목의 구분이 여럿({', '.join(keys)}): 정렬순 앞쪽을 더 위험한 구분으로 봄")
        res = _result("확정" if len(keys) == 1 else "경계", keys[-1], keys[0])
        inputs[-1]["used_as"] = keys
        return _out(item_id, rules, res, rule_id, "대표성분의 분류를 혼합물 분류로 채택", inputs, asm,
                    extra=_flag(item, mixture_props, rules))
    if item.get("rules"):  # 9항 물성 단계 (규칙표 property)
        props = build_props(mixture_props, rules)
        tr = evaluate_rules_trace(item["rules"], {}, props=props)
        inputs.append({"role": "물성", **{k: props.get(k) for k in ("STATE", "LEL", "UEL")}, "source": "9항 physchem"})
        thresholds = [{"rule_id": r["id"], "when": r["when"], "result": r["result"]} for r in tr["checked"]]
        if tr["category"].startswith("근거부족"):
            return _out(item_id, rules, _result("근거부족", reason=tr["category"]), rule_id, "대표성분 분류 → 9항 물성", inputs, asm,
                        thresholds=thresholds)
        return _out(item_id, rules, _result("확정", tr["category"], tr["category"]), tr["rule_id"] or rule_id,
                    "대표성분 분류 → 9항 물성", inputs, asm, thresholds=thresholds)
    if not rep.get("class_rows"):
        return _out(item_id, rules, _result("근거부족", reason="대표성분의 분류 정보(class_rows) 없음"), rule_id, "대표성분 분류", inputs, asm,
                    extra=_flag(item, mixture_props, rules))
    asm.append("대표성분의 분류 목록에 이 항목이 없으면 분류안됨으로 봄")
    return _out(item_id, rules, _result("확정", _NO_CLASS, _NO_CLASS), rule_id, "대표성분 분류", inputs, asm,
                extra=_flag(item, mixture_props, rules))


def _flag(item, mixture_props, rules):
    """flag_if(PH_METAL_CORR의 pH 극단)가 참이면 표시만 남긴다. 구분을 바꾸지 않는다."""
    expr = item.get("flag_if")
    if not expr:
        return None
    hit = evaluate_rules([{"id": "FLAG", "category": "표시", "when": expr}], {}, props=build_props(mixture_props, rules)) == "표시"
    return {"flag_if": expr, "hit": hit} if hit else None


def _compare(item_id, components, mixture_props, physical, state, rules):
    msds = [{"category": c.get("category"), "raw": c.get("raw")} for c in physical.get("msds_classes") or []
            if c.get("class_code") == item_id]
    ours = []
    for c in components:
        built = build_class_inputs([{**c, "high": 0}], mode="high")["by_class"].get(item_id, {}) if c.get("class_rows") else {}
        ours += [{"cas": c.get("cas"), "name": c.get("name"), "category": k, "content": {"low": c.get("low"), "high": c.get("high")}}
                 for k in built]
    st = _state(mixture_props, state)
    asm = ["대조만 한다: 일치·불일치 판정(규칙표 compare_rules)은 하지 않음",
           "MSDS 기재값은 2항 hazard.classes 의 같은 class_code 행, 우리 쪽 값은 성분 class_rows(지식DB)의 같은 항목 구분"]
    if item_id == "PH_PRESS_GAS":
        asm.append("고압가스는 구분이 아니라 가스 여부만 확인: 9항 성상(STATE)을 함께 담음")
    return _out(item_id, rules, _result("대조"), "CMP", "MSDS 기재와 성분 분류를 나란히 둠",
                [{"role": "대조", "msds": msds or None, "ours": ours or None, "state": st}], asm,
                calc={"compare": {"msds": msds or None, "ours": ours or None}})


def classify_physical(item_id, item, components, mixture_props, physical, *, state=None, rules) -> dict:
    """transport·compare 항목 하나를 판정한다. physical = physical_inputs(msds_item)."""
    if item["method"] == "compare":
        return _compare(item_id, components, mixture_props, physical, state, rules)
    return _transport(item_id, item, components, mixture_props, physical, state, rules)
