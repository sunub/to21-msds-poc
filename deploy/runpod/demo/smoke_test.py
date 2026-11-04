"""체험 서버 끝까지 시험 (외부 HTTPS 주소, 심사위원과 같은 경로).
업로드 → 추출 완료 → 판정으로 넘기기 → 판정·설명 → 저장 → PDF 리포트. 단계별 시간을 잰다.
사용: python deploy/runpod/demo/smoke_test.py <base_url> <pdf> <password>  (브라우저 User-Agent를 보낸다. 기본 urllib는 Cloudflare 1010으로 막힌다)
"""
import base64
import json
import sys
import time
import urllib.parse
import urllib.request

BASE, PDF, PW = sys.argv[1].rstrip("/"), sys.argv[2], sys.argv[3]
AUTH = "Basic " + base64.b64encode(f"to21:{PW}".encode()).decode()


def call(method, path, body=None, ctype="application/json", raw=False):
    data = body if isinstance(body, (bytes, type(None))) else json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=data, method=method, headers={"Authorization": AUTH, "Content-Type": ctype, "User-Agent": "Mozilla/5.0 (to21 e2e)"})
    with urllib.request.urlopen(req, timeout=90) as r:
        out = r.read()
        return out if raw else json.loads(out or b"null")


t0 = time.time()
LIMIT = 900  # 초. 넘으면 실패로 끝낸다
name = PDF.rsplit("/", 1)[-1]
doc = call("POST", "/api/documents?filename=" + urllib.parse.quote(name), open(PDF, "rb").read(), "application/pdf")
did = doc["id"]
print(f"업로드 {did} ({time.time()-t0:.1f}s) reused_from={doc.get('reused_from')}", flush=True)
while True:
    s = call("GET", f"/api/documents/{did}")
    if s["status"] in ("done", "failed", "stopped"):
        break
    if time.time() - t0 > LIMIT:
        sys.exit(f"추출이 {LIMIT}초 안에 안 끝남: {s['status']}")
    time.sleep(5)
t1 = time.time()
val = (call("GET", f"/api/documents/{did}/result") or {}).get("validation") or {}
print(f"추출 {s['status']} ({t1-t0:.1f}s) reused_from={s.get('reused_from')} 검증={val.get('status')} 오류={ {k: v for k, v in val.items() if isinstance(v, int) and v} }", flush=True)
if s["status"] != "done":
    print(json.dumps(s, ensure_ascii=False)[:800]); sys.exit(1)
h = call("POST", f"/api/documents/{did}/to-judgment", {"reviewer": "E2E시험"})
print(f"판정으로 넘기기 seq={h['handoff_seq']}", flush=True)
while True:
    st = call("GET", f"/api/judgments/{did}/status")
    ex = st.get("explanations") or {}
    if st["state"] == "판정 있음" and ex.get("done") == ex.get("total"):
        break
    if st.get("error"):
        print("판정 오류", st["error"]); sys.exit(1)
    if time.time() - t0 > LIMIT:
        sys.exit("판정이 시간 안에 안 끝남")
    time.sleep(5)
t2 = time.time()
print(f"판정·설명 완료 ({t2-t1:.1f}s) 설명 {ex}", flush=True)
ov = call("GET", f"/api/judgments/{did}/save-overview")
snap = call("POST", f"/api/judgments/{did}/snapshots", {"reviewer": "E2E시험", "seen_version": ov["version"], "note": "체험 서버 시험"})
rep = call("POST", f"/api/judgments/{did}/reports", {"format": "pdf", "snapshot_no": snap["snapshot_no"],
           "include": {"regenerated_msds": True, "findings_2": True, "findings_15": True, "components": True, "history": True}}, raw=True)
print(f"저장 #{snap['snapshot_no']}, PDF 리포트 {len(rep)//1024}KB, 판정 {ov['verdicts']['total']}", flush=True)
print(f"전체 {time.time()-t0:.1f}s", flush=True)
