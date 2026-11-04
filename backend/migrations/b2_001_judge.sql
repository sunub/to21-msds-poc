-- B 판정·저장 부분의 judge 스키마. 관리자 계정으로 한 번 실행한다 (scripts/b2_migrate.py). 다시 실행해도 안전하다.
-- 판정·저장본은 쓴 뒤 바꾸지 않고, 검토 이벤트는 지우거나 고치지 않는다. 계정 권한으로 막는다.

CREATE SCHEMA IF NOT EXISTS judge;

CREATE TABLE IF NOT EXISTS judge.handoff_state (
  job_id       text NOT NULL,
  handoff_seq  integer NOT NULL,
  state        text NOT NULL CHECK (state IN ('판정 중', '완료', '건너뜀', '실패')),
  attempts     integer NOT NULL DEFAULT 1,
  error        text,
  version      integer,
  taken_at     timestamptz NOT NULL DEFAULT now(),
  finished_at  timestamptz,
  PRIMARY KEY (job_id, handoff_seq)
);
-- 연결 장애로 실패한 줄. 시도 횟수를 쓰지 않고 복구될 때까지 다시 잡힌다.
ALTER TABLE judge.handoff_state ADD COLUMN IF NOT EXISTS retryable boolean NOT NULL DEFAULT false;

CREATE TABLE IF NOT EXISTS judge.judgment (
  job_id            text NOT NULL,
  version           integer NOT NULL CHECK (version >= 1),
  handoff_seq       integer NOT NULL,
  judge_key         text NOT NULL,
  consistency       jsonb NOT NULL,
  explain_keys      jsonb NOT NULL,
  changed_findings  jsonb NOT NULL,
  judged_at         timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (job_id, version)
);
CREATE INDEX IF NOT EXISTS judgment_key_idx ON judge.judgment (judge_key);

-- 요청 내용 해시로 묶어 작업·판정 버전이 달라도 같은 요청이면 다시 만들지 않는다.
CREATE TABLE IF NOT EXISTS judge.explanation (
  finding_id    text NOT NULL,
  input_sha256  text NOT NULL,
  request       jsonb NOT NULL,
  state         text NOT NULL DEFAULT '대기' CHECK (state IN ('대기', '작성 중', '완료')),
  body          jsonb,
  created_at    timestamptz NOT NULL DEFAULT now(),
  taken_at      timestamptz,
  PRIMARY KEY (finding_id, input_sha256)
);
CREATE INDEX IF NOT EXISTS explanation_state_idx ON judge.explanation (state, created_at);

CREATE TABLE IF NOT EXISTS judge.review_event (
  event_id      bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  job_id        text NOT NULL,
  finding_id    text NOT NULL,
  action        text NOT NULL CHECK (action IN ('불일치 확정', '예외 승인', '확인', '의견', '되돌리기')),
  comment       text,
  reviewer      text NOT NULL,
  at            timestamptz NOT NULL DEFAULT now(),
  version       integer NOT NULL,
  verdict_seen  text NOT NULL,
  finding_sha   text NOT NULL
);
CREATE INDEX IF NOT EXISTS review_event_job_idx ON judge.review_event (job_id, event_id);

CREATE TABLE IF NOT EXISTS judge.snapshot (
  job_id                text NOT NULL,
  snapshot_no           integer NOT NULL CHECK (snapshot_no >= 1),
  handoff_seq           integer NOT NULL,
  version               integer NOT NULL,
  last_review_event_id  bigint,
  counts                jsonb NOT NULL,
  saved_by              text NOT NULL,
  saved_at              timestamptz NOT NULL DEFAULT now(),
  note                  text,
  PRIMARY KEY (job_id, snapshot_no)
);

DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'judge_writer') THEN
    CREATE ROLE judge_writer LOGIN;
  END IF;
END $$;

GRANT USAGE ON SCHEMA judge TO judge_writer;
REVOKE ALL ON ALL TABLES IN SCHEMA judge FROM judge_writer;
GRANT SELECT, INSERT, UPDATE ON judge.handoff_state, judge.explanation TO judge_writer;
GRANT SELECT, INSERT ON judge.judgment, judge.review_event, judge.snapshot TO judge_writer;
