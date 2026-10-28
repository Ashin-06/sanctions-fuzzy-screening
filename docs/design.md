# Design

## Transliteration and phonetics

`phonetics.py`:
- Rule tables handle Cyrillic, Devanagari (inherent vowel, word-final schwa deletion, nukta) and Arabic (diacritics removed, the al- article, two common vowel patterns).
- Small hand-written lexicons cover common names. They include the names used in the benchmark; with the lexicons emptied, the cross-script cases still match 43 of 45.
- Each token gets a consonant code: digraphs merged, vowels dropped, doubled letters collapsed, plus a few dialect maps (Gaddafi → Qaddafi, Lukashenka → Lukashenko).
- Titles, patronymic particles and company forms (LLC, OJSC, GmbH, AS and spelled-out forms such as JOINT STOCK COMPANY) are removed before matching.

## Matching

`matcher.py`:
- Each pair of query and listed tokens is scored with Jaro-Winkler on the letters, blended with Jaro-Winkler on the phonetic codes. Equal phonetic codes only count as a near-exact match if the spelling is also close (Jaro-Winkler 0.90 or more), because short codes collide on a full list (Green and Guarino, Zaman and Osman). A single letter only matches as an initial. The Jaro-Winkler code is checked against Winkler's published reference values.
- Tokens are paired by an exact maximum-weight assignment, so word order doesn't matter, and each token is weighted by how rare it is. Common words such as "trading", "global" or "mohammed" carry little weight, as do initials and misspelt company forms.
- The name score is a weighted harmonic mean of how much of the wire's name and of the listed name was matched (45:55), so an unmatched distinctive word on either side pulls it down. Pairs below 0.80 similarity don't count, and a matched pair counts (similarity − 0.75) / 0.25. A listed name is capped at 0.58 unless one of its distinctive tokens is matched.
- The score is then adjusted for an exact passport, BIC or LEI match, and for date of birth and country agreeing or conflicting.
- People are only compared with listed people, and companies with listed companies and vessels, when the type is given.
- A score of 0.75 or more is BLOCK and 0.60–0.75 is REVIEW. A name that scores 0.75 on its own but is pulled down by a conflicting date of birth or country goes to REVIEW rather than CLEAR, because the payer supplies those fields.

## Candidate index

Only a listed name's distinctive tokens can lead to REVIEW or BLOCK (apart from an exact ID match). Each listed name is filed under those tokens' phonetic codes, the codes with one letter dropped, and their first three letters; each entry is also filed under its IDs. A wire is only scored against entries that share a key, a median of 304 of OFAC's 19,471 entries.

The index can miss a listed name whose distinctive token is more than one letter away in phonetic code and doesn't share its first three letters.

## Ownership

`ubo.py` resolves company names against an ownership graph by exact normalised name.
- Blocking follows OFAC's 50% rule: a company is blocked when blocked parties, including companies already blocked by the same rule, hold 50% or more of it. It is computed until nothing changes, so cross-holdings are handled.
- Exposure is the proportional look-through stake. 25% or more (the EU beneficial-ownership level) sends the company to enhanced due diligence. India's PML Rules use 10% for companies; the threshold is configurable.
