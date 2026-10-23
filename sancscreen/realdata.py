"""Screening against the real OFAC SDN list.

OFAC's SDN.XML (sanctionslistservice.ofac.treas.gov, a US government work, public domain)
lists every designated person, entity, vessel and aircraft with its a.k.a. names, dates of
birth, identity documents and addresses. `load_sdn_xml` turns it into SDNEntry records:
- name: first name + last name (OFAC's order), each a.k.a. as an alias. OFAC grades a.k.a.s
  strong or weak; weak ones ("BUTT" for Viktor Bout) are left out unless asked for;
- dob: the first date of birth, as YYYY-MM-DD, YYYY-MM or YYYY;
- countries: ISO codes of nationality, citizenship, address and ID-issuing countries;
- identifiers: ID numbers, minus the non-document fields OFAC keeps in the same list
  (gender, secondary-sanctions notes, establishment dates, websites and so on).

`experiments` then measures screening latency at full list size with the candidate index,
compares it with a full scan on a sample of wires, and screens the 300 benchmark wires
against the real list, without and with the weak a.k.a.s.

    python -m sancscreen realdata --sdn SDN.XML [--sample 30]
"""
from __future__ import annotations

import json
import random
import re
import statistics
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

from sancscreen.lists import WireTransferCase, generate_benchmark_wires, get_default_watchlist
from sancscreen.matcher import SanctionsMatcher, ScreeningQuery, SDNEntry
from sancscreen.phonetics import normalize_tokens, phonetic_code

# OFAC spellings Babel's English territory names don't use
_COUNTRY_OVERRIDES = {
    "turkey": "TR", "hong kong": "HK", "korea, north": "KP", "korea, south": "KR", "burma": "MM",
    "congo, democratic republic of the": "CD", "congo, republic of the": "CG", "palestinian": "PS",
    "gaza": "PS", "west bank": "PS", "virgin islands, british": "VG", "bosnia and herzegovina": "BA",
    "saint kitts and nevis": "KN", "north macedonia, the republic of": "MK", "the gambia": "GM",
    "czech republic": "CZ", "cote d ivoire": "CI", "trinidad and tobago": "TT", "macau": "MO",
    "saint vincent and the grenadines": "VC", "cabo verde": "CV", "man, isle of": "IM",
    "bahamas, the": "BS", "antigua and barbuda": "AG", "curacao": "CW", "saint lucia": "LC",
    "crimea": "UA", "russia": "RU", "iran": "IR",
}
_NOT_AN_ID = re.compile(
    r"date|year|information|determination|type|gender|risk|prohibited|model|operator|flag|website|email|phone",
    re.IGNORECASE,
)


def _country_codes() -> Dict[str, str]:
    from babel import Locale  # only the loader needs it

    codes = {name.lower(): code for code, name in Locale("en").territories.items() if len(code) == 2}
    codes.update(_COUNTRY_OVERRIDES)
    return codes


def _dob(raw: str) -> Optional[str]:
    raw = raw.strip()
    for fmt, out in (("%d %b %Y", "%Y-%m-%d"), ("%b %Y", "%Y-%m"), ("%Y", "%Y")):
        try:
            return datetime.strptime(raw, fmt).strftime(out)
        except ValueError:
            pass
    m = re.search(r"\b(19|20)\d{2}\b", raw)  # "circa 1960", "1960 to 1962"
    return m.group(0) if m else None


def load_sdn_xml(path: str | Path, weak_akas: bool = False) -> List[SDNEntry]:
    countries = _country_codes()
    root = ET.parse(path).getroot()
    ns = {"o": root.tag.split("}")[0].strip("{")} if root.tag.startswith("{") else {"o": ""}
    p = "o:" if ns["o"] else ""

    def text(el: ET.Element, tag: str) -> str:
        return (el.findtext(p + tag, default="", namespaces=ns) or "").strip()

    def full_name(el: ET.Element) -> str:
        return " ".join(x for x in (text(el, "firstName"), text(el, "lastName")) if x)

    entries: List[SDNEntry] = []
    for e in root.iterfind(p + "sdnEntry", ns):
        country_names: List[str] = [c.text or "" for c in e.iterfind(f".//{p}country", ns)]
        country_names += [c.text or "" for c in e.iterfind(f".//{p}idCountry", ns)]
        ccs: List[str] = []
        for c in country_names:
            code = countries.get(c.strip().lower().removeprefix("region: "))
            if code and code not in ccs:
                ccs.append(code)
        ids = [text(i, "idNumber") for i in e.iterfind(f"{p}idList/{p}id", ns)
               if not _NOT_AN_ID.search(text(i, "idType")) and re.search(r"\d", text(i, "idNumber"))]
        dobs = [_dob(d.text or "") for d in e.iterfind(f"{p}dateOfBirthList/{p}dateOfBirthItem/{p}dateOfBirth", ns)]
        akas = [a for a in e.iterfind(f"{p}akaList/{p}aka", ns) if weak_akas or text(a, "category") != "weak"]
        entries.append(SDNEntry(
            sdn_id=f"OFAC-{text(e, 'uid')}",
            name=full_name(e),
            entity_type=text(e, "sdnType").lower(),
            program=";".join(x.text or "" for x in e.iterfind(f"{p}programList/{p}program", ns)),
            aliases=[n for n in (full_name(a) for a in akas) if n],
            dob=next((d for d in dobs if d), None),
            countries=ccs,
            identifiers=ids,
        ))
    return entries


def _key(name: str) -> frozenset:
    return frozenset(normalize_tokens(name))


def _queries(wires: List[WireTransferCase]) -> List[ScreeningQuery]:
    return [ScreeningQuery(query_id=w.wire_id, name=w.party_name, entity_type=w.entity_type, dob=w.dob,
                           country=w.country, identifier=w.identifier) for w in wires]


def screen_wires(real: List[SDNEntry]) -> dict:
    """Screen the 300 benchmark wires against `real` and tabulate decisions by what each wire names."""
    matcher = SanctionsMatcher(real)
    by_id = {e.sdn_id: e for e in real}
    # A synthetic entry is on the real list if one of its names equals a listed name or a.k.a.,
    # or (people) the full DOB matches and the surnames share a phonetic code (But / BOUT).
    name_to_real: Dict[object, Set[str]] = {}
    for e in real:
        for nm in [e.name] + e.aliases:
            name_to_real.setdefault(_key(nm), set()).add(e.sdn_id)
            if e.dob and len(e.dob) == 10 and _key(nm):
                name_to_real.setdefault((e.dob, phonetic_code(normalize_tokens(nm)[-1])), set()).add(e.sdn_id)
    synthetic_to_real = {
        s.sdn_id: sorted(set().union(*(name_to_real.get(k, set()) for nm in [s.name] + s.aliases
                                       for k in (_key(nm), (s.dob, phonetic_code(normalize_tokens(nm)[-1]))))))
        for s in get_default_watchlist()
    }

    wires = generate_benchmark_wires()
    results, lat_ms, n_cands = [], [], []
    for q in _queries(wires):
        t0 = time.perf_counter()
        results.append(matcher.screen(q, top_k=3))
        lat_ms.append((time.perf_counter() - t0) * 1000)
        n_cands.append(len(matcher.candidates(q)))

    rows: Dict[str, Dict[str, int]] = {}
    misses, flagged = [], []
    for w, r in zip(wires, results):
        listed = synthetic_to_real.get(w.expected_sdn_or_ubo_id or "") if w.should_block else None
        group = ("names a listed person or company" if listed else
                 "shell company (synthetic ownership graph)" if w.category == "ubo_shell" else
                 "names a synthetic entry not on the real list" if w.should_block else "hard negative")
        row = rows.setdefault(group, {"wires": 0, "BLOCK": 0, "REVIEW": 0, "CLEAR": 0, "blocked_on_a_one_word_name": 0})
        row["wires"] += 1
        row[r["decision"]] += 1
        best = r["best_match"]
        row["blocked_on_a_one_word_name"] += r["decision"] == "BLOCK" and len(normalize_tokens(best.matched_alias)) == 1
        if listed:
            right = r["decision"] == "BLOCK" and best.sdn_id in listed
            row["blocked_on_the_right_entry"] = row.get("blocked_on_the_right_entry", 0) + right
            if not right:
                misses.append({"wire": w.wire_id, "name": w.party_name, "dob": w.dob, "country": w.country,
                               "decision": r["decision"], "score": r["best_score"],
                               "top_match": best.matched_alias if best else None,
                               "listed_as": by_id[listed[0]].name, "listed_dob": by_id[listed[0]].dob})
        elif r["decision"] != "CLEAR":
            flagged.append({"wire": w.wire_id, "group": group, "name": w.party_name, "dob": w.dob,
                            "country": w.country, "decision": r["decision"], "score": r["best_score"],
                            "matched": best.matched_alias, "listed_dob": by_id[best.sdn_id].dob,
                            "listed_countries": by_id[best.sdn_id].countries})
    p95 = sorted(lat_ms)[int(0.95 * len(lat_ms))]
    return {
        "matcher": matcher, "results": results,
        "summary": {
            "entries": len(real),
            "aliases": sum(len(e.aliases) for e in real),
            "latency_ms_indexed": {"median": round(statistics.median(lat_ms), 2), "p95": round(p95, 2),
                                   "max": round(max(lat_ms), 2)},
            "candidates_per_wire": {"median": statistics.median(n_cands), "max": max(n_cands)},
            "synthetic_entries_on_real_list": {k: v for k, v in synthetic_to_real.items() if v},
            "synthetic_entries_not_on_real_list": [k for k, v in synthetic_to_real.items() if not v],
            "wires": rows,
            "listed_wires_not_blocked_on_their_entry": misses,
            "flagged_wires_outside_listed": flagged,
        },
    }


def experiments(sdn_path: str | Path, sample: int = 30, seed: int = 0, log=print) -> dict:
    t0 = time.perf_counter()
    real = load_sdn_xml(sdn_path)
    t_load = time.perf_counter() - t0
    t0 = time.perf_counter()
    SanctionsMatcher(real)
    t_index = time.perf_counter() - t0
    log(f"{len(real)} entries; load {t_load:.1f} s, matcher + index build {t_index:.1f} s")

    strong = screen_wires(real)
    log(f"strong a.k.a.s: {strong['summary']['latency_ms_indexed']} {strong['summary']['wires']}")
    weak = screen_wires(load_sdn_xml(sdn_path, weak_akas=True))
    log(f"with weak a.k.a.s: {weak['summary']['wires']}")

    # The old way: score every entry. Slow, so only on a sample of wires.
    matcher, results = strong["matcher"], strong["results"]
    queries = _queries(generate_benchmark_wires())
    idx = sorted(random.Random(seed).sample(range(len(queries)), sample))
    full_s, same = [], 0
    for k, i in enumerate(idx):
        t0 = time.perf_counter()
        full = matcher.screen(queries[i], top_k=3, full_scan=True)
        full_s.append(time.perf_counter() - t0)
        same += full["decision"] == results[i]["decision"] and (
            full["decision"] == "CLEAR" or full["best_match"].sdn_id == results[i]["best_match"].sdn_id)
        log(f"  full scan {k + 1}/{sample}: {full_s[-1]:.1f} s")

    return {
        "dataset": "OFAC SDN list (SDN.XML, sanctionslistservice.ofac.treas.gov)",
        "publish_date": re.search(r"<Publish_Date>([^<]+)", Path(sdn_path).read_text(encoding="utf-8")[:2000]).group(1),
        "by_type": {t: sum(e.entity_type == t for e in real) for t in sorted({e.entity_type for e in real})},
        "with_dob": sum(e.dob is not None for e in real),
        "with_country": sum(bool(e.countries) for e in real),
        "with_identifier": sum(bool(e.identifiers) for e in real),
        "load_seconds": round(t_load, 2),
        "matcher_and_index_build_seconds": round(t_index, 2),
        "full_scan_sample": {"wires": sample, "median_seconds": round(statistics.median(full_s), 2),
                             "same_decision_and_top_entry_as_index": same},
        "strong_akas_only": strong["summary"],
        "with_weak_akas": {k: v for k, v in weak["summary"].items() if k != "flagged_wires_outside_listed"},
    }


def main(sdn: str, out: str = "results/real_data.json", sample: int = 30) -> dict:
    res = experiments(sdn, sample)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    return res
