# Sanctions Fuzzy Screening (`sancscreen`)

This screens the parties on a payment against a sanctions watchlist and a company-ownership graph. A name can arrive in Latin, Cyrillic, Arabic or Devanagari script, in any token order, with honorifics and corporate suffixes, and in different spellings ("Gaddafi" / "Kadhafi" / "Qaddafi"). It returns BLOCK, REVIEW or CLEAR, with the candidates and a token-by-token explanation.

> **The bundled watchlist is synthetic test data, not the OFAC SDN list.** It uses the names of real designated people and companies for realism, but the dates of birth, passport numbers, programme codes and remarks are not authoritative, and some entries and every company in the ownership graph are invented. Do not use it for compliance decisions.

## How it works

**Transliteration and phonetics** (`phonetics.py`).
- Rule tables handle Cyrillic, Devanagari (inherent vowel and word-final schwa deletion, nukta) and Arabic (diacritics stripped, the *al-* article, two common vowel patterns).
- Small hand-written lexicons cover common names. They include the names used in the benchmark; with the lexicons emptied, the cross-script cases still match 43 of 45.
- Each token gets a consonant code: digraphs merged, vowels dropped, doubled letters collapsed, plus a few dialect maps (Gaddafi → Qaddafi, Lukashenka → Lukashenko).
- Honorifics, patronymic particles and corporate suffixes (LLC, OJSC, GmbH, AS, …) are removed before matching.

**Matching** (`matcher.py`).
- Each pair of query and listed tokens is scored on the stronger of Jaro-Winkler on the letters and on the phonetic codes. The Jaro-Winkler implementation is checked against Winkler's published reference values.
- Tokens are paired by an exact maximum-weight bipartite assignment, so token order doesn't matter, and each token is weighted by IDF. Generic words like "trading", "global" or "mohammed" carry little weight.
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
| hard negatives correctly not blocked | 150 | 140 | 88 |

Precision is 93.8%, recall 100% and F1 96.8%. Plain Levenshtein gets 31.1% F1.

The 10 false positives are five company names, each tested twice, that differ from a listed company only in the distinctive word: "Mahogany/Maharani/Mahaba/Maharaja Air General Aviation Co" vs "Mahan Air General Aviation Co", and "Gazstroibank JSC" vs "Gazprombank JSC". A real system would send these to an analyst.

Things to keep in mind:
- The test wires were written by the same author as the matcher and the list, so they mostly exercise the variations the matcher was built to handle.
- Every positive wire carries the listed DOB and country. By name alone, 148 of 150 are still blocked.
- The 50 "innocent homonym" negatives have a DOB 20 or more years away from the listed one. They are not blocked; they now go to REVIEW.
- Screening takes about 30 ms per wire at the median and 225 ms at p95, against 20 entries. Every entry is scored for every wire, and per-entry cost is about 1.5 ms, so a real list with thousands of entries and aliases would take tens of seconds per wire. It needs a candidate index (for example on phonetic codes) first.

## Run it

```bash
pip install -r requirements.txt
python -m pytest -q                                      # 13 tests
python -m sancscreen bench
python -m sancscreen screen --name "Виктор Бут" --dob 1967-01-13
python -m sancscreen serve --port 8016                   # API only, no browser console
```

Endpoints: `POST /screen`, `POST /ubo/check`, `GET /watchlist`, `GET /bench`, `GET /health`. Set `SANCSCREEN_API_KEY` to require it in the `X-API-Key` header. Without the key the server runs open, and `serve` refuses to bind a non-loopback address.

## Limits

- **No real list.** You would need to load the OFAC SDN, UN, EU and UK lists with their aliases, and keep them updated. The loader for that doesn't exist yet.
- **Doesn't scale past small lists** without a candidate index; see above.
- **Transliteration is rule-based and partial.** There's no Persian, Urdu, Chinese, Korean or Hebrew, no full Arabic vowel recovery, and the lexicons are tiny.
- **Thresholds and weights are hand-set** and were checked only against the bundled test wires.
- **The ownership graph is a hand-made toy.** Real use needs registry data (ownership chains, nominee and trust structures), and lookup is by exact normalised name.
- **No case management, audit log or list versioning**, and no deployment story (TLS, rate limiting).
