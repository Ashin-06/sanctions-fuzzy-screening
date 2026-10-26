"""Every screening and every analyst decision on it, kept in the database (see db.py) as
evidence of what was screened, against which list version, and who cleared or confirmed it."""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.engine import Engine

STATUSES = ("open", "cleared", "confirmed")  # cleared = false positive, confirmed = true match


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class ScreeningLog:
    def __init__(self, engine: Engine):
        self.db = engine
        self._lock = threading.Lock()

    def record(self, user: str, result: dict, list_version: str) -> str:
        sid = uuid.uuid4().hex
        best = result.get("best_watchlist_match") or {}
        # Only hits need a human; a CLEAR is kept as evidence and starts closed.
        status = "open" if result["decision"] != "CLEAR" else "cleared"
        with self._lock, self.db.begin() as c:
            c.execute(text("INSERT INTO screenings (id, created_at, requested_by, query_id, name, decision, hit_source, "
                           "sdn_id, list_version, status, result) VALUES (:i, :t, :u, :q, :n, :d, :h, :s, :v, :st, :r)"),
                      {"i": sid, "t": _now(), "u": user, "q": result["query_id"], "n": result["query_name"],
                       "d": result["decision"], "h": result["hit_source"], "s": best.get("sdn_id"), "v": list_version,
                       "st": status, "r": json.dumps(result)})
        return sid

    @staticmethod
    def _row(r) -> dict:
        return {"id": r.id, "created_at": r.created_at, "requested_by": r.requested_by, "query_id": r.query_id,
                "decision": r.decision, "hit_source": r.hit_source, "sdn_id": r.sdn_id, "list_version": r.list_version,
                "status": r.status, "result": json.loads(r.result)}

    def list(self, status: str | None = None, decision: str | None = None, limit: int = 100) -> list[dict]:
        sql, args = "SELECT * FROM screenings WHERE 1 = 1", {"n": limit}
        if status:
            sql, args["st"] = sql + " AND status = :st", status
        if decision:
            sql, args["d"] = sql + " AND decision = :d", decision
        with self.db.connect() as c:
            return [self._row(r) for r in c.execute(text(sql + " ORDER BY created_at DESC, id LIMIT :n"), args)]

    def get(self, sid: str) -> dict | None:
        with self.db.connect() as c:
            r = c.execute(text("SELECT * FROM screenings WHERE id = :i"), {"i": sid}).first()
            if r is None:
                return None
            reviews = c.execute(text("SELECT reviewed_at, reviewer, status, note FROM screening_reviews "
                                     "WHERE screening_id = :i ORDER BY reviewed_at"), {"i": sid}).mappings().all()
        return {**self._row(r), "reviews": [dict(x) for x in reviews]}

    def review(self, sid: str, reviewer: str, status: str, note: str) -> dict | None:
        if status not in STATUSES:
            raise ValueError(f"status must be one of {STATUSES}")
        with self._lock, self.db.begin() as c:
            if c.execute(text("UPDATE screenings SET status = :s WHERE id = :i"), {"s": status, "i": sid}).rowcount == 0:
                return None
            c.execute(text("INSERT INTO screening_reviews (screening_id, reviewed_at, reviewer, status, note) "
                           "VALUES (:i, :t, :r, :s, :n)"), {"i": sid, "t": _now(), "r": reviewer, "s": status, "n": note})
        return self.get(sid)
