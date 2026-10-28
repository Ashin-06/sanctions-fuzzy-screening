# Evaluation

## Benchmark wires

`python -m sancscreen bench`: 300 hand-written wires against the 20-entry test list.

| Category | Wires | sancscreen | Plain Levenshtein |
|---|---|---|---|
| exact names, with titles and company forms | 30 | 30 | 29 |
| other scripts (Devanagari, Arabic, Cyrillic) | 45 | 45 | 0 |
| reordered words and spelling variants | 45 | 45 | 10 |
| shell companies blocked through ownership | 30 | 30 | 0 |
| hard negatives correctly not blocked | 150 | 146 | 88 |

Precision is 97.4%, recall 100% and F1 98.7%; plain Levenshtein gets 31.1% F1. These are in-sample: the wires were written by the same author as the matcher and have been looked at many times.

The 4 false positives are two company names, each tested twice, that differ from a listed company only in the distinctive word ("Mahogany Air" and "Maharani Air" against "Mahan Air General Aviation Co"). Every positive wire carries the listed date of birth and country; by name alone, 146 of 150 are still blocked. The 50 namesake negatives have a date of birth 20 or more years from the listed one; none is blocked and 48 go to REVIEW.

## The real OFAC list

`python -m sancscreen realdata --sdn SDN.XML` loads OFAC's SDN list (public domain) and screens the benchmark wires against it; results go to `results/real_data.json`. The list published on 21 October 2026 has 19,471 entries (7,519 people, 10,042 entities, 1,568 vessels, 342 aircraft) and 20,192 strong aliases. OFAC marks another 4,421 aliases as weak; they are left out unless requested.

The loader keeps each entry's aliases, first date of birth, country codes and ID numbers.

| Screening one wire against 19,471 entries | Median | p95 |
|---|---|---|
| every entry (about 1.5 ms each) | about 29 s (estimated) | |
| every entry, phonetic codes cached | 1.7 s | |
| candidate index | 41 ms | 145 ms |

On the 30 wires screened both ways, the index gave the same decision and top entry every time.

The first run against the real list showed the scorer was far too loose: 86 of the 150 hard negatives were blocked, against 10 on the small list. Most hits were short listed names contained in or resembling the wire's name ("Blue Horizon Maritime Logistics" against HORIZON), because a fully matched one-word listed name scored high whatever else the wire said.

## Held-out test set

The 300 wires had been looked at against the real list, so a new set of 8,400 cases was built with `realdata --wikidata DIR`:

- Positives: 1,200 listed people and 1,200 listed entities chosen at random, each used under its name or one strong alias and changed one way: unchanged, reordered, a middle name dropped, the first name cut to an initial, a one-letter typo, a spelling swap (ou/u, y/i, kh/h, ph/f and so on) or a different company form.
- Negatives: 3,000 real people and 3,000 real companies from Wikidata (CC0) that are not on the list, from 25 countries including Russia, Iran, Syria, Iraq, North Korea and Venezuela. Names that might be listed were removed first.
- Half the cases carry a country and half the people a date of birth.
- Cases are split into a tuning half (4,299) and a test half (4,101) by a hash of the entry. The scorer's constants were chosen on the tuning half, and the test half was only screened at the end.

Results on the test half (BLOCK on the right entry in brackets):

| Test cases | Cases | Before: BLOCK | REVIEW | CLEAR | After: BLOCK | REVIEW | CLEAR |
|---|---|---|---|---|---|---|---|
| listed people, changed one way | 586 | 568 (545) | 11 | 7 | 577 (571) | 3 | 6 |
| listed companies, changed one way | 593 | 591 (575) | 2 | 0 | 576 (573) | 12 | 5 |
| unlisted people (Wikidata) | 1,491 | 716 | 565 | 210 | 84 | 257 | 1,150 |
| unlisted companies (Wikidata) | 1,431 | 1,070 | 270 | 91 | 108 | 329 | 994 |

Blocks of real unlisted names fell from 48% to 5.6% for people and from 75% to 7.5% for companies. Listed people are found more often (93.0% to 97.4%), listed companies about as often (97.0% to 96.6%). Every count is in `results/heldout.json`.

What remains on the test half:
- 108 companies blocked, 48 of them on one-word listed names where the wire only adds generic words ("Air Memphis" against MEMPHIS).
- 84 people blocked, mostly common Arabic names sharing two words in a different order, and near-namesakes.
- 17% of unlisted people and 23% of unlisted companies still go to REVIEW.
- 20 of 593 listed companies are not blocked on their own entry, mostly because of misspelt company forms. These were found on the test half, so they are not fixed here; fixing them needs a fresh test set.

## Benchmark wires against the real list

17 of the test list's 20 entries are real designations; 3 are invented. In-sample, since these wires were used during the change:

| Wires that name | Wires | BLOCK before → after | REVIEW | CLEAR |
|---|---|---|---|---|
| a listed person or company | 99 | 94 → 99 | 5 → 0 | 0 → 0 |
| an invented entry | 21 | 17 → 4 | 4 → 6 | 0 → 11 |
| an invented shell company | 30 | 24 → 0 | 6 → 23 | 0 → 7 |
| nobody listed (hard negatives) | 150 | 86 → 23 | 58 → 63 | 6 → 64 |
