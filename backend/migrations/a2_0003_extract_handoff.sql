-- A→B 불변 전달본. 각 행의 전체 JSON Schema 및 추출 JSON 정규 해시는 서비스에서 검증한다.
BEGIN;

CREATE TABLE extract.handoff (
    job_id TEXT NOT NULL REFERENCES extract.jobs (job_id),
    handoff_seq INTEGER NOT NULL CHECK (handoff_seq > 0),
    reason TEXT NOT NULL CHECK (reason IN ('extraction_done', 'values_reviewed', 'value_edited', 'rerun')),
    as_of DATE NOT NULL,
    extraction_sha256 TEXT NOT NULL CHECK (extraction_sha256 ~ '^[0-9a-f]{64}$'),
    payload_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (job_id, handoff_seq),
    CONSTRAINT extract_handoff_payload_shape CHECK ((
        jsonb_typeof(payload_json) = 'object'
        AND payload_json ?& ARRAY['contract', 'job_id', 'handoff_seq', 'reason', 'created_at', 'as_of',
                                  'source', 'extraction_settings', 'extraction', 'extraction_sha256',
                                  'checks', 'field_status']
        AND payload_json->>'contract' = 'handoff/1'
        AND jsonb_typeof(payload_json->'source') = 'object'
        AND jsonb_typeof(payload_json->'extraction_settings') = 'object'
        AND jsonb_typeof(payload_json->'extraction') = 'object'
        AND jsonb_typeof(payload_json->'checks') = 'object'
        AND (payload_json->'checks') ?& ARRAY['validator', 'failed_sections', 'reextracted_sections', 'source_mismatch']
        AND jsonb_typeof(payload_json->'checks'->'validator') = 'object'
        AND jsonb_typeof(payload_json->'checks'->'failed_sections') = 'array'
        AND jsonb_typeof(payload_json->'checks'->'reextracted_sections') = 'array'
        AND jsonb_typeof(payload_json->'checks'->'source_mismatch') = 'array'
        AND jsonb_typeof(payload_json->'field_status') = 'array'
        AND jsonb_typeof(payload_json->'created_at') = 'string'
        AND payload_json->>'created_at' ~ '(Z|[+-][0-9]{2}:[0-9]{2})$'
    ) IS TRUE),
    CONSTRAINT extract_handoff_payload_columns_match CHECK ((
        payload_json->>'job_id' = job_id
        AND payload_json->'handoff_seq' = to_jsonb(handoff_seq)
        AND payload_json->>'reason' = reason
        AND payload_json->>'as_of' = to_char(as_of, 'YYYY-MM-DD')
        AND payload_json->>'extraction_sha256' = extraction_sha256
        AND (payload_json->>'created_at')::timestamptz = created_at
    ) IS TRUE)
);

-- 작업당 발행 순서와 동시성은 작업 행 잠금으로 직렬화한다.
-- 같은 extraction이어도 새 전달본이면 새 순번으로 저장한다.
CREATE FUNCTION extract.reject_handoff_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'extract.handoff records are immutable' USING ERRCODE = '55000';
END;
$$;
CREATE TRIGGER extract_handoff_immutable
    BEFORE UPDATE OR DELETE ON extract.handoff
    FOR EACH ROW EXECUTE FUNCTION extract.reject_handoff_mutation();

COMMIT;
