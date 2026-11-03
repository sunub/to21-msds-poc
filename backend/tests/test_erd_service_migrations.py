"""Real PostgreSQL checks for the extract/judge ERD migrations.

Opt in only with TO21_ERD_TEST_DATABASE_URL pointing at a disposable database.
Each test creates random schemas, applies the actual migrations with only the
schema qualifiers changed, and drops those schemas afterward. This test never
uses or removes the fixed production `extract` or `judge` schemas.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
import pytest

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"
TABLE_FILES = (
    "a1_0001_extract_jobs.sql",
    "a2_0002_extract_results_reviews_artifacts.sql",
    "a2_0003_extract_handoff.sql",
    "b2_0004_judge_runs_versions.sql",
    "b2_0005_judge_explanations_reviews.sql",
    "b2_0006_judge_snapshots_artifacts.sql",
)
HASH = "a" * 64


def _isolated_sql(source: str, extract_schema: str, judge_schema: str) -> str:
    """Redirect explicit schema qualifiers, retaining actual migration SQL."""
    source = re.sub(r"\bextract\.", extract_schema + ".", source)
    source = re.sub(r"\bjudge\.", judge_schema + ".", source)
    # GRANT statements refer to a schema as a standalone identifier, not just
    # as a table qualifier (e.g. ON SCHEMA and ON ALL SEQUENCES IN SCHEMA).
    source = re.sub(r"(\b(?:ON|IN)\s+SCHEMA\s+)extract\b",
                    lambda match: match.group(1) + extract_schema, source, flags=re.I)
    source = re.sub(r"(\b(?:ON|IN)\s+SCHEMA\s+)judge\b",
                    lambda match: match.group(1) + judge_schema, source, flags=re.I)
    return source


def test_grants_are_retargeted_to_temporary_schemas():
    # Security regression: test grants must never touch the fixed live schemas.
    grants = (MIGRATIONS / "0007_service_grants.sql").read_text(encoding="utf-8")
    isolated = _isolated_sql(grants, "erd_a_example", "erd_b_example")
    assert not re.search(r"\b(?:ON|IN)\s+SCHEMA\s+(?:extract|judge)\b", isolated, re.I)
    assert not re.search(r"\b(?:extract|judge)\.", isolated)
    assert "ON SCHEMA erd_a_example" in isolated
    assert "ON SCHEMA erd_b_example" in isolated
    assert "IN SCHEMA erd_a_example" in isolated
    assert "IN SCHEMA erd_b_example" in isolated


@pytest.fixture
def migrated_db():
    dsn = os.environ.get("TO21_ERD_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("Set TO21_ERD_TEST_DATABASE_URL to an explicit disposable PostgreSQL database")
    suffix = uuid4().hex
    a, b = "erd_a_" + suffix, "erd_b_" + suffix
    with psycopg.connect(dsn, autocommit=True) as conn:
        try:
            conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(a)))
            conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(b)))
            for name in TABLE_FILES:
                ddl = _isolated_sql((MIGRATIONS / name).read_text(encoding="utf-8"), a, b)
                try:
                    conn.execute(ddl)
                except Exception:
                    conn.execute("ROLLBACK")
                    raise
            yield conn, a, b
        finally:
            conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(b)))
            conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(a)))


def _table(schema: str, name: str):
    return sql.Identifier(schema, name)


def _job(conn, schema, job_id):
    conn.execute(sql.SQL("""INSERT INTO {} (job_id, filename, file_sha256, size_bytes, model_tag)
                            VALUES (%s, 'source.pdf', %s, 17, 'model')""")
                 .format(_table(schema, "jobs")), (job_id, HASH))


def _result(conn, schema, job_id, result_id):
    conn.execute(sql.SQL("""INSERT INTO {} (job_id, result_id, attempt_no, kind, payload_json, content_sha256)
                            VALUES (%s, %s, 0, 'extraction', %s, %s)""")
                 .format(_table(schema, "results")), (job_id, result_id, Jsonb({}), HASH))


def _handoff(conn, schema, job_id, *, seq=1, payload_seq=None):
    date = "2026-11-02"
    timestamp = "2026-11-02T14:30:00+09:00"
    payload = {
        "contract": "handoff/1", "job_id": job_id,
        "handoff_seq": seq if payload_seq is None else payload_seq,
        "reason": "extraction_done", "created_at": timestamp, "as_of": date,
        "source": {}, "extraction_settings": {}, "extraction": {},
        "extraction_sha256": HASH,
        "checks": {"validator": {}, "failed_sections": [], "reextracted_sections": [], "source_mismatch": []},
        "field_status": [],
    }
    conn.execute(sql.SQL("""INSERT INTO {} (job_id, handoff_seq, reason, as_of, extraction_sha256,
                                               payload_json, created_at)
                            VALUES (%s, %s, 'extraction_done', %s, %s, %s, %s)""")
                 .format(_table(schema, "handoff")), (job_id, seq, date, HASH, Jsonb(payload), timestamp))


def _run(conn, schema, job_id):
    conn.execute(sql.SQL("INSERT INTO {} (job_id) VALUES (%s)").format(_table(schema, "runs")), (job_id,))


def _version(conn, schema, job_id, version, handoff_seq):
    conn.execute(sql.SQL("""INSERT INTO {} (job_id, version, handoff_seq, judgment_key, as_of,
                                               engine_version, knowledge_json, consistency_json)
                            VALUES (%s, %s, %s, %s, '2026-11-02', '1.0.0', %s, %s)""")
                 .format(_table(schema, "versions")),
                 (job_id, version, handoff_seq, HASH, Jsonb({}), Jsonb({})))


def _snapshot(conn, schema, job_id, no, version, handoff_seq, event_id=None):
    conn.execute(sql.SQL("""INSERT INTO {} (job_id, snapshot_no, version, handoff_seq, last_review_event_id,
                                               review_state_json, counts_json, saved_by)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, 'reviewer')""")
                 .format(_table(schema, "snapshots")),
                 (job_id, no, version, handoff_seq, event_id, Jsonb({}), Jsonb({})))


def test_duplicate_pdf_and_same_job_result_references(migrated_db):
    conn, a, _ = migrated_db
    first, second = "U-20261102-001", "U-20261102-002"
    _job(conn, a, first)
    _job(conn, a, second)  # identical file hash must not reject a new upload
    _result(conn, a, second, "result-2")
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        conn.execute(sql.SQL("""INSERT INTO {} (review_id, job_id, result_id, review_seq, msds_index,
                                                   field_path, action, reviewer)
                                VALUES ('bad-review', %s, 'result-2', 1, 0, 'product.name',
                                        'confirm', 'reviewer')""").format(_table(a, "reviews")), (first,))
    _result(conn, a, first, "result-1")
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        conn.execute(sql.SQL("""INSERT INTO {} (result_id, job_id, attempt_no, kind, parent_result_id,
                                                   payload_json, content_sha256)
                                VALUES ('wrong-parent', %s, 0, 'extraction', 'result-2', %s, %s)""")
                     .format(_table(a, "results")), (first, Jsonb({}), HASH))
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        conn.execute(sql.SQL("""INSERT INTO {} (artifact_id, job_id, result_id, kind, storage_uri,
                                                   content_sha256)
                                VALUES ('wrong-file', %s, 'result-2', 'original', 'test://source', %s)""")
                     .format(_table(a, "artifacts")), (first, HASH))
    conn.execute(sql.SQL("""INSERT INTO {} (review_id, job_id, result_id, review_seq, msds_index,
                                               field_path, action, reviewer)
                            VALUES ('ok-review', %s, 'result-1', 1, 0, 'product.name',
                                    'confirm', 'reviewer')""").format(_table(a, "reviews")), (first,))



def test_extract_queue_claim_skips_rows_locked_by_another_worker(migrated_db):
    """Two live PG transactions must select different queued jobs.

    This exercises the queue SQL primitive; the application worker's claim,
    lease fencing and recovery still require their own integration tests.
    """
    conn, a, _ = migrated_db
    first, second = "U-20261102-001", "U-20261102-002"
    _job(conn, a, first)
    _job(conn, a, second)
    claim = sql.SQL("""SELECT job_id FROM {} WHERE status = 'queued'
                       ORDER BY created_at, job_id LIMIT 1 FOR UPDATE SKIP LOCKED""")
    claim = claim.format(_table(a, "jobs"))
    update = sql.SQL("UPDATE {} SET status = 'running' WHERE job_id = %s").format(_table(a, "jobs"))
    # Fixture requires this explicit disposable DSN. Never create connections
    # to an implicit default database or an application/production environment.
    with psycopg.connect(os.environ["TO21_ERD_TEST_DATABASE_URL"], autocommit=True) as worker_b:
        with conn.transaction():
            claimed_a = conn.execute(claim).fetchone()[0]
            with worker_b.transaction():
                claimed_b = worker_b.execute(claim).fetchone()[0]
                assert {claimed_a, claimed_b} == {first, second}
                worker_b.execute(update, (claimed_b,))
                # The second worker's own row is no longer queued, and the
                # remaining queued row is still locked by the first worker.
                assert worker_b.execute(claim).fetchone() is None
            conn.execute(update, (claimed_a,))
    rows = conn.execute(sql.SQL("SELECT job_id, status FROM {} ORDER BY job_id")
                        .format(_table(a, "jobs"))).fetchall()
    assert rows == [(first, "running"), (second, "running")]


def test_invalid_job_and_queue_lease_states_are_rejected(migrated_db):
    conn, a, b = migrated_db
    job_id = "U-20261102-001"
    _job(conn, a, job_id)
    assert conn.execute(sql.SQL("SELECT as_of FROM {} WHERE job_id=%s")
                        .format(_table(a, "jobs")), (job_id,)).fetchone() == (None,)
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(sql.SQL("UPDATE {} SET status='unknown' WHERE job_id=%s")
                     .format(_table(a, "jobs")), (job_id,))
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(sql.SQL("UPDATE {} SET lease_token='orphan' WHERE job_id=%s")
                     .format(_table(a, "jobs")), (job_id,))
    _run(conn, b, job_id)
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(sql.SQL("UPDATE {} SET processed_handoff_seq=3, pending_handoff_seq=2 WHERE job_id=%s")
                     .format(_table(b, "runs")), (job_id,))


def test_handoff_rejects_metadata_mismatch(migrated_db):
    conn, a, _ = migrated_db
    job_id = "U-20261102-001"
    _job(conn, a, job_id)
    _handoff(conn, a, job_id)
    with pytest.raises(psycopg.errors.UniqueViolation):
        _handoff(conn, a, job_id)
    with pytest.raises(psycopg.errors.CheckViolation):
        _handoff(conn, a, job_id, seq=2, payload_seq=99)
    with pytest.raises(psycopg.Error) as error:
        conn.execute(sql.SQL("UPDATE {} SET reason = reason WHERE job_id = %s")
                     .format(_table(a, "handoff")), (job_id,))
    assert error.value.sqlstate == "55000"  # published handoffs remain immutable
    with pytest.raises(psycopg.Error) as error:
        conn.execute(sql.SQL("DELETE FROM {} WHERE job_id = %s")
                     .format(_table(a, "handoff")), (job_id,))
    assert error.value.sqlstate == "55000"


def test_snapshot_and_report_remain_in_their_job_and_version(migrated_db):
    conn, _, b = migrated_db
    first, second = "U-20261102-001", "U-20261102-002"
    for job_id in (first, second):
        _run(conn, b, job_id)
    _version(conn, b, first, 1, 1)
    _version(conn, b, first, 2, 2)
    _version(conn, b, second, 1, 1)
    other_event = conn.execute(sql.SQL("""INSERT INTO {} (job_id, version, finding_id, action, reviewer,
                                                            verdict_seen, review_seq)
                                          VALUES (%s, 1, 'm0/F2:HH_SKIN_CORR:-', '확인', 'reviewer',
                                                  '일치', 1) RETURNING event_id""")
                               .format(_table(b, "reviews")), (second,)).fetchone()[0]
    _snapshot(conn, b, first, 1, 1, 1)  # saving without reviewed findings is allowed
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        _snapshot(conn, b, first, 2, 1, 2)  # version 1 was made from handoff 1
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        _snapshot(conn, b, first, 3, 1, 1, other_event)
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        conn.execute(sql.SQL("""INSERT INTO {} (artifact_id, job_id, version, snapshot_no, format,
                                                   storage_uri, content_sha256, request_json)
                                VALUES ('wrong-version', %s, 2, 1, 'pdf', 'test://report', %s, %s)""")
                     .format(_table(b, "artifacts")), (first, HASH, Jsonb({})))
    conn.execute(sql.SQL("""INSERT INTO {} (artifact_id, job_id, version, snapshot_no, format,
                                               storage_uri, content_sha256, request_json)
                            VALUES ('preview', %s, 2, NULL, 'html', 'test://preview', %s, %s)""")
                 .format(_table(b, "artifacts")), (first, HASH, Jsonb({})))


def test_explanations_can_start_empty_but_completed_need_audited_content(migrated_db):
    conn, _, b = migrated_db
    job_id = "U-20261102-001"
    _run(conn, b, job_id)
    _version(conn, b, job_id, 1, 1)
    conn.execute(sql.SQL("""INSERT INTO {} (explanation_id, job_id, version, finding_id, status)
                            VALUES ('pending', %s, 1, 'm0/F2:HH_SKIN_CORR:-', '작성 중')""")
                 .format(_table(b, "explanations")), (job_id,))
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(sql.SQL("UPDATE {} SET status='완료' WHERE explanation_id='pending'")
                     .format(_table(b, "explanations")))
    conn.execute(sql.SQL("""UPDATE {} SET status='완료', source='template', checked=true,
                                        input_sha256=%s, payload_json=%s WHERE explanation_id='pending'""")
                 .format(_table(b, "explanations")),
                 (HASH, Jsonb({"summary": "근거", "reasons": [], "basis": []})))


def test_role_grants_restrict_cross_area_access(migrated_db):
    conn, a, b = migrated_db
    can_create_roles = conn.execute("SELECT rolsuper OR rolcreaterole FROM pg_roles WHERE rolname = current_user").fetchone()[0]
    if not can_create_roles:
        pytest.skip("Role privilege check requires a disposable PostgreSQL admin with CREATEROLE")
    suffix = uuid4().hex
    role_a, role_b = "erd_role_a_" + suffix, "erd_role_b_" + suffix
    created = []
    try:
        for role in (role_a, role_b):
            conn.execute(sql.SQL("CREATE ROLE {} NOLOGIN NOINHERIT").format(sql.Identifier(role)))
            created.append(role)
        grant = (MIGRATIONS / "0007_service_grants.sql").read_text(encoding="utf-8")
        grant = _isolated_sql(grant, a, b)
        grant = grant.replace(':"extract_role"', sql.Identifier(role_a).as_string(conn))
        grant = grant.replace(':"judge_role"', sql.Identifier(role_b).as_string(conn))
        conn.execute(grant)
        rows = conn.execute("""SELECT has_table_privilege(%s, %s, 'SELECT'),
                                      has_table_privilege(%s, %s, 'SELECT'),
                                      has_table_privilege(%s, %s, 'INSERT'),
                                      has_schema_privilege(%s, %s, 'USAGE')""",
                            (role_b, f"{a}.handoff", role_b, f"{a}.jobs",
                             role_b, f"{a}.handoff", role_a, b)).fetchone()
        assert rows == (True, False, False, False)
    finally:
        # The grants script may start a transaction before failing. Clear an
        # aborted transaction before revoking privileges and removing roles.
        if conn.info.transaction_status != psycopg.pq.TransactionStatus.IDLE:
            conn.execute("ROLLBACK")
        for role in reversed(created):
            conn.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
            conn.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))
