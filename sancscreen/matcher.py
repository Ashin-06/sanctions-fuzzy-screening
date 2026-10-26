"""
Order-Invariant IDF-Weighted Bipartite Token Matcher & Secondary Identifier Resolver.

Combines:
1. Corpus + Prior Inverse Document Frequency (IDF) token weighting
2. Jaro-Winkler character similarity + Consonant Phonetic Code similarity + Initial alignment
3. Exact optimal maximum-weight bipartite token matching (order-invariant)
4. Secondary identifier reconciliation (DOB exact/year match, Nationality/Country ISO, Passport/BIC/LEI)
5. Naive Levenshtein baseline for benchmark comparison
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from sancscreen.phonetics import (
    detect_script,
    normalize_tokens,
    phonetic_code,
    transliterate,
)

# ---------------------------------------------------------------------------
# Ubiquitous Commercial & Personal Name Priors (Low IDF Weight)
# ---------------------------------------------------------------------------
# In real SWIFT traffic, generic corporate terms and ultra-common given names
# appear in millions of wires and must carry lower discriminative weight than
# rare family names or distinctive entity identifiers.
LOW_IDF_PRIORS: Dict[str, float] = {
    # Generic commercial / corporate words
    "trading": 0.25,
    "international": 0.25,
    "global": 0.28,
    "general": 0.28,
    "import": 0.25,
    "export": 0.25,
    "imports": 0.25,
    "exports": 0.25,
    "logistics": 0.30,
    "maritime": 0.32,
    "shipping": 0.30,
    "holdings": 0.28,
    "holding": 0.28,
    "group": 0.25,
    "enterprise": 0.28,
    "enterprises": 0.28,
    "commercial": 0.28,
    "services": 0.25,
    "service": 0.25,
    "solutions": 0.28,
    "industrial": 0.30,
    "industries": 0.30,
    "investment": 0.28,
    "investments": 0.28,
    "capital": 0.30,
    "finance": 0.30,
    "financial": 0.30,
    "bank": 0.35,
    "energy": 0.35,
    "petroleum": 0.38,
    "oil": 0.38,
    "gas": 0.38,
    "aviation": 0.38,
    "air": 0.35,
    "lines": 0.32,
    "transport": 0.30,
    "transportation": 0.30,
    "supply": 0.30,
    "supplies": 0.30,
    "construction": 0.32,
    "development": 0.30,
    "tijarah": 0.28,
    "dawliyah": 0.28,
    "alamiyah": 0.28,
    # Ultra-common first/given names across jurisdictions
    "mohammed": 0.38,
    "muhammad": 0.38,
    "mohamed": 0.38,
    "mohammad": 0.38,
    "ahmed": 0.42,
    "ahmad": 0.42,
    "ali": 0.42,
    "hassan": 0.48,
    "hasan": 0.48,
    "hussein": 0.48,
    "husein": 0.48,
    "ibrahim": 0.50,
    "abdullah": 0.48,
    "abdul": 0.40,
    "rahman": 0.48,
    "omar": 0.52,
    "khalid": 0.52,
    "kumar": 0.38,
    "singh": 0.40,
    "sharma": 0.45,
    "patel": 0.45,
    "rajesh": 0.48,
    "john": 0.42,
    "david": 0.42,
    "michael": 0.42,
    "alexander": 0.52,
    "aleksandr": 0.52,
    "sergei": 0.55,
    "sergey": 0.55,
    "vladimir": 0.55,
    "dmitry": 0.55,
    "ivan": 0.50,
}

# Company forms are stripped before matching, but a misspelt one ("Liited", "Joint Stocck")
# would otherwise count as a rare, distinctive word
FORM_WORDS = ("company", "limited", "corporation", "incorporated", "joint", "stock", "liability",
              "aktsionernoe", "obshchestvo", "ogranichennoi", "otvetstvennostyu")
FORM_WORD_WEIGHT = 0.20


@dataclass
class SDNEntry:
    """Represents an entity or individual on a Sanctions Watchlist (OFAC SDN / UN / EU)."""
    sdn_id: str
    name: str
    entity_type: str = "individual"  # "individual" | "entity" | "vessel"
    program: str = "OFAC-SDN"
    aliases: List[str] = field(default_factory=list)
    dob: Optional[str] = None  # YYYY-MM-DD or YYYY
    countries: List[str] = field(default_factory=list)  # ISO-2 codes e.g. ["RU"], ["IR"], ["SY"]
    identifiers: List[str] = field(default_factory=list)  # Passports, National IDs, BICs, LEIs
    remarks: str = ""


@dataclass
class ScreeningQuery:
    """Represents an incoming wire transfer party (originator, beneficiary, or intermediary)."""
    query_id: str
    name: str
    entity_type: Optional[str] = None
    dob: Optional[str] = None
    country: Optional[str] = None
    identifier: Optional[str] = None  # Passport, National ID, BIC, LEI
    amount_usd: float = 0.0
    currency: str = "USD"


@dataclass
class TokenAlignment:
    """Details of a single aligned token pair in the bipartite graph."""
    query_token: str
    sdn_token: str
    query_phonetic: str
    sdn_phonetic: str
    char_similarity: float
    phonetic_similarity: float
    combined_similarity: float
    idf_weight: float


@dataclass
class MatchCandidate:
    """Detailed match breakdown against a single SDN entry."""
    sdn_id: str
    sdn_name: str
    matched_alias: str
    program: str
    entity_type: str
    raw_name_score: float
    secondary_adjustment: float
    final_score: float
    token_alignments: List[TokenAlignment] = field(default_factory=list)
    id_exact_match: bool = False
    dob_status: str = "not_provided"  # "exact_match", "year_match", "conflict", "not_provided"
    country_status: str = "not_provided"  # "match", "mismatch", "not_provided"
    explanation: str = ""


# ---------------------------------------------------------------------------
# String Distance & Similarity Primitives
# ---------------------------------------------------------------------------
def levenshtein_distance(s1: str, s2: str) -> int:
    """Compute exact Levenshtein edit distance between two strings."""
    if s1 == s2:
        return 0
    if not s1:
        return len(s2)
    if not s2:
        return len(s1)
    if len(s1) < len(s2):
        s1, s2 = s2, s1

    prev = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1, start=1):
        curr = [i]
        for j, c2 in enumerate(s2, start=1):
            ins = curr[j - 1] + 1
            delete = prev[j] + 1
            sub = prev[j - 1] + (0 if c1 == c2 else 1)
            curr.append(min(ins, delete, sub))
        prev = curr
    return prev[-1]


def naive_levenshtein_similarity(s1: str, s2: str) -> float:
    """
    Standard character-level normalized Levenshtein similarity on raw lowercase strings.
    Used as the legacy baseline in benchmarks.
    """
    a = re.sub(r"\s+", " ", s1.strip().lower())
    b = re.sub(r"\s+", " ", s2.strip().lower())
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    dist = levenshtein_distance(a, b)
    return 1.0 - (dist / max(len(a), len(b)))


def jaro_similarity(s1: str, s2: str) -> float:
    """Compute Jaro similarity between two strings in [0.0, 1.0]."""
    if s1 == s2:
        return 1.0
    len1, len2 = len(s1), len(s2)
    if len1 == 0 or len2 == 0:
        return 0.0

    match_distance = max(len1, len2) // 2 - 1
    if match_distance < 0:
        match_distance = 0

    s1_matches = [False] * len1
    s2_matches = [False] * len2

    matches = 0
    transpositions = 0

    for i in range(len1):
        start = max(0, i - match_distance)
        end = min(i + match_distance + 1, len2)
        for j in range(start, end):
            if s2_matches[j]:
                continue
            if s1[i] != s2[j]:
                continue
            s1_matches[i] = True
            s2_matches[j] = True
            matches += 1
            break

    if matches == 0:
        return 0.0

    k = 0
    for i in range(len1):
        if not s1_matches[i]:
            continue
        while not s2_matches[k]:
            k += 1
        if s1[i] != s2[k]:
            transpositions += 1
        k += 1

    return (
        (matches / len1)
        + (matches / len2)
        + ((matches - transpositions / 2.0) / matches)
    ) / 3.0


def jaro_winkler(s1: str, s2: str, prefix_weight: float = 0.1) -> float:
    """Compute Jaro-Winkler similarity between two strings in [0.0, 1.0]."""
    j_sim = jaro_similarity(s1, s2)
    if j_sim <= 0.0:
        return 0.0

    prefix_len = 0
    max_prefix = min(4, len(s1), len(s2))
    for i in range(max_prefix):
        if s1[i] == s2[i]:
            prefix_len += 1
        else:
            break

    return min(1.0, j_sim + prefix_len * prefix_weight * (1.0 - j_sim))


# Tuned on the "tune" half of the held-out set in realdata.py (README, "Real data")
MIN_PAIR_SIMILARITY = 0.80  # weaker token pairs don't count as matched
SIM_FLOOR = 0.75            # a matched pair counts (similarity - floor) / (1 - floor): 0.90 counts 0.6
PHONETIC_MIN_CHAR = 0.90    # equal phonetic codes lift a pair to 0.95+ only from this spelling similarity
QUERY_WEIGHT = 0.45         # weight of the wire's own name against the listed name in the score
DISTINCTIVE_RATIO = 0.85    # listed tokens weighing this share of the rarest one's weight count as distinctive
INITIAL_WEIGHT = 2.0        # a single letter says little about whose name it is


@lru_cache(maxsize=500_000)  # pure; the same pairs recur across aliases and wires
def token_pair_similarity(q_tok: str, s_tok: str, q_phon: str, s_phon: str) -> Tuple[float, float, float]:
    """
    Compute hybrid similarity between two normalized Latin tokens and their phonetic codes.
    Returns (char_similarity, phonetic_similarity, combined_similarity).
    """
    if q_tok == s_tok:
        return 1.0, 1.0, 1.0

    char_sim = jaro_winkler(q_tok, s_tok)
    phon_sim = jaro_winkler(q_phon, s_phon) if (q_phon and s_phon) else 0.0

    # A single letter only matches as an initial ("v" -> "viktor")
    if min(len(q_tok), len(s_tok)) == 1:
        return char_sim, phon_sim, 0.84 if q_tok[0] == s_tok[0] else 0.0

    if q_phon and q_phon == s_phon:
        phon_sim = 1.0
    # Hybrid blend of character Jaro-Winkler and phonetic Jaro-Winkler
    hybrid = 0.55 * char_sim + 0.45 * phon_sim
    # Phonetic similarity leads only if the spelling is close too: against a full list short consonant
    # skeletons collide (Green / Guarino, Zaman / Osman)
    if char_sim >= PHONETIC_MIN_CHAR:
        if phon_sim == 1.0:  # same skeleton: Bout / But, Mohammed / Muhammad
            return char_sim, phon_sim, max(char_sim, 0.95 + 0.05 * char_sim)
        if phon_sim >= 0.88 and char_sim >= 0.70:  # cross-dialect transliterations
            hybrid = max(hybrid, 0.72 * phon_sim + 0.28 * char_sim)

    return char_sim, phon_sim, min(1.0, max(char_sim, hybrid))


def _solve_bipartite_assignment(sim_matrix: List[List[float]]) -> List[Tuple[int, int, float]]:
    """
    Find exact maximum-weight bipartite matching between m query tokens and n target tokens.
    Uses dynamic programming with bitmask for small token sets (m, n <= 10) and greedy
    fallback for larger sets.
    """
    m = len(sim_matrix)
    if m == 0:
        return []
    n = len(sim_matrix[0])
    if n == 0:
        return []

    # Transpose if m > n so the bitmask is over the larger dimension <= 12
    transposed = False
    if m > n:
        sim_matrix = [[sim_matrix[i][j] for i in range(m)] for j in range(n)]
        m, n = n, m
        transposed = True

    if n <= 12:
        memo: Dict[Tuple[int, int], Tuple[float, List[Tuple[int, int, float]]]] = {}

        def dp(i: int, mask: int) -> Tuple[float, List[Tuple[int, int, float]]]:
            if i == m:
                return 0.0, []
            state = (i, mask)
            if state in memo:
                return memo[state]

            # Option 1: leave row i unmatched
            best_val, best_pairs = dp(i + 1, mask)

            # Option 2: match row i with an available column j
            for j in range(n):
                if not (mask & (1 << j)):
                    w = sim_matrix[i][j]
                    if w > 0.0:
                        sub_val, sub_pairs = dp(i + 1, mask | (1 << j))
                        cand_val = w + sub_val
                        if cand_val > best_val:
                            best_val = cand_val
                            best_pairs = [(i, j, w)] + sub_pairs

            memo[state] = (best_val, best_pairs)
            return best_val, best_pairs

        _, pairs = dp(0, 0)
    else:
        # Greedy max-weight matching for very long token strings
        all_edges = [
            (sim_matrix[i][j], i, j)
            for i in range(m)
            for j in range(n)
            if sim_matrix[i][j] > 0.0
        ]
        all_edges.sort(reverse=True)
        used_i: Set[int] = set()
        used_j: Set[int] = set()
        pairs = []
        for w, i, j in all_edges:
            if i not in used_i and j not in used_j:
                used_i.add(i)
                used_j.add(j)
                pairs.append((i, j, w))

    if transposed:
        return [(j, i, w) for (i, j, w) in pairs]
    return pairs


def _normalize_id(raw_id: Optional[str]) -> str:
    if not raw_id:
        return ""
    return re.sub(r"[^A-Z0-9]", "", raw_id.upper())


def _extract_year(dob: Optional[str]) -> Optional[int]:
    if not dob:
        return None
    m = re.search(r"\b(19\d{2}|20\d{2})\b", dob)
    return int(m.group(1)) if m else None


def _blocking_keys(token: str, query: bool = False) -> Set[str]:
    """
    First three letters and the phonetic code, plus keys that pair codes one letter longer or
    shorter (Prigozhin prgsn / Prigozin prgn): a listed code of 4+ letters is also filed under
    each one-letter deletion ("d:"), and a query looks up its own code there and its deletions
    among the listed codes. Deleting on both sides would also pair substitutions, and pairing
    3-letter with 2-letter codes (Nordea nrd / Noor nr), but short codes like "sn" collect
    hundreds of entries each.
    """
    code = phonetic_code(token)
    keys = {"t:" + token[:3]}
    if code:
        keys.add("p:" + code)
        dels = {code[:i] + code[i + 1:] for i in range(len(code))} if len(code) >= 4 else set()
        if query:
            if len(code) >= 3:
                keys.add("d:" + code)
            keys.update("p:" + d for d in dels)
        else:
            keys.update("d:" + d for d in dels)
    return keys


def _join_split(tokens: List[str], other: List[str]) -> List[str]:
    """Merge adjacent tokens that `other` writes as one word ("nasr allah" / "nasrallah")."""
    out: List[str] = []
    for t in tokens:
        if out and out[-1] + t in other and out[-1] not in other:
            out[-1] += t
        else:
            out.append(t)
    return out


@lru_cache(maxsize=100_000)
def _looks_like_form_word(token: str) -> bool:
    return any(jaro_winkler(token, f) >= 0.90 for f in FORM_WORDS)


def types_compatible(query_type: Optional[str], entry_type: str) -> bool:
    """A person is only compared with listed persons, a company with listed entities/vessels."""
    if not query_type:
        return True
    return (query_type.lower() == "individual") == (entry_type.lower() == "individual")


class SanctionsMatcher:
    """
    Order-Invariant IDF-Weighted Bipartite Token Matcher with Secondary Identifier Resolution.
    """

    def __init__(self, watchlist: Sequence[SDNEntry], alert_threshold: float = 0.75) -> None:
        self.watchlist: List[SDNEntry] = list(watchlist)
        self.alert_threshold: float = alert_threshold
        self.token_idf: Dict[str, float] = {}
        self.phonetic_idf: Dict[str, float] = {}
        self._build_idf_index()
        self.candidate_index: Dict[str, Set[int]] = {}
        self._build_candidate_index()

    def _build_idf_index(self) -> None:
        """Compute empirical corpus IDF combined with domain priors."""
        doc_freq_tok: Dict[str, int] = {}
        doc_freq_phon: Dict[str, int] = {}
        total_docs = max(1, len(self.watchlist))

        for entry in self.watchlist:
            seen_toks: Set[str] = set()
            seen_phons: Set[str] = set()
            all_names = [entry.name] + list(entry.aliases)
            for nm in all_names:
                for tok in normalize_tokens(nm, strip_affixes=True):
                    seen_toks.add(tok)
                    pc = phonetic_code(tok)
                    if pc:
                        seen_phons.add(pc)
            for t in seen_toks:
                doc_freq_tok[t] = doc_freq_tok.get(t, 0) + 1
            for p in seen_phons:
                doc_freq_phon[p] = doc_freq_phon.get(p, 0) + 1

        self.token_idf = {}
        for tok, df in doc_freq_tok.items():
            empirical = math.log((total_docs + 1.0) / (df + 0.5)) + 1.0
            if tok in LOW_IDF_PRIORS:
                self.token_idf[tok] = min(empirical, LOW_IDF_PRIORS[tok] * 2.0)
            else:
                self.token_idf[tok] = empirical

        self.phonetic_idf = {}
        for pc, df in doc_freq_phon.items():
            self.phonetic_idf[pc] = math.log((total_docs + 1.0) / (df + 0.5)) + 1.0

    def _build_candidate_index(self) -> None:
        """
        Blocking index so a query is scored against tens of entries, not the whole list.

        A name reaches REVIEW or BLOCK only if one of the listed name's distinctive tokens (IDF
        within DISTINCTIVE_RATIO of its highest) is matched (the distinctive-token cap in
        _score_token_sets holds it to 0.58 otherwise) or an ID matches exactly. So each name is
        indexed under the blocking keys of those tokens, and each entry under its IDs. Names whose
        top token is generic (weight < 0.80, no cap) are indexed under every token. A strong partial
        name plus an exact DOB and country can still reach REVIEW without a distinctive token; the
        index misses those.
        """
        for k, entry in enumerate(self.watchlist):
            for nm in [entry.name] + list(entry.aliases):
                toks = normalize_tokens(nm, strip_affixes=True)
                if not toks:
                    continue
                weights = [self.get_token_weight(t) for t in toks]
                top = max(weights)
                for t in (t for t, w in zip(toks, weights) if top < 0.80 or w >= DISTINCTIVE_RATIO * top):
                    for key in _blocking_keys(t):
                        self.candidate_index.setdefault(key, set()).add(k)
            for raw_id in entry.identifiers:
                if _normalize_id(raw_id):
                    self.candidate_index.setdefault("id:" + _normalize_id(raw_id), set()).add(k)

    def candidates(self, query: ScreeningQuery) -> List[SDNEntry]:
        keys = {key for t in normalize_tokens(query.name, strip_affixes=True) for key in _blocking_keys(t, query=True)}
        if _normalize_id(query.identifier):
            keys.add("id:" + _normalize_id(query.identifier))
        hits: Set[int] = set()
        for key in keys:
            hits |= self.candidate_index.get(key, set())
        return [self.watchlist[k] for k in sorted(hits)]

    def get_token_weight(self, token: str) -> float:
        """Return discriminative IDF weight for a normalized Latin token."""
        if not token:
            return 0.1
        if len(token) == 1:
            return INITIAL_WEIGHT
        if token in LOW_IDF_PRIORS:
            return LOW_IDF_PRIORS[token]
        if token in self.token_idf:
            return self.token_idf[token]
        if _looks_like_form_word(token):
            return FORM_WORD_WEIGHT
        # Unseen token: check if its phonetic code is a known low-IDF prior
        pc = phonetic_code(token)
        for prior_tok, prior_w in LOW_IDF_PRIORS.items():
            if phonetic_code(prior_tok) == pc and len(pc) >= 2:
                return prior_w
        # Rare/unseen token gets high default IDF weight
        default_high = math.log(max(2, len(self.watchlist)) + 1.0) + 1.0
        return default_high

    def _score_token_sets(
        self,
        q_tokens: List[str],
        s_tokens: List[str],
    ) -> Tuple[float, List[TokenAlignment]]:
        """
        Compute Order-Invariant IDF-Weighted Bipartite similarity between
        query tokens and target SDN name tokens.
        """
        if not q_tokens or not s_tokens:
            return 0.0, []
        q_tokens, s_tokens = _join_split(q_tokens, s_tokens), _join_split(s_tokens, q_tokens)

        q_phons = [phonetic_code(t) for t in q_tokens]
        s_phons = [phonetic_code(t) for t in s_tokens]
        q_weights = [self.get_token_weight(t) for t in q_tokens]
        s_weights = [self.get_token_weight(t) for t in s_tokens]

        m, n = len(q_tokens), len(s_tokens)
        raw_sims: List[List[ Tuple[float, float, float] ]] = [
            [token_pair_similarity(q_tokens[i], s_tokens[j], q_phons[i], s_phons[j]) for j in range(n)]
            for i in range(m)
        ]

        # Weight each bipartite edge by average IDF weight * similarity (only for sim >= MIN_PAIR_SIMILARITY)
        weighted_matrix: List[List[float]] = []
        for i in range(m):
            row: List[float] = []
            for j in range(n):
                _, _, comb = raw_sims[i][j]
                if comb >= MIN_PAIR_SIMILARITY:
                    edge_w = 0.5 * (q_weights[i] + s_weights[j]) * comb
                else:
                    edge_w = 0.0
                row.append(edge_w)
            weighted_matrix.append(row)

        pairs = _solve_bipartite_assignment(weighted_matrix)

        alignments: List[TokenAlignment] = []
        matched_s_weight = 0.0
        matched_q_weight = 0.0
        matched_s_indices: Set[int] = set()

        for i, j, _ in pairs:
            c_sim, p_sim, comb_sim = raw_sims[i][j]
            avg_idf = 0.5 * (q_weights[i] + s_weights[j])
            alignments.append(
                TokenAlignment(
                    query_token=q_tokens[i],
                    sdn_token=s_tokens[j],
                    query_phonetic=q_phons[i],
                    sdn_phonetic=s_phons[j],
                    char_similarity=round(c_sim, 4),
                    phonetic_similarity=round(p_sim, 4),
                    combined_similarity=round(comb_sim, 4),
                    idf_weight=round(avg_idf, 4),
                )
            )
            # Against a full list nearly every rare token has a neighbour at 0.85, so near-misses count little
            effective_sim = (comb_sim - SIM_FLOOR) / (1 - SIM_FLOOR)
            matched_s_weight += s_weights[j] * effective_sim
            matched_q_weight += q_weights[i] * effective_sim
            matched_s_indices.add(j)

        total_s_weight = sum(s_weights)
        total_q_weight = sum(q_weights)

        sdn_recall = matched_s_weight / total_s_weight if total_s_weight > 0 else 0.0
        query_precision = matched_q_weight / total_q_weight if total_q_weight > 0 else 0.0

        # Weighted harmonic mean, so an unmatched distinctive word on either side pulls the score down:
        # a short listed name inside a longer wire name ("Blue Horizon Maritime" / HORIZON) scores low
        if sdn_recall and query_precision:
            score = 1.0 / (QUERY_WEIGHT / query_precision + (1 - QUERY_WEIGHT) / sdn_recall)
        else:
            score = 0.0

        # Subset boost: if query has >= 2 tokens and ALL query tokens matched strongly (>= 0.90)
        # AND a distinctive token of the SDN name was matched (e.g. omitting a middle patronymic)
        top_weight = max(s_weights)
        highest_idf_matched = any(
            s_weights[j] >= DISTINCTIVE_RATIO * top_weight and raw_sims[i][j][2] >= 0.85 for i, j, _ in pairs
        )
        if m >= 2 and len(alignments) == m and all(a.combined_similarity >= 0.88 for a in alignments) and highest_idf_matched:
            score = max(score, 0.88 * query_precision + 0.12 * sdn_recall)

        # Distinctive-token safeguard:
        # If none of the SDN entry's most distinctive (highest-IDF) tokens was matched,
        # or if only generic low-IDF tokens (< 0.60) matched, cap the score to prevent
        # false positives on "Global Trading LLC" or "Mohammed Ali".
        max_matched_idf = max((s_weights[j] for j in matched_s_indices), default=0.0)
        if not highest_idf_matched and top_weight >= 0.80:
            score = min(score, 0.58 * score)
        if max_matched_idf <= 0.55 and len(alignments) < max(m, n):
            score = min(score, 0.48)

        return min(1.0, max(0.0, score)), alignments

    def _evaluate_secondary_identifiers(
        self,
        query: ScreeningQuery,
        entry: SDNEntry,
        raw_name_score: float,
        alignments: List[TokenAlignment],
    ) -> Tuple[float, bool, str, str, List[str]]:
        """
        Compute score adjustment from secondary identifiers:
        - Passport / National ID / BIC / LEI exact match
        - Date of Birth (DOB) exact match, year match, or conflict suppression
        - Country / Nationality ISO match or conflict
        """
        adj = 0.0
        id_exact = False
        dob_status = "not_provided"
        country_status = "not_provided"
        notes: List[str] = []

        # 1. Exact Identifier Match (Passport / National ID / BIC / LEI)
        q_id = _normalize_id(query.identifier)
        s_ids = {_normalize_id(x) for x in entry.identifiers if _normalize_id(x)}
        if q_id and s_ids:
            if q_id in s_ids:
                id_exact = True
                adj += 0.35
                notes.append(f"Exact ID match ({q_id})")
            else:
                adj -= 0.08
                notes.append("ID number differs")

        # 2. Date of Birth (DOB) Verification
        if query.dob and entry.dob:
            q_dob = query.dob.strip()
            s_dob = entry.dob.strip()
            if q_dob == s_dob:
                dob_status = "exact_match"
                adj += 0.10
                notes.append(f"DOB exact match ({q_dob})")
            else:
                q_yr = _extract_year(q_dob)
                s_yr = _extract_year(s_dob)
                if q_yr is not None and s_yr is not None:
                    diff = abs(q_yr - s_yr)
                    if diff <= 1:
                        dob_status = "year_match"
                        adj += 0.04
                        notes.append(f"DOB year match ({q_yr} vs {s_yr})")
                    elif diff <= 4:
                        dob_status = "conflict"
                        adj -= 0.16
                        notes.append(f"DOB near-conflict ({q_yr} vs {s_yr})")
                    else:
                        dob_status = "conflict"
                        adj -= 0.38
                        notes.append(f"DOB conflict ({q_yr} vs {s_yr}, Δ={diff}y)")

        # 3. Country / Nationality ISO Code Verification
        if query.country and entry.countries:
            q_country = query.country.strip().upper()
            s_countries = {c.strip().upper() for c in entry.countries if c.strip()}
            if q_country in s_countries:
                country_status = "match"
                adj += 0.05
                notes.append(f"Country match ({q_country})")
            else:
                country_status = "mismatch"
                # If DOB also conflicts, or if the matched tokens are all common/low-IDF names,
                # apply strong country mismatch suppression.
                avg_idf = (
                    sum(a.idf_weight for a in alignments) / len(alignments)
                    if alignments else 0.0
                )
                if dob_status == "conflict":
                    adj -= 0.15
                    notes.append(f"Country mismatch ({q_country} vs {sorted(s_countries)}) with DOB conflict")
                elif dob_status == "not_provided" and avg_idf < 0.70:
                    adj -= 0.22
                    notes.append(f"Country mismatch ({q_country} vs {sorted(s_countries)}) on common name")
                elif not id_exact and dob_status not in ("exact_match", "year_match") and q_id and s_ids and q_id not in s_ids:
                    adj -= 0.15
                    notes.append(f"Country & ID mismatch ({q_country})")

        return adj, id_exact, dob_status, country_status, notes

    def match_entry(self, query: ScreeningQuery, entry: SDNEntry) -> MatchCandidate:
        """Score a ScreeningQuery against a single SDNEntry across its primary name and all aliases."""
        q_tokens = normalize_tokens(query.name, strip_affixes=True)
        candidate_names = [entry.name] + list(entry.aliases)

        best_raw = -1.0
        best_alias = entry.name
        best_alignments: List[TokenAlignment] = []

        for cand_name in candidate_names:
            s_tokens = normalize_tokens(cand_name, strip_affixes=True)
            raw_score, aligns = self._score_token_sets(q_tokens, s_tokens)
            if raw_score > best_raw:
                best_raw = raw_score
                best_alias = cand_name
                best_alignments = aligns

        best_raw = max(0.0, best_raw)
        adj, id_exact, dob_status, country_status, notes = self._evaluate_secondary_identifiers(
            query, entry, best_raw, best_alignments
        )

        if id_exact:
            final_score = max(0.98, min(1.0, best_raw + adj))
        else:
            final_score = max(0.0, min(1.0, best_raw + adj))

        script = detect_script(query.name)
        trans_q = transliterate(query.name)
        expl_parts = [
            f"script={script}",
            f"transliterated='{trans_q}'",
            f"raw_name_score={best_raw:.3f}",
        ]
        if notes:
            expl_parts.extend(notes)

        return MatchCandidate(
            sdn_id=entry.sdn_id,
            sdn_name=entry.name,
            matched_alias=best_alias,
            program=entry.program,
            entity_type=entry.entity_type,
            raw_name_score=round(best_raw, 4),
            secondary_adjustment=round(adj, 4),
            final_score=round(final_score, 4),
            token_alignments=best_alignments,
            id_exact_match=id_exact,
            dob_status=dob_status,
            country_status=country_status,
            explanation="; ".join(expl_parts),
        )

    def screen(self, query: ScreeningQuery, top_k: int = 5, full_scan: bool = False) -> Dict[str, Any]:
        """
        Screen a query against the watchlist entries the candidate index returns (or every
        entry with `full_scan`) and return ranked candidates plus decision (`BLOCK`, `REVIEW`, or `CLEAR`).
        """
        pool = self.watchlist if full_scan else self.candidates(query)
        candidates = [
            self.match_entry(query, entry)
            for entry in pool
            if types_compatible(query.entity_type, entry.entity_type)
        ]
        # Ties are common at 1.0 (scores are capped after the DOB/country bonus); the uncapped score breaks them
        candidates.sort(key=lambda c: (c.final_score, c.raw_name_score + c.secondary_adjustment), reverse=True)
        top_candidates = candidates[:top_k]

        best = top_candidates[0] if top_candidates else None
        best_score = best.final_score if best else 0.0
        is_hit = best_score >= self.alert_threshold

        # A strong name match that only falls below the threshold because of DOB, country or ID
        # goes to an analyst: those fields come from the payer, and a listed person can misstate them.
        strong_name = any(c.raw_name_score >= self.alert_threshold for c in candidates)
        if best_score >= self.alert_threshold:
            decision = "BLOCK"
        elif best_score >= 0.60 or strong_name:
            decision = "REVIEW"
        else:
            decision = "CLEAR"

        return {
            "query_id": query.query_id,
            "query_name": query.name,
            "detected_script": detect_script(query.name),
            "transliterated_name": transliterate(query.name),
            "phonetic_skeleton": " ".join(phonetic_code(t) for t in normalize_tokens(query.name)),
            "is_hit": is_hit,
            "decision": decision,
            "best_score": round(best_score, 4),
            "best_match": best,
            "top_candidates": top_candidates,
        }


class NaiveLevenshteinMatcher:
    """
    Legacy character-level Levenshtein matcher used as a baseline in benchmarks.
    Compares raw lowercase query name against primary SDN name (no multi-script
    transliteration, no phonetic coding, no IDF weighting, no DOB/Country verification).
    """

    def __init__(self, watchlist: Sequence[SDNEntry], alert_threshold: float = 0.72) -> None:
        self.watchlist: List[SDNEntry] = list(watchlist)
        self.alert_threshold: float = alert_threshold

    def screen(self, query: ScreeningQuery) -> Dict[str, Any]:
        best_score = 0.0
        best_entry: Optional[SDNEntry] = None
        for entry in self.watchlist:
            sim = naive_levenshtein_similarity(query.name, entry.name)
            if sim > best_score:
                best_score = sim
                best_entry = entry

        return {
            "query_id": query.query_id,
            "is_hit": best_score >= self.alert_threshold,
            "best_score": round(best_score, 4),
            "best_sdn_id": best_entry.sdn_id if best_entry else None,
        }
