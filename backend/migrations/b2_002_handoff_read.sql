-- B 쓰기 계정에 extract.handoff 읽기 권한만 준다 (개요 6.2). 표는 A2가 만든다 (또는 개발용 dev/a2_stub_extract_handoff.sql).
GRANT USAGE ON SCHEMA extract TO judge_writer;
GRANT SELECT ON extract.handoff TO judge_writer;
