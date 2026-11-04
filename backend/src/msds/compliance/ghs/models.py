"""TO21 스키마 이름을 그대로 쓰는 GHS 분류 입력·출력 계약."""

from typing import Any, Literal, Self, TypedDict

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ...common.models import Component, Composition, HazardClass, RouteForm


DecisionStatus = Literal["확정", "경계", "근거부족", "해당 없음"]


class _Contract(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


class GhsHazardInput(_Contract):
    classes: list[HazardClass] = Field(default_factory=list)
    h_codes: list[str | None] = Field(default_factory=list)
    pictograms: list[str | None] = Field(default_factory=list)
    signal_word: Literal["위험", "경고", "없음"] | None = None


class GhsInputs(_Contract):
    """추출 JSON 한 건에서 손실 없이 만든 2차 GHS 입력."""

    doc_id: str | None = None
    msds_index: int = Field(ge=0)
    as_of_date: str | None = None
    revision_date: str | None = None
    composition: Composition = Field(default_factory=Composition)
    components: list[Component] = Field(default_factory=list)
    hazard: GhsHazardInput = Field(default_factory=GhsHazardInput)
    physchem: dict[str | None, list[dict[str, Any]]] = Field(default_factory=dict)
    toxicity: list[dict[str, Any]] = Field(default_factory=list)
    ecotox: list[dict[str, Any]] = Field(default_factory=list)
    regulations: list[dict[str, Any]] = Field(default_factory=list)
    dangerous_goods: list[dict[str, Any]] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)


class ClassificationDecision(_Contract):
    """분류 결과 한 줄과 재현에 필요한 규칙 근거."""

    class_code: str = Field(min_length=1)
    category: str | None = None
    route_form: RouteForm | None = None
    status: DecisionStatus
    rule_id: str = Field(min_length=1)
    rule_version: str = Field(min_length=1)
    valid_from: str = Field(min_length=1)
    source: str = Field(min_length=1)
    evidence: list[dict[str, Any]]

    @model_validator(mode="after")
    def validate_inhalation_and_evidence(self) -> Self:
        if self.class_code.startswith("HH_ACUTE_INHAL_"):
            raise ValueError("흡입 급성독성은 HH_ACUTE_INHAL + route_form으로 표현합니다")
        if self.class_code == "HH_ACUTE_INHAL":
            if self.route_form is None:
                raise ValueError("HH_ACUTE_INHAL에는 route_form이 필요합니다")
        elif self.route_form is not None:
            raise ValueError("route_form은 HH_ACUTE_INHAL에만 사용합니다")
        if self.status in ("확정", "경계") and not self.evidence:
            raise ValueError(f"{self.status} 판정에는 evidence가 필요합니다")
        return self


class ReferenceKnowledge(TypedDict):
    cas_no: str
    as_of: str | None
    knowledge_version: str | None
    classes: list[dict[str, Any]]
    ate: dict[str, Any]
    un_no: str | None
    source: str | None


class RegulationKnowledge(TypedDict):
    cas_no: str
    as_of: str | None
    knowledge_version: str | None
    rows: list[dict[str, Any]]


class CutOffRule(TypedDict):
    categories: list[str] | None  # None 이면 그 class_code 의 모든 구분
    threshold_op: str
    threshold_value: float
    threshold_unit: str
    source: str


class MixtureRuleKnowledge(TypedDict):
    as_of: str | None
    knowledge_version: str | None
    cut_off: dict[str, list[CutOffRule]]
    additivity: dict[str, Any]
