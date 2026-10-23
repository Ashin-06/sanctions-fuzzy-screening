"""
Unified Sanctions Screening Pipeline & Benchmark Suite (300 SWIFT Wire Transfers).

Compares `sancscreen` (Multi-Script Phonetic + IDF Bipartite + Secondary ID + UBO 50% Graph)
against a legacy `NaiveLevenshteinMatcher` across 300 labeled test wire transfers.
"""

from __future__ import annotations

import time
from dataclasses import asdict
from typing import Any, Dict, List, Optional

from sancscreen.lists import (
    WireTransferCase,
    build_default_ubo_graph,
    generate_benchmark_wires,
    get_default_watchlist,
)
from sancscreen.matcher import (
    NaiveLevenshteinMatcher,
    SDNEntry,
    SanctionsMatcher,
    ScreeningQuery,
)
from sancscreen.ubo import UBOGraphEngine, UBOResult


class SanctionsScreeningPipeline:
    """
    Production SWIFT / Cross-Border Payment Sanctions Screening Engine combining:
    1. Multi-script transliteration & consonant phonetic skeletonization
    2. Order-invariant IDF-weighted bipartite token matching + DOB/Country/ID reconciliation
    3. OFAC 50%-rule blocking and beneficial-ownership exposure (UBO) graph engine
    """

    def __init__(
        self,
        watchlist: Optional[List[SDNEntry]] = None,
        ubo_engine: Optional[UBOGraphEngine] = None,
        alert_threshold: float = 0.75,
    ) -> None:
        self.watchlist = watchlist if watchlist is not None else get_default_watchlist()
        self.ubo_engine = ubo_engine if ubo_engine is not None else build_default_ubo_graph()
        self.matcher = SanctionsMatcher(self.watchlist, alert_threshold=alert_threshold)

    def screen_wire(self, query: ScreeningQuery, top_k: int = 5) -> Dict[str, Any]:
        """Screen a single wire transfer party against both the SDN watchlist and UBO graph."""
        t0 = time.perf_counter()
        name_res = self.matcher.screen(query, top_k=top_k)
        # Ownership screening is for companies. Sending a person's name through it resolved
        # e.g. "Tariq Al-Rashid" to the listed individual's graph node and blocked every
        # homonym, bypassing the name matcher's DOB and country checks.
        ubo_res: Optional[UBOResult] = None
        if (query.entity_type or "").lower() != "individual":
            node_id = self.ubo_engine.resolve_node_id(query.name)
            if node_id is not None and self.ubo_engine.nodes[node_id].node_type != "individual":
                ubo_res = self.ubo_engine.evaluate_entity(node_id)

        name_hit = bool(name_res["is_hit"])
        ubo_blocked = bool(ubo_res is not None and ubo_res.ofac_50_rule_blocked)
        ubo_edd = bool(ubo_res is not None and ubo_res.edd_25_rule_flagged)

        is_hit = name_hit or ubo_blocked

        if name_hit and ubo_blocked:
            hit_source = "NAME_AND_UBO_50_RULE"
            decision = "BLOCK"
        elif ubo_blocked:
            hit_source = "UBO_50_RULE"
            decision = "BLOCK"
        elif name_hit:
            hit_source = "WATCHLIST_NAME_MATCH"
            decision = "BLOCK"
        elif ubo_edd:
            hit_source = "UBO_25_EDD"
            decision = "REVIEW_EDD_25"
        elif name_res["decision"] == "REVIEW":
            hit_source = "NAME_NEAR_THRESHOLD"
            decision = "REVIEW"
        else:
            hit_source = "NONE"
            decision = "CLEAR"

        effective_score = name_res["best_score"]
        if ubo_blocked and ubo_res is not None:
            # OFAC 50% rule is a statutory block; surface high risk score
            effective_score = max(effective_score, round(min(1.0, 0.50 + ubo_res.aggregate_sdn_ownership), 4))

        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        return {
            "query_id": query.query_id,
            "query_name": query.name,
            "detected_script": name_res["detected_script"],
            "transliterated_name": name_res["transliterated_name"],
            "phonetic_skeleton": name_res["phonetic_skeleton"],
            "is_hit": is_hit,
            "decision": decision,
            "hit_source": hit_source,
            "effective_score": round(effective_score, 4),
            "name_score": name_res["best_score"],
            "best_watchlist_match": asdict(name_res["best_match"]) if name_res["best_match"] else None,
            "top_candidates": [asdict(c) for c in name_res["top_candidates"]],
            "ubo_assessment": asdict(ubo_res) if ubo_res else None,
            "latency_ms": round(elapsed_ms, 3),
        }


def _compute_metrics(tp: int, fp: int, tn: int, fn: int) -> Dict[str, Any]:
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2.0 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
    total = tp + fp + tn + fn
    accuracy = (tp + tn) / total if total > 0 else 0.0
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
    return {
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "total": total,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "accuracy": round(accuracy, 4),
        "false_positive_rate": round(fpr, 4),
    }


def run_benchmark() -> Dict[str, Any]:
    """
    Execute the 300-wire benchmark comparing `sancscreen` against `NaiveLevenshteinMatcher`.
    """
    watchlist = get_default_watchlist()
    ubo_graph = build_default_ubo_graph()
    wires: List[WireTransferCase] = generate_benchmark_wires()

    pipeline = SanctionsScreeningPipeline(watchlist=watchlist, ubo_engine=ubo_graph, alert_threshold=0.75)
    naive = NaiveLevenshteinMatcher(watchlist=watchlist, alert_threshold=0.72)

    s_tp = s_fp = s_tn = s_fn = 0
    n_tp = n_fp = n_tn = n_fn = 0

    category_stats: Dict[str, Dict[str, int]] = {}
    latencies_ms: List[float] = []
    sample_highlights: List[Dict[str, Any]] = []

    t_start = time.perf_counter()
    for w in wires:
        q = ScreeningQuery(
            query_id=w.wire_id,
            name=w.party_name,
            entity_type=w.entity_type,
            dob=w.dob,
            country=w.country,
            identifier=w.identifier,
            amount_usd=w.amount_usd,
        )

        s_res = pipeline.screen_wire(q, top_k=3)
        n_res = naive.screen(q)
        latencies_ms.append(s_res["latency_ms"])

        s_pred = bool(s_res["is_hit"])
        n_pred = bool(n_res["is_hit"])
        truth = bool(w.should_block)

        cat = category_stats.setdefault(
            w.category,
            {"total": 0, "sancscreen_correct": 0, "naive_correct": 0},
        )
        cat["total"] += 1

        if truth:
            if s_pred:
                s_tp += 1
                cat["sancscreen_correct"] += 1
            else:
                s_fn += 1

            if n_pred:
                n_tp += 1
                cat["naive_correct"] += 1
            else:
                n_fn += 1
        else:
            if not s_pred:
                s_tn += 1
                cat["sancscreen_correct"] += 1
            else:
                s_fp += 1

            if not n_pred:
                n_tn += 1
                cat["naive_correct"] += 1
            else:
                n_fp += 1

        # Capture representative examples where sancscreen succeeds and naive fails
        if (s_pred == truth) and (n_pred != truth) and len(sample_highlights) < 12:
            sample_highlights.append(
                {
                    "wire_id": w.wire_id,
                    "category": w.category,
                    "party_name": w.party_name,
                    "dob": w.dob,
                    "country": w.country,
                    "ground_truth_block": truth,
                    "sancscreen_decision": s_res["decision"],
                    "sancscreen_score": s_res["effective_score"],
                    "sancscreen_hit_source": s_res["hit_source"],
                    "naive_hit": n_pred,
                    "naive_score": n_res["best_score"],
                    "notes": w.notes,
                }
            )

    total_time_s = max(1e-6, time.perf_counter() - t_start)
    latencies_sorted = sorted(latencies_ms)
    p50_ms = latencies_sorted[len(latencies_sorted) // 2]
    p95_ms = latencies_sorted[int(len(latencies_sorted) * 0.95)]

    sancscreen_metrics = _compute_metrics(s_tp, s_fp, s_tn, s_fn)
    naive_metrics = _compute_metrics(n_tp, n_fp, n_tn, n_fn)

    category_breakdown: Dict[str, Any] = {}
    for cat_name, st in category_stats.items():
        tot = max(1, st["total"])
        category_breakdown[cat_name] = {
            "total_cases": st["total"],
            "sancscreen_correct": st["sancscreen_correct"],
            "sancscreen_rate": round(st["sancscreen_correct"] / tot, 4),
            "naive_correct": st["naive_correct"],
            "naive_rate": round(st["naive_correct"] / tot, 4),
        }

    return {
        "watchlist_entries": len(watchlist),
        "total_wires": len(wires),
        "positive_wires": sum(1 for w in wires if w.should_block),
        "negative_wires": sum(1 for w in wires if not w.should_block),
        "sancscreen": sancscreen_metrics,
        "naive_levenshtein": naive_metrics,
        "f1_lift": round(sancscreen_metrics["f1"] - naive_metrics["f1"], 4),
        "ubo_shell_detection_rate": category_breakdown["ubo_shell"]["sancscreen_rate"],
        "cross_script_detection_rate": category_breakdown["cross_script"]["sancscreen_rate"],
        "category_breakdown": category_breakdown,
        "performance": {
            "p50_latency_ms": round(p50_ms, 3),
            "p95_latency_ms": round(p95_ms, 3),
            "throughput_wires_per_sec": round(len(wires) / total_time_s, 1),
        },
        "sample_highlights": sample_highlights,
    }


def format_benchmark_report(res: Dict[str, Any]) -> str:
    """Format benchmark results into a clean ASCII table report."""
    s = res["sancscreen"]
    n = res["naive_levenshtein"]
    p = res["performance"]
    lines = [
        "=" * 78,
        " SANCSCREEN BENCHMARK REPORT (300 SWIFT / ISO-20022 WIRE TRANSFERS)",
        "=" * 78,
        f" Watchlist Entries : {res['watchlist_entries']} synthetic entries (not the real SDN list)",
        f" Test Wire Corpus  : {res['total_wires']} wires ({res['positive_wires']} Blocked / {res['negative_wires']} Clean)",
        f" Latency & Speed   : p50={p['p50_latency_ms']:.2f} ms | p95={p['p95_latency_ms']:.2f} ms | {p['throughput_wires_per_sec']:.0f} wires/sec",
        "-" * 78,
        f" {'Metric':<26} | {'sancscreen (Ours)':>20} | {'Naive Levenshtein':>20}",
        "-" * 78,
        f" {'Precision':<26} | {s['precision'] * 100:>19.2f}% | {n['precision'] * 100:>19.2f}%",
        f" {'Recall (Sensitivity)':<26} | {s['recall'] * 100:>19.2f}% | {n['recall'] * 100:>19.2f}%",
        f" {'F1 Score':<26} | {s['f1'] * 100:>19.2f}% | {n['f1'] * 100:>19.2f}%",
        f" {'Accuracy':<26} | {s['accuracy'] * 100:>19.2f}% | {n['accuracy'] * 100:>19.2f}%",
        f" {'False Positive Rate':<26} | {s['false_positive_rate'] * 100:>19.2f}% | {n['false_positive_rate'] * 100:>19.2f}%",
        f" {'True Positives (TP)':<26} | {s['tp']:>20d} | {n['tp']:>20d}",
        f" {'False Positives (FP)':<26} | {s['fp']:>20d} | {n['fp']:>20d}",
        f" {'True Negatives (TN)':<26} | {s['tn']:>20d} | {n['tn']:>20d}",
        f" {'False Negatives (FN)':<26} | {s['fn']:>20d} | {n['fn']:>20d}",
        "-" * 78,
        " Category Accuracy / Detection Breakdown:",
    ]
    for cat, stats in res["category_breakdown"].items():
        lines.append(
            f"   - {cat:<22}: sancscreen={stats['sancscreen_correct']:>3d}/{stats['total_cases']:<3d} ({stats['sancscreen_rate']*100:>6.1f}%) "
            f"| naive={stats['naive_correct']:>3d}/{stats['total_cases']:<3d} ({stats['naive_rate']*100:>6.1f}%)"
        )
    lines.append("=" * 78)
    return "\n".join(lines)
