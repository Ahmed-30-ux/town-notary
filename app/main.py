"""Town Notary — timestamping, verification & reputation for AI agents."""
from __future__ import annotations

import hmac
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

_is_vercel = bool(os.environ.get("VERCEL"))
DB_PATH = Path("/tmp/notary.db") if _is_vercel else Path(__file__).resolve().parent.parent / "notary.db"
SECRET = os.environ.get("TOWN_NOTARY_SECRET", "town-notary-dev-secret-change-in-prod")


def get_db():
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    db.execute("""CREATE TABLE IF NOT EXISTS notary (
        id TEXT PRIMARY KEY, agent_id TEXT NOT NULL, data_hash TEXT NOT NULL,
        data_type TEXT DEFAULT 'text', metadata TEXT DEFAULT '{}',
        timestamp TEXT NOT NULL, signature TEXT
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS reputation (
        id TEXT PRIMARY KEY, record_id TEXT NOT NULL, reporter_id TEXT NOT NULL,
        status TEXT NOT NULL, timestamp TEXT NOT NULL
    )""")
    for col in ("data_hash", "agent_id", "record_id"):
        db.execute(f"CREATE INDEX IF NOT EXISTS idx_{col} ON notary({col})")
    db.commit()
    return db


def _sign(payload: str) -> str:
    return hmac.new(SECRET.encode(), payload.encode(), sha256).hexdigest()


class NotarizeRequest(BaseModel):
    agent_id: str
    data: str
    data_type: str = "text"
    metadata: dict = {}


class ReportRequest(BaseModel):
    reporter_id: str
    status: str  # "fulfilled" | "disputed"


app = FastAPI(title="Town Notary", version="0.2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
def startup():
    get_db().close()


@app.get("/health")
def health():
    return {"status": "ok", "service": "town-notary", "version": "0.2.0"}


# ── Notarize ──────────────────────────────────────────────────────────
@app.post("/notarize")
def notarize(req: NotarizeRequest):
    record_id = str(uuid.uuid4())
    data_hash = sha256(req.data.encode()).hexdigest()
    ts = datetime.now(timezone.utc).isoformat()
    to_sign = f"{record_id}:{req.agent_id}:{data_hash}:{ts}"
    signature = _sign(to_sign)
    db = get_db()
    db.execute(
        "INSERT INTO notary (id, agent_id, data_hash, data_type, metadata, timestamp, signature) VALUES (?,?,?,?,?,?,?)",
        (record_id, req.agent_id, data_hash, req.data_type, json.dumps(req.metadata), ts, signature),
    )
    db.commit()
    db.close()
    return {
        "id": record_id,
        "data_hash": data_hash,
        "timestamp": ts,
        "signature": signature,
        "verify_url": f"/verify/{record_id}",
    }


# ── Verify ────────────────────────────────────────────────────────────
@app.get("/verify/{record_id}")
def verify(record_id: str):
    db = get_db()
    row = db.execute("SELECT * FROM notary WHERE id = ?", (record_id,)).fetchone()
    if not row:
        db.close()
        return {"exists": False, "record": None}
    db.close()
    return {
        "exists": True,
        "record": {
            "id": row["id"],
            "agent_id": row["agent_id"],
            "data_hash": row["data_hash"],
            "data_type": row["data_type"],
            "metadata": json.loads(row["metadata"]),
            "timestamp": row["timestamp"],
            "signature": row["signature"],
        },
    }


# ── Search ────────────────────────────────────────────────────────────
@app.get("/search")
def search(agent_id: str | None = None, hash: str | None = None, limit: int = 20):
    db = get_db()
    if agent_id:
        rows = db.execute("SELECT * FROM notary WHERE agent_id = ? ORDER BY timestamp DESC LIMIT ?", (agent_id, limit)).fetchall()
    elif hash:
        rows = db.execute("SELECT * FROM notary WHERE data_hash = ? ORDER BY timestamp DESC LIMIT ?", (hash, limit)).fetchall()
    else:
        rows = db.execute("SELECT * FROM notary ORDER BY timestamp DESC LIMIT ?", (limit,)).fetchall()
    db.close()
    return {"records": [{ "id": r["id"], "agent_id": r["agent_id"], "data_hash": r["data_hash"],
        "data_type": r["data_type"], "metadata": json.loads(r["metadata"]),
        "timestamp": r["timestamp"], "signature": r["signature"] } for r in rows]}


# ── Report fulfillment / dispute ──────────────────────────────────────
@app.post("/report/{record_id}")
def report(record_id: str, req: ReportRequest):
    if req.status not in ("fulfilled", "disputed"):
        raise HTTPException(400, "status must be 'fulfilled' or 'disputed'")
    db = get_db()
    row = db.execute("SELECT id FROM notary WHERE id = ?", (record_id,)).fetchone()
    if not row:
        db.close()
        raise HTTPException(404, "Record not found")
    report_id = str(uuid.uuid4())
    ts = datetime.now(timezone.utc).isoformat()
    db.execute("INSERT INTO reputation (id, record_id, reporter_id, status, timestamp) VALUES (?,?,?,?,?)",
               (report_id, record_id, req.reporter_id, req.status, ts))
    db.commit()
    db.close()
    return {"status": "ok", "report_id": report_id, "record_id": record_id, "resolution": req.status}


# ── Reputation score ──────────────────────────────────────────────────
@app.get("/reputation/{agent_id}")
def reputation(agent_id: str):
    db = get_db()
    records = db.execute("SELECT id FROM notary WHERE agent_id = ?", (agent_id,)).fetchall()
    record_ids = tuple(r["id"] for r in records) or ("__none__",)
    placeholders = ",".join("?" for _ in record_ids)
    reports = db.execute(
        f"SELECT status FROM reputation WHERE record_id IN ({placeholders})", record_ids
    ).fetchall()
    db.close()
    fulfilled = sum(1 for r in reports if r["status"] == "fulfilled")
    disputed = sum(1 for r in reports if r["status"] == "disputed")
    total = fulfilled + disputed
    score = round(fulfilled / total, 4) if total > 0 else 0.5
    return {"agent_id": agent_id, "score": score, "fulfilled": fulfilled, "disputed": disputed, "total_records": len(records)}


# ── UI Dashboard ──────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
def ui():
    return HTMLResponse(UI_HTML)


UI_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Town Notary</title>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family:-apple-system,BlinkMacSystemFont,sans-serif; background:#0a0a0f; color:#e0e0e0; }
  .container { max-width:960px; margin:0 auto; padding:2rem; }
  h1 { font-size:2rem; background:linear-gradient(135deg,#a78bfa,#60a5fa); -webkit-background-clip:text; -webkit-text-fill-color:transparent; margin-bottom:.5rem; }
  .subtitle { color:#888; margin-bottom:2rem; }
  .card { background:#14141f; border:1px solid #2a2a3a; border-radius:12px; padding:1.5rem; margin-bottom:1.5rem; }
  .card h2 { font-size:1.2rem; margin-bottom:1rem; color:#a78bfa; }
  label { display:block; font-size:.85rem; color:#888; margin-bottom:.3rem; }
  input,textarea,select { width:100%; padding:.6rem; background:#1a1a28; border:1px solid #333; border-radius:8px; color:#e0e0e0; font-size:.9rem; margin-bottom:1rem; }
  textarea { font-family:monospace; resize:vertical; min-height:60px; }
  button { background:#a78bfa; color:#000; border:none; padding:.6rem 1.5rem; border-radius:8px; font-size:.9rem; font-weight:600; cursor:pointer; }
  button:hover { background:#b99dfb; }
  button:disabled { opacity:.5; cursor:not-allowed; }
  pre { background:#1a1a28; padding:1rem; border-radius:8px; overflow-x:auto; font-size:.8rem; margin-top:.5rem; }
  .tabs { display:flex; gap:.5rem; margin-bottom:1.5rem; }
  .tab { padding:.5rem 1rem; border-radius:8px; cursor:pointer; background:#1a1a28; color:#888; }
  .tab.active { background:#a78bfa; color:#000; font-weight:600; }
  .nav { display:flex; gap:1rem; margin-bottom:2rem; }
  .nav a { color:#60a5fa; text-decoration:none; font-size:.85rem; }
  .badge { display:inline-block; padding:.15rem .5rem; border-radius:4px; font-size:.75rem; font-weight:600; }
  .badge.ok { background:#065f46; color:#6ee7b7; }
  .badge.fail { background:#7f1d1d; color:#fca5a5; }
</style>
</head>
<body>
<div class="container">
  <h1>Town Notary</h1>
  <p class="subtitle">Timestamp, verify, and build reputation for AI agent interactions on NANDA Town.</p>

  <div class="nav">
    <a href="#" onclick="showTab('notarize');return false">Notarize</a>
    <a href="#" onclick="showTab('verify');return false">Verify</a>
    <a href="#" onclick="showTab('search');return false">Search</a>
    <a href="#" onclick="showTab('reputation');return false">Reputation</a>
    <a href="#" onclick="showTab('recent');return false">Recent Records</a>
    <a href="/docs" target="_blank">API Docs</a>
  </div>

  <div id="notarize" class="tab-content card">
    <h2>Notarize Data</h2>
    <label>Agent ID</label>
    <input id="n-agent" value="agent-1" placeholder="your-agent-id">
    <label>Data</label>
    <textarea id="n-data" placeholder="Data to notarize">I agree to deliver 100 units at price 50</textarea>
    <label>Data Type</label>
    <input id="n-type" value="agreement">
    <button onclick="notarize()">Notarize</button>
    <pre id="n-result"></pre>
  </div>

  <div id="verify" class="tab-content card" style="display:none">
    <h2>Verify Record</h2>
    <label>Record ID</label>
    <input id="v-id" placeholder="uuid from notarize">
    <button onclick="verify()">Verify</button>
    <pre id="v-result"></pre>
  </div>

  <div id="search" class="tab-content card" style="display:none">
    <h2>Search Records</h2>
    <label>Agent ID (optional)</label>
    <input id="s-agent" placeholder="agent-id">
    <label>Data Hash (optional)</label>
    <input id="s-hash" placeholder="sha256 hex">
    <button onclick="search()">Search</button>
    <pre id="s-result"></pre>
  </div>

  <div id="reputation" class="tab-content card" style="display:none">
    <h2>Agent Reputation</h2>
    <label>Agent ID</label>
    <input id="r-agent" value="agent-1">
    <button onclick="reputation()">Get Score</button>
    <pre id="r-result"></pre>
  </div>

  <div id="recent" class="tab-content card" style="display:none">
    <h2>Recent Records</h2>
    <button onclick="recent()">Refresh</button>
    <pre id="recent-result"></pre>
  </div>
</div>

<script>
const BASE = window.location.origin;
async function api(method, path, body) {
  const opts = { method, headers:{"Content-Type":"application/json"} };
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch(BASE + path, opts);
  return r.ok ? r.json() : { error: r.status + " " + r.statusText, body: await r.text() };
}
function showTab(name) {
  document.querySelectorAll(".tab-content").forEach(t => t.style.display = "none");
  const el = document.getElementById(name);
  if (el) el.style.display = "block";
}
async function notarize() {
  const r = await api("POST", "/notarize", { agent_id: document.getElementById("n-agent").value, data: document.getElementById("n-data").value, data_type: document.getElementById("n-type").value });
  document.getElementById("n-result").textContent = JSON.stringify(r, null, 2);
}
async function verify() {
  const id = document.getElementById("v-id").value;
  const r = await api("GET", "/verify/" + id);
  document.getElementById("v-result").textContent = JSON.stringify(r, null, 2);
}
async function search() {
  const p = new URLSearchParams();
  const a = document.getElementById("s-agent").value;
  const h = document.getElementById("s-hash").value;
  if (a) p.set("agent_id", a);
  if (h) p.set("hash", h);
  const r = await api("GET", "/search?" + p.toString());
  document.getElementById("s-result").textContent = JSON.stringify(r, null, 2);
}
async function reputation() {
  const id = document.getElementById("r-agent").value;
  const r = await api("GET", "/reputation/" + encodeURIComponent(id));
  document.getElementById("r-result").textContent = JSON.stringify(r, null, 2);
}
async function recent() {
  const r = await api("GET", "/search?limit=10");
  document.getElementById("recent-result").textContent = JSON.stringify(r, null, 2);
}
showTab("notarize");
</script>
</body>
</html>"""
