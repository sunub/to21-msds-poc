-- 추출 작업 및 대기열. extract 스키마는 배포 단계에서 미리 만든다.
-- 최초 적용용: 동일 테이블이 있으면 실패한다. 변경은 후속 마이그레이션으로 한다.
BEGIN;

CREATE TABLE extract.jobs (
    job_id TEXT PRIMARY KEY CHECK (job_id ~ '^U-[0-9]{8}-[0-9]{3,}$'),
    filename TEXT NOT NULL CHECK (length(filename) > 0),
    file_sha256 TEXT NOT NULL CHECK (file_sha256 ~ '^[0-9a-f]{64}$'),
    size_bytes BIGINT NOT NULL CHECK (size_bytes > 0),
    as_of DATE,
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'done', 'failed', 'interrupted')),
    stage TEXT CHECK (stage IN ('preprocess', 'sections', 'extract', 'checks', 'finalize', 'done')),
    review_stage TEXT CHECK (review_stage IN ('검수 대기', '추출값 확인 중', '판정으로 넘김')),
    review_mode TEXT CHECK (review_mode IN ('values_first', 'judgments_first')),
    model_tag TEXT NOT NULL CHECK (length(model_tag) > 0),
    settings_json JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(settings_json) = 'object'),
    progress_json JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(progress_json) = 'object'),
    attempt_no INTEGER NOT NULL DEFAULT 0 CHECK (attempt_no >= 0),
    attempts_json JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(attempts_json) = 'array'),
    lease_token TEXT,
    lease_expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK ((lease_token IS NULL) = (lease_expires_at IS NULL)),
    CHECK (lease_token IS NULL OR length(lease_token) > 0)
);

-- 같은 해시 파일을 여러 번 업로드할 수 있으므로 file_sha256에 UNIQUE를 두지 않는다.
CREATE INDEX extract_jobs_queue_idx ON extract.jobs (status, stage, created_at, job_id);
CREATE INDEX extract_jobs_file_idx ON extract.jobs (file_sha256);

COMMIT;
