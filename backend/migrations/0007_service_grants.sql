-- psql 식별자 변수: -v extract_role=... -v judge_role=...
-- 데이터베이스와 스키마·테이블 생성이 완료된 뒤 해당 객체 소유자가 적용한다.
-- handoff의 불변성을 위해 A·B에 UPDATE/DELETE를 부여하지 않는다.
BEGIN;

GRANT USAGE ON SCHEMA extract TO :"extract_role";
GRANT SELECT, INSERT, UPDATE ON extract.jobs TO :"extract_role";
GRANT SELECT, INSERT ON extract.results, extract.reviews,
    extract.artifacts, extract.handoff TO :"extract_role";
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA extract TO :"extract_role";

GRANT USAGE ON SCHEMA judge TO :"judge_role";
GRANT SELECT, INSERT, UPDATE ON judge.runs, judge.explanations TO :"judge_role";
GRANT SELECT, INSERT ON judge.versions, judge.reviews,
    judge.snapshots, judge.artifacts TO :"judge_role";
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA judge TO :"judge_role";

-- B는 추출 서비스의 불변 전달본만 읽는다. 지식 DB 계정은 별도로 관리한다.
GRANT USAGE ON SCHEMA extract TO :"judge_role";
GRANT SELECT ON extract.handoff TO :"judge_role";

COMMIT;
