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
    for col in ("data_hash", "agent_id"):
        db.execute(f"CREATE INDEX IF NOT EXISTS idx_notary_{col} ON notary({col})")
    db.execute("CREATE INDEX IF NOT EXISTS idx_reputation_record ON reputation(record_id)")
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
from app.ui import UI_HTML

@app.get("/", response_class=HTMLResponse)
def ui():
    return HTMLResponse(UI_HTML)
