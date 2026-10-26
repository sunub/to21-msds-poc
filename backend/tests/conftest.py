import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def pytest_sessionstart(session):
    """TO21 제공 파일이 없으면 시험 수십 개가 같은 이유로 실패하므로, 처음에 한 번만 알리고 멈춘다 (D-47)."""
    from msds.common.paths import TO21, TO21_FILES

    missing = [name for name in TO21_FILES.values() if not (TO21 / name).exists()]
    if missing:
        pytest.exit(
            "TO21 제공 파일이 없습니다 (" + ", ".join(missing) + ").\n"
            "TO21 자료는 저장소에 올리지 않습니다(D-47). 팀 공유 위치(노션)에서 받아 "
            "to21/v0.5/에 원래 파일 이름 그대로 두세요. 목록: to21/README.md",
            returncode=2,
        )


@pytest.fixture(scope="session")
def gold25():
    """TO21 정답 예제(25번 황산). 형식 시험용으로만 쓴다 (프롬프트 조정에 쓰지 않음, D-43)."""
    from msds.common.paths import to21_file   # 파일이 없으면 받는 방법을 알려 준다 (D-47)

    return json.loads(to21_file("example25").read_text(encoding="utf-8"))


def todo(fn, *args, **kwargs):
    """아직 구현 전인 함수는 건너뛴다. 담당 역할의 완료 기준: 이 파일의 시험이 모두 passed (skipped 0)."""
    try:
        return fn(*args, **kwargs)
    except NotImplementedError as e:
        pytest.skip(f"구현 전: {e}")
