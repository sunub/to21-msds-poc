"""재생성 MSDS 리포트 줄의 None 은 화면과 같이 '값 없음'으로 보인다."""
from types import SimpleNamespace

from msds.judge import reports


def test_재생성_줄의_None은_값_없음으로(monkeypatch):
    class Db:
        def close(self):
            pass

    fake = SimpleNamespace(to_db=lambda doc, path: Db(), regenerate=lambda db, n: ["최초 작성일: None 최종 개정일: None", "NoneType 그대로"])
    monkeypatch.setattr(reports, "_load_regen", lambda: fake)
    lines, error = reports._regenerated_lines({"msds": [{}]})
    assert error is None
    assert lines == ["최초 작성일: 값 없음 최종 개정일: 값 없음", "NoneType 그대로"]
