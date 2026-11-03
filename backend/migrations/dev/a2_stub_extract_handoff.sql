-- 개발·시험 전용. A2의 진짜 마이그레이션(a2_0003_extract_handoff.sql)이 들어오면 이 파일을 지운다.
-- 칸은 A2 표와 같다 (브랜치 a2/one-pdf, 2026-11-03). A2 표의 외래 키·형식 검사·변경 금지 트리거는 뺐다.
CREATE SCHEMA IF NOT EXISTS extract;
CREATE TABLE IF NOT EXISTS extract.handoff (
  job_id            text NOT NULL,
  handoff_seq       integer NOT NULL,
  reason            text NOT NULL,
  as_of             date NOT NULL,
  extraction_sha256 text NOT NULL,
  payload_json      jsonb NOT NULL,
  created_at        timestamptz NOT NULL,
  PRIMARY KEY (job_id, handoff_seq)
);
