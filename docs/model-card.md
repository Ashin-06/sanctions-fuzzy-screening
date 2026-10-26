# Model card: sancscreen name matcher

A rule-based scorer with six tuned constants, not a trained model. Numbers come from the README,
`results/real_data.json` and `results/heldout.json`.

## What it does

Scores a payment party's name against every listed name and a.k.a. that shares a candidate key
with it:
1. Transliterates Cyrillic, Devanagari and Arabic to Latin; strips honorifics and company forms.
2. Gives each token a consonant phonetic code.
3. Pairs query and listed tokens by maximum-weight bipartite assignment (order-free), scoring each
   pair on Jaro-Winkler over letters blended with Jaro-Winkler over codes, weighted by IDF.
4. Combines coverage of both names as a weighted harmonic mean (45 : 55), capped unless a
   distinctive listed token is matched.
5. Adjusts for ID, date-of-birth and country agreement or conflict.

Score ≥ 0.75 is BLOCK, 0.60–0.75 REVIEW, otherwise CLEAR. A strong name pulled below 0.75 only by a
conflicting DOB or country goes to REVIEW. Companies are also checked against an ownership graph
(OFAC 50% rule), but production runs without one: the bundled graph is a toy.

## Intended use

First-line screening of wire parties against OFAC's SDN list, with every BLOCK and REVIEW going
to a sanctions analyst. It must not clear a payment on its own authority where policy requires
human review, and it is not a substitute for the bank's list coverage (UN, EU, UK, MHA).

## Evaluation

**Held-out set against the full OFAC list** (19,471 entries, list of 21 October 2026). Positives are
real listed names changed one way by rule (typo, spelling swap, reorder, dropped middle name,
initial, other company form); negatives are real unlisted Wikidata people and companies. Constants
were tuned on the tune half; these are test-half results:

| Test cases | Cases | BLOCK (on the right entry) | REVIEW | CLEAR |
|---|---|---|---|---|
| listed people, changed one way | 586 | 577 (571) | 3 | 6 |
| listed companies, changed one way | 593 | 576 (573) | 12 | 5 |
| unlisted people | 1,491 | 84 | 257 | 1,150 |
| unlisted companies | 1,431 | 108 | 329 | 994 |

So: 97.4% of changed listed people and 96.6% of listed companies blocked on their entry; 5.6% of
unlisted people and 7.5% of unlisted companies blocked, and another 17% and 23% sent to REVIEW.

**Latency** against the full list with the candidate index: median 41 ms, p95 145 ms per wire
(measured while other jobs ran on the machine). On 30 wires screened both ways, the index gave the
same decision and top entry as a full scan.

**300 hand-written benchmark wires** (in-sample: written with the matcher and inspected against the
real list): on the 20-entry demo list precision 97.4%, recall 100%, F1 98.7%; against the real
list, 99 of 99 wires naming listed parties blocked (98 on the right entry).

## Known failure modes

- One-word listed names plus generic words ("Air Memphis" → MEMPHIS, "Phoenix Aviation" →
  PHOENIX) cause most company false blocks.
- Common Arabic names that share two tokens in another order or role, and near-namesakes, cause
  most person false blocks.
- REVIEW volume is heavy for name-only screening (17–23% of unlisted names).
- Misspelt company forms ("Lymited Liability Company ...") and one-letter swaps in short one-word
  names are the main misses; found on the test half, so not fixed without a fresh test set.
- The candidate index can miss a name whose distinctive token is more than one letter off in
  phonetic code and doesn't share its first three letters.
- Transliteration covers only Cyrillic, Devanagari and Arabic, with tiny lexicons; no Persian,
  Urdu, Chinese, Korean or Hebrew.
- Positives in the held-out set are synthetic changes of listed names, not real payment traffic,
  and include no cross-script cases; its negatives may still hold a few listed parties under other
  spellings.

## Before relying on it

Run it in parallel with the bank's current screening on real payment traffic, compare decisions
case by case with analysts, and set the REVIEW band to the analyst capacity you have.
