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

The 300 wires were written alongside the matcher and have been looked at against the real list,
so `heldout` builds a fresh set: listed names with realistic changes (typos, other spellings,
reordering, dropped middle names, initials, other company forms) and real names that aren't
listed (Wikidata people and companies). Scorer constants are tuned on its "tune" half only.

    python -m sancscreen realdata --sdn SDN.XML [--sample 30] [--wikidata DIR]
"""
from __future__ import annotations

import csv
import hashlib
import json
import random
import re
import statistics
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

from defusedxml.ElementTree import parse as safe_parse

from sancscreen.lists import WireTransferCase, generate_benchmark_wires, get_default_watchlist
from sancscreen.matcher import SanctionsMatcher, ScreeningQuery, SDNEntry
from sancscreen.phonetics import normalize_tokens, phonetic_code, transliterate

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
    root = safe_parse(path).getroot()  # defusedxml: no entity expansion or external fetches
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


# ---------------------------------------------------------------------------
# Held-out evaluation: perturbed listed names vs real names that aren't listed
# ---------------------------------------------------------------------------
# Negatives are Wikidata people and companies (CC0), one capped SPARQL query per country:
#   people_<Q>.csv: SELECT ?p ?name ?dob ?cc WHERE { ?p wdt:P27 wd:<Q>; wdt:P31 wd:Q5; wdt:P569 ?dob.
#       wd:<Q> wdt:P297 ?cc. ?p rdfs:label ?name. FILTER(LANG(?name)='en') FILTER(YEAR(?dob) >= 1930) } LIMIT 500
#   firms_<Q>.csv: SELECT ?c ?name ?cc WHERE { VALUES ?t { wd:Q4830453 wd:Q783794 wd:Q891723 wd:Q6881511
#       wd:Q22687 wd:Q1589009 wd:Q46970 } ?c wdt:P31 ?t; wdt:P17 wd:<Q>. wd:<Q> wdt:P297 ?cc.
#       ?c rdfs:label ?name. FILTER(LANG(?name)='en') } LIMIT 500
# Each case goes to the "tune" or "test" split by a hash of its source (SDN entry or Wikidata item).

# Fixed here, not taken from the matcher, so the contamination filter doesn't move when the scorer does
_FORM_WORDS = frozenset(
    "llc inc corp corporation co company ltd limited plc gmbh ag jsc ojsc pjsc cjsc ooo zao pao ao sa "
    "joint stock public open closed liability of the and".split())
_FORMS = ["LLC", "Ltd", "JSC", "Co.", "Limited", "Company", "Joint Stock Company", "S.A.", "FZE", "OOO"]
_SWAPS = [("ou", "u"), ("u", "ou"), ("y", "i"), ("i", "y"), ("j", "y"), ("kh", "h"), ("x", "ks"), ("ks", "x"),
          ("ph", "f"), ("f", "ph"), ("w", "v"), ("v", "w"), ("c", "k"), ("k", "c"), ("q", "k"), ("ee", "i"),
          ("oo", "u"), ("ll", "l"), ("ss", "s"), ("mm", "m"), ("e", "a"), ("a", "e")]
PERTURBATIONS = {
    "individual": ["exact", "reorder", "drop_middle", "typo", "translit", "initial"],
    "entity": ["exact", "typo", "translit", "company_form"],
}


def _plain(name: str) -> frozenset:
    return frozenset(transliterate(name).split()) - _FORM_WORDS


def _split(source_id: str) -> str:
    return "tune" if hashlib.md5(source_id.encode(), usedforsecurity=False).digest()[0] % 2 == 0 else "test"


def perturb(name: str, kind: str, rng: random.Random) -> Optional[str]:
    """A variant of a listed name as it might be typed on a wire; None if `kind` doesn't apply."""
    toks = name.split()
    if kind == "exact":
        return name.title()
    if kind == "reorder" and len(toks) >= 2:
        return f"{toks[-1]}, {' '.join(toks[:-1])}"
    if kind == "drop_middle" and len(toks) >= 3:
        drop = rng.randrange(1, len(toks) - 1)
        return " ".join(toks[:drop] + toks[drop + 1:])
    if kind == "initial" and len(toks) >= 2 and len(toks[0]) > 1:
        return f"{toks[0][0]}. {' '.join(toks[1:])}"
    if kind == "typo":
        long = [i for i, t in enumerate(toks) if len(t) >= 5 and t.isalpha()]
        if not long:
            return None
        i = rng.choice(long)
        t, p = toks[i].lower(), rng.randrange(1, len(toks[i]) - 1)
        op = rng.choice(["sub", "del", "swap", "dup"])
        t = (t[:p] + rng.choice("abcdefghijklmnopqrstuvwxyz") + t[p + 1:] if op == "sub" else
             t[:p] + t[p + 1:] if op == "del" else
             t[:p] + t[p + 1] + t[p] + t[p + 2:] if op == "swap" else t[:p] + t[p] + t[p:])
        return " ".join(toks[:i] + [t] + toks[i + 1:]).title()
    if kind == "translit":
        low = name.lower()
        options = [(a, b, m.start()) for a, b in _SWAPS for m in re.finditer(a, low) if m.start() > 0]
        if not options:
            return None
        a, b, at = rng.choice(options)
        return (low[:at] + b + low[at + len(a):]).title()
    if kind == "company_form":
        core = [t for t in toks if t.lower().strip(".,") not in _FORM_WORDS]
        return " ".join(core + [rng.choice(_FORMS)]).title() if core else None
    return None


def load_wikidata(folder: str | Path) -> List[dict]:
    rows: Dict[str, dict] = {}
    for f in sorted(Path(folder).glob("*.csv")):
        kind = "individual" if f.name.startswith("people") else "entity"
        with f.open(encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                qid = (r.get("p") or r.get("c") or "").rsplit("/", 1)[-1]
                dob = (r.get("dob") or "")[:10]
                rows.setdefault(qid, {"source": qid, "name": r["name"].strip(), "entity_type": kind,
                                      "country": r["cc"] or None,
                                      "dob": dob[:4] if dob.endswith("-01-01") else dob or None})
    return [rows[k] for k in sorted(rows)]


def build_heldout(real: List[SDNEntry], wikidata: List[dict], n_pos: int = 1200, n_neg: int = 3000,
                  seed: int = 0) -> dict:
    """
    Positives: `n_pos` listed people and `n_pos` listed entities, each under its name or one strong a.k.a.,
    changed one way (PERTURBATIONS). Negatives: up to `n_neg` Wikidata people and companies each, minus
    names that may be listed: the same words as a listed name, a company name inside a listed one
    (Sberbank / SBERBANK OF RUSSIA) or holding a listed name of 2+ words, a person born in the same year
    as a listed person with the same surname code. On both sides half the cases carry the country and
    half the people their date of birth.
    """
    rng = random.Random(seed)
    by_tok: Dict[str, List[frozenset]] = {}
    listed_sets: Set[frozenset] = set()
    surname_years: Set[tuple] = set()
    for e in real:
        for nm in [e.name] + e.aliases:
            s = _plain(nm)
            if not s:
                continue
            listed_sets.add(s)
            for t in s:
                by_tok.setdefault(t, []).append(s)
            if e.entity_type == "individual" and e.dob:
                surname_years.add((e.dob[:4], phonetic_code(transliterate(nm).split()[-1])))

    def possibly_listed(c: dict) -> bool:
        s = _plain(c["name"])
        if not s or s in listed_sets:
            return True
        if c["entity_type"] == "individual":
            return bool(c["dob"]) and (c["dob"][:4], phonetic_code(transliterate(c["name"]).split()[-1])) in surname_years
        near = {x for t in s for x in by_tok.get(t, [])}
        return any(s <= x or (len(x) >= 2 and x <= s) for x in near)

    def wire(case: dict) -> dict:
        case["country"] = case["country"] if rng.random() < 0.5 else None
        case["dob"] = case["dob"] if case["entity_type"] == "individual" and rng.random() < 0.5 else None
        case["split"] = _split(case["source"])
        return case

    cases, dropped = [], {}
    for kind in ("individual", "entity"):
        pool = sorted((e for e in real if e.entity_type == kind), key=lambda e: e.sdn_id)
        for e in rng.sample(pool, n_pos):
            listed = rng.choice([e.name] + e.aliases)
            name, pert = None, None
            while not (name and normalize_tokens(name)):
                pert = rng.choice(PERTURBATIONS[kind])
                name = perturb(listed, pert, rng)
            cases.append(wire({"source": e.sdn_id, "name": name, "entity_type": kind, "listed_name": listed,
                               "perturbation": pert, "country": e.countries[0] if e.countries else None,
                               "dob": e.dob}))
        mine = [c for c in wikidata if c["entity_type"] == kind]
        clean = [c for c in mine if not possibly_listed(c)]
        dropped[kind] = len(mine) - len(clean)
        cases += [wire(dict(c)) for c in rng.sample(clean, min(n_neg, len(clean)))]
    return {"cases": cases, "negatives_dropped_as_possibly_listed": dropped}


_POOL_MATCHER: Optional[SanctionsMatcher] = None


def _init_worker(real: List[SDNEntry]) -> None:
    global _POOL_MATCHER
    _POOL_MATCHER = SanctionsMatcher(real)


def _screen_case(c: dict) -> dict:
    r = _POOL_MATCHER.screen(ScreeningQuery(c["source"], c["name"], c["entity_type"], c["dob"], c["country"]), top_k=1)
    best = r["best_match"]
    return {"decision": r["decision"], "score": r["best_score"], "sdn_id": best.sdn_id if best else None,
            "matched": best.matched_alias if best else None}


def screen_heldout(real: List[SDNEntry], cases: List[dict], workers: int = 0) -> List[dict]:
    from multiprocessing import Pool, cpu_count

    with Pool(workers or max(1, cpu_count() - 1), _init_worker, (real,)) as pool:
        return pool.map(_screen_case, cases, chunksize=16)


def summarize_heldout(real: List[SDNEntry], cases: List[dict], results: List[dict]) -> dict:
    """Decisions by split and group. A positive is found if blocked on its own entry or on another
    entry listed under the same name."""
    same_name: Dict[frozenset, Set[str]] = {}
    for e in real:
        for nm in [e.name] + e.aliases:
            same_name.setdefault(_plain(nm), set()).add(e.sdn_id)
    out: Dict[str, dict] = {}
    for c, r in zip(cases, results):
        pos = "listed_name" in c
        group = ("listed, perturbed: " if pos else "not listed (Wikidata): ") + (
            "people" if c["entity_type"] == "individual" else "companies")
        row = out.setdefault(c["split"], {}).setdefault(group, {"cases": 0, "BLOCK": 0, "REVIEW": 0, "CLEAR": 0})
        row["cases"] += 1
        row[r["decision"]] += 1
        if pos:
            right = r["decision"] == "BLOCK" and r["sdn_id"] in same_name[_plain(c["listed_name"])] | {c["source"]}
            row["blocked_on_the_right_entry"] = row.get("blocked_on_the_right_entry", 0) + right
            hit = row.setdefault("blocked_on_the_right_entry_by_perturbation", {}).setdefault(c["perturbation"], [0, 0])
            hit[0] += right
            hit[1] += 1
        else:
            row["blocked_on_a_one_word_name"] = row.get("blocked_on_a_one_word_name", 0) + (
                r["decision"] == "BLOCK" and len(normalize_tokens(r["matched"])) == 1)
    return out


def heldout(sdn_path: str | Path, wikidata_dir: str | Path) -> dict:
    real = load_sdn_xml(sdn_path)
    built = build_heldout(real, load_wikidata(wikidata_dir))
    cases = built["cases"]
    results = screen_heldout(real, cases)

    def example(c: dict, r: dict) -> dict:
        return {"name": c["name"], "listed_as": c.get("listed_name"), "country": c["country"], "dob": c["dob"],
                "decision": r["decision"], "score": r["score"], "matched": r["matched"]}

    test = [(c, r) for c, r in zip(cases, results) if c["split"] == "test"]
    return {
        "cases": len(cases),
        "negatives_dropped_as_possibly_listed": built["negatives_dropped_as_possibly_listed"],
        "by_split": summarize_heldout(real, cases, results),
        "test_negatives_blocked": [example(c, r) for c, r in test if "listed_name" not in c and r["decision"] == "BLOCK"],
        "test_positives_not_blocked": [example(c, r) for c, r in test if "listed_name" in c and r["decision"] != "BLOCK"],
    }


def main(sdn: str, out: str = "results/real_data.json", sample: int = 30, wikidata: Optional[str] = None) -> dict:
    res = experiments(sdn, sample)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    if wikidata:
        res["heldout"] = heldout(sdn, wikidata)
        Path(out).with_name("heldout.json").write_text(json.dumps(res["heldout"], indent=2, ensure_ascii=False),
                                                       encoding="utf-8")
    return res
