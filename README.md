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
- Screening takes 0.2 ms per wire at the median against the 20 entries. It took about 30 ms before phonetic codes were cached and the candidate index below was added.

## Real data

`python -m sancscreen realdata --sdn SDN.XML` loads OFAC's SDN list (the XML export from sanctionslistservice.ofac.treas.gov, public domain) and screens the 300 benchmark wires against it. Results are in `results/real_data.json`. The list published on 21 October 2026 has 19,471 entries (7,519 people, 10,042 entities, 1,568 vessels, 342 aircraft) and 20,192 strong a.k.a.s. OFAC grades another 4,421 a.k.a.s as weak ("BUTT" for Viktor Bout); they are left out unless asked for.

- **Loader** (`realdata.py`). Each entry keeps its a.k.a.s, first date of birth, country codes (nationality, citizenship, addresses and ID issuers, mapped to ISO codes with Babel) and ID numbers. OFAC's ID list also holds gender, establishment dates, websites and sanctions notes; those are dropped.
- **Candidate index** (`matcher.py`). The scorer caps a listed name at 0.58 unless its most distinctive token is matched, so only that token can lead to REVIEW or BLOCK, apart from an exact ID match. Each name is filed under that token's phonetic code, the code with one letter dropped, and its first three letters; each entry is also filed under its IDs. A wire is scored only against entries that share a key: a median of 177 of the 19,471.

| Screening one wire against 19,471 entries | Median | p95 |
|---|---|---|
| every entry, as before (about 1.5 ms each) | about 29 s (estimated) | |
| every entry, phonetic codes cached (30 wires) | 2.0 s | |
| candidate index (300 wires) | 32 ms | 98 ms |

On the 30 wires screened both ways, the index gave the same decision every time and the same top entry on 29. On the 30th the full scan picked a different Lukashenko, whose patronymic is two letters away in phonetic code. On the 20-entry benchmark list the index reproduces every full-scan decision but one: "Nordea Corporate Markets AB" stays CLEAR instead of going to REVIEW against "Al Noor Trading LLC". Pairing three-letter codes with two-letter ones would catch that, but keys like "sn" then hold hundreds of entries.

**The 300 wires against the real list.** The wires were written for the synthetic list. 17 of its 20 entries are real designations (same name, or same full date of birth and surname code); Tariq Al-Rashid, Ahmed Al-Baghdadi and Al-Noor Global Trading are invented.

| Wires that name | Wires | BLOCK | REVIEW | CLEAR |
|---|---|---|---|---|
| a listed person or company | 99 | 94 (87 on the right entry) | 5 | 0 |
| an invented entry | 21 | 17 | 4 | 0 |
| an invented shell company | 30 | 24 | 6 | 0 |
| nobody listed (hard negatives) | 150 | **86** | 58 | 6 |

What the real list shows:
- **The scorer over-blocks at full list size.** 86 of the 150 hard negatives are blocked, against 10 on the 20-entry list: 68 of 88 companies and 18 of 62 people (39 more people go to REVIEW). Most hits are on short listed names that the wire's name contains or resembles: "Blue Horizon Maritime Logistics" → HORIZON, "Al-Nil Global Trading" → NILE, "Gazinvestbank JSC" → GAZ JSC, "Sabanci Industrial Holdings" → SEABASS. 40 of the 86 are on one-word listed names. 62% of the score is how much of the listed name was matched, so a fully matched one-word name scores high whatever else the wire says. A few hits are arguably right: "Korea Daesong General Corporation" was invented as a look-alike, but OFAC lists Korea Daesong General Trading Corporation.
- **Invented names get blocked on real people.** 17 of the 21 wires naming invented entries are blocked, for example "Tariq Al-Rashid" on Amin ABU RASHED.
- **12 of the 99 real-name wires miss their entry.** Arabic "Hasan Nasrallah" is blocked on Nasr AL-ALI (same date of birth) instead of Hasan NASRALLAH. "Gazprombank JSC" is blocked on OOO GAZPROMMASH because the listed "GAZPROMBANK JOINT STOCK COMPANY" spells out its company form, which isn't stripped. Short forms of Viktor Bout ("Victor Bout", "Виктор Бут") go to REVIEW against Abdul Majid BUTT: Bout's rarest listed token is his patronymic, and the scorer insists on the rarest token.
- **Weak a.k.a.s** catch the remaining real names (99 of 99 blocked, 94 on the right entry) and block 8 more hard negatives (94 of 150).

The scorer was not changed after seeing these numbers; only the index keys were tightened for speed, checked against a full scan. Fixing the over-blocking needs a score that also weighs the unmatched part of the wire's name and strips spelled-out company forms. It would then need a fresh test set, since these 300 wires have now been seen.

## Run it

```bash
pip install -r requirements.txt
python -m pytest -q                                      # 14 tests
python -m sancscreen bench
python -m sancscreen screen --name "Виктор Бут" --dob 1967-01-13
python -m sancscreen serve --port 8016                   # API only, no browser console
python -m sancscreen realdata --sdn SDN.XML              # screen against the real OFAC list
```

Endpoints: `POST /screen`, `POST /ubo/check`, `GET /watchlist`, `GET /bench`, `GET /health`. Set `SANCSCREEN_API_KEY` to require it in the `X-API-Key` header. Without the key the server runs open, and `serve` refuses to bind a non-loopback address.

## Limits

- **Not ready for a real list.** The OFAC SDN loader works, but against the full list the scorer blocks most look-alike names (see Real data). The UN, EU and UK lists have no loader, and nothing keeps any list updated.
- **The candidate index can miss** a listed name whose distinctive token is more than one letter away in phonetic code and doesn't share its first three letters, and a REVIEW reached by a strong partial name plus a matching DOB and country.
- **Transliteration is rule-based and partial.** There's no Persian, Urdu, Chinese, Korean or Hebrew, no full Arabic vowel recovery, and the lexicons are tiny.
- **Thresholds and weights are hand-set** and were checked only against the bundled test wires.
- **The ownership graph is a hand-made toy.** Real use needs registry data (ownership chains, nominee and trust structures), and lookup is by exact normalised name.
- **No case management, audit log or list versioning**, and no deployment story (TLS, rate limiting).
