-- 개발·시험 전용. A2의 진짜 마이그레이션이 들어오면 이 파일을 지운다.
-- 약속 ①의 표 모양: 한 줄이 1-handoff.schema.json 하나다.
CREATE SCHEMA IF NOT EXISTS extract;
CREATE TABLE IF NOT EXISTS extract.handoff (
  job_id       text NOT NULL,
  handoff_seq  integer NOT NULL,
  body         jsonb NOT NULL,
  created_at   timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (job_id, handoff_seq)
);
