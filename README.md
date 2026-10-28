# Sanctions Fuzzy Screening

Screens the parties on a payment against a sanctions list and a company-ownership graph, and returns BLOCK, REVIEW or CLEAR with the matching entries and a word-by-word explanation.

A sanctioned name can arrive in Latin, Cyrillic, Arabic or Devanagari script, in any word order, with titles and company forms, and in different spellings (Gaddafi, Kadhafi, Qaddafi). Companies owned by listed people are blocked even when their own names are clean.

The bundled demo list is test data, not the OFAC list. It uses the names of real designated people and companies, but the dates of birth, passport numbers and remarks are made up, and some entries and every company in the ownership graph are invented. Production mode uses the real OFAC SDN list instead.

## Features

- Transliteration of Cyrillic, Arabic and Devanagari names, and phonetic codes for spelling variants.
- Word-by-word matching that ignores word order and gives common words like "trading" or "mohammed" little weight.
- Score adjustments for passport, BIC or LEI matches and for date of birth and country.
- OFAC's 50% ownership rule, applied through chains of companies, plus look-through exposure for enhanced due diligence.
- A loader for the real OFAC SDN list and an index that keeps screening fast against all 19,471 entries.
- A screening log where analysts mark hits as cleared or confirmed.

The matching rules are described in [docs/design.md](docs/design.md).

## Quick start

```bash
pip install -r requirements.txt
python -m pytest -q                                      # 30 tests
python -m sancscreen bench
python -m sancscreen screen --name "Виктор Бут" --dob 1967-01-13
python -m sancscreen serve                               # API on http://127.0.0.1:8016 with the demo list
SANCSCREEN_SDN_XML=SDN.XML python -m sancscreen serve    # the same against the real OFAC list
python -m sancscreen realdata --sdn SDN.XML              # test against the real OFAC list
```

To build the container image: `docker build -t sanctions-fuzzy-screening .` (see [docs/runbook.md](docs/runbook.md)).

## API

| Endpoint | Purpose |
|---|---|
| `POST /screen`, `/ubo/check` | screen a party; every result is logged with the caller and the list version |
| `GET /screenings`, `/screenings/{id}` | the screening log |
| `POST /screenings/{id}/review` | mark a hit as cleared or confirmed, with a note |
| `GET /watchlist`, `/bench` | the loaded list and the benchmark |
| `GET /healthz`, `/readyz`, `/metrics` | health, readiness and Prometheus metrics |

API keys carry a role: `screener` for payment systems, `viewer`, `analyst` (screens, reads and reviews) or `monitor`. Create one with `python -m sancscreen.ops keygen`.

## Results

| Test | Result |
|---|---|
| 300 benchmark wires, demo list | F1 98.7% (plain Levenshtein 31.1%); all 45 other-script names matched |
| Real OFAC list, 8,400-case held-out set: unlisted real people / companies wrongly blocked | 5.6% / 7.5% (48% / 75% before tuning) |
| Real OFAC list, held-out set: listed people / companies found | 97.4% / 96.6% |
| Screening time against the full OFAC list | 41 ms per wire (median) |

The held-out set mixes listed names changed by rules (typos, reordering, initials) with real unlisted people and companies from Wikidata; the scorer was tuned on one half and tested on the other. Details are in [docs/evaluation.md](docs/evaluation.md).

## Configuration

| Variable | Purpose |
|---|---|
| `SANCSCREEN_ENV=production` | refuse to start without hashed API keys, a database and the real OFAC list |
| `SANCSCREEN_SDN_XML` | path to OFAC's SDN XML file |
| `SANCSCREEN_API_KEYS` / `SANCSCREEN_KEYS_FILE` | hashed API keys with roles |
| `SANCSCREEN_DATABASE_URL` | `sqlite:///...` or `postgresql://...` |

## Limitations

- Against the full OFAC list, 5.6% of real unlisted people and 7.5% of companies are still blocked, and about a fifth go to REVIEW, which is a lot for analysts.
- One-word listed names inside longer company names ("Air Memphis" against MEMPHIS) still block.
- Only OFAC is loaded. The UN, EU, UK and Indian lists have no loader, and list updates mean replacing the file and restarting.
- Transliteration is partial: no Persian, Urdu, Chinese, Korean or Hebrew.
- The ownership graph is a hand-made example and is looked up by exact name; real use needs registry data.
- The code has not had an independent security review, and it should run in parallel with the bank's current screening before it is relied on.

See [SECURITY.md](SECURITY.md), [docs/threat-model.md](docs/threat-model.md) and [docs/model-card.md](docs/model-card.md).
