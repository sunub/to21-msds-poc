-- 판정 상태와 불변 판정 버전. 실행 전 judge 스키마가 준비돼 있어야 한다.
-- A/B 경계: B는 extract.handoff를 SELECT만 한다. cross-schema FK를 두지
-- 않으므로 서비스는 버전 발행 전 (job_id, handoff_seq)의 존재 및 입력을 확인한다.
BEGIN;

CREATE TABLE judge.runs (
    job_id TEXT PRIMARY KEY CHECK (job_id ~ '^U-[0-9]{8}-[0-9]{3,}$'),
    state TEXT NOT NULL DEFAULT '판정 없음'
        CHECK (state IN ('판정 없음', '판정 중', '판정 있음', '판정 실패')),
    latest_version INTEGER CHECK (latest_version > 0),
    pending_handoff_seq INTEGER CHECK (pending_handoff_seq > 0),
    processed_handoff_seq INTEGER NOT NULL DEFAULT 0 CHECK (processed_handoff_seq >= 0),
    error TEXT,
    lease_token TEXT,
    lease_expires_at TIMESTAMPTZ,
    attempt_no INTEGER NOT NULL DEFAULT 0 CHECK (attempt_no >= 0),
    retry_count INTEGER NOT NULL DEFAULT 0 CHECK (retry_count >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT runs_lease_pair CHECK ((lease_token IS NULL) = (lease_expires_at IS NULL)),
    CONSTRAINT runs_pending_after_processed CHECK (
        pending_handoff_seq IS NULL OR pending_handoff_seq > processed_handoff_seq
    )
);

CREATE TABLE judge.versions (
    job_id TEXT NOT NULL REFERENCES judge.runs (job_id),
    version INTEGER NOT NULL CHECK (version > 0),
    handoff_seq INTEGER NOT NULL CHECK (handoff_seq > 0),
    judgment_key TEXT NOT NULL CHECK (judgment_key ~ '^[0-9a-f]{64}$'),
    as_of DATE NOT NULL,
    engine_version TEXT NOT NULL CHECK (btrim(engine_version) <> ''),
    knowledge_json JSONB NOT NULL CHECK (jsonb_typeof(knowledge_json) = 'object'),
    consistency_json JSONB NOT NULL CHECK (jsonb_typeof(consistency_json) = 'object'),
    display_json JSONB CHECK (display_json IS NULL OR jsonb_typeof(display_json) = 'object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (job_id, version),
    CONSTRAINT versions_handoff_version_unique UNIQUE (job_id, version, handoff_seq)
);

-- 상태의 최신 버전은 같은 작업의 실제 판정만 가리킨다. 두 행을 한 트랜잭션에
-- 추가할 수 있도록 커밋 시점에 확인한다. NULL은 아직 판정 없음이다.
ALTER TABLE judge.runs ADD CONSTRAINT runs_latest_version_fk
    FOREIGN KEY (job_id, latest_version) REFERENCES judge.versions (job_id, version)
    DEFERRABLE INITIALLY DEFERRED;

CREATE INDEX runs_pending_idx ON judge.runs (created_at, job_id)
    WHERE pending_handoff_seq IS NOT NULL;
CREATE INDEX versions_handoff_idx ON judge.versions (job_id, handoff_seq);
-- 입력이 같아도 각 handoff에 대한 버전은 별도로 저장하므로 유일 인덱스가 아니다.
CREATE INDEX versions_judgment_key_idx ON judge.versions (judgment_key);

COMMIT;
