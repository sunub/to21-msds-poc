"""A1의 API 계약: 대기 상태와 게시된 작업 시도의 조회."""
import json

from fastapi.testclient import TestClient

from msds.api.extract_app import create_app
from msds.service.store import DocumentStore


class Worker:
    def start(self):
        pass

    def stop(self, timeout=None):
        pass

    def submit(self, doc_id):
        pass


class QueuedStore(DocumentStore):
    def queue_info(self, doc_id, *, workers=1):
        assert self.get(doc_id) is not None
        return {"queue_position": 2, "estimated_wait_seconds": 120, "estimated_completion_seconds": None}


def test_queue_fields_are_exposed_in_upload_list_and_detail(tmp_path):
    store = QueuedStore(tmp_path)
    with TestClient(create_app(store=store, worker=Worker(), static_dir=None)) as client:
        response = client.post("/api/documents?filename=x.pdf", content=b"%PDF-1.7\n")
        assert response.status_code == 202
        item = response.json()
        assert item["queue_position"] == 2
        # The queue wait is not a measured completion estimate.
        assert item["eta_seconds"] is None
        assert item["review_stage"] is None
        assert client.get(f"/api/documents/{item['id']}").json()["queue_position"] == 2
        assert client.get("/api/documents").json()["items"][0]["queue_position"] == 2


def test_result_and_page_endpoints_follow_published_attempt(tmp_path):
    class ArtifactStore(DocumentStore):
        def artifact_paths(self, doc_id):
            return {"pages_dir": tmp_path / "attempt" / "pages",
                    "sections_dir": tmp_path / "attempt" / "sections",
                    "runs_dir": tmp_path / "attempt" / "runs"}

    store = ArtifactStore(tmp_path / "store")
    with TestClient(create_app(store=store, worker=Worker(), static_dir=None)) as client:
        item = client.post("/api/documents?filename=x.pdf", content=b"%PDF-1.7\n").json()
        doc_id = item["id"]
        dirs = store.artifact_paths(doc_id)
        pages = dirs["pages_dir"] / doc_id
        pages.mkdir(parents=True)
        (pages / "p001.txt").write_text("게시된 쪽 글", encoding="utf-8")
        out = dirs["runs_dir"] / doc_id / "outputs" / f"{doc_id}.json"
        out.parent.mkdir(parents=True)
        out.write_text(json.dumps({"doc": {"doc_id": doc_id}, "msds": []}), encoding="utf-8")
        store.apply(doc_id, {"type": "done", "summary": {}})
        assert client.get(f"/api/documents/{doc_id}/pages/1/lines").json()["lines"][0]["text"] == "게시된 쪽 글"
        assert client.get(f"/api/documents/{doc_id}/result").json()["to21"]["doc"]["doc_id"] == doc_id
