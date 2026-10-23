"""
FastAPI REST API for `sancscreen` (Port 8016).

Endpoints:
- GET  /           : Interactive Sanctions & UBO Screening Web Console (HTML)
- GET  /health     : Service health check
- POST /screen     : Screen a SWIFT / cross-border wire party (Name + Phonetic + IDF + DOB/Country + UBO)
- POST /ubo/check  : Evaluate multi-hop transitive beneficial ownership (OFAC 50% & EU/RBI 25% rules)
- GET  /watchlist  : Inspect the SDN watchlist, token IDF weights, and UBO corporate graph
- GET  /bench      : Run the 300-wire benchmark comparing `sancscreen` vs `NaiveLevenshteinMatcher`
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from sancscreen.bench import SanctionsScreeningPipeline, run_benchmark
from sancscreen.matcher import ScreeningQuery
from sancscreen.phonetics import normalize_tokens, phonetic_code, phonetic_skeleton, transliterate

app = FastAPI(
    title="sancscreen — Cross-Script Phonetic & UBO Graph Sanctions Screening Engine",
    version="1.0.0",
    description=(
        "Multi-Script Transliterator (Devanagari/Arabic/Cyrillic), Consonant Phonetic Skeleton, "
        "Order-Invariant IDF-Weighted Bipartite Token Matcher, Secondary ID Resolver, and "
        "OFAC 50%-Rule / EU-RBI 25%-Control Transitive Beneficial Ownership Graph Engine."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_PIPELINE = SanctionsScreeningPipeline()
_WEB_CONSOLE_PATH = Path(__file__).resolve().parent.parent / "web" / "console.html"


class ScreenRequest(BaseModel):
    query_id: str = Field(default="WIRE-LIVE-001", description="Wire transfer or party reference ID")
    name: str = Field(..., description="Originator, beneficiary, or corporate entity name in any script")
    entity_type: Optional[str] = Field(default="individual", description="individual or entity")
    dob: Optional[str] = Field(default=None, description="Date of Birth (YYYY-MM-DD or YYYY)")
    country: Optional[str] = Field(default=None, description="2-letter ISO Country / Nationality code")
    identifier: Optional[str] = Field(default=None, description="Passport, National ID, BIC, or LEI")
    amount_usd: float = Field(default=50000.0, description="Transaction amount in USD")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of top SDN candidates to return")


class UBOCheckRequest(BaseModel):
    entity: str = Field(
        ...,
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


@app.post("/screen")
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


@app.post("/ubo/check")
def check_ubo(req: UBOCheckRequest) -> Dict[str, Any]:
    """Evaluate transitive beneficial ownership (OFAC 50% rule & EU/RBI 25% rule) for an entity."""
    res = _PIPELINE.ubo_engine.evaluate_entity(req.entity)
    if res is None:
        raise HTTPException(
            status_code=404,
            detail=f"Entity '{req.entity}' not found in corporate UBO registry.",
        )
    return asdict(res)


@app.get("/watchlist")
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


@app.get("/bench")
def get_benchmark() -> Dict[str, Any]:
    """Execute and return the 300-wire benchmark suite comparing sancscreen vs Naive Levenshtein."""
    return run_benchmark()
