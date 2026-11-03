-- 저장본과 판정 산출물. 저장 시 검토 상태를 JSON으로 고정하며 미검토도 허용한다.
BEGIN;

CREATE TABLE judge.snapshots (
    job_id TEXT NOT NULL,
    snapshot_no INTEGER NOT NULL CHECK (snapshot_no > 0),
    version INTEGER NOT NULL,
    handoff_seq INTEGER NOT NULL,
    last_review_event_id BIGINT,
    review_state_json JSONB NOT NULL CHECK (jsonb_typeof(review_state_json) = 'object'),
    counts_json JSONB NOT NULL CHECK (jsonb_typeof(counts_json) = 'object'),
    saved_by TEXT NOT NULL CHECK (char_length(saved_by) BETWEEN 1 AND 50),
    saved_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    note TEXT CHECK (note IS NULL OR char_length(note) <= 2000),
    PRIMARY KEY (job_id, snapshot_no),
    CONSTRAINT snapshots_version_handoff_fk FOREIGN KEY (job_id, version, handoff_seq)
        REFERENCES judge.versions (job_id, version, handoff_seq),
    -- MATCH SIMPLE: 검토 이벤트가 없으면 NULL; 있으면 같은 작업에 속해야 한다.
    CONSTRAINT snapshots_review_event_fk FOREIGN KEY (job_id, last_review_event_id)
        REFERENCES judge.reviews (job_id, event_id),
    CONSTRAINT snapshots_version_unique UNIQUE (job_id, snapshot_no, version)
);
CREATE INDEX snapshots_latest_idx ON judge.snapshots (job_id, snapshot_no DESC);

CREATE TABLE judge.artifacts (
    artifact_id TEXT PRIMARY KEY CHECK (btrim(artifact_id) <> ''),
    job_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    snapshot_no INTEGER CHECK (snapshot_no > 0),
    format TEXT NOT NULL CHECK (format IN ('html', 'xlsx', 'json', 'pdf')),
    storage_uri TEXT NOT NULL CHECK (btrim(storage_uri) <> ''),
    content_sha256 TEXT NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    request_json JSONB NOT NULL CHECK (jsonb_typeof(request_json) = 'object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT artifacts_version_fk FOREIGN KEY (job_id, version)
        REFERENCES judge.versions (job_id, version),
    -- snapshot_no가 NULL이면 저장 전 미리보기. 저장본 파일은 버전까지 일치한다.
    CONSTRAINT artifacts_snapshot_version_fk FOREIGN KEY (job_id, snapshot_no, version)
        REFERENCES judge.snapshots (job_id, snapshot_no, version)
);
CREATE INDEX artifacts_job_version_idx ON judge.artifacts (job_id, version);
CREATE INDEX artifacts_snapshot_idx ON judge.artifacts (job_id, snapshot_no)
    WHERE snapshot_no IS NOT NULL;

COMMIT;
