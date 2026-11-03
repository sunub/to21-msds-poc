"""계약 시험 공용: docs/backend/contracts 스키마와 TO21 스키마를 묶어 검사기를 만든다 (contracts/README.md 2·4절)."""
import json
from pathlib import Path

import jsonschema
import pytest
import referencing

from msds.common.paths import ROOT, to21_file

CONTRACTS = ROOT / "docs" / "superpowers" / "specs" / "contracts"


@pytest.fixture(scope="session")
def contract_registry():
    reg = referencing.Registry()
    paths = [*CONTRACTS.glob("*.json"), to21_file("schema")]
    for path in paths:
        schema = json.loads(Path(path).read_text(encoding="utf-8"))
        reg = reg.with_resource(schema["$id"], referencing.Resource.from_contents(schema))
    return reg


@pytest.fixture(scope="session")
def contract_errors(contract_registry):
    """contract_errors('3-consistency.schema.json', obj) 또는 ('5-api.schema.json#/$defs/snapshot', obj) → 오류 글 목록."""

    def check(name: str, obj) -> list[str]:
        file, _, pointer = name.partition("#")
        base = json.loads((CONTRACTS / file).read_text(encoding="utf-8"))
        schema = base if not pointer else {"$ref": f"{base['$id']}#{pointer}"}
        validator = jsonschema.Draft202012Validator(schema, registry=contract_registry)
        return [f"{list(e.absolute_path)}: {e.message[:200]}" for e in validator.iter_errors(obj)]

    return check


@pytest.fixture(scope="session")
def judge_database():
    """시험 전용 DB judge_test 에 스키마를 만든다. PostgreSQL이 없으면 건너뛴다(HTODB_SKIP과 같은 뜻)."""
    import importlib.util
    import os

    if os.environ.get("HTODB_SKIP"):
        pytest.skip("HTODB_SKIP")
    spec = importlib.util.spec_from_file_location("b2_migrate", ROOT / "backend" / "scripts" / "b2_migrate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    try:
        mod.migrate("judge_test", dev=True)
    except Exception as e:
        pytest.skip(f"PostgreSQL에 붙지 못함: {e}")
    return "judge_test"
