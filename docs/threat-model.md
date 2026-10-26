# Threat model

What the screening service protects, from whom, and what is still open. Written for the 1.0.0
code; nobody independent has reviewed it.

## What it protects

| Asset | Where it lives |
|---|---|
| Wire parties sent for screening (names, dates of birth, IDs, countries) | request bodies; stored in the screening log |
| Screening results and analyst decisions | `screenings`, `screening_reviews` tables |
| The watchlist in use | `SANCSCREEN_SDN_XML`, loaded at startup; its hash is the list version on every result |
| API keys | callers hold the key; the service holds only SHA-256 hashes |

The two failures that matter: a listed party gets through (sanctions breach), and the record of
what was screened, against which list, and who cleared it, is lost or altered.

## Trust boundaries

```
payment hub ──► sancscreen API ──► database (screening log, reviews)
analyst     ──►       ▲
                      └── SDN.XML from OFAC (file mounted read-only)
```

1. **Callers → API.** `screener` keys can screen and nothing else; `analyst` keys also review.
   The reviewer's name comes from the key.
2. **OFAC file → service.** Treated as untrusted input: parsed with `defusedxml` (no entity
   expansion, no external entities), and its hash is recorded with every result.
3. **API → database.** Holds customer names and screening outcomes in plain form.

## Threats and what stops them

| Threat | Mitigation | Residual risk |
|---|---|---|
| A listed party gets through on a spelling variant | Transliteration, phonetic codes, token-order-free matching, ID matches; REVIEW band | **Misses exist.** On the held-out set 2.6% of changed listed people and 3.4% of listed companies were not blocked on their entry (see model card). |
| Screening against a stale or demo list | Production refuses to start without `SANCSCREEN_SDN_XML`; the list hash is on every result and in the log; `/readyz` checks it loaded | Nothing fetches or ages the list: an operator must replace the file and restart at least daily |
| Tampered list file (entries removed) | Mount read-only from a controlled location; compare the logged `list_version` with OFAC's published file | The service can't verify OFAC's signature (OFAC doesn't sign the XML) |
| Malicious XML (billion laughs, external entities) | `defusedxml` refuses both; the service won't start on a bad file | — |
| An insider clears a true hit | Every review is stored with the reviewer and a note; history is kept | Reviews aren't tamper-evident against someone with database write access |
| Payer misstates DOB or country to escape a match | A strong name match pulled below BLOCK by a conflicting DOB or country goes to REVIEW, not CLEAR | Name-only variants beyond the matcher's rules |
| Data leak of screened names | API keys with roles; no CORS; validation errors don't echo input; 404s don't echo names | Anyone with database access sees every screened party; set retention per DPDP and your regulator |
| Flooding | 64 KB body cap, per-client token bucket, candidate index keeps a screening around 40 ms | Rate limit is per process |
| Stolen API key | Per-client keys, revocable by removing the hash and restarting | A stolen `screener` key can probe which names are listed (OFAC's list is public anyway) |

## Not covered

- UN, EU, UK and Indian (MHA / UAPA) lists: no loaders yet.
- Beneficial ownership on real data: production runs without an ownership graph.
- TLS (terminate it at the ingress).
