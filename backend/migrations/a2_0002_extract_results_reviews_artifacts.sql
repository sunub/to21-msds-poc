-- 불변 추출 결과, 추출값 검수 이벤트, 원본/변환 파일 메타데이터.
-- JSON 전체 계약 및 결과 kind 간 의미적 참조는 호출 측에서 검증한다.
BEGIN;

CREATE TABLE extract.results (
    result_id TEXT PRIMARY KEY CHECK (length(result_id) > 0),
    job_id TEXT NOT NULL REFERENCES extract.jobs (job_id),
    attempt_no INTEGER NOT NULL CHECK (attempt_no >= 0),
    kind TEXT NOT NULL CHECK (kind IN ('extraction_draft', 'extraction', 'extraction_check')),
    parent_result_id TEXT,
    payload_json JSONB NOT NULL CHECK (jsonb_typeof(payload_json) = 'object'),
    content_sha256 TEXT NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    context_json JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(context_json) = 'object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT extract_results_job_result_unique UNIQUE (job_id, result_id),
    CONSTRAINT extract_results_parent_same_job_fk FOREIGN KEY (job_id, parent_result_id)
        REFERENCES extract.results (job_id, result_id),
    CHECK (parent_result_id IS NULL OR parent_result_id <> result_id)
);

CREATE INDEX extract_results_job_attempt_idx ON extract.results (job_id, attempt_no, created_at);

CREATE TABLE extract.reviews (
    review_id TEXT PRIMARY KEY CHECK (length(review_id) > 0),
    job_id TEXT NOT NULL REFERENCES extract.jobs (job_id),
    result_id TEXT NOT NULL,
    review_seq BIGINT NOT NULL CHECK (review_seq > 0),
    msds_index INTEGER NOT NULL CHECK (msds_index >= 0),
    field_path TEXT,
    section_no INTEGER CHECK (section_no IN (1, 2, 3, 8, 9, 11, 12, 14, 15)),
    action TEXT NOT NULL CHECK (action IN ('confirm', 'edit', 'reset', 'section_confirm', 'section_unconfirm')),
    before_json JSONB,
    after_json JSONB,
    reviewer TEXT NOT NULL CHECK (length(reviewer) BETWEEN 1 AND 50),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT extract_reviews_job_seq_unique UNIQUE (job_id, review_seq),
    CONSTRAINT extract_reviews_result_same_job_fk FOREIGN KEY (job_id, result_id)
        REFERENCES extract.results (job_id, result_id),
    CHECK (field_path IS NULL OR length(field_path) > 0),
    CHECK ((action IN ('confirm', 'edit', 'reset') AND field_path IS NOT NULL)
        OR (action IN ('section_confirm', 'section_unconfirm') AND field_path IS NULL AND section_no IS NOT NULL))
);

CREATE INDEX extract_reviews_result_idx ON extract.reviews (job_id, result_id, msds_index);

CREATE TABLE extract.artifacts (
    artifact_id TEXT PRIMARY KEY CHECK (length(artifact_id) > 0),
    job_id TEXT NOT NULL REFERENCES extract.jobs (job_id),
    result_id TEXT,
    attempt_no INTEGER CHECK (attempt_no >= 0),
    kind TEXT NOT NULL CHECK (length(kind) > 0),
    storage_uri TEXT NOT NULL CHECK (length(storage_uri) > 0),
    content_sha256 TEXT NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata_json) = 'object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT extract_artifacts_result_same_job_fk FOREIGN KEY (job_id, result_id)
        REFERENCES extract.results (job_id, result_id)
);

CREATE INDEX extract_artifacts_job_kind_idx ON extract.artifacts (job_id, kind, created_at);

COMMIT;
