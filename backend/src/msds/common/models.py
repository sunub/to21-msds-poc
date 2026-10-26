"""추출 JSON(TO21 스키마 v0.5)에서 2차가 읽는 부분의 형태.

검사하는 것은 타입과 허용값이다. 칸이 없거나 null 인 것은 허용한다. 골드·실버·추출 결과에는
빈 칸이 흔하고, 비었다는 사실은 로더의 missing 목록이 알려 준다.
CAS 체크디지트, 함유량 합계 같은 업무 규칙은 여기서 검사하지 않는다. TO21 검증기(V01~V23)의 몫이다.

모르는 칸은 버린다(extra="ignore"). 스키마의 나머지 칸은 2차가 읽지 않는다.
class_code, law, item_code 는 TO21 코드표 값이라 이 저장소에 옮겨 적지 않고 str 로 둔다 (D-47).
"""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

Status = Literal["값있음", "자료없음", "해당없음", "미기재", "판독불가", "마스킹"]
RouteForm = Literal["가스", "증기", "분진·미스트"]


class _Model(BaseModel):
    # strict: "1" 을 1 로 바꿔 주지 않는다. 구분 "1", 개정 번호 "01" 은 글자로 남아야 한다.
    model_config = ConfigDict(strict=True, extra="ignore", frozen=True)


class Quantity(_Model):
    """수치 객체(Q). 함유량·물성·노출기준·독성·규제 기준 값이 모두 이 모양이다."""

    raw: str | None = None
    approx: bool | None = None
    value: float | None = None
    lower_op: Literal[">", ">="] | None = None
    lower: float | None = None
    upper_op: Literal["<", "<="] | None = None
    upper: float | None = None
    unit: str | None = None
    dp: int | None = None
    status: Status | None = None
    note: str | None = None


class Meta(_Model):
    msds_no: str | None = None
    first_issue_date: str | None = None
    last_revision_date: str | None = None


class Composition(_Model):
    type: Literal["단일물질", "혼합물"] | None = None
    no_hazardous_component: bool | None = None


class Component(_Model):
    seq: int | None = None
    name: str | None = None
    cas_no: str | None = None
    content: Quantity | None = None
    content_note: Literal["미검출", "극미량", "최대함량", "불순물", "기타"] | None = None
    trade_secret: bool | None = None


class HazardClass(_Model):
    class_code: str | None = None
    category: str | None = None  # "1", "1A" 처럼 원문 표기. 숫자로 바꾸지 않는다.
    route_form: RouteForm | None = None


class Statement(_Model):
    code: str | None = None


class Hazard(_Model):
    classes: list[HazardClass] | None = None
    signal_word: Literal["위험", "경고", "없음"] | None = None
    pictograms: list[Statement] | None = None
    h_statements: list[Statement] | None = None


class Regulation(_Model):
    law: str | None = None
    item_code: str | None = None
    # 성분 순번의 글자("1", "2") 또는 혼합물 전체를 뜻하는 "MIX"
    comp_ref: str | None = None
    applicable: Literal["해당", "비해당", "자료없음", "미기재"] | None = None
    threshold: Quantity | None = None


class Msds(_Model):
    meta: Meta | None = None
    composition: Composition | None = None
    components: list[Component] | None = None
    hazard: Hazard | None = None
    regulations: list[Regulation] | None = None
    # 아래는 로더가 그대로 넘기며, 어떤 칸을 쓸지는 설계서를 읽은 뒤 모델로 올린다.
    physchem: list[dict[str, Any]] | None = None
    toxicity: list[dict[str, Any]] | None = None
    ecotox: list[dict[str, Any]] | None = None
    dangerous_goods: list[dict[str, Any]] | None = None


class DocInfo(_Model):
    doc_id: str | None = None
    schema_version: str | None = None


class ExtractionDoc(_Model):
    """파일 하나. 한 파일에 MSDS 가 여러 건일 수 있어 msds 는 목록이다."""

    doc: DocInfo | None = None
    msds: list[Msds] = []
