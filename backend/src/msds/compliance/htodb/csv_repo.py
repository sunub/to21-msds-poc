"""TO21 지식DB(HTODB) 샘플 CSV를 htodb.repo 와 같은 모양으로 읽는다.

설계서 43장: PoC는 HTODB에서 대상 물질만 뽑은 테이블 형식 CSV(to21_sample, 테이블·컬럼 이름 동일)로 개발하고,
운영은 같은 테이블을 직접 조회한다. 그래서 이 클래스는 repo.py 의 chemicals·classifications·toxicity 와
같은 이름·같은 반환 모양을 갖는다. 컬럼 이름은 DB 적재본처럼 소문자로 바꾼다. 값은 바꾸지 않는다.

CSV는 TO21 자료라 저장소에 올리지 않는다(D-47). 기본 위치는 to21/v0.4/to21_sample/ 이며
.gitignore 의 to21/v*/* 규칙으로 git 이 무시한다.

쓰는 법: make_db_class_lookup(CsvRepo()), make_db_tox_lookup(CsvRepo()), RegulationProvider(CsvRepo())
"""
import csv
from pathlib import Path

DEFAULT_DIR = Path(__file__).resolve().parents[5] / "to21" / "v0.4" / "to21_sample"

_MASTER = "TB_ENG_CHEM_MASTER_INFO"
_CLASS = "TB_GHS_CHEM_CLASS_MAP"
_TOX = "TB_ENG_CHEM_TOXICITY_TEST_INFO"
_REG_MAP = "TB_ENG_REGULA_CHEM_MAP"
_REG_STD = "TB_ENG_REG_NOTICE_STD"
_REG_CONTENT = "TB_ENG_REG_NOTICE_CONTENT"


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


class CsvRepo:
    """to21_sample 폴더의 CSV를 읽는 지식DB 대용. 파일은 처음 쓸 때 한 번만 읽는다."""

    def __init__(self, folder=DEFAULT_DIR):
        self.folder = Path(folder)
        self._cache: dict[str, list[dict]] = {}

    def version(self) -> str:
        return "to21_sample(HTODB 발췌 CSV)"

    def available(self) -> bool:
        return all((self.folder / f"{t}.csv").exists() for t in (_MASTER, _CLASS, _TOX))

    def _rows(self, table: str) -> list[dict]:
        if table not in self._cache:
            path = self.folder / f"{table}.csv"
            if not path.exists():
                raise FileNotFoundError(f"지식DB 샘플 CSV가 없음: {path}")
            with open(path, encoding="utf-8-sig", newline="") as f:
                self._cache[table] = [{k.lower(): v for k, v in r.items()} for r in csv.DictReader(f)]
        return self._cache[table]

    def chemicals(self, *, cas: str, limit: int = 50) -> dict:
        rows = sorted((r for r in self._rows(_MASTER) if r.get("cas_no") == cas), key=lambda r: r["chem_id"])
        return {"total": len(rows), "rows": rows[:limit]}

    def classifications(self, chem_id: str) -> dict:
        rows = sorted((r for r in self._rows(_CLASS) if r.get("chem_id") == chem_id),
                      key=lambda r: (r["class_source_db_code"], r["class_result_code"], _int(r.get("hcode_seq"))))
        return {"rows": rows}

    def toxicity(self, chem_id: str) -> dict:
        rows = sorted((r for r in self._rows(_TOX) if r.get("chem_id") == chem_id),
                      key=lambda r: (r.get("experiment_div", ""), r["div_code"], _int(r.get("toxic_seq"))))
        return {"rows": rows}

    def regulations(self, chem_id: str) -> dict:
        """repo.regulations 와 같은 키 중 판정에 쓰는 셋: rows(물질↔세부규제), notice_std(함량 기준), notice_content(조문 문구)."""
        rows = sorted((r for r in self._rows(_REG_MAP) if r.get("chem_id") == chem_id),
                      key=lambda r: (r["regulate_id"], r["regulate_item_id"]))
        std = sorted((r for r in self._rows(_REG_STD) if r.get("chem_id") == chem_id),
                     key=lambda r: (r["regulate_item_id"], _int(r.get("notice_seq")), _int(r.get("std_seq"))))
        content = []
        if (self.folder / f"{_REG_CONTENT}.csv").exists():
            content = sorted((r for r in self._rows(_REG_CONTENT) if r.get("chem_id") == chem_id),
                             key=lambda r: (r["regulate_item_id"], _int(r.get("notice_seq")), r.get("lang_code") or ""))
        return {"rows": rows, "notice_std": std, "notice_content": content}
