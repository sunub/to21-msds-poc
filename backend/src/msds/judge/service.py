"""판정 서비스: 넘김 기록 → 판정 버전 → 설명 → 검토 → 저장본. 화면 API(judge_app)와 작업자(worker)가 이 클래스만 쓴다.

A 쪽에서 읽는 것은 extract.handoff 표 하나뿐이다 (개요 6절). 판정 계산은 compliance.judge.judge() 하나만 부른다.
"""
from datetime import datetime, timedelta, timezone

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from msds.compliance.htodb.config import pg_address, pg_kwargs, setting
from msds.compliance.judge import KnowledgeUnavailable, current_versions, is_connection_error, judge

from . import explain as ex
from .display import view_display

KST = timezone(timedelta(hours=9))
LEASE = timedelta(minutes=5)
# 보통의 호출보다 길게. 재요청이 겹쳐 넘으면 모델을 한 번 더 부를 수 있지만, 저장은 소유 조건으로 안전하다
EXPLAIN_LEASE = timedelta(minutes=25)
MAX_ATTEMPTS = 3
RETRY_AFTER = timedelta(seconds=30)
NEEDS_REVIEW = ("불일치", "경계", "근거부족", "경고")
JUDGED = ("일치", "불일치", "경계", "근거부족", "경고")
# 확인은 일치 쪽, 확정·승인은 일치가 아닌 쪽에만 쓴다 (5-api review_event_request). 의견·되돌리기는 어디든 된다
ACTION_VERDICTS = {"확인": ("일치", "참고", "범위 외"), "불일치 확정": NEEDS_REVIEW, "예외 승인": NEEDS_REVIEW}
VERDICTS = ("일치", "불일치", "경계", "근거부족", "경고", "참고", "범위 외")
TRANSIENT_MESSAGE = "지식DB 또는 저장소에 연결하지 못함. 복구되면 자동으로 다시 판정함"


NOT_SENT = object()
ALIVE_LOCK = 0x4A554447  # 판정 작업자가 살아 있음을 나타내는 PostgreSQL 잠금 번호


class NotFound(Exception):
    pass


class HandoffInvalid(ValueError):
    """넘김 기록 자체가 잘못됨. 글은 화면에 그대로 나간다."""


class InvalidAction(Exception):
    """이 판정에 할 수 없는 검토 동작."""


class Conflict(Exception):
    """보던 버전이 최신이 아니거나, 고친 값을 아직 판정하지 않았음 (화면은 다시 불러온다)."""

    def __init__(self, latest: int, pending: int | None = None, message: str | None = None):
        super().__init__(message or (f"넘김 기록 {pending}을 아직 판정하지 않음" if pending else f"최신 판정 버전은 {latest}"))
        self.latest, self.pending = latest, pending


def writer_kwargs(database: str | None = None) -> dict:
    return {**pg_address(), "dbname": database or setting("JUDGE_PG_DATABASE", "kdb"), "user": "judge_writer",
            "password": setting("JUDGE_PG_PASSWORD")}


def _public_error(e: Exception) -> str:
    """상태 API로 나가는 글. 다른 오류 원문에는 호스트·계정·파일 경로가 들어 있을 수 있어 서버 기록에만 남긴다."""
    if isinstance(e, (KnowledgeUnavailable, HandoffInvalid)):
        return str(e)[:1000]
    return TRANSIENT_MESSAGE if is_connection_error(e) else f"판정 중 내부 오류 ({type(e).__name__}). 서버 기록을 확인하세요"


def _iso(dt: datetime) -> str:
    return dt.astimezone(KST).isoformat(timespec="seconds")


def _findings(consistency: dict) -> list[dict]:
    return [f for r in consistency["results"] for f in r["findings"]]


def _judgment_fingerprint(f: dict) -> str:
    # MSDS 쪽 값이 바뀌어도 검토한 근거가 달라진 것이다. 원문 조각(evidence)은 판정 값이 아니라 뺀다
    msds = {k: v for k, v in f["msds"].items() if k != "evidence"}
    return ex.sha256({"verdict": f["verdict"], "msds": msds, "expected": f["expected"]})


class JudgeService:
    def __init__(self, pool: ConnectionPool | None = None, provider=None, llm=None, gate=None, database: str | None = None):
        self.pool = pool or ConnectionPool("", kwargs={**writer_kwargs(database), "row_factory": dict_row},
                                           min_size=1, max_size=8, open=True)
        self.provider, self.llm, self.gate = provider, llm, gate or ex.default_gate()
        self._alive = None

    # ── 넘김 기록 가져가기 ─────────────────────────────────────────────

    def claim_handoff(self) -> dict | None:
        """작업마다 가장 큰 번호만 판정한다. 더 작은 번호는 건너뜀으로 남긴다. 죽은 작업은 임대 시간이 지나면 다시 잡힌다."""
        with self.pool.connection() as conn:
            conn.execute("""UPDATE judge.handoff_state SET state = '실패', error = '작업자가 끝내지 못함 (시도 한도)', finished_at = now()
                            WHERE state = '판정 중' AND taken_at < now() - %s AND attempts >= %s""", (LEASE, MAX_ATTEMPTS))
            row = conn.execute(
                """SELECT h.job_id, h.handoff_seq FROM extract.handoff h
                   JOIN (SELECT job_id, max(handoff_seq) AS seq FROM extract.handoff GROUP BY job_id) l
                     ON l.job_id = h.job_id AND l.seq = h.handoff_seq
                   LEFT JOIN judge.handoff_state s ON s.job_id = h.job_id AND s.handoff_seq = h.handoff_seq
                   WHERE s.job_id IS NULL
                      OR (s.state = '판정 중' AND s.taken_at < now() - %(lease)s)
                      OR (s.state = '실패' AND s.attempts < %(max)s AND s.finished_at < now() - %(retry)s)
                   ORDER BY h.created_at LIMIT 1""",
                {"lease": LEASE, "max": MAX_ATTEMPTS, "retry": RETRY_AFTER}).fetchone()
            if not row:
                return None
            taken = conn.execute(
                """INSERT INTO judge.handoff_state (job_id, handoff_seq, state) VALUES (%(j)s, %(s)s, '판정 중')
                   ON CONFLICT (job_id, handoff_seq) DO UPDATE
                     SET state = '판정 중', attempts = judge.handoff_state.attempts + 1, taken_at = now(), error = NULL, retryable = false
                     WHERE judge.handoff_state.state = '실패'
                        OR (judge.handoff_state.state = '판정 중' AND judge.handoff_state.taken_at < now() - %(lease)s)
                   RETURNING attempts""", {"j": row["job_id"], "s": row["handoff_seq"], "lease": LEASE}).fetchone()
            if not taken:
                return None  # 다른 작업자가 먼저 잡았다
            conn.execute(
                """INSERT INTO judge.handoff_state (job_id, handoff_seq, state, finished_at)
                   SELECT job_id, handoff_seq, '건너뜀', now() FROM extract.handoff
                   WHERE job_id = %s AND handoff_seq < %s ON CONFLICT DO NOTHING""", (row["job_id"], row["handoff_seq"]))
            body = conn.execute("SELECT payload_json FROM extract.handoff WHERE job_id = %s AND handoff_seq = %s",
                                (row["job_id"], row["handoff_seq"])).fetchone()["payload_json"]
            if not isinstance(body, dict) or (body.get("job_id"), body.get("handoff_seq")) != (row["job_id"], row["handoff_seq"]):
                # 본문 값대로 저장하면 다른 작업에 판정이 들어간다. 다시 해도 같으니 바로 멈춘다. 여기서 예외가 나면 줄이 뒤 작업을 모두 막는다
                conn.execute("UPDATE judge.handoff_state SET state = '실패', attempts = %s, finished_at = now(), "
                             "error = '넘김 기록 본문이 표의 작업 번호와 맞지 않음' WHERE job_id = %s AND handoff_seq = %s",
                             (MAX_ATTEMPTS, row["job_id"], row["handoff_seq"]))
                return None
            return body

    def recover(self) -> None:
        """잡혀 있던 일은 끝날 수 없을 때 바로 다시 잡히게 한다. 서버 시작은 recover_if_alone 을 쓴다."""
        with self.pool.connection() as conn:
            conn.execute("UPDATE judge.handoff_state SET taken_at = now() - %s WHERE state = '판정 중'", (LEASE * 2,))
            conn.execute("UPDATE judge.explanation SET state = '대기', taken_at = NULL WHERE state = '작성 중'")

    def recover_if_alone(self) -> None:
        """다른 프로세스가 살아 있으면 그 작업은 진행 중이니 건드리지 않는다 (A1은 여러 프로세스를 지원한다). 그때는 임대 시간이 지나야 다시 잡힌다.

        프로세스마다 공유 잠금을 쥐고 있어, 배타 잠금을 얻었다면 혼자라는 뜻이다. 프로세스가 죽으면 연결과 함께 잠금이 풀린다.
        """
        self._alive = psycopg.connect(autocommit=True, **self.pool.kwargs)
        if self._alive.execute("SELECT pg_try_advisory_lock(%s) AS ok", (ALIVE_LOCK,)).fetchone()["ok"]:
            self.recover()
            self._alive.execute("SELECT pg_advisory_unlock(%s)", (ALIVE_LOCK,))
        self._alive.execute("SELECT pg_advisory_lock_shared(%s)", (ALIVE_LOCK,))

    def process_handoff(self, body: dict) -> int | None:
        """한 건 판정. 반환: 판정 버전. 건너뛰었거나 실패하면 None (실패 이유는 상태에 남는다)."""
        job_id, seq = body["job_id"], body["handoff_seq"]
        try:
            if ex.sha256(body.get("extraction")) != body.get("extraction_sha256"):
                raise HandoffInvalid("extraction_sha256 이 추출값과 맞지 않음")
            return self._judge_and_store(body)
        except Exception as e:  # 판정 하나가 죽어도 작업자는 계속 돈다. 이유는 화면(judgment_status.error)에 보인다
            print(f"판정 실패 {job_id}#{seq}: {type(e).__name__}: {e}")
            # 복구되면 같은 입력으로 성공하므로 시도 횟수를 쓰지 않고 계속 다시 잡는다
            transient = isinstance(e, KnowledgeUnavailable) or is_connection_error(e)
            with self.pool.connection() as conn:
                conn.execute("UPDATE judge.handoff_state SET state = '실패', error = %s, finished_at = now(), retryable = %s, "
                             "attempts = CASE WHEN %s THEN %s ELSE attempts - %s END "
                             "WHERE job_id = %s AND handoff_seq = %s AND state = '판정 중'",
                             (_public_error(e), transient, isinstance(e, HandoffInvalid), MAX_ATTEMPTS, int(transient), job_id, seq))
            return None

    def _judge_and_store(self, body: dict) -> int | None:
        job_id, seq = body["job_id"], body["handoff_seq"]
        failed = (body.get("checks") or {}).get("failed_sections") or []
        key = ex.sha256({"extraction": body["extraction_sha256"], "as_of": body["as_of"], "failed_sections": failed,
                         "versions": current_versions(self.provider)})
        with self.pool.connection() as conn:
            reused = conn.execute("SELECT consistency FROM judge.judgment WHERE judge_key = %s LIMIT 1", (key,)).fetchone()
        consistency = reused["consistency"] if reused else judge(body["extraction"], body["as_of"], self.provider, failed)

        requests = {}
        for r in consistency["results"]:
            for f in r["findings"]:
                if f["needs_explanation"]:
                    requests[f["id"]] = ex.build_request(f, r["traces"].get(f["trace_id"]))
        keys = {fid: ex.sha256(req) for fid, req in requests.items()}

        # 무엇이 최신인지 정하는 일과 그 결과를 표시하는 일을 한 트랜잭션에 둔다. 나뉘면 그 틈에 옛 넘김이 끼어든다
        with self.pool.connection() as conn, conn.transaction():
            conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (job_id,))
            own = conn.execute("SELECT state, version FROM judge.handoff_state WHERE job_id = %s AND handoff_seq = %s", (job_id, seq)).fetchone()
            if own and own["state"] in ("완료", "건너뜀"):
                return own["version"]  # 이미 끝난 넘김을 늦게 다시 처리한 경우
            latest = self._latest(conn, job_id)
            newer = conn.execute("SELECT 1 FROM judge.handoff_state WHERE job_id = %s AND handoff_seq > %s AND state = '완료' LIMIT 1",
                                 (job_id, seq)).fetchone()
            if newer or (latest and latest["handoff_seq"] > seq):
                version = None
            elif latest and latest["judge_key"] == key:
                version = latest["version"]  # 값이 그대로면 새 판정 버전을 만들지 않는다 (확인만 한 넘김②)
            else:
                version = (latest["version"] if latest else 0) + 1
                before = {f["id"]: f for f in _findings(latest["consistency"])} if latest else {}
                changed = {f["id"] for f in _findings(consistency) if f["id"] in before
                           and _judgment_fingerprint(f) != _judgment_fingerprint(before[f["id"]])}
                changed |= ({f["id"] for f in _findings(consistency)} ^ set(before)) if before else set()
                conn.execute(
                    """INSERT INTO judge.judgment (job_id, version, handoff_seq, judge_key, consistency, explain_keys, changed_findings)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                    (job_id, version, seq, key, Jsonb(consistency), Jsonb(keys), Jsonb(sorted(changed))))
                for fid, req in requests.items():
                    conn.execute("INSERT INTO judge.explanation (finding_id, input_sha256, request) VALUES (%s, %s, %s) "
                                 "ON CONFLICT DO NOTHING", (fid, keys[fid], Jsonb(req)))
            conn.execute("UPDATE judge.handoff_state SET state = %s, version = %s, finished_at = now() WHERE job_id = %s AND handoff_seq = %s",
                         ("건너뜀" if version is None else "완료", version, job_id, seq))
        return version

    @staticmethod
    def _latest(conn, job_id: str) -> dict | None:
        return conn.execute("SELECT * FROM judge.judgment WHERE job_id = %s ORDER BY version DESC LIMIT 1", (job_id,)).fetchone()

    # ── 설명 ──────────────────────────────────────────────────────────

    def claim_explanation(self) -> dict | None:
        with self.pool.connection() as conn:
            return conn.execute(
                """UPDATE judge.explanation SET state = '작성 중', taken_at = now()
                   WHERE (finding_id, input_sha256) = (
                     SELECT finding_id, input_sha256 FROM judge.explanation
                     WHERE state = '대기' OR (state = '작성 중' AND taken_at < now() - %s)
                     ORDER BY created_at, finding_id FOR UPDATE SKIP LOCKED LIMIT 1)
                   RETURNING finding_id, input_sha256, request, taken_at""", (EXPLAIN_LEASE,)).fetchone()

    def process_explanation(self, row: dict) -> None:
        try:
            if self.llm is None:
                body = ex.generate(row["request"], None)
            else:
                with self.gate.slot_sync("explain"):
                    body = ex.generate(row["request"], self.llm)
            self._store_explanation(row, body)
        except Exception as e:  # 창구 장애, 이상한 응답, 저장 못 할 글자(NUL 등)로 설명이 '작성 중'에 멈추면 안 된다
            body = ex.generate(row["request"], None)
            print(f"설명 저장 실패: {type(e).__name__}: {e}")
            body["check_failures"].append(type(e).__name__)  # 화면 API로 나간다. 원문의 서버 주소는 서버 기록에만 남긴다
            self._store_explanation(row, body)

    def _store_explanation(self, row: dict, body: dict) -> None:
        stored = {"contract": "explanation/1", "finding_id": row["finding_id"], "input_sha256": row["input_sha256"],
                  "created_at": _iso(datetime.now(KST)), **body}
        # 임대가 끝나 다른 작업자가 다시 잡은 줄은 늦게 온 쪽이 덮어쓰지 못한다
        with self.pool.connection() as conn:
            conn.execute("UPDATE judge.explanation SET state = '완료', body = %s "
                         "WHERE finding_id = %s AND input_sha256 = %s AND state = '작성 중' AND taken_at = %s",
                         (Jsonb(stored), row["finding_id"], row["input_sha256"], row["taken_at"]))

    # ── 화면이 읽는 것 ─────────────────────────────────────────────────

    def status(self, job_id: str) -> dict:
        with self.pool.connection() as conn:
            head = conn.execute("SELECT handoff_seq FROM extract.handoff WHERE job_id = %s ORDER BY handoff_seq DESC LIMIT 1",
                                (job_id,)).fetchone()
            base = {"job_id": job_id, "latest_version": None, "pending_handoff": None, "saved_snapshot": None,
                    "explanations": {"done": 0, "total": 0}, "unreviewed": 0, "error": None}
            if not head:
                return {**base, "state": "판정 없음"}
            seq = head["handoff_seq"]
            st = conn.execute("SELECT state, attempts, error, retryable FROM judge.handoff_state WHERE job_id = %s AND handoff_seq = %s",
                              (job_id, seq)).fetchone()
            latest = self._latest(conn, job_id)
            snap = conn.execute("SELECT max(snapshot_no) AS n FROM judge.snapshot WHERE job_id = %s", (job_id,)).fetchone()["n"]
            out = {**base, "saved_snapshot": snap, "unreviewed": 0}
            if latest:
                keys = latest["explain_keys"]
                done = conn.execute(
                    """SELECT count(*) AS n FROM judge.explanation e
                       JOIN jsonb_each_text(%s) k ON k.key = e.finding_id AND k.value = e.input_sha256
                       WHERE e.state = '완료'""", (Jsonb(keys),)).fetchone()["n"]
                unreviewed, _ = self._review_counts(_findings(latest["consistency"]), self._events(conn, job_id))
                out.update(latest_version=latest["version"], explanations={"done": done, "total": len(keys)},
                           unreviewed=len(unreviewed))
        if st and st["state"] == "완료":
            return {**out, "state": "판정 있음"}
        out["pending_handoff"] = seq
        if st and st["state"] == "실패" and (st["attempts"] >= MAX_ATTEMPTS or st["retryable"]):
            return {**out, "state": "판정 실패", "error": st["error"]}
        return {**out, "state": "판정 중"}

    def _job_or_404(self, conn, job_id: str, version: int | None = None) -> dict:
        if version is None:
            row = self._latest(conn, job_id)
        else:
            row = conn.execute("SELECT * FROM judge.judgment WHERE job_id = %s AND version = %s", (job_id, version)).fetchone()
        if not row:
            raise NotFound(f"판정이 없음: {job_id}" + (f" 버전 {version}" if version else ""))
        return row

    @staticmethod
    def _handoff(conn, job_id: str, seq: int | None = None) -> dict:
        sql = "SELECT payload_json FROM extract.handoff WHERE job_id = %s "
        row = (conn.execute(sql + "AND handoff_seq = %s", (job_id, seq)) if seq else
               conn.execute(sql + "ORDER BY handoff_seq DESC LIMIT 1", (job_id,))).fetchone()
        if not row:
            raise NotFound(f"넘김 기록이 없음: {job_id}")
        return row["payload_json"]

    @classmethod
    def _handoff_of_version(cls, conn, judgment: dict) -> dict:
        """그 판정 버전과 같은 값을 가진 가장 새 넘김. 값을 확인만 한 넘김은 새 버전을 만들지 않고, 아직 판정 전인 넘김은 포함하지 않는다.
        화면과 리포트가 추출값과 판정을 서로 다른 넘김에서 읽지 않게 한다."""
        row = conn.execute("SELECT max(handoff_seq) AS seq FROM judge.handoff_state WHERE job_id = %s AND version = %s AND state = '완료'",
                           (judgment["job_id"], judgment["version"])).fetchone()
        return cls._handoff(conn, judgment["job_id"], row["seq"] or judgment["handoff_seq"])

    @staticmethod
    def _events(conn, job_id: str, upto: int | None = None) -> list[dict]:
        if upto is None:
            return conn.execute("SELECT * FROM judge.review_event WHERE job_id = %s ORDER BY event_id", (job_id,)).fetchall()
        return conn.execute("SELECT * FROM judge.review_event WHERE job_id = %s AND event_id <= %s ORDER BY event_id",
                            (job_id, upto)).fetchall()

    @staticmethod
    def _review_states(events: list[dict], findings: list[dict]) -> dict:
        current = {f["id"]: _judgment_fingerprint(f) for f in findings}
        out: dict[str, dict] = {}
        for e in events:
            s = out.setdefault(e["finding_id"], {"status": "미검토", "comment": None, "reviewer": None, "at": None,
                                                 "history_count": 0, "stale": False, "notes": [], "_sha": None})
            s["history_count"] += 1
            s["last_event_id"] = e["event_id"]
            if e["action"] == "되돌리기":
                s.update(status="미검토", comment=None, reviewer=e["reviewer"], at=_iso(e["at"]), _sha=None)
            elif e["action"] == "의견":  # 처리 상태와 stale 을 바꾸지 않는다 (5-api status). 처리한 항목은 승인 사유·처리자도 지우지 않고 이력에만 남긴다
                # 화면이 더한 의견을 모두 보이게 쌓는다 (오래된 것부터)
                s["notes"].append({"comment": e["comment"], "reviewer": e["reviewer"], "at": _iso(e["at"])})
                if s["status"] == "미검토":
                    s.update(comment=e["comment"], reviewer=e["reviewer"], at=_iso(e["at"]))
            else:
                s.update(status=e["action"], comment=e["comment"], reviewer=e["reviewer"], at=_iso(e["at"]), _sha=e["finding_sha"])
        for fid, s in out.items():
            sha = s.pop("_sha")
            s["stale"] = s["status"] != "미검토" and sha != current.get(fid)
        return out

    def view(self, job_id: str, version: int | None = None) -> dict:
        with self.pool.connection() as conn:
            row = self._job_or_404(conn, job_id, version)
            latest = self._latest(conn, job_id)["version"]
            handoff = self._handoff_of_version(conn, row)
            events = self._events(conn, job_id)
            keys = row["explain_keys"]
            rows = conn.execute(
                """SELECT e.finding_id, e.state, e.body FROM judge.explanation e
                   JOIN jsonb_each_text(%s) k ON k.key = e.finding_id AND k.value = e.input_sha256""", (Jsonb(keys),)).fetchall()
        done = {r["finding_id"]: r for r in rows}
        explanations = {}
        for fid in keys:
            r = done.get(fid)
            if r and r["state"] == "완료":
                b = r["body"]
                explanations[fid] = {"status": "완료", "by": b["by"], "checked": b["checked"], "summary": b["summary"],
                                     "reasons": b["reasons"], "basis": b["basis"]}
            else:
                explanations[fid] = {"status": "작성 중"}
        return {"job_id": job_id, "version": row["version"], "is_latest": row["version"] == latest,
                "handoff_seq": handoff["handoff_seq"], "judged_at": _iso(row["judged_at"]), "consistency": row["consistency"],
                "explanations": explanations, "reviews": self._review_states(events, _findings(row["consistency"])),
                "field_status": handoff["field_status"], "display": view_display(row["consistency"])}

    def versions(self, job_id: str) -> list[dict]:
        with self.pool.connection() as conn:
            rows = conn.execute("SELECT version, handoff_seq, judged_at, consistency, changed_findings FROM judge.judgment "
                                "WHERE job_id = %s ORDER BY version DESC", (job_id,)).fetchall()
        if not rows:
            raise NotFound(f"판정이 없음: {job_id}")
        return [{"version": r["version"], "handoff_seq": r["handoff_seq"], "judged_at": _iso(r["judged_at"]),
                 "summary": _count(_findings(r["consistency"])), "changed_findings": r["changed_findings"]} for r in rows]

    # ── 검토·저장 ──────────────────────────────────────────────────────

    @staticmethod
    def _check_current(conn, job_id: str, latest: dict, seen_version: int) -> int:
        """옛 화면을 보고 확정하거나, 고친 값을 판정하기 전에 저장해 추출값과 판정이 어긋나는 일을 막는다. 반환: 확인한 최신 넘김 번호."""
        head = conn.execute(
            """SELECT h.handoff_seq, s.state FROM extract.handoff h
               LEFT JOIN judge.handoff_state s ON s.job_id = h.job_id AND s.handoff_seq = h.handoff_seq
               WHERE h.job_id = %s ORDER BY h.handoff_seq DESC LIMIT 1""", (job_id,)).fetchone()
        if head and head["state"] != "완료":
            raise Conflict(latest["version"], head["handoff_seq"])
        if seen_version != latest["version"]:
            raise Conflict(latest["version"])
        return head["handoff_seq"] if head else latest["handoff_seq"]

    def _record_review(self, job_id, finding_id, action, comment, reviewer, seen_version, seen_event_id=NOT_SENT) -> tuple[dict, dict]:
        with self.pool.connection() as conn, conn.transaction():
            conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (job_id,))
            latest = self._job_or_404(conn, job_id)
            self._check_current(conn, job_id, latest, seen_version)
            findings = _findings(latest["consistency"])
            f = next((x for x in findings if x["id"] == finding_id), None)
            if f is None:
                raise NotFound(f"이 판정 버전에 없는 항목: {finding_id}")
            if f["verdict"] not in ACTION_VERDICTS.get(action, VERDICTS):
                raise InvalidAction(f"{f['verdict']} 판정에는 '{action}'을 쓸 수 없음")
            events = self._events(conn, job_id)
            if seen_event_id is not NOT_SENT:  # 같은 버전을 보던 다른 사람의 처리를 모르고 덮지 않게 한다. None = 기록이 없는 것을 봤음
                last = next((e["event_id"] for e in reversed(events) if e["finding_id"] == finding_id), None)
                if last != seen_event_id:
                    raise Conflict(latest["version"], message=f"다른 검토자가 먼저 처리함 (이벤트 {last})")
            event = conn.execute(
                """INSERT INTO judge.review_event (job_id, finding_id, action, comment, reviewer, version, verdict_seen, finding_sha)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING *""",
                (job_id, finding_id, action, comment, reviewer, latest["version"], f["verdict"], _judgment_fingerprint(f))).fetchone()
            return event, self._review_states(events + [event], findings)[finding_id]

    def add_review(self, job_id: str, finding_id: str, action: str, comment: str | None, reviewer: str, seen_version: int,
                   seen_event_id=NOT_SENT) -> dict:
        return self._record_review(job_id, finding_id, action, comment, reviewer, seen_version, seen_event_id)[1]

    def add_review_event(self, job_id: str, finding_id: str, action: str, comment: str | None, reviewer: str, seen_version: int,
                         seen_event_id=NOT_SENT) -> dict:
        """화면 응답: 쌓인 이벤트 한 건 (5-api review_event)."""
        e = self._record_review(job_id, finding_id, action, comment, reviewer, seen_version, seen_event_id)[0]
        return {"event_id": e["event_id"], "job_id": e["job_id"], "finding_id": e["finding_id"], "action": e["action"], "comment": e["comment"],
                "reviewer": e["reviewer"], "at": _iso(e["at"]), "version": e["version"], "verdict_seen": e["verdict_seen"]}

    def history(self, job_id: str) -> list[dict]:
        """최근 것부터. ref.in_latest 가 false 면 화면은 과거 버전 항목임을 밝히고 다른 판정에 잇지 않는다."""
        with self.pool.connection() as conn:
            events = self._events(conn, job_id)
            info = {}
            for v in sorted({e["version"] for e in events}):
                info.update({f["id"]: f for f in _findings(self._job_or_404(conn, job_id, v)["consistency"])})
            latest = self._latest(conn, job_id)
            snaps = self.snapshots(conn, job_id)
        current = {f["id"] for f in _findings(latest["consistency"])} if latest else set()
        rows = [((_iso(e["at"]), e["event_id"]), {
            "at": _iso(e["at"]), "reviewer": e["reviewer"], "area": f"{info[e['finding_id']]['section']}항", "target": info[e["finding_id"]]["label"],
            "action": e["action"], "detail": e["verdict_seen"], "comment": e["comment"],
            "ref": {"finding_id": e["finding_id"], "version": e["version"], "in_latest": e["finding_id"] in current}}) for e in events]
        rows += [((s["saved_at"], (s["last_review_event_id"] or 0) + 0.5), {
            "at": s["saved_at"], "reviewer": s["saved_by"], "area": "저장", "target": f"저장본 {s['snapshot_no']}", "action": "저장",
            "detail": f"판정 버전 {s['version']}", "comment": s["note"], "ref": {"snapshot_no": s["snapshot_no"]}}) for s in snaps]
        return [r for _, r in sorted(rows, key=lambda x: x[0], reverse=True)]

    def _review_counts(self, findings, events) -> tuple[list[str], dict]:
        states = self._review_states(events, findings)
        by_status: dict[str, int] = {}
        unreviewed = []
        for f in findings:
            state = states.get(f["id"], {})
            status = state.get("status", "미검토")
            # 검토한 뒤 판정이 바뀌어 지금 판정이 일치가 아니면 처리하지 않은 것으로 센다
            if f["verdict"] in NEEDS_REVIEW and (status == "미검토" or state.get("stale")):
                unreviewed.append(f["id"])
            elif status != "미검토" and not state.get("stale"):  # 판정이 바뀐 처리는 지금 판정의 처리로 세지 않는다
                by_status[status] = by_status.get(status, 0) + 1
        return unreviewed, by_status

    def _counts(self, findings, events, handoff) -> dict:
        unreviewed, by_status = self._review_counts(findings, events)
        values = value_counts(handoff)
        return {"unreviewed": unreviewed, "by_status": by_status, "values": values,
                "snapshot": {"findings": sum(f["verdict"] in JUDGED for f in findings), "미검토": len(unreviewed),
                             **{k: by_status.get(k, 0) for k in ("불일치 확정", "예외 승인", "확인")},
                             "미검수 칸": values["model_as_is"]}}

    def save_snapshot(self, job_id: str, reviewer: str, seen_version: int, note: str | None) -> dict:
        with self.pool.connection() as conn, conn.transaction():
            conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (job_id,))
            latest = self._job_or_404(conn, job_id)
            # 확인한 번호로 읽는다. A의 넘김 쓰기는 이 잠금 밖이라 다시 "최신"을 읽으면 판정 전 값이 끼어들 수 있다
            seq = self._check_current(conn, job_id, latest, seen_version)
            events = self._events(conn, job_id)
            handoff = self._handoff(conn, job_id, seq)
            counts = self._counts(_findings(latest["consistency"]), events, handoff)["snapshot"]
            no = conn.execute("SELECT coalesce(max(snapshot_no), 0) + 1 AS n FROM judge.snapshot WHERE job_id = %s", (job_id,)).fetchone()["n"]
            row = conn.execute(
                """INSERT INTO judge.snapshot (job_id, snapshot_no, handoff_seq, version, last_review_event_id, counts, saved_by, note)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING *""",
                (job_id, no, handoff["handoff_seq"], latest["version"], events[-1]["event_id"] if events else None, Jsonb(counts), reviewer, note)).fetchone()
        return _snapshot(row)

    def snapshots(self, conn, job_id: str) -> list[dict]:
        rows = conn.execute("SELECT * FROM judge.snapshot WHERE job_id = %s ORDER BY snapshot_no DESC", (job_id,)).fetchall()
        return [_snapshot(r) for r in rows]

    def save_overview(self, job_id: str) -> dict:
        with self.pool.connection() as conn:
            latest = self._job_or_404(conn, job_id)
            # 저장본을 처리 기록보다 먼저 읽는다. 그 사이 다른 사람이 처리하고 저장해도 거짓 "저장 뒤 바뀜"이 나오지 않는다
            snaps = self.snapshots(conn, job_id)
            events = self._events(conn, job_id)
            handoff = self._handoff_of_version(conn, latest)
        findings = _findings(latest["consistency"])
        c = self._counts(findings, events, handoff)
        reviews = {k: c["by_status"].get(k, 0) for k in ("불일치 확정", "예외 승인", "확인")}
        return {"job_id": job_id, "version": latest["version"], "handoff_seq": handoff["handoff_seq"],
                "verdicts": {"total": _count(findings),
                             "by_section": {s: _count([f for f in findings if f["section"] == s]) for s in ("2", "15")}},
                "reviews": {"미검토": len(c["unreviewed"]), **reviews, "unreviewed_ids": c["unreviewed"]},
                "values": c["values"], "snapshots": snaps,
                # 저장본의 같은 칸과 비교해 저장 뒤 더한 검토 처리를 알린다 (판정 버전·넘김 번호만으로는 모른다)
                "last_review_event_id": events[-1]["event_id"] if events else None}

    def _grade_of(self, conn, job_id: str, latest: dict, snaps: list[dict]) -> str:
        return _grade(snaps, latest["version"], self._handoff(conn, job_id)["handoff_seq"], self._events(conn, job_id),
                      value_counts(self._handoff_of_version(conn, latest)))

    def summary(self, job_ids: list[str]) -> list[dict]:
        out = []
        for job_id in job_ids:
            st = self.status(job_id)
            item = {"job_id": job_id, "state": st["state"], "latest_version": st["latest_version"], "unreviewed": st["unreviewed"],
                    "saved_snapshot": st["saved_snapshot"], "saved_at": None, "data_grade": "실버"}
            if st["latest_version"]:
                with self.pool.connection() as conn:
                    snaps = self.snapshots(conn, job_id)
                    item["data_grade"] = self._grade_of(conn, job_id, self._latest(conn, job_id), snaps)
                item["saved_at"] = snaps[0]["saved_at"] if snaps else None
            out.append(item)
        return out

    def report_data(self, job_id: str, snapshot_no: int | None) -> dict:
        """리포트 재료. 저장본 번호를 주면 그 순간의 넘김 기록·판정·검토만 읽는다."""
        with self.pool.connection() as conn:
            snap = None
            if snapshot_no is not None:
                row = conn.execute("SELECT * FROM judge.snapshot WHERE job_id = %s AND snapshot_no = %s", (job_id, snapshot_no)).fetchone()
                if not row:
                    raise NotFound(f"저장본이 없음: {job_id} {snapshot_no}")
                snap = _snapshot(row)
            judgment = self._job_or_404(conn, job_id, snap["version"] if snap else None)
            handoff = self._handoff(conn, job_id, snap["handoff_seq"]) if snap else self._handoff_of_version(conn, judgment)
            if snap and snap["last_review_event_id"] is None:
                events = []
            else:
                events = self._events(conn, job_id, snap["last_review_event_id"] if snap else None)
        findings = _findings(judgment["consistency"])
        return {"job_id": job_id, "snapshot": snap, "version": judgment["version"], "handoff": handoff,
                "counts": self._counts(findings, events, handoff)["snapshot"],
                "consistency": judgment["consistency"], "reviews": self._review_states(events, _findings(judgment["consistency"])),
                "events": [{"event_id": e["event_id"], "finding_id": e["finding_id"], "action": e["action"], "comment": e["comment"],
                            "reviewer": e["reviewer"], "at": _iso(e["at"]), "version": e["version"], "verdict_seen": e["verdict_seen"]}
                           for e in events]}

    def put_test_handoff(self, body: dict) -> None:
        """시험용: A 없이 넘김 기록을 넣는다 (파트 B 설계 6절). B 계정은 이 표를 쓸 수 없어 관리자 계정을 쓴다. 운영에서는 API가 꺼져 있다."""
        with psycopg.connect(**{**pg_kwargs("admin"), "dbname": self.pool.kwargs["dbname"]}) as conn:
            insert_handoff(conn, body)

    def close(self):
        if self._alive:
            self._alive.close()
        self.pool.close()

    # ── 작업자 한 걸음 ────────────────────────────────────────────────

    def judge_step(self) -> bool:
        body = self.claim_handoff()
        if body:
            self.process_handoff(body)
        return bool(body)

    def explain_step(self) -> bool:
        row = self.claim_explanation()
        if row:
            self.process_explanation(row)
        return bool(row)

    def run_once(self) -> bool:
        return any([self.judge_step(), self.explain_step()])

    def drain(self, limit: int = 2000) -> None:
        for _ in range(limit):
            if not self.run_once():
                return


def _count(findings: list[dict]) -> dict:
    return {v: sum(f["verdict"] == v for f in findings) for v in VERDICTS}


def _snapshot(r: dict) -> dict:
    return {"contract": "snapshot/1", "job_id": r["job_id"], "snapshot_no": r["snapshot_no"], "handoff_seq": r["handoff_seq"],
            "version": r["version"], "last_review_event_id": r["last_review_event_id"], "counts": r["counts"],
            "saved_by": r["saved_by"], "saved_at": _iso(r["saved_at"]), "note": r["note"]}


def _grade(snaps: list[dict], version: int, head_seq: int, events: list[dict], values: dict) -> str:
    """골드 = 최신 저장본이 지금의 값·판정·검토 기록을 그대로 담고, 미검토·미검수 칸이 없음. 저장 뒤 무엇이든 바뀌면 다시 저장할 때까지 실버다."""
    if not snaps or values["fields_total"] == 0:
        return "실버"
    last = snaps[0]
    current = (last["version"] == version and last["handoff_seq"] == head_seq
               and last["last_review_event_id"] == (events[-1]["event_id"] if events else None))
    return "골드" if current and last["counts"]["미검토"] == 0 and last["counts"]["미검수 칸"] == 0 else "실버"


def insert_handoff(conn, body: dict) -> None:
    """넘김 기록 한 건을 A2 표 모양으로 넣는다 (시험·개발용). 실제 표는 A2가 쓴다."""
    conn.execute("""INSERT INTO extract.handoff (job_id, handoff_seq, reason, as_of, extraction_sha256, payload_json, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                 (body["job_id"], body["handoff_seq"], body.get("reason") or "extraction_done", body.get("as_of") or "2026-11-03",
                  body.get("extraction_sha256") or "0" * 64, Jsonb(body), body.get("created_at") or datetime.now(timezone.utc)))


def value_counts(handoff: dict) -> dict:
    """칸 수는 A2가 넘김 기록의 fields_total 로 준다 (검수 보기와 같은 기준). 같은 칸은 마지막 표시만 센다."""
    marks = {(m["msds_index"], m["field"]): m["status"] for m in handoff.get("field_status") or []}
    status = list(marks.values())
    confirmed, edited = status.count("확인함"), status.count("수정됨")
    total = handoff.get("fields_total") or 0  # A2 사본 계약에서 빠진 적이 있다(2026-11-03). 없으면 골드가 될 수 없다
    as_is = max(total - len(marks), 0)
    state = "미검수" if not marks or total == 0 else "완료" if as_is == 0 else "일부"
    return {"state": state, "model_as_is": as_is, "confirmed": confirmed, "edited": edited, "fields_total": total}
