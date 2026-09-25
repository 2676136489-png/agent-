import json, sqlite3, urllib.request

TID = "verify-utf8-001"
QUESTION = "请说明 AI Agent 在中文环境下的典型应用场景"

payload = json.dumps(
    {
        "question": QUESTION,
        "max_iterations": 1,
        "max_verify_attempts": 1,
        "thread_id": TID,
    },
    ensure_ascii=False,
).encode("utf-8")

req = urllib.request.Request(
    "http://127.0.0.1:8000/api/graph/research",
    data=payload,
    method="POST",
    headers={"Content-Type": "application/json; charset=utf-8"},
)
try:
    with urllib.request.urlopen(req, timeout=90) as resp:
        ct = resp.headers.get("Content-Type")
        d = json.loads(resp.read().decode("utf-8"))["data"]
        print("POST Content-Type:", ct)
        print("POST question:", d["question"])
except Exception as e:
    print("POST timeout/async still running:", e)

db = r"d:/UserData/Desktop/项目/backend/storage/agent_runs.db"
conn = sqlite3.connect(db)
conn.row_factory = sqlite3.Row
row = conn.execute("SELECT question, status FROM agent_runs WHERE thread_id = ?", (TID,)).fetchone()
if row:
    print("DB question:", row["question"])
    print("DB status:", row["status"])
else:
    print("DB record not found")

req2 = urllib.request.Request("http://127.0.0.1:8000/api/graph/runs?status=awaiting_approval", method="GET")
with urllib.request.urlopen(req2) as resp:
    print("GET Content-Type:", resp.headers.get("Content-Type"))
conn.close()
