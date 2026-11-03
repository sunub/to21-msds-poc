-- B 쓰기 계정이 A의 넘김 표(extract.handoff)를 읽게 한다 (개요 6.2). extract 스키마는 A 것이다.
-- 팀 DB: A 실행기(apply_erd_migrations.py)가 0007에서 to21_judge 그룹에 읽기 권한을 준다. B 계정은 그 그룹에 넣는다.
-- extract에 직접 GRANT하면 A 실행기가 "스키마가 이력과 다르다"며 멈춘다 (2026-11-03 확인). 예전에 준 직접 권한은 되돌린다.
DO $grant$
BEGIN
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'to21_judge')
     AND has_table_privilege('to21_judge', 'extract.handoff', 'SELECT') THEN
    REVOKE SELECT ON extract.handoff FROM judge_writer;
    REVOKE USAGE ON SCHEMA extract FROM judge_writer;
    GRANT to21_judge TO judge_writer;
  ELSE
    -- A 실행기 없이 개발용 대역(dev/a2_stub_extract_handoff.sql)을 쓸 때
    GRANT USAGE ON SCHEMA extract TO judge_writer;
    GRANT SELECT ON extract.handoff TO judge_writer;
  END IF;
END
$grant$;
