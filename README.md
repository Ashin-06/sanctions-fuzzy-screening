# Sanctions Fuzzy Screening (`sancscreen`)

This screens the parties on a payment against a sanctions watchlist and a company-ownership graph. A name can arrive in Latin, Cyrillic, Arabic or Devanagari script, in any token order, with honorifics and corporate suffixes, and in different spellings ("Gaddafi" / "Kadhafi" / "Qaddafi"). It returns BLOCK, REVIEW or CLEAR, with the candidates and a token-by-token explanation.

> **The bundled watchlist is synthetic test data, not the OFAC SDN list.** It uses the names of real designated people and companies for realism, but the dates of birth, passport numbers, programme codes and remarks are not authoritative, and some entries and every company in the ownership graph are invented. Do not use it for compliance decisions.

## How it works

**Transliteration and phonetics** (`phonetics.py`).
- Rule tables handle Cyrillic, Devanagari (inherent vowel and word-final schwa deletion, nukta) and Arabic (diacritics stripped, the *al-* article, two common vowel patterns).
- Small hand-written lexicons cover common names. They include the names used in the benchmark; with the lexicons emptied, the cross-script cases still match 43 of 45.
- Each token gets a consonant code: digraphs merged, vowels dropped, doubled letters collapsed, plus a few dialect maps (Gaddafi → Qaddafi, Lukashenka → Lukashenko).
- Honorifics, patronymic particles and corporate suffixes (LLC, OJSC, GmbH, AS, …) are removed before matching, including spelled-out forms (JOINT STOCK COMPANY, OBSHCHESTVO S OGRANICHENNOI OTVETSTVENNOSTYU).

**Matching** (`matcher.py`).
- Each pair of query and listed tokens is scored on Jaro-Winkler over the letters, blended with Jaro-Winkler over the phonetic codes. Equal phonetic codes count as a near-exact match only if the spelling is close too (Jaro-Winkler 0.90 or more): against a full list, short consonant codes collide (Green / Guarino, Zaman / Osman). A single letter only matches as an initial. The Jaro-Winkler implementation is checked against Winkler's published reference values.
- Tokens are paired by an exact maximum-weight bipartite assignment, so token order doesn't matter, and each token is weighted by IDF. Generic words like "trading", "global" or "mohammed" carry little weight, and so do initials and misspelt company forms ("Liited").
- The name score is a weighted harmonic mean of how much of the wire's name and of the listed name was matched (45 : 55). An unmatched distinctive word on either side pulls it down, so a short listed name inside a longer wire name ("Blue Horizon Maritime Logistics" / HORIZON) no longer scores high. Pairs below 0.80 don't count, and a matched pair counts (similarity − 0.75) / 0.25, so a pair at 0.90 counts 0.6. A listed name is capped at 0.58 of its score unless one of its distinctive tokens (IDF at least 85% of its rarest token's) is matched.
- The score is then adjusted for secondary data: an exact passport/BIC/LEI match, DOB agreement or conflict, and country agreement or conflict.
- People are only compared with listed people, and companies with listed companies and vessels (when the type is given).
- Decisions: a score of 0.75 or more is BLOCK (hold the payment); 0.60–0.75 is REVIEW. A name that scores 0.75 on its own but is pulled down by a conflicting DOB or country also goes to REVIEW, not CLEAR, because the payer supplies those fields and a listed person could misstate them.

**Ownership** (`ubo.py`). Company names are resolved against an ownership graph by exact normalised name (no fuzzy lookup).
- *Blocking* follows OFAC's 50% rule as written: a company is blocked when blocked persons, including companies already blocked under the same rule, hold 50% or more of it. Computed as a fixpoint, so cross-holdings are safe.
- *Exposure* is the proportional look-through stake. Exposure of 25% or more (the EU AMLD beneficial-ownership level) sends the company to enhanced due diligence. India's PML Rules use 10% for companies since 2023; the threshold is configurable.

## Results

`python -m sancscreen bench`: 300 hand-written wires against the 20-entry synthetic list.

| Category | Wires | sancscreen | Plain Levenshtein |
|---|---|---|---|
| exact names, with titles and suffixes | 30 | 30 | 29 |
| other scripts (Devanagari, Arabic, Cyrillic) | 45 | 45 | 0 |
| reordered tokens and spelling variants | 45 | 45 | 10 |
| shell companies blocked through ownership | 30 | 30 | 0 |
| hard negatives correctly not blocked | 150 | 146 | 88 |

Precision is 97.4%, recall 100% and F1 98.7% (before the scorer change in "Real data": 93.8%, 100%, 96.8%). Plain Levenshtein gets 31.1% F1. These are in-sample numbers: the wires have been looked at many times, and the new scorer was checked against them before it was accepted.

The 4 false positives are two company names, each tested twice, that differ from a listed company only in the distinctive word: "Mahogany/Maharani Air General Aviation Co" vs "Mahan Air General Aviation Co". A real system would send these to an analyst. "Mahaba/Maharaja Air" and "Gazstroibank JSC" (vs Gazprombank) were blocked before and no longer are.

Things to keep in mind:
- The test wires were written by the same author as the matcher and the list, so they mostly exercise the variations the matcher was built to handle.
- Every positive wire carries the listed DOB and country. By name alone, 146 of 150 are still blocked (148 before). "V. A. But", "T. Al-Rashid", "Oleh V. Derypaska" and "Sharikah Al-Nour Lil-Tijara" go to REVIEW.
- The 50 "innocent homonym" negatives have a DOB 20 or more years away from the listed one. None is blocked; 48 go to REVIEW and 2 are cleared.
- Screening takes 0.2 ms per wire at the median against the 20 entries. It took about 30 ms before phonetic codes were cached and the candidate index below was added.

## Real data

`python -m sancscreen realdata --sdn SDN.XML` loads OFAC's SDN list (the XML export from sanctionslistservice.ofac.treas.gov, public domain) and screens the 300 benchmark wires against it. Results are in `results/real_data.json`. With `--wikidata` it also screens the held-out set described below (`results/heldout.json`). The list published on 21 October 2026 has 19,471 entries (7,519 people, 10,042 entities, 1,568 vessels, 342 aircraft) and 20,192 strong a.k.a.s. OFAC grades another 4,421 a.k.a.s as weak ("BUTT" for Viktor Bout); they are left out unless asked for.

- **Loader** (`realdata.py`). Each entry keeps its a.k.a.s, first date of birth, country codes (nationality, citizenship, addresses and ID issuers, mapped to ISO codes with Babel) and ID numbers. OFAC's ID list also holds gender, establishment dates, websites and sanctions notes; those are dropped.
- **Candidate index** (`matcher.py`). The scorer caps a listed name at 0.58 of its score unless one of its distinctive tokens (IDF at least 85% of its rarest token's) is matched, so only those tokens can lead to REVIEW or BLOCK, apart from an exact ID match. Each name is filed under those tokens' phonetic codes, the codes with one letter dropped, and their first three letters; each entry is also filed under its IDs. A wire is scored only against entries that share a key: a median of 304 of the 19,471 (177 when only the single rarest token was indexed; see below).

| Screening one wire against 19,471 entries | Median | p95 |
|---|---|---|
| every entry, as before (about 1.5 ms each) | about 29 s (estimated) | |
| every entry, phonetic codes cached (30 wires) | 1.7 s | |
| candidate index, before the scorer change (300 wires) | 32 ms | 98 ms |
| candidate index, now (300 wires; token-pair scores cached) | 41 ms | 145 ms |

The last row was measured while other jobs ran on the same machine.

On the 30 wires screened both ways, the index gave the same decision and the same top entry every time. On the 20-entry benchmark list the index reproduces every full-scan decision but one: "Nordea Corporate Markets AB" stays CLEAR instead of going to REVIEW against "Al Noor Trading LLC". Pairing three-letter codes with two-letter ones would catch that, but keys like "sn" then hold hundreds of entries.

**What the first run against the real list showed.** With the scorer as it was (commit d6f8634), 86 of the 150 benchmark hard negatives were blocked, against 10 on the 20-entry list. Most hits were on short listed names that the wire's name contains or resembles: "Blue Horizon Maritime Logistics" → HORIZON, "Al-Nil Global Trading" → NILE, "Gazinvestbank JSC" → GAZ JSC. 62% of the score was how much of the listed name was matched, so a fully matched one-word name scored high whatever else the wire said. "Gazprombank JSC" missed the listed "GAZPROMBANK JOINT STOCK COMPANY", whose spelled-out company form wasn't stripped. Short forms of Viktor Bout went to REVIEW against Abdul Majid BUTT, because the rarest token of his listed name is his patronymic and the scorer insisted on that one token.

**A held-out test set.** The 300 wires had now been looked at against the real list, so they could no longer be used to tune anything. `realdata --wikidata DIR` builds a new set of 8,400 cases:
- *Positives*: 1,200 listed people and 1,200 listed entities drawn at random. Each is used under its name or one strong a.k.a. and changed one way: unchanged, reordered ("BOUT, Viktor"), a middle name dropped, the first name cut to an initial, a one-letter typo, one spelling swap (ou/u, y/i, kh/h, ph/f, w/v, c/k, …) or another company form.
- *Negatives*: real names that aren't listed. These are 3,000 people and 3,000 companies from Wikidata (CC0), drawn from 12,082 people with a birth date (25 countries, including Russia, Iran, Syria, Iraq, North Korea and Venezuela) and 7,330 companies (25 countries). The SPARQL queries are in `realdata.py`. Names that may be listed were dropped: 1,823 people (same words as a listed name, or born the same year as a listed person with the same surname code) and 426 companies (same words, inside a listed name, or containing one of 2+ words). In a random 30 of the blocked test negatives, none looked like the listed entity itself.
- On both sides half the cases carry the country and half the people a date of birth.
- Cases go to a *tune* half (4,299) or a *test* half (4,101) by a hash of the SDN entry or Wikidata item. The scorer's constants were chosen on the tune half; the test half was screened only at the end.

**What changed in the scorer** (`matcher.py`; see "How it works"): the weighted harmonic mean instead of 62% listed-name recall; pairs below 0.80 dropped and near-misses rescaled; equal phonetic codes trusted only with close spelling; initials weighted low and matched only as initials; the prefix rule (gaz / gazinvestbank) removed; spelled-out and misspelt company forms treated as company forms; every distinctive token, not just the single rarest one, in the cap and the index; split compounds joined ("nasr allah" / "nasrallah"). About 35 settings of six constants were tried on the tune half. A phonetic-spelling gate of 0.95 instead of 0.90 blocked 18 fewer tune negatives but lost two of the 99 real-name benchmark wires, so 0.90 was kept. Two small fixes came from the 300-wire check after the first test run: Russian "NK" (oil company) stripped like other company forms, and ties at a capped 1.0 broken on the uncapped score. They moved the test numbers by two listed companies (571 to 573) and one Wikidata company (107 to 108).

**Results on the test half** (decisions; "right entry" means blocked on the listed entry the name came from, or on another entry listed under the same name):

| Test cases | Cases | Before: BLOCK (right entry) | REVIEW | CLEAR | Now: BLOCK (right entry) | REVIEW | CLEAR |
|---|---|---|---|---|---|---|---|
| listed people, changed one way | 586 | 568 (545) | 11 | 7 | 577 (**571**) | 3 | 6 |
| listed companies, changed one way | 593 | 591 (575) | 2 | 0 | 576 (**573**) | 12 | 5 |
| Wikidata people, not listed | 1,491 | **716** | 565 | 210 | **84** | 257 | 1,150 |
| Wikidata companies, not listed | 1,431 | **1,070** | 270 | 91 | **108** | 329 | 994 |

Blocks of real unlisted names fall from 48% to 5.6% for people and from 75% to 7.5% for companies. Listed people are found more often (93.0% → 97.4%, mostly initials 74 → 89 of 97 and dropped middle names 62 → 69 of 72). Listed companies are found about as often as before (97.0% → 96.6%, 2 fewer of 593). The tune half, on which the constants were picked, moved the same way: listed people 557 → 601 of 614, listed companies 579 → 594 of 607, unlisted people blocked 734 → 82 of 1,509, unlisted companies 1,176 → 111 of 1,569. Every count is in `results/heldout.json`, before and after, with the blocked test negatives and missed test positives listed.

What's left on the test half:
- **108 companies blocked**, 48 of them on one-word listed names where the wire only adds generic words: "Air Memphis" → MEMPHIS, "Dolphin Air" → DOLPHIN, "Phoenix Aviation" → PHOENIX. Words like "air" and "aviation" carry little weight, so the extra words don't pull the score down.
- **84 people blocked**, mostly common Arabic names that share two tokens in another order or role ("Ali Yousef" → Yusef Ali MERAJ, "Mohamed Hashem" → Abdul HASHIM), and near-namesakes ("Andriy Shevchenko" → Andrei Anatolyevich SHEVCHENKO).
- **REVIEW stays heavy**: 17% of unlisted people and 23% of unlisted companies, against 38% and 19% before. Name-only screening against 19,000 entries leaves an analyst a lot to look at.
- **20 of 593 listed companies are not blocked on their entry.** Most are misspelt company forms: when a typo breaks a phrase ("Lymited Liability Company Profistail"), the leftover word ("liability") also occurs on the list and counts as rare. One-letter spelling swaps in short one-word names also lose more than before (153 of 165, against 160). These were found on the test half, so they aren't fixed here; fixing them needs a fresh test set.

**The 300 benchmark wires against the real list** (in-sample: these wires were looked at before and during the change). The wires were written for the synthetic list. 17 of its 20 entries are real designations (same name, or same full date of birth and surname code); Tariq Al-Rashid, Ahmed Al-Baghdadi and Al-Noor Global Trading are invented.

| Wires that name | Wires | BLOCK before → now | REVIEW | CLEAR |
|---|---|---|---|---|
| a listed person or company | 99 | 94 (87 on the right entry) → **99 (98)** | 5 → 0 | 0 → 0 |
| an invented entry | 21 | 17 → 4 | 4 → 6 | 0 → 11 |
| an invented shell company | 30 | 24 → 0 | 6 → 23 | 0 → 7 |
| nobody listed (hard negatives) | 150 | **86 → 23** | 58 → 63 | 6 → 64 |

The one real-name wire still off its entry is "Muhammed I. Al-Masri", blocked on a different listed Mohammed AL-MASRI. Arabic "Hasan Nasrallah", "Gazprombank JSC" and the short forms of Viktor Bout are now blocked on the right entry. With OFAC's weak a.k.a.s added, the real names stay at 99 blocked (98 on the right entry) and 25 hard negatives are blocked (94 before).

## Run it

```bash
pip install -r requirements.txt                          # or: pip install -r requirements-dev.lock && pip install -e .
python -m pytest -q                                      # 30 tests
python -m sancscreen bench
python -m sancscreen screen --name "Виктор Бут" --dob 1967-01-13
python -m sancscreen serve                               # API on :8016 with the demo list (open, loopback only)
SANCSCREEN_SDN_XML=SDN.XML python -m sancscreen serve    # the same against the real OFAC list
docker build -t sanctions-fuzzy-screening .              # production image; see docs/runbook.md
python -m sancscreen realdata --sdn SDN.XML              # screen against the real OFAC list
python -m sancscreen realdata --sdn SDN.XML --wikidata wikidata/   # plus the held-out set
```

`--wikidata` expects the `people_*.csv` and `firms_*.csv` query results described in `realdata.py`. Wikidata changes over time, so a fresh download gives a slightly different set.

Endpoints:
- `POST /screen`, `POST /ubo/check`: screen a party. Every result is logged with the caller and the list version, and comes back with a `screening_id`.
- `GET /screenings`, `GET /screenings/{id}`, `POST /screenings/{id}/review`: the screening log. Analysts mark hits `cleared` (false positive) or `confirmed`, with a note.
- `GET /watchlist` (a page at a time), `GET /bench`.
- `GET /healthz`, `GET /readyz`, `GET /metrics`: liveness, readiness and Prometheus metrics.

Each caller gets an API key with a role: `screener` for payment systems, `viewer`, `analyst` (screens, reads and reviews), `monitor` for metrics. Make one with `python -m sancscreen.ops keygen` and list its hash in `SANCSCREEN_API_KEYS` or `SANCSCREEN_KEYS_FILE`. Without keys the server runs open and refuses to bind a non-loopback address. With `SANCSCREEN_ENV=production` it refuses to start without hashed keys, a database and `SANCSCREEN_SDN_XML`; the bundled list and ownership graph are never used in production. Settings, daily list updates and backups are in [docs/runbook.md](docs/runbook.md); what the matcher gets right and wrong is in [docs/model-card.md](docs/model-card.md).

## Limits

- **Not ready for a real list.** On the held-out test against the full OFAC list, the scorer still blocks 5.6% of real unlisted people and 7.5% of companies, and sends another 17% and 23% to REVIEW (see Real data). The UN, EU and UK lists have no loader, and nothing fetches list updates: an operator replaces the file and restarts (see the runbook).
- **The held-out set is synthetic on the positive side.** Listed names were changed by rules (one typo, one spelling swap, …), not taken from real payment traffic, and there are no cross-script positives in it. Its negatives may still include a few listed people or companies under other spellings.
- **The candidate index can miss** a listed name whose distinctive token is more than one letter away in phonetic code and doesn't share its first three letters, and a REVIEW reached by a strong partial name plus a matching DOB and country.
- **Transliteration is rule-based and partial.** There's no Persian, Urdu, Chinese, Korean or Hebrew, no full Arabic vowel recovery, and the lexicons are tiny.
- **Thresholds and weights.** The six scorer constants in `matcher.py` were tuned on the tune half of the held-out set. The BLOCK/REVIEW thresholds, the IDF priors and the DOB/country adjustments are still hand-set.
- **The ownership graph is a hand-made toy.** Real use needs registry data (ownership chains, nominee and trust structures), and lookup is by exact normalised name.
- **Thin case management.** Every screening and review is logged with the list version, but there is no assignment, four-eyes approval or tamper-evident history. TLS is left to the ingress.

## Production readiness

**In place** (see [docs/runbook.md](docs/runbook.md), [docs/threat-model.md](docs/threat-model.md), [docs/model-card.md](docs/model-card.md)):
- Pinned dependencies (`requirements.lock`), `pyproject.toml`, a container image that runs as a non-root user with a health check, and CI (ruff, bandit, pip-audit, tests with coverage).
- Production mode that refuses to start without hashed per-client API keys, a database and the real OFAC list. No default secrets, no public listening without keys, and OFAC's XML parsed with `defusedxml`.
- Roles on keys, per-client rate limits, a body cap, security headers, no CORS by default, and errors that don't echo names or IDs.
- A screening log with the list version on every result and analyst reviews, in SQLite or Postgres with numbered migrations.
- JSON logs with request IDs, `/healthz`, `/readyz`, and Prometheus metrics by decision.

**Still needed before it screens real payments**, none of which code can supply:
- An independent security review and penetration test.
- Validation on the bank's own payment traffic, run in parallel with its current screening. The held-out positives are synthetic changes of listed names, and 5.6–7.5% of real unlisted names are still blocked.
- Sign-off from compliance and the regulators: RBI's KYC and sanctions-screening directions, FEMA for cross-border wires, PMLA record-keeping, and the DPDP Act 2023 for the stored customer names.
- Real integrations: the payment hub and SWIFT gateway, automated daily list updates (OFAC plus the UN, EU, UK and MHA lists, which have no loader yet), a real ownership data source, and the bank's case management system.
- Managed infrastructure (a KMS or HSM for key material, encrypted storage, retention rules), and an on-call team with SLOs: screening sits in the payment path.
