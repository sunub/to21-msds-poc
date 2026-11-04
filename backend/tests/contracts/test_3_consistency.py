"""약속 ③ judge() 계약 시험. 샘플 CSV로 돌리고, 실제 HTODB 대조는 지식DB가 떠 있을 때만 한다."""
import copy
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from msds.common.paths import ROOT
from msds.compliance.consistency import run_consistency
from msds.compliance.htodb.csv_repo import CsvRepo
from msds.compliance.judge import current_versions, judge
from msds.judge.display import finding_display

AS_OF = "2026-11-02"
SILVER = ROOT / "data" / "silver" / "claude"


@pytest.fixture(scope="module")
def repo():
    r = CsvRepo()
    if not r.available():
        pytest.skip("to21_sample CSV 없음")
    return r


@pytest.fixture(scope="module")
def out25(gold25, repo):
    return judge(gold25, AS_OF, repo)


def _by_id(result):
    return {f["id"]: f for f in result["findings"]}


def test_25번_결과가_계약을_통과한다(out25, contract_errors):
    assert contract_errors("3-consistency.schema.json", out25) == []


def test_기준일과_개정일을_따로_낸다(out25, gold25):
    assert out25["as_of"] == AS_OF
    assert out25["results"][0]["msds_revision_date"] == gold25["msds"][0]["meta"]["last_revision_date"]


def test_finding은_id순이고_요약이_개수와_같고_trace가_이어진다(out25):
    r = out25["results"][0]
    ids = [f["id"] for f in r["findings"]]
    assert ids == sorted(ids) and len(ids) == len(set(ids))
    for k, n in r["summary"].items():
        assert n == sum(f["verdict"] == k for f in r["findings"])
    linked = {f["trace_id"] for f in r["findings"] if f["trace_id"]}
    assert linked == set(r["traces"])


def test_엔진_판정값을_그대로_옮긴다(gold25, repo, out25):
    engine = run_consistency(gold25, repo)["consistency"]
    ours = _by_id(out25["results"][0])
    for row in engine["findings"]:
        if row["section"] == "2" and not row["class_code"].startswith("LABEL_"):
            f = ours[f"m0/F2:{row['class_code']}:{row.get('form') or '-'}"]
            assert (f["verdict"], f["type"], f["severity"]) == (row["verdict"], row["type"], row["severity"]), row["id"]
        if row["section"] == "15" and row["item_code"] != "DG_HAZMAT":
            f = next(x for x in ours.values() if x["kind"] == "regulation" and x["item"] == f"{row['law']}.{row['item_code']}"
                     and (x["comp"] or {}).get("comp_ref") == str(row["comp_ref"]))
            assert (f["verdict"], f["type"], f["severity"]) == (row["verdict"], row["type"], row["severity"]), row["id"]


def test_같은_입력이면_프로세스와_해시시드가_달라도_바이트까지_같다(gold25, repo):
    code = ("import json,sys;from msds.compliance.judge import judge;from msds.compliance.htodb.csv_repo import CsvRepo;"
            "d=json.load(open(sys.argv[1]));r=judge(d,'2026-11-02',CsvRepo());"
            "print(json.dumps(r,sort_keys=True,separators=(',',':'),ensure_ascii=False))")
    from msds.common.paths import to21_file
    src = ROOT / "backend" / "src"
    runs = {subprocess.run([sys.executable, "-c", code, str(to21_file("example25"))], capture_output=True, check=True,
                           env={**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": str(src), "PYTHONIOENCODING": "utf-8"}).stdout
            for seed in ("1", "2", "77")}
    assert len(runs) == 1


def test_성분_순번이_바뀌어도_finding_id가_같다(gold25, repo, out25):
    doc = copy.deepcopy(gold25)
    m = doc["msds"][0]
    new_seq = {str(c["seq"]): str(c["seq"] + 10) for c in m["components"]}
    for c in m["components"]:
        c["seq"] += 10
    m["components"].reverse()
    for section in ("toxicity", "ecotox", "regulations", "physchem", "exposure_limits", "cmr"):
        for row in m.get(section) or []:
            ref = str(row.get("comp_ref"))
            if ref in new_seq:
                row["comp_ref"] = new_seq[ref]
    moved = judge(doc, AS_OF, repo)
    assert {f["id"] for f in moved["results"][0]["findings"]} == {f["id"] for f in out25["results"][0]["findings"]}


def test_한_PDF의_MSDS_여러_건을_따로_낸다(gold25, repo, contract_errors):
    doc = copy.deepcopy(gold25)
    doc["msds"] = [doc["msds"][0], copy.deepcopy(doc["msds"][0])]
    out = judge(doc, AS_OF, repo)
    assert contract_errors("3-consistency.schema.json", out) == []
    assert [r["msds_index"] for r in out["results"]] == [0, 1]
    assert all(f["id"].startswith("m1/") for f in out["results"][1]["findings"])


def test_같은_CAS_두_줄의_번호는_성분_순서와_무관하다(gold25, repo):
    def twice(reverse):
        doc = copy.deepcopy(gold25)
        m = doc["msds"][0]
        acid = next(c for c in m["components"] if c["cas_no"] == "7664-93-9")
        low = copy.deepcopy(acid)
        low["seq"] = 9
        low["content"] = {**acid["content"], "raw": "1", "value": 1, "lower": None, "upper": None}
        m["components"].append(low)
        if reverse:
            acid["seq"], low["seq"] = 9, acid["seq"]
            for r in m.get("regulations") or []:
                r["comp_ref"] = {"1": "9", "9": "1"}.get(str(r.get("comp_ref")), r.get("comp_ref"))
        out = {f["id"]: f["expected"].get("content") for f in judge(doc, AS_OF, repo)["results"][0]["findings"] if "#2" in f["id"]}
        return {k: (v or {}).get("raw") for k, v in out.items()}
    assert twice(False) and twice(False) == twice(True)


def test_조회_오류가_한_번이라도_나면_예외를_낸다(gold25):
    class Flaky(CsvRepo):
        def toxicity(self, chem_id):
            raise ConnectionError("끊김")

    with pytest.raises(ConnectionError, match="끊김"):
        judge(gold25, AS_OF, Flaky())


def test_규칙_파일이_바뀌면_규칙_버전도_바뀐다(tmp_path):
    from msds.compliance.judge import rules_digest

    (tmp_path / "a.csv").write_text("x", encoding="utf-8")
    before = rules_digest(tmp_path)
    (tmp_path / "a.csv").write_text("y", encoding="utf-8")
    assert rules_digest(tmp_path) != before
    assert rules_digest() in current_versions(CsvRepo())["knowledge"]["rules"]  # 시험 중 규칙 파일은 그대로다


def test_해외_규제와_범위_밖_항목을_보인다(gold25, repo):
    doc = copy.deepcopy(gold25)
    row = copy.deepcopy(doc["msds"][0]["regulations"][0])
    row.update(law="INTL", item_code=None, item_raw="EU REACH", applicable="해당")
    doc["msds"][0]["regulations"].append(row)
    r = judge(doc, AS_OF, repo)["results"][0]
    rows = [f for f in r["findings"] if f["out_of_scope_reason"] == "해외 규제"]
    assert all(f["verdict"] == "범위 외" and not f["needs_explanation"] for f in rows)
    assert any(f["label"] == "EU REACH" for f in rows)
    assert any("8항 노출기준" in x["text"] for x in r["limitations"])
    doc["msds"][0]["regulations"][-1]["comp_ref"] = None
    product = [f for f in judge(doc, AS_OF, repo)["results"][0]["findings"] if f["label"] == "EU REACH"][0]
    assert product["id"].startswith("m0/F15:MIX:INTL") and product["comp"] is None
    assert finding_display(product, None)["component"] == "제품"


def test_제공자_적합성_값_없음_형식_버전(repo):
    from msds.compliance.htodb.reference import ReferenceProvider
    from msds.compliance.htodb.regulation import RegulationProvider

    assert current_versions(repo)["knowledge"]["version"]
    for known in (ReferenceProvider(repo).get_reference("7664-93-9", AS_OF), RegulationProvider(repo).get_regulation("7664-93-9", AS_OF)):
        assert known["as_of"] == AS_OF and known["knowledge_version"] and known["reason"] is None
    for empty in (ReferenceProvider(repo).get_reference("0000-00-0", AS_OF), RegulationProvider(repo).get_regulation("0000-00-0", AS_OF)):
        assert empty["knowledge_version"] is None and empty["reason"]


@pytest.mark.parametrize("op,expected", [(">=", "해당"), (">", "비해당")])
def test_함량이_기준과_정확히_같을_때(op, expected):
    from msds.compliance.sec15 import _expected

    content = {"value": 10, "status": "값있음", "unit": "%"}
    assert _expected(content, {"threshold_op": op, "threshold_value": 10.0, "threshold_unit": "%"})[0] == expected


@pytest.mark.parametrize("ref,expected", [((">=", 0.0), "해당"), ((">", 0.0), "경계"), ((">=", 0.5), "경계"), ((">=", 1.0), "비해당")])
def test_함량_하한이_없으면_0으로_본다(ref, expected):
    """'1% 미만'처럼 하한이 없으면 0~1%. 함유하면 해당(>=0)인 기준에는 해당이다 (탈크 보정 FX-02·03)."""
    from msds.compliance.sec15 import _expected

    content = {"raw": "<1", "upper": 1.0, "upper_op": "<", "status": "값있음", "unit": "%"}
    assert _expected(content, {"threshold_op": ref[0], "threshold_value": ref[1], "threshold_unit": "%"})[0] == expected


def _single_acid(gold25, msds_form="분진·미스트", state="액체"):
    doc = copy.deepcopy(gold25)
    m = doc["msds"][0]
    acid = next(c for c in m["components"] if c["cas_no"] == "7664-93-9")
    m["components"] = [{**acid, "seq": 1}]
    m["composition"] = {**(m.get("composition") or {}), "type": "단일물질"}
    m["regulations"] = []
    m["physchem"] = [{"prop_code": "APPEARANCE_STATE", "comp_ref": "MIX", "text_value": state}] if state else []
    for c in m["hazard"]["classes"]:
        if c["class_code"] == "HH_ACUTE_INHAL":
            c["route_form"], c["category"] = msds_form, "2"
    return doc


def test_액체_물질의_환경부_흡입_가스는_다른_출처_형태로_재지정한다_D22(gold25):
    """TO21 test_sulfuric_acid_official_and_form_fix: 황산 KR02 '흡입:가스' → 분진·미스트 구분 2."""
    try:
        current_versions(None)
    except Exception as e:
        pytest.skip(f"지식DB 없음: {e}")
    found = _by_id(judge(_single_acid(gold25), AS_OF)["results"][0])
    inhal = {k: f for k, f in found.items() if k.startswith("m0/F2:HH_ACUTE_INHAL")}
    assert "m0/F2:HH_ACUTE_INHAL:가스" not in inhal
    f = inhal["m0/F2:HH_ACUTE_INHAL:분진·미스트"]
    assert (f["verdict"], f["expected"]["route_form"], f["expected"]["category"]) == ("일치", "분진·미스트", "2")


def test_기체_물질은_재지정하지_않고_성상을_모르면_그대로_둔다_D22(repo):
    from msds.compliance.consistency import _reassign_gas

    gas = [{"class_code": "HH_ACUTE_INHAL", "category": "2", "route_form": "가스", "effect": None, "source": "환경부", "result_code": "x"}]
    both = [{"class_code": "HH_ACUTE_INHAL", "form": "mist"}, {"class_code": "HH_ACUTE_INHAL", "form": "vapour"}]
    assert _reassign_gas(gas, both, "액체")[0]["route_form"] == "증기"  # 둘 다 있으면 성상 순서
    labour = [{**gas[0], "source": "고용노동부"}]
    assert _reassign_gas(labour, both, "액체")[0]["route_form"] == "가스"  # 환경부 줄만 바꾼다
    other = [{"class_code": "HH_ACUTE_INHAL", "category": "2", "form": "mist", "source": "KR03"}]
    assert _reassign_gas(gas, other, "기체")[0]["route_form"] == "가스"
    assert _reassign_gas(gas, other, None)[0]["route_form"] == "가스"
    assert _reassign_gas(gas, other, "액체")[0]["route_form"] == "분진·미스트"
    assert _reassign_gas(gas, [], "액체")[0]["route_form"] == "증기"  # 다른 출처가 없으면 성상 기준 (D-06)
    assert _reassign_gas(gas, [], "고체")[0]["route_form"] == "분진·미스트"
    assert gas[0]["route_form"] == "가스"  # 입력을 바꾸지 않는다


def test_설계서_48장_오류_주입을_탐지한다(gold25, repo):
    doc = copy.deepcopy(gold25)
    classes = doc["msds"][0]["hazard"]["classes"]
    doc["msds"][0]["hazard"]["classes"] = [c for c in classes if c["class_code"] != "HH_SKIN_CORR"]
    f = _by_id(judge(doc, AS_OF, repo)["results"][0])["m0/F2:HH_SKIN_CORR:-"]
    assert (f["verdict"], f["type"], f["severity"]) == ("불일치", "과소분류", "높음")

    doc = copy.deepcopy(gold25)
    regs = doc["msds"][0]["regulations"]
    doc["msds"][0]["regulations"] = [r for r in regs if r.get("item_code") != "CCA_ACCIDENT"]
    f = _by_id(judge(doc, AS_OF, repo)["results"][0])["m0/F15:7664-93-9:CCA.CCA_ACCIDENT"]
    assert (f["verdict"], f["type"], f["severity"]) == ("불일치", "규제 누락", "높음")


def test_표시_요소는_코드별로_나뉜다(gold25, repo):
    doc = copy.deepcopy(gold25)
    hz = doc["msds"][0]["hazard"]
    hz["h_statements"] = [h for h in hz["h_statements"] if h["code"] != "H350"]
    hz["h_statements"].append({**hz["h_statements"][0], "code": "H999"})
    found = _by_id(judge(doc, AS_OF, repo)["results"][0])
    missing, extra = found["m0/F2L:H:H350"], found["m0/F2L:H:H999"]
    assert missing["verdict"] == "불일치" and extra["verdict"] == "경고"  # 규칙표 CMP-2
    assert extra["severity"] == "낮음" and extra["needs_explanation"] is False
    assert missing["msds"]["present"] is False and missing["expected"]["present"] is True
    assert extra["msds"]["present"] is True and extra["expected"]["present"] is False
    assert missing["causes"] == ["LABEL_MISSING"]
    assert found["m0/F2L:H:H314"]["verdict"] == "일치"


def test_H314가_있을_때_H318_생략은_참고다(gold25, repo):
    doc = copy.deepcopy(gold25)
    hz = doc["msds"][0]["hazard"]
    hz["h_statements"] = [h for h in hz["h_statements"] if h["code"] != "H318"]
    f = _by_id(judge(doc, AS_OF, repo)["results"][0])["m0/F2L:H:H318"]
    assert f["verdict"] == "참고" and f["needs_explanation"] is False


def test_추출_실패_항은_근거부족으로_낸다(gold25, repo, out25, contract_errors):
    failed = [{"msds_index": 0, "section": 15, "error": "모델 응답 시간 초과"}]
    out = judge(gold25, AS_OF, repo, failed)
    assert contract_errors("3-consistency.schema.json", out) == []
    before = _by_id(out25["results"][0])
    for f in out["results"][0]["findings"]:
        if f["kind"] in ("regulation", "dangerous_goods") and before[f["id"]]["verdict"] in ("일치", "불일치", "경계"):
            assert f["verdict"] == "근거부족" and "15항 추출 실패" in f["reason"] and f["needs_explanation"]
        elif f["section"] == "2":
            assert f["verdict"] == before[f["id"]]["verdict"]


@pytest.mark.parametrize("section", [2, 3, 9, 11, 12, 14])
def test_어느_항이_실패해도_이미_근거부족인_줄의_이유를_추출_실패로_바꾼다(gold25, repo, contract_errors, section):
    out = judge(gold25, AS_OF, repo, [{"msds_index": 0, "section": section, "error": "x"}])
    assert contract_errors("3-consistency.schema.json", out) == []
    hit = [f for f in out["results"][0]["findings"] if f"{section}항 추출 실패" in (f["reason"] or "")]
    assert hit and all(f["verdict"] == "근거부족" and f["causes"] == ["NO_BASIS"] for f in hit)


def test_내용이_빈_문서는_일치로_나오지_않는다(repo):
    for empty in ({"msds": []}, {"msds": [{}]}, {}):
        verdicts = {f["verdict"] for f in judge(empty, AS_OF, repo)["results"][0]["findings"]}
        assert "일치" not in verdicts and "불일치" not in verdicts
    for empty in ({"msds": [{"meta": {"product_name": "X"}}]}, {"msds": [{"components": [{"seq": 1}]}]}, {"msds": [{"a": "  "}]}, {"msds": [{"components": [{"seq": 1, "trade_secret": False}]}]}, {"msds": [{"x": 0}]}, {"msds": [{"meta": {}}]}, {"msds": [{}, {}]}):
        for r in judge(empty, AS_OF, repo)["results"]:
            assert not {f["verdict"] for f in r["findings"]} & {"일치", "불일치"}


def test_지수_표기_기준값을_숫자로_읽는다():
    from msds.compliance.judge import _threshold_q
    q = _threshold_q(">= 1e-07%")
    assert q["lower"] == 1e-07 and q["unit"] == "%"


def test_다른_msds의_실패는_영향이_없다(gold25, repo, out25):
    out = judge(gold25, AS_OF, repo, [{"msds_index": 3, "section": 15, "error": "x"}])
    assert out == out25


def test_비어_있는_추출값도_계약을_지킨다(repo, contract_errors):
    doc = {"doc": {"doc_id": "T21-EMPTY"}, "msds": []}
    out = judge(doc, AS_OF, repo)
    assert contract_errors("3-consistency.schema.json", out) == []
    r = out["results"][0]
    assert r["product_type"]["value"] == "불명확"
    assert _by_id(r)["m0/FPT:TYPE"]["verdict"] == "근거부족"


def test_성분_요약이_계약_칸을_채운다(out25):
    comps = {c["cas"]: c for c in out25["results"][0]["components"]}
    assert set(comps) == {"7664-93-9", "7732-18-5"}
    acid, water = comps["7664-93-9"], comps["7732-18-5"]
    assert acid["content"]["raw"] and acid["regulation_hits"] > 0 and isinstance(acid["regulation_hits"], int)
    assert any(a["route"] == "inhal" and a["unit"] for a in acid["ate"]) and all(a["route"] in ("oral", "dermal", "inhal") for a in acid["ate"])
    assert water["regulation_hits"] == 0 and acid["reliability"] in ("높음", "보통", "낮음")


def _display(result, finding_id):
    f = _by_id(result)[finding_id]
    return finding_display(f, result["traces"].get(f["trace_id"]))


def test_화면_문장은_B2가_판정과_근거에서_만든다(out25):
    r = out25["results"][0]
    assert all("display" not in f for f in r["findings"])  # 판정 결과에는 화면 글을 넣지 않는다 (계약 ③·⑤)
    inhal = _by_id(r)["m0/F2:HH_ACUTE_INHAL:분진·미스트"]
    assert inhal["verdict"] == "불일치" and inhal["type"] == "형태·세부 표기" and inhal["causes"][0] == "FORM_DIFF"
    d = _display(r, inhal["id"])
    assert d["msds"] == "구분 2 (증기)" and d["expected"] == "구분 2 (분진·미스트)" and d["component"] is None
    assert any("ATEmix" in x for x in d["calc_lines"]) and d["basis_lines"][0] == inhal["reason"]
    reg = next(f for f in r["findings"] if f["kind"] == "regulation" and f["verdict"] == "일치" and f["comp"])
    rd = finding_display(reg, r["traces"].get(reg["trace_id"]))
    assert reg["law_label"] in ("산안법", "화관법", "화평법") and "≥" in rd["expected"] and rd["component"].startswith("황산")
    assert not reg["label"].startswith(("OSH", "CCA", "KREACH"))
    assert reg["expected"]["threshold"]["lower"] is not None and reg["expected"]["threshold"]["unit"] == "%"


def test_계산에_쓴_11항도_원문_쪽에_보인다(repo):
    path = SILVER / "T21-025.json"
    if not path.exists():
        pytest.skip("silver 추출본 없음")
    result = judge(json.loads(path.read_text(encoding="utf-8")), AS_OF, repo)["results"][0]
    fid = next(k for k in _by_id(result) if k.startswith("m0/F2:HH_ACUTE_INHAL"))
    pages = _display(result, fid)["source_pages"]
    assert {p["section"] for p in pages} >= {2, 11}


def test_범위_외는_이유_분류를_갖는다(out25):
    rows = [f for f in out25["results"][0]["findings"] if f["verdict"] == "범위 외"]
    assert rows and all(f["out_of_scope_reason"] in ("해당 없음", "대조만", "구버전 제외", "해외 규제") for f in rows)
    assert all(f["out_of_scope_reason"] is None for f in out25["results"][0]["findings"] if f["verdict"] != "범위 외")


def test_silver_전체가_계약을_통과하고_ID가_유일하다(repo, contract_errors):
    paths = [p for p in sorted(SILVER.glob("*.json")) if not p.name.endswith(".review.json")]
    if not paths:
        pytest.skip("silver 추출본 없음")
    for path in paths:
        out = judge(json.loads(path.read_text(encoding="utf-8")), AS_OF, repo)
        assert contract_errors("3-consistency.schema.json", out) == [], path.name
        for r in out["results"]:
            ids = [f["id"] for f in r["findings"]]
            assert len(ids) == len(set(ids)), path.name
            assert all(" " not in i for i in ids), path.name


def test_지식DB에_못_붙으면_판정하지_않고_예외를_낸다(gold25, monkeypatch):
    from msds.compliance.mixture import class_lookup_db

    def down(self):
        raise ConnectionError("지식DB 내려감")

    monkeypatch.setattr(class_lookup_db._DbRepo, "version", down)
    with pytest.raises(ConnectionError):
        judge(gold25, AS_OF)


def test_실제_HTODB로도_계약을_통과한다(gold25, contract_errors):
    if os.environ.get("HTODB_SKIP"):
        pytest.skip("HTODB_SKIP")
    try:
        current_versions(None)
    except Exception as e:
        pytest.skip(f"지식DB 없음: {e}")
    out = judge(gold25, AS_OF)
    assert contract_errors("3-consistency.schema.json", out) == []
    assert out["knowledge"]["version"].startswith("htodb-")
    h = lambda o: hashlib.sha256(json.dumps(o, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    assert h(out) == h(judge(gold25, AS_OF))


def test_판정과_성분_탭의_흡입_형태가_같다_D22(gold25):
    try:
        current_versions(None)
    except Exception as e:
        pytest.skip(f"지식DB 없음: {e}")
    result = judge(_single_acid(gold25), AS_OF)["results"][0]
    classes = [c for c in result["components"][0]["reference_classes"] if c["class_code"] == "HH_ACUTE_INHAL"]
    assert classes and all(c["route_form"] == "분진·미스트" for c in classes)


def test_물리적_위험성과_판별도_원문_쪽을_찾는다(repo):
    path = SILVER / "T21-025.json"
    if not path.exists():
        pytest.skip("silver 추출본 없음")
    result = judge(json.loads(path.read_text(encoding="utf-8")), AS_OF, repo)["results"][0]
    assert any(p["section"] == 3 for p in _display(result, "m0/FPT:TYPE")["source_pages"])
    ph = next(f for f in result["findings"] if f["item"].startswith("PH_") and f["kind"] == "class" and f["verdict"] == "일치")
    assert any(p["section"] in (9, 14) for p in finding_display(ph, result["traces"].get(ph["trace_id"]))["source_pages"])


def test_제외_줄도_성분_함량을_보이고_근거부족과_기준_없음을_구분한다(gold25, repo):
    result = judge(gold25, AS_OF, repo)["results"][0]
    for f in result["findings"]:
        if f["kind"] == "regulation" and f["comp"]:
            assert "(" in finding_display(f, result["traces"].get(f["trace_id"]))["component"], f["id"]
    lacking = {"kind": "class", "section": "2", "comp": None, "reason": "", "verdict": "근거부족", "msds": {}, "expected": {"low": None, "high": None, "status": "근거부족"}}
    assert finding_display(lacking, None)["expected"] == "판단 못 함"
    no_std = {"kind": "regulation", "section": "15", "comp": None, "reason": "", "verdict": "일치", "msds": {}, "expected": {"present": False}}
    assert finding_display(no_std, None)["expected"] == "기준 없음"


def test_시간_초과도_판정_대신_예외다(gold25):
    class Slow(CsvRepo):
        def regulations(self, chem_id):
            raise TimeoutError("응답 없음")

    with pytest.raises(TimeoutError, match="응답 없음"):
        judge(gold25, AS_OF, Slow())
