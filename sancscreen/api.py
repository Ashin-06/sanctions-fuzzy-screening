"""
FastAPI REST API for `sancscreen` (Port 8016).

Endpoints (permission in brackets):
- GET  /                 : Service banner (no browser console ships with this API)
- GET  /healthz, /readyz : Liveness and readiness (database reachable, watchlist loaded)
- GET  /metrics          : Prometheus metrics [metrics]
- POST /screen           : Screen a SWIFT / cross-border wire party; every result is logged [screen]
- POST /ubo/check        : Evaluate multi-hop transitive beneficial ownership (OFAC 50% rule) [screen]
- GET  /screenings       : Logged screenings, newest first, by status / decision [read]
- GET  /screenings/{id}  : One screening with its review history [read]
- POST /screenings/{id}/review : Clear (false positive) or confirm (true match) a hit, with a note [review]
- GET  /watchlist        : The loaded watchlist, a page at a time, with IDF weights and UBO entities [read]
- GET  /bench            : The 300-wire benchmark against the built-in demo list [read]

Callers send an API key (X-API-Key or Authorization: Bearer); its role decides the permissions.
SANCSCREEN_SDN_XML points at OFAC's SDN.XML; production refuses to start without it. Without it
(development) the built-in demo list and toy ownership graph are used. Settings: ops.py and
docs/runbook.md.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import asdict
from functools import lru_cache
from typing import Any, Dict, List, Literal, Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from sancscreen import db, ops
from sancscreen.bench import SanctionsScreeningPipeline, run_benchmark
from sancscreen.matcher import ScreeningQuery
from sancscreen.phonetics import normalize_tokens, phonetic_skeleton, transliterate
from sancscreen.store import ScreeningLog
from sancscreen.ubo import UBOGraphEngine

settings = ops.load_settings()
ops.setup_logging(settings.log_level)
SDN_XML = os.environ.get("SANCSCREEN_SDN_XML", "").strip()
if settings.production and not SDN_XML:
    raise ops.ConfigError("production needs SANCSCREEN_SDN_XML: the current OFAC SDN.XML; the built-in list is a demo")


def _pipeline() -> tuple[SanctionsScreeningPipeline, str]:
    """The real list (no ownership graph: the built-in one is a toy) or, in development, the demo list."""
    if not SDN_XML:
        return SanctionsScreeningPipeline(), "demo"
    from sancscreen.realdata import load_sdn_xml

    try:
        data = open(SDN_XML, "rb").read()
        entries = load_sdn_xml(SDN_XML)
    except (OSError, ValueError, SyntaxError) as e:  # ParseError is a SyntaxError; defusedxml refusals are ValueErrors
        raise ops.ConfigError(f"cannot load SANCSCREEN_SDN_XML: {type(e).__name__}") from e
    if not entries:
        raise ops.ConfigError("SANCSCREEN_SDN_XML holds no sdnEntry records")
    return SanctionsScreeningPipeline(watchlist=entries, ubo_engine=UBOGraphEngine()), "sha256:" + hashlib.sha256(data).hexdigest()[:16]


_PIPELINE, LIST_VERSION = _pipeline()
log_store = ScreeningLog(db.connect(settings.database_url))
ops.log.info("watchlist loaded", extra={"fields": {"entries": len(_PIPELINE.watchlist), "version": LIST_VERSION}})

app = FastAPI(
    title="sancscreen — Cross-Script Phonetic & UBO Graph Sanctions Screening Engine",
    version="1.0.0",
    description=(
        "Multi-Script Transliterator (Devanagari/Arabic/Cyrillic), Consonant Phonetic Skeleton, "
        "Order-Invariant IDF-Weighted Bipartite Token Matcher, Secondary ID Resolver, and "
        "OFAC 50%-Rule and Beneficial-Ownership Exposure Graph Engine."
    ),
)
ops.install(app, settings, {"database": lambda: log_store.db.connect().close(),
                            "watchlist": lambda: len(_PIPELINE.watchlist) > 0})


class ScreenRequest(BaseModel):
    query_id: str = Field(default="WIRE-LIVE-001", max_length=64, description="Wire transfer or party reference ID")
    name: str = Field(..., min_length=1, max_length=200, description="Originator, beneficiary, or corporate entity name in any script")
    entity_type: Optional[Literal["individual", "entity", "vessel"]] = Field(
        default=None, description="individual, entity or vessel; omit if unknown (then all entries are compared)"
    )
    dob: Optional[str] = Field(default=None, max_length=10, pattern=r"^\d{4}(-\d{2}-\d{2})?$", description="Date of Birth (YYYY-MM-DD or YYYY)")
    country: Optional[str] = Field(default=None, pattern=r"^[A-Za-z]{2}$", description="2-letter ISO Country / Nationality code")
    identifier: Optional[str] = Field(default=None, max_length=64, description="Passport, National ID, BIC, or LEI")
    amount_usd: float = Field(default=50000.0, ge=0, le=1e12, allow_inf_nan=False, description="Transaction amount in USD")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of top SDN candidates to return")


class UBOCheckRequest(BaseModel):
    entity: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Target company name or UBO graph node ID (e.g., 'Blue Horizon Maritime Logistics Ltd' or 'UBO-SHELL-01')",
    )


class ReviewRequest(BaseModel):
    status: Literal["open", "cleared", "confirmed"]
    note: str = Field(..., min_length=2, max_length=2000)


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(content="<h1>sancscreen API</h1><p>See /docs for the endpoints.</p>", status_code=200)


@app.post("/screen")
def screen_party(req: ScreenRequest, ident: dict = Depends(ops.require("screen"))) -> Dict[str, Any]:
    """Screen a wire transfer party against the SDN watchlist and UBO ownership graph."""
    query = ScreeningQuery(
        query_id=req.query_id,
        name=req.name,
        entity_type=req.entity_type,
        dob=req.dob if req.dob else None,
        country=req.country if req.country else None,
        identifier=req.identifier if req.identifier else None,
        amount_usd=req.amount_usd,
    )
    result = _PIPELINE.screen_wire(query, top_k=req.top_k)
    ops.DECISIONS.labels(decision=result["decision"]).inc()
    result["screening_id"] = log_store.record(ident["user"] or "demo", result, LIST_VERSION)
    result["list_version"] = LIST_VERSION
    return result


@app.post("/ubo/check", dependencies=[Depends(ops.require("screen"))])
def check_ubo(req: UBOCheckRequest) -> Dict[str, Any]:
    """Evaluate transitive beneficial ownership (OFAC 50% rule and 25% EDD exposure) for an entity."""
    res = _PIPELINE.ubo_engine.evaluate_entity(req.entity)
    if res is None:
        raise HTTPException(status_code=404, detail="entity not found in the ownership graph")
    return asdict(res)


@app.get("/screenings", dependencies=[Depends(ops.require("read"))])
def list_screenings(status: Optional[Literal["open", "cleared", "confirmed"]] = None,
                    decision: Optional[Literal["BLOCK", "REVIEW", "REVIEW_EDD_25", "CLEAR"]] = None,
                    limit: int = Query(100, ge=1, le=1000)) -> Dict[str, Any]:
    rows = log_store.list(status, decision, limit)
    return {"count": len(rows), "screenings": rows}


@app.get("/screenings/{screening_id}", dependencies=[Depends(ops.require("read"))])
def get_screening(screening_id: str) -> Dict[str, Any]:
    row = log_store.get(screening_id[:64])
    if row is None:
        raise HTTPException(404, "screening not found")
    return row


@app.post("/screenings/{screening_id}/review")
def review_screening(screening_id: str, body: ReviewRequest, ident: dict = Depends(ops.require("review"))) -> Dict[str, Any]:
    row = log_store.review(screening_id[:64], ident["user"] or "demo", body.status, body.note)
    if row is None:
        raise HTTPException(404, "screening not found")
    ops.DECISIONS.labels(decision=f"review_{body.status}").inc()
    return row


@app.get("/watchlist", dependencies=[Depends(ops.require("read"))])
def get_watchlist(offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=1000)) -> Dict[str, Any]:
    """A page of the watchlist with phonetic skeletons and IDF weights, plus the UBO entities."""
    entries_out: List[Dict[str, Any]] = []
    for entry in _PIPELINE.watchlist[offset:offset + limit]:
        toks = normalize_tokens(entry.name, strip_affixes=True)
        entries_out.append(
            {
                **asdict(entry),
                "transliterated_name": transliterate(entry.name),
                "phonetic_skeleton": phonetic_skeleton(entry.name),
                "token_idf_weights": {
                    t: round(_PIPELINE.matcher.get_token_weight(t), 3) for t in toks
                },
            }
        )

    ubo_entities = [asdict(r) for r in _PIPELINE.ubo_engine.scan_all_entities()]
    return {
        "list_version": LIST_VERSION,
        "watchlist_count": len(_PIPELINE.watchlist),
        "offset": offset,
        "watchlist": entries_out,
        "ubo_entities_count": len(ubo_entities),
        "ubo_entities": ubo_entities,
    }


@app.get("/bench", dependencies=[Depends(ops.require("read"))])
def get_benchmark() -> Dict[str, Any]:
    """Return the 300-wire benchmark (computed once; it takes tens of seconds)."""
    return _cached_benchmark()


@lru_cache(maxsize=1)
def _cached_benchmark() -> Dict[str, Any]:
    return run_benchmark()
