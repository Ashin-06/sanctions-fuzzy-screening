"""Tests for sancscreen: transliteration, matching, ownership graph, pipeline and API."""

from __future__ import annotations

import itertools

import pytest
from fastapi.testclient import TestClient

from sancscreen.api import app
from sancscreen.bench import SanctionsScreeningPipeline, run_benchmark
from sancscreen.lists import build_default_ubo_graph
from sancscreen.matcher import ScreeningQuery, _solve_bipartite_assignment, jaro_winkler
from sancscreen.phonetics import phonetic_code, transliterate


@pytest.fixture(scope="module")
def pipeline() -> SanctionsScreeningPipeline:
    return SanctionsScreeningPipeline()


def screen(pipeline: SanctionsScreeningPipeline, name: str, **kw) -> dict:
    return pipeline.screen_wire(ScreeningQuery(query_id="T", name=name, **kw))


def test_transliteration_and_phonetic_codes() -> None:
    assert transliterate("Виктор Бут") == "viktor but"
    assert transliterate("विक्टर बुट") == "viktor but"
    assert transliterate("طارق الرشيد") == "tariq al rashid"
    assert transliterate("तारिक अल रशीद") == "tariq al rashid"
    assert transliterate("Müller") == "muller"
    assert phonetic_code("Gaddafi") == phonetic_code("Qaddafi") == phonetic_code("Kadhafi")
    assert phonetic_code("Abdullah") == phonetic_code("Abdulla")


def test_jaro_winkler_matches_published_values() -> None:
    # Winkler (1990) / standard reference pairs
    assert jaro_winkler("martha", "marhta") == pytest.approx(0.9611, abs=1e-4)
    assert jaro_winkler("dwayne", "duane") == pytest.approx(0.84, abs=1e-4)
    assert jaro_winkler("dixon", "dicksonx") == pytest.approx(0.8133, abs=1e-4)


def test_bipartite_assignment_is_optimal() -> None:
    m = [[0.9, 0.8, 0.0], [0.85, 0.1, 0.7], [0.0, 0.75, 0.6]]
    pairs = _solve_bipartite_assignment(m)
    best = max(sum(m[i][p[i]] for i in range(3)) for p in itertools.permutations(range(3)))
    assert sum(w for _, _, w in pairs) == pytest.approx(best)


def test_name_matching_across_scripts_and_orders(pipeline) -> None:
    assert screen(pipeline, "Viktor Anatolyevich But", dob="1967-01-13", country="RU")["decision"] == "BLOCK"
    for variant in ("Виктор Бут", "विक्टर बुट", "But, Viktor Anatolyevich", "Victor A. Bout"):
        res = screen(pipeline, variant, dob="1967-01-13")
        assert res["decision"] == "BLOCK", variant
        assert res["best_watchlist_match"]["sdn_id"] == "SDN-001"
    assert screen(pipeline, "John Smith", dob="1980-01-01", country="GB")["decision"] == "CLEAR"


def test_ownership_graph_thresholds() -> None:
    g = build_default_ubo_graph()
    assert g.evaluate_entity("Blue Horizon Maritime Logistics Ltd").ofac_50_rule_blocked
    assert g.evaluate_entity("Aegean Star Petrotech FZE").ofac_50_rule_blocked
    minority = g.evaluate_entity("Emerald Bosporus Shipping Co")
    assert not minority.ofac_50_rule_blocked and minority.edd_25_rule_flagged
    assert g.evaluate_entity("Pacific Rim Semiconductor Corp").risk_status == "CLEAR"
    # The HOLD-09 <-> HOLD-10 cross-holding must not loop forever
    assert g.evaluate_entity("Nordic Baltic Bunker Services AS").ofac_50_rule_blocked
    assert g.evaluate_entity("Unknown Widgets Ltd") is None


def test_benchmark_runs() -> None:
    res = run_benchmark()
    assert res["total_wires"] == 300
    assert res["sancscreen"]["recall"] > 0.9


def test_api_endpoints() -> None:
    client = TestClient(app)
    assert client.get("/health").status_code == 200
    r = client.post("/screen", json={"name": "Сергей Лавров", "dob": "1950-03-21"})
    assert r.status_code == 200 and r.json()["decision"] == "BLOCK"
    assert client.post("/ubo/check", json={"entity": "UBO-SHELL-01"}).json()["ofac_50_rule_blocked"] is True
    assert client.post("/ubo/check", json={"entity": "Nobody Ltd"}).status_code == 404


def test_people_are_not_screened_through_the_ownership_graph(pipeline) -> None:
    # A homonym born 26 years after the listed person, different country and passport.
    # The ownership lookup used to resolve the name to the SDN's own graph node and block.
    res = screen(pipeline, "Tariq Al-Rashid", entity_type="individual", dob="1994-11-23",
                 country="JO", identifier="JO4410928")
    assert res["hit_source"] != "UBO_50_RULE" and res["ubo_assessment"] is None
    assert res["decision"] != "BLOCK"


def test_people_are_not_matched_against_listed_companies(pipeline) -> None:
    # "nair" and "noor" share the phonetic code "nr"; a person must not hit "Al Noor Trading LLC"
    res = screen(pipeline, "Smt. Priya Darshini Nair", entity_type="individual", dob="1990-11-04", country="IN")
    assert res["decision"] == "CLEAR"


def test_listed_name_with_conflicting_details_goes_to_review(pipeline) -> None:
    res = screen(pipeline, "Tariq Al-Rashid", entity_type="individual", dob="1994-11-23", country="JO")
    assert res["decision"] == "REVIEW"
    assert screen(pipeline, "John Smith", entity_type="individual", dob="1994-11-23")["decision"] == "CLEAR"


def test_ofac_rule_counts_only_holdings_by_blocked_persons() -> None:
    from sancscreen.ubo import GraphNode, OwnershipEdge, UBOGraphEngine

    nodes = [GraphNode("X", "Listed Person", "individual", "XX", True, "SDN-X")] + [
        GraphNode(n, n, "entity") for n in ("A", "B", "C", "D", "E")
    ]
    edges = [
        # OFAC's worked examples: X 50% of A, X 10% of B, A 40% of B -> B blocked (10% + 40%)
        OwnershipEdge("X", "A", 0.50), OwnershipEdge("X", "B", 0.10), OwnershipEdge("A", "B", 0.40),
        # X 40% of C (C not blocked), X 10% of D, C 40% of D -> D not blocked
        OwnershipEdge("X", "C", 0.40), OwnershipEdge("X", "D", 0.10), OwnershipEdge("C", "D", 0.40),
        # X holds 30% of E directly; C (40% X, so not blocked) holds the other 70%. E is not
        # blocked, though the proportional look-through (0.30 + 0.40 * 0.70 = 58%) exceeds 50%
        OwnershipEdge("X", "E", 0.30), OwnershipEdge("C", "E", 0.70),
    ]
    g = UBOGraphEngine(nodes, edges)
    assert g.evaluate_entity("B").ofac_50_rule_blocked
    assert not g.evaluate_entity("D").ofac_50_rule_blocked
    e = g.evaluate_entity("E")
    assert not e.ofac_50_rule_blocked and e.aggregate_sdn_ownership > 0.5 and e.edd_25_rule_flagged


def test_ownership_lookup_ignores_nordic_company_suffixes(pipeline) -> None:
    # The graph node is "Nordic Baltic Bunker Services AS"; "AS" was not a known suffix
    for name in ("Nordic Baltic Bunker Services Ltd", "Nordic Baltic Bunker Services"):
        assert screen(pipeline, name, entity_type="entity", country="EE")["hit_source"] == "UBO_50_RULE"


def test_api_key_and_input_limits(monkeypatch) -> None:
    import sancscreen.api as api

    client = TestClient(app)
    monkeypatch.setattr(api, "API_KEY", "s3cret")
    assert client.post("/screen", json={"name": "John Smith"}).status_code == 401
    assert client.get("/health").status_code == 200
    hdr = {"X-API-Key": "s3cret"}
    assert client.post("/screen", json={"name": "John Smith"}, headers=hdr).status_code == 200
    assert client.post("/screen", json={"name": "x" * 201}, headers=hdr).status_code == 422
    assert client.post("/screen", json={"name": "A", "dob": "13/01/1967"}, headers=hdr).status_code == 422
    assert client.post("/screen", json={"name": "A", "entity_type": "robot"}, headers=hdr).status_code == 422
    # No browser console ships with this API, so no CORS headers are sent
    r = client.options("/screen", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in r.headers
