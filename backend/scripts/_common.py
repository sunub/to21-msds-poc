"""스크립트 공통: src 경로 등록, 날짜 기반 실행 이름."""
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def today() -> str:
    return datetime.now().strftime("%Y%m%d")
