"""2차가 기준 정보를 꺼내는 함수 3개의 입출력 형태.

PoC 에서는 TO21 엑셀, 운영에서는 TO21 API 로 바꿔 끼우므로 판정 코드는 이 함수로만 지식을 읽는다.
실데이터 구현은 아직 없으며, 지식DB 엑셀이 오기 전에는 EmptyProvider 로 빈 지식을 돌려준다.

형태는 임시다. 기준은 정합성검증 개발설계서 v0.2 의 메시지 명세인데 저장소에 없어 확인하지 못했고,
지금은 D 가이드 3.4 의 예시와 E 가이드 3.4 의 15항 칸 구성을 따랐다 (docs/adr/0001). 설계서와
다르면 설계서를 따른다.

공통 약속
- 모든 응답에 knowledge_version 과 as_of(기준일)를 남긴다. 같은 입력이면 같은 응답이어야 하고,
  지식을 바꿨을 때 결과 차이를 비교할 수 있어야 한다.
- 지식이 없으면 knowledge_version 이 None 이다. 빈 목록만으로는 "조회했으나 해당 없음"과
  "지식 없음"을 구분할 수 없어서, 목록도 상자(dict)에 담아 돌려준다.
"""

from .ghs.models import MixtureRuleKnowledge, ReferenceKnowledge, RegulationKnowledge


class EmptyProvider:
    """기준 데이터가 없을 때 호출자가 근거 부족으로 처리할 빈 지식을 돌려준다."""

    def get_reference(self, cas_no: str, as_of: str | None) -> ReferenceKnowledge:
        return {
            "cas_no": cas_no,
            "as_of": as_of,
            "knowledge_version": None,
            "classes": [],
            "ate": {},
            "un_no": None,
            "source": None,
        }

    def get_regulation(self, cas_no: str, as_of: str | None) -> RegulationKnowledge:
        return {
            "cas_no": cas_no,
            "as_of": as_of,
            "knowledge_version": None,
            "rows": [],
        }

    def classify_mixture(
        self, components: list[dict], as_of: str | None
    ) -> MixtureRuleKnowledge:
        return {
            "as_of": as_of,
            "knowledge_version": None,
            "cut_off": {},
            "additivity": {},
        }


def get_reference(cas_no: str, as_of: str | None) -> ReferenceKnowledge:
    """CAS 하나의 기준 분류와 독성 기준값.

    {
      "cas_no": str, "as_of": str | None, "knowledge_version": str | None,
      "classes": [{"class_code", "category", "route_form", "source"}],  # 기준 분류
      "ate": {"oral", "dermal", "inhal"},   # 급성독성 추정값. 모르면 키가 없거나 None
      "un_no": str | None,
      "source": str | None,
    }
    """
    raise NotImplementedError


def get_regulation(cas_no: str, as_of: str | None) -> RegulationKnowledge:
    """CAS 하나에 걸리는 국내 법규제 기준 행.

    {
      "cas_no": str, "as_of": str | None, "knowledge_version": str | None,
      "rows": [{"law", "item_code", "item_name", "threshold_op", "threshold_value",
                "threshold_unit", "valid_from", "source", "note"}],
    }
    rows 의 칸 이름은 E 의 rules/sec15_rules.csv 머리글(E 가이드 3.4)을 따른다.
    cas_no 는 조회 키라서 rows 에는 다시 담지 않는다. note 는 사람이 읽는 참고라 판정에 쓰지 않는다.
    """
    raise NotImplementedError


def classify_mixture(components: list[dict], as_of: str | None) -> MixtureRuleKnowledge:
    """혼합물 분류에 쓰는 한계농도와 가산 규칙.

    components 는 load_inputs 결과의 components(seq, name, cas_no, content, ...) 이다.
    {
      "as_of": str | None, "knowledge_version": str | None,
      "cut_off": {...},      # 한계농도. 안의 구조는 설계서 확인 후 정한다
      "additivity": {...},   # 가산 규칙. 안의 구조는 설계서 확인 후 정한다
    }
    """
    raise NotImplementedError
