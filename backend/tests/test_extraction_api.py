"""PDF upload API tests; fake store isolates HTTP behavior from PostgreSQL."""
from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import fastapi.routing
import pymupdf

from msds.api.extraction_app import create_app
from msds.preprocess.jobs import run_one
from msds.preprocess.pdf_pipeline import extract_pdf


class FakeStore:
    def __init__(self, _dsn):
        self.jobs = {}

    def create_job(self, job_id, doc_id, source_path, output_path, original_filename):
        self.jobs[job_id] = dict(job_id=job_id, doc_id=doc_id, source_path=str(source_path),
            output_path=str(output_path), original_filename=original_filename, status='queued',
            stage='queued', completed_pages=0, total_pages=None, result_dir=None, error=None,
            created_at='now', started_at=None, updated_at='now', finished_at=None)
        return self.jobs[job_id].copy()

    def get_job(self, job_id):
        job = self.jobs.get(job_id)
        return job.copy() if job else None

    def recover_expired(self):
        return 0

    def claim(self, worker_id, lease_seconds):
        for job in self.jobs.values():
            if job['status'] == 'queued':
                job.update(status='running', stage='preparing', worker_id=worker_id)
                return job.copy()
        return None

    def heartbeat(self, job_id, worker_id, lease_seconds):
        return self.jobs[job_id]['status'] == 'running'

    def progress(self, job_id, worker_id, event):
        job = self.jobs[job_id]
        job.update(stage=event['stage'], completed_pages=event.get('completed_pages', job['completed_pages']),
                   total_pages=event.get('total_pages', job['total_pages']))
        return True

    def finish(self, job_id, worker_id, *, error=None, result_dir=None):
        job = self.jobs[job_id]
        job.update(status='failed' if error else 'succeeded', error=error, result_dir=result_dir)
        return True


def make_pdf(*pages: str) -> bytes:
    with pymupdf.open() as document:
        for text in pages:
            page = document.new_page(width=420, height=540)
            page.insert_text((32, 60), text, fontsize=12)
        return document.tobytes()


def test_upload_then_real_extraction_pipeline(tmp_path, monkeypatch):
    # The sandbox cannot wake the asyncio loop from an AnyIO worker thread.
    async def inline_threadpool(func, *args, **kwargs):
        return func(*args, **kwargs)
    monkeypatch.setattr(fastapi.routing, "run_in_threadpool", inline_threadpool)
    async def scenario():
        app = create_app(data_root=tmp_path, database_url='fake', store_factory=FakeStore)
        data = make_pdf('Fresh product CAS 71-43-2', 'Transport UN 1114')
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                response = await client.post('/api/v1/documents', files={'file': ('input.pdf', data, 'application/pdf')})
                assert response.status_code == 202, response.text
                submitted = response.json()
                assert submitted['status'] == 'queued'
                job_id, doc_id = submitted['job_id'], submitted['doc_id']
                assert job_id.startswith('job_') and doc_id.startswith('doc_')
                assert (tmp_path / 'uploads' / f'{doc_id}.pdf').read_bytes() == data
                store = app.state.store
                queued = await client.get(f'/api/v1/jobs/{job_id}')
                assert queued.status_code == 200
                assert queued.json()['result_ready'] is False
                snapshots = []

                def observed_extractor(source, output, **kwargs):
                    callback = kwargs['on_progress']

                    def observer(event):
                        callback(event)
                        if event['stage'] == 'page' and event['completed_pages'] == 2:
                            snapshots.append((store.get_job(job_id), Path(output).exists()))

                    kwargs['on_progress'] = observer
                    return extract_pdf(source, output, **kwargs)

                assert run_one(store, extractor=observed_extractor, ocr_device='cpu', use_docling=False)
                assert snapshots and snapshots[0][0]['status'] == 'running' and not snapshots[0][1]
                assert store.get_job(job_id)['status'] == 'succeeded'
                status = await client.get(f'/api/v1/jobs/{job_id}')
                assert status.status_code == 200 and status.json()['result_ready'] is True
                assert (await client.get('/api/v1/jobs/job_missing')).status_code == 404
                output = tmp_path / 'pages' / doc_id
                assert '71-43-2' in (output / 'p001.txt').read_text(encoding='utf-8')
                assert '1114' in (output / 'p002.txt').read_text(encoding='utf-8')
                assert (output / 'p001.png').is_file()
                assert (output / 'meta.json').is_file()
    asyncio.run(scenario())


def test_invalid_uploads_are_rejected_and_cleaned(tmp_path):
    async def scenario():
        app = create_app(data_root=tmp_path, database_url='fake', store_factory=FakeStore,
                         max_upload_bytes=512)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                for data in (b'', b'not a pdf'):
                    response = await client.post('/api/v1/documents', files={'file': ('bad.pdf', data, 'application/pdf')})
                    assert response.status_code == 422
                response = await client.post('/api/v1/documents', files={'file': ('huge.pdf', b'x' * 1024, 'application/pdf')})
                assert response.status_code == 413
                assert app.state.store.jobs == {}
                assert not list((tmp_path / 'uploads').glob('*.pdf'))
    asyncio.run(scenario())


def test_worker_failure_is_returned_by_status(tmp_path, monkeypatch):
    async def inline_threadpool(func, *args, **kwargs):
        return func(*args, **kwargs)
    monkeypatch.setattr(fastapi.routing, 'run_in_threadpool', inline_threadpool)

    async def scenario():
        app = create_app(data_root=tmp_path, database_url='fake', store_factory=FakeStore)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                response = await client.post('/api/v1/documents', files={'file': ('input.pdf', make_pdf('Page text'), 'application/pdf')})
                job_id = response.json()['job_id']
                def fail(*args, **kwargs):
                    raise RuntimeError('Test extraction failure')
                assert run_one(app.state.store, extractor=fail)
                status = (await client.get(f'/api/v1/jobs/{job_id}')).json()
                assert status['status'] == 'failed'
                assert status['result_ready'] is False
                assert status['error']
    asyncio.run(scenario())
