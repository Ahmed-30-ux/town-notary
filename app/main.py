"""Town Notary — timestamping & verification service for NANDA Town agents."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

DB_PATH = Path(__file__).resolve().parent.parent / "notary.db"

app = FastAPI(title="Town Notary", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def get_db():
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    db.execute(
        """CREATE TABLE IF NOT EXISTS notary (
            id TEXT PRIMARY KEY,
            agent_id TEXT NOT NULL,
            data_hash TEXT NOT NULL,
            data_type TEXT DEFAULT 'text',
            metadata TEXT DEFAULT '{}',
            timestamp TEXT NOT NULL,
            signature TEXT
        )"""
    )
    db.execute(
        """CREATE INDEX IF NOT EXISTS idx_hash ON notary(data_hash)"""
    )
    db.execute(
        """CREATE INDEX IF NOT EXISTS idx_agent ON notary(agent_id)"""
    )
    db.commit()
    return db


class NotarizeRequest(BaseModel):
    agent_id: str
    data: str
    data_type: str = "text"
    metadata: dict = {}


class NotarizeResponse(BaseModel):
    id: str
    data_hash: str
    timestamp: str
    verify_url: str


class VerifyResponse(BaseModel):
    exists: bool
    record: dict | None = None


class LookupResponse(BaseModel):
    records: list[dict]


@app.on_event("startup")
def startup():
    get_db().close()


@app.get("/health")
def health():
    return {"status": "ok", "service": "town-notary", "version": "0.1.0"}


@app.post("/notarize", response_model=NotarizeResponse)
def notarize(req: NotarizeRequest):
    record_id = str(uuid.uuid4())
    data_hash = sha256(req.data.encode()).hexdigest()
    timestamp = datetime.now(timezone.utc).isoformat()
    metadata_json = json.dumps(req.metadata)
    db = get_db()
    db.execute(
        "INSERT INTO notary (id, agent_id, data_hash, data_type, metadata, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
        (record_id, req.agent_id, data_hash, req.data_type, metadata_json, timestamp),
    )
    db.commit()
    db.close()
    return NotarizeResponse(
        id=record_id,
        data_hash=data_hash,
        timestamp=timestamp,
        verify_url=f"/verify/{record_id}",
    )


@app.get("/verify/{record_id}", response_model=VerifyResponse)
def verify(record_id: str):
    db = get_db()
    row = db.execute("SELECT * FROM notary WHERE id = ?", (record_id,)).fetchone()
    db.close()
    if not row:
        return VerifyResponse(exists=False, record=None)
    return VerifyResponse(
        exists=True,
        record={
            "id": row["id"],
            "agent_id": row["agent_id"],
            "data_hash": row["data_hash"],
            "data_type": row["data_type"],
            "metadata": json.loads(row["metadata"]),
            "timestamp": row["timestamp"],
        },
    )


@app.get("/search", response_model=LookupResponse)
def search(agent_id: str | None = None, hash: str | None = None, limit: int = 20):
    db = get_db()
    if agent_id:
        rows = db.execute(
            "SELECT * FROM notary WHERE agent_id = ? ORDER BY timestamp DESC LIMIT ?",
            (agent_id, limit),
        ).fetchall()
    elif hash:
        rows = db.execute(
            "SELECT * FROM notary WHERE data_hash = ? ORDER BY timestamp DESC LIMIT ?",
            (hash, limit),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM notary ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
    db.close()
    return LookupResponse(
        records=[
            {
                "id": r["id"],
                "agent_id": r["agent_id"],
                "data_hash": r["data_hash"],
                "data_type": r["data_type"],
                "metadata": json.loads(r["metadata"]),
                "timestamp": r["timestamp"],
            }
            for r in rows
        ]
    )


@app.delete("/revoke/{record_id}")
def revoke(record_id: str):
    db = get_db()
    row = db.execute("SELECT id FROM notary WHERE id = ?", (record_id,)).fetchone()
    if not row:
        db.close()
        raise HTTPException(status_code=404, detail="Record not found")
    db.execute("DELETE FROM notary WHERE id = ?", (record_id,))
    db.commit()
    db.close()
    return {"status": "revoked", "id": record_id}
