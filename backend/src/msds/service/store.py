"""업로드한 문서의 원본 PDF와 진행 상태를 파일로 둔다 (서비스 API).

<root>/<문서 번호>/source.pdf   올린 원본
<root>/<문서 번호>/state.json   진행 상태 (progress.new_state 모양)

진행 상태는 메모리에 들고 바뀔 때마다 파일에 바로 쓴다(임시 파일에 쓴 뒤 바꿔 끼운다).
화면을 닫거나 서버를 다시 켜도 이어서 볼 수 있게 하기 위해서다. 항별 호출 스레드가 동시에 apply를
부르므로 잠금 하나로 묶는다.
문서 번호는 U-<날짜>-<순번>이다. manifest의 T21- 번호와 겹치지 않는다. 쪽 폴더(data/pages/<번호>)는 저장소 밖이라
taken_dirs에 이미 있는 이름도 피한다. 전처리가 남은 폴더를 덮어쓰지 않게 하기 위해서다.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import threading
from pathlib import Path

from msds.common.merge import now_kst
from msds.service import progress

_ID = re.compile(r"^U-(\d{8})-(\d{3,})$")
PDF_NAME = "source.pdf"
STATE_NAME = "state.json"


class DocumentStore:
    def __init__(self, root: Path, taken_dirs: list[Path] = ()):
        self.root = Path(root)
        self.taken_dirs = [Path(d) for d in taken_dirs]
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._states: dict[str, dict] = {}
        for path in sorted(self.root.glob(f"*/{STATE_NAME}")):
            state = json.loads(path.read_text(encoding="utf-8"))
            self._states[state["id"]] = state

    # ── 읽기 ──
    def pdf_path(self, doc_id: str) -> Path:
        return self.root / doc_id / PDF_NAME

    def get(self, doc_id: str) -> dict | None:
        with self._lock:
            state = self._states.get(doc_id)
            return copy.deepcopy(state) if state else None

    def list(self) -> list[dict]:
        """새로 올린 것부터."""
        with self._lock:
            states = sorted(self._states.values(), key=lambda s: (s["created_at"], s["id"]), reverse=True)
            return copy.deepcopy(states)

    # ── 쓰기 ──
    def create(self, pdf: bytes, filename: str, as_of: str | None, model_tag: str,
               today: str | None = None) -> dict:
        """원본을 저장하고 대기(queued) 상태를 만든다. 같은 PDF가 이미 있으면 duplicate_of에 그 번호를 적는다."""
        sha = hashlib.sha256(pdf).hexdigest()
        now = now_kst()
        today = today or now[:10].replace("-", "")
        with self._lock:
            doc_id = self._next_id(today)
            dup = sorted(s["id"] for s in self._states.values() if s["sha256"] == sha)
            state = progress.new_state(doc_id, filename, sha, len(pdf), as_of, model_tag, now, dup)
            folder = self.root / doc_id
            folder.mkdir(parents=True)
            self.pdf_path(doc_id).write_bytes(pdf)
            self._write(state)
            self._states[doc_id] = state
            return copy.deepcopy(state)

    def apply(self, doc_id: str, event: dict) -> dict:
        """진행 이벤트를 반영해 저장하고 새 상태를 돌려준다. 없는 문서면 KeyError."""
        with self._lock:
            state = self._states[doc_id]
            progress.apply_event(state, event)
            state["updated_at"] = now_kst()
            self._write(state)
            return copy.deepcopy(state)

    def requeue(self, doc_id: str) -> dict | None:
        """다시 돌릴 수 있으면 대기로 되돌린다. 없으면 None. 확인과 변경을 한 잠금 안에서 해 동시 요청이 두 번 들어가지 않게 한다."""
        with self._lock:
            if not progress.can_retry(self._states[doc_id]):
                return None
            return self.apply(doc_id, {"type": "queued"})

    def recover(self) -> list[str]:
        """서버를 켤 때 부른다. 돌던(running) 작업은 interrupted로 바꾸고, 대기 중이던 문서 번호를 올린 순서로 돌려준다."""
        with self._lock:
            for doc_id, state in self._states.items():
                if state["status"] == "running":
                    self.apply(doc_id, {"type": "interrupted"})
            queued = [s for s in self._states.values() if s["status"] == "queued"]
            return [s["id"] for s in sorted(queued, key=lambda s: (s["created_at"], s["id"]))]

    # ── 내부 ──
    def _next_id(self, today: str) -> str:
        used = [int(m.group(2)) for i in self._states if (m := _ID.match(i)) and m.group(1) == today]
        for folder in (self.root, *self.taken_dirs):
            if folder.is_dir():
                used += [int(m.group(2)) for p in folder.iterdir() if (m := _ID.match(p.name)) and m.group(1) == today]
        return f"U-{today}-{max(used, default=0) + 1:03d}"

    def _write(self, state: dict) -> None:
        path = self.root / state["id"] / STATE_NAME
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, path)
