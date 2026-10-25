"""여러 역할이 같이 쓰는 성분 참조 맞춤."""
from typing import Any


def comp_map(msds_item: dict[str, Any]) -> dict[str, str]:
    """성분 순번(글자) -> CAS. CAS 가 없으면 이름.

    11·12·15항의 행은 성분을 comp_ref("1", "2" ...)로 가리키고, 지식 조회는 CAS 로 한다.
    혼합물 전체를 뜻하는 "MIX" 는 대응하는 성분이 없어 담기지 않는다.
    """
    out: dict[str, str] = {}
    for c in msds_item.get("components") or []:
        key = c.get("cas_no") or c.get("name")
        if c.get("seq") is not None and key:
            out[str(c["seq"])] = key
    return out
