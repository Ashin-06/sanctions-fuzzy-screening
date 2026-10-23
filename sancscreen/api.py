"""
FastAPI REST API for `sancscreen` (Port 8016).

Endpoints:
- GET  /           : Interactive Sanctions & UBO Screening Web Console (HTML)
- GET  /health     : Service health check
- POST /screen     : Screen a SWIFT / cross-border wire party (Name + Phonetic + IDF + DOB/Country + UBO)
- POST /ubo/check  : Evaluate multi-hop transitive beneficial ownership (OFAC 50% rule & 25% EDD exposure)
- GET  /watchlist  : Inspect the SDN watchlist, token IDF weights, and UBO corporate graph
- GET  /bench      : Run the 300-wire benchmark comparing `sancscreen` vs `NaiveLevenshteinMatcher`

Set SANCSCREEN_API_KEY to require it in the X-API-Key header on every endpoint except / and /health
(unset = open, for local use; `python -m sancscreen serve` refuses a non-loopback host without it).
"""

from __future__ import annotations

import hmac
import os
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from sancscreen.bench import SanctionsScreeningPipeline, run_benchmark
from sancscreen.matcher import ScreeningQuery
from sancscreen.phonetics import normalize_tokens, phonetic_skeleton, transliterate

app = FastAPI(
    title="sancscreen — Cross-Script Phonetic & UBO Graph Sanctions Screening Engine",
    version="1.0.0",
    description=(
        "Multi-Script Transliterator (Devanagari/Arabic/Cyrillic), Consonant Phonetic Skeleton, "
        "Order-Invariant IDF-Weighted Bipartite Token Matcher, Secondary ID Resolver, and "
        "OFAC 50%-Rule and Beneficial-Ownership Exposure Graph Engine."
    ),
)

API_KEY = os.environ.get("SANCSCREEN_API_KEY")
MAX_BODY_BYTES = 64_000


def require_key(x_api_key: str | None = Header(default=None)) -> None:
    if API_KEY and not hmac.compare_digest(x_api_key or "", API_KEY):
        raise HTTPException(401, "missing or wrong X-API-Key")


@app.middleware("http")
async def limit_body(request: Request, call_next):
    if request.method == "POST":
        length = request.headers.get("content-length", "")
        if not length.isdigit() or int(length) > MAX_BODY_BYTES:
            return JSONResponse({"detail": "body missing Content-Length or over 64 KB"}, status_code=413)
    return await call_next(request)


_PIPELINE = SanctionsScreeningPipeline()
_WEB_CONSOLE_PATH = Path(__file__).resolve().parent.parent / "web" / "console.html"


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


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    """Serve the interactive Sanctions & UBO Screening Web Console."""
    if _WEB_CONSOLE_PATH.exists():
        return HTMLResponse(content=_WEB_CONSOLE_PATH.read_text(encoding="utf-8"), status_code=200)
    return HTMLResponse(
        content="<h1>sancscreen API is running on port 8016</h1>", status_code=200
    )


@app.get("/health")
def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "service": "sancscreen",
        "version": "1.0.0",
        "watchlist_count": len(_PIPELINE.watchlist),
        "ubo_graph_nodes": len(_PIPELINE.ubo_engine.nodes),
    }


@app.post("/screen", dependencies=[Depends(require_key)])
def screen_party(req: ScreenRequest) -> Dict[str, Any]:
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
    return _PIPELINE.screen_wire(query, top_k=req.top_k)


@app.post("/ubo/check", dependencies=[Depends(require_key)])
def check_ubo(req: UBOCheckRequest) -> Dict[str, Any]:
    """Evaluate transitive beneficial ownership (OFAC 50% rule and 25% EDD exposure) for an entity."""
    res = _PIPELINE.ubo_engine.evaluate_entity(req.entity)
    if res is None:
        raise HTTPException(
            status_code=404,
            detail=f"Entity '{req.entity}' not found in corporate UBO registry.",
        )
    return asdict(res)


@app.get("/watchlist", dependencies=[Depends(require_key)])
def get_watchlist() -> Dict[str, Any]:
    """Return the SDN watchlist with precomputed phonetic skeletons, IDF weights, and UBO entities."""
    entries_out: List[Dict[str, Any]] = []
    for entry in _PIPELINE.watchlist:
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
        "watchlist_count": len(entries_out),
        "watchlist": entries_out,
        "ubo_entities_count": len(ubo_entities),
        "ubo_entities": ubo_entities,
    }


@app.get("/bench", dependencies=[Depends(require_key)])
def get_benchmark() -> Dict[str, Any]:
    """Return the 300-wire benchmark (computed once; it takes tens of seconds)."""
    return _cached_benchmark()


@lru_cache(maxsize=1)
def _cached_benchmark() -> Dict[str, Any]:
    return run_benchmark()
