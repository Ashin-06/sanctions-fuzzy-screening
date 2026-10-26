"""
Deterministic Multi-Script Transliterator & Phonetic Skeleton Engine.

Supports:
- Devanagari (Hindi) -> Canonical Latin phonetics (with inherent schwa & word-final deletion)
- Arabic -> Canonical Latin phonetics (with tashkeel stripping, al- prefix handling & abjad pattern mapping)
- Cyrillic (Russian/Ukrainian/Belarusian) -> Canonical Latin phonetics
- Honorifics, titles, patronymic particles, and corporate suffix stripping
- Consonant Phonetic Skeleton coding for cross-script / cross-dialect entity resolution
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from typing import Dict, List, Set, Tuple

# ---------------------------------------------------------------------------
# Honorifics, Titles, Particles & Corporate Suffixes
# ---------------------------------------------------------------------------
HONORIFICS_AND_TITLES: Set[str] = {
    "mr", "mrs", "ms", "miss", "smt", "shri", "sri", "kumari",
    "sheikh", "shaykh", "shaikh", "dr", "prof", "gen", "general",
    "col", "colonel", "maj", "major", "capt", "captain", "adm",
    "hajj", "haji", "haj", "sayyid", "syed", "ayatollah", "mullah",
    "sir", "lord", "lady",
}

PATRONYMIC_PARTICLES: Set[str] = {
    "al", "el", "ul", "bin", "ibn", "binti", "bint", "abu", "umm",
    "abdel", "abdul", "abd", "lil",
}

CORPORATE_SUFFIXES: Set[str] = {
    "llc", "inc", "incorporated", "corp", "corporation", "co", "company",
    "pvt", "private", "ltd", "limited", "plc", "gmbh", "ag", "kg",
    "jsc", "ojsc", "pjsc", "cjsc", "ooo", "zao", "pao", "ao",
    "sa", "sarl", "sas", "bv", "nv", "ab", "oy", "kk", "as", "asa", "aps",
    "fze", "fzco", "dmcc", "pjsc", "llp", "lp", "est", "establishment",
    "sharikah", "sharikat", "kompaniya", "pte", "pty", "sti", "sirketi",
}

# Company forms spelled out over several words, as OFAC often lists them
# ("GAZPROMBANK JOINT STOCK COMPANY", "OBSHCHESTVO S OGRANICHENNOI OTVETSTVENNOSTYU ...")
CORPORATE_PHRASES = re.compile(
    r"\b(?:(?:public|open|closed|private) )?joint stock\b"
    r"|\blimited liability\b"
    r"|\b(?:(?:publichnoe|otkrytoe|zakrytoe) )?aktsionernoy?e obs?h?chestvo\b"
    r"|\bobs?h?chestvo s ogranichenno[iy] otvetstvennost(?:yu|iu)\b"
    r"|\banonim\b(?= sirketi)|\bsendirian berhad\b|\bsdn bhd\b"
)

STOP_AFFIXES: Set[str] = HONORIFICS_AND_TITLES | PATRONYMIC_PARTICLES | CORPORATE_SUFFIXES

# ---------------------------------------------------------------------------
# Cyrillic -> Latin Transliteration Table
# ---------------------------------------------------------------------------
_CYRILLIC_MAP: Dict[str, str] = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d",
    "е": "e", "ё": "yo", "ж": "zh", "з": "z", "и": "i",
    "й": "y", "к": "k", "л": "l", "м": "m", "н": "n",
    "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
    "у": "u", "ф": "f", "х": "kh", "ц": "ts", "ч": "ch",
    "ш": "sh", "щ": "shch", "ъ": "", "ы": "y", "ь": "",
    "э": "e", "ю": "yu", "я": "ya",
    # Ukrainian / Belarusian / Serbian extensions
    "і": "i", "ї": "yi", "є": "ye", "ґ": "g", "ў": "u",
    "ђ": "dj", "ј": "j", "љ": "lj", "њ": "nj", "ћ": "c", "џ": "dz",
}

# Canonical token-level overrides for well-known Cyrillic names where English convention
# uses a specific vowel/ending (e.g., Евгений -> yevgeny, Сергей -> sergei, Дмитрий -> dmitry)
_CYRILLIC_LEXICON: Dict[str, str] = {
    "евгений": "yevgeny",
    "сергей": "sergei",
    "дмитрий": "dmitry",
    "валерий": "valery",
    "анатолий": "anatoly",
    "геннадий": "gennady",
    "виталий": "vitaly",
    "аркадий": "arkady",
    "николай": "nikolai",
    "алексей": "aleksei",
    "андрей": "andrei",
    "юрий": "yury",
    "василий": "vasily",
    "григорий": "grigory",
}

# ---------------------------------------------------------------------------
# Devanagari (Hindi) -> Latin Transliteration Tables
# ---------------------------------------------------------------------------
_DEV_VOWELS: Dict[str, str] = {
    "अ": "a", "आ": "a", "इ": "i", "ई": "i", "उ": "u", "ऊ": "u",
    "ऋ": "ri", "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au",
    "ऑ": "o", "ऍ": "e",
}

_DEV_MATRAS: Dict[str, str] = {
    "ा": "a", "ि": "i", "ी": "i", "ु": "u", "ू": "u",
    "ृ": "ri", "े": "e", "ै": "ai", "ो": "o", "ौ": "au",
    "ॉ": "o", "ॅ": "e",
}

_DEV_CONSONANTS: Dict[str, str] = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n",
    "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "n",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n",
    "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m",
    "य": "y", "र": "r", "ल": "l", "व": "v", "ळ": "l",
    "श": "sh", "ष": "sh", "स": "s", "ह": "h",
}

# Nukta combinations (e.g. क़ -> q, ख़ -> kh, ग़ -> gh, ज़ -> z, फ़ -> f, ड़ -> r, ढ़ -> rh)
_DEV_NUKTA_CONSONANTS: Dict[str, str] = {
    "क": "q",
    "ख": "kh",
    "ग": "gh",
    "ज": "z",
    "फ": "f",
    "ड": "r",
    "ढ": "rh",
}

_DEV_VIRAMA = "\u094d"  # ्
_DEV_NUKTA = "\u093c"   # ़
_DEV_ANUSVARA = {"\u0902", "\u0901"}  # ं, ँ
_DEV_VISARGA = "\u0903"  # ः

# Canonical word-level phonetic restorations for loanwords in Devanagari
# (e.g. English/Russian/Arabic names written in Hindi script where inherent schwa 'a'
# represents 'o' or 'q' represents Arabic Qaf)
_DEVANAGARI_LEXICON: Dict[str, str] = {
    "विक्टर": "viktor",
    "बुट": "but",
    "तारिक": "tariq",
    "तारिक़": "tariq",
    "रशीद": "rashid",
    "अल": "al",
    "कासिम": "qasim",
    "क़ासिम": "qasim",
    "सुलेमानी": "suleimani",
    "मोहम्मद": "mohammed",
    "मुहम्मद": "muhammad",
    "गद्दाफी": "qaddafi",
    "कद्दाफी": "qaddafi",
    "हसन": "hassan",
    "हुसैन": "hussein",
    "नसरल्लाह": "nasrallah",
    "व्लादिमीर": "vladimir",
    "सर्गेई": "sergei",
    "येवगेनी": "yevgeny",
    "प्रिगोज़िन": "prigozhin",
    "प्रिगोजिन": "prigozhin",
    "अलेक्जेंडर": "aleksandr",
    "लुकाशेंको": "lukashenko",
    "ओलेग": "oleg",
    "देरिपास्का": "deripaska",
    "बशर": "bashar",
    "असद": "assad",
    "इब्राहिम": "ibrahim",
    "अब्दुल्ला": "abdullah",
    "शेख": "sheikh",
    "श्री": "shri",
    "श्रीमती": "smt",
}

# ---------------------------------------------------------------------------
# Arabic -> Latin Transliteration Tables
# ---------------------------------------------------------------------------
_ARABIC_DIACRITICS = re.compile(r"[\u064b-\u065f\u0670\u0640]")

_ARABIC_CHAR_MAP: Dict[str, str] = {
    "ا": "a", "أ": "a", "إ": "i", "آ": "a", "ى": "a", "ٱ": "a",
    "ب": "b", "ت": "t", "ة": "ah", "ث": "th", "ج": "j",
    "ح": "h", "خ": "kh", "د": "d", "ذ": "dh", "ر": "r",
    "ز": "z", "س": "s", "ش": "sh", "ص": "s", "ض": "d",
    "ط": "t", "ظ": "z", "ع": "a", "غ": "gh", "ف": "f",
    "ق": "q", "ك": "k", "ک": "k", "گ": "g", "ل": "l",
    "م": "m", "ن": "n", "ه": "h", "ۀ": "h",
    "و": "u", "ؤ": "u", "ي": "i", "ئ": "i", "ی": "i",
    "ء": "", "پ": "p", "چ": "ch", "ژ": "zh", "ڤ": "v",
}

# Common Arabic name/entity vocabulary with short vowels restored
_ARABIC_LEXICON: Dict[str, str] = {
    "طارق": "tariq",
    "رشيد": "rashid",
    "الرشيد": "al rashid",
    "قاسم": "qasim",
    "سليماني": "suleimani",
    "محمد": "mohammed",
    "أحمد": "ahmed",
    "احمد": "ahmed",
    "محمود": "mahmoud",
    "مصطفى": "mustafa",
    "إبراهيم": "ibrahim",
    "ابراهيم": "ibrahim",
    "إسماعيل": "ismail",
    "اسماعيل": "ismail",
    "حسن": "hassan",
    "حسين": "hussein",
    "الحسين": "al hussein",
    "علي": "ali",
    "عمر": "omar",
    "عثمان": "othman",
    "خالد": "khalid",
    "وليد": "walid",
    "الوليد": "al walid",
    "صالح": "salih",
    "ناصر": "nasir",
    "منصور": "mansour",
    "المنصور": "al mansour",
    "معمر": "muammar",
    "قذافي": "qaddafi",
    "القذافي": "al qaddafi",
    "بشار": "bashar",
    "أسد": "assad",
    "الأسد": "al assad",
    "اسد": "assad",
    "الاسد": "al assad",
    "نصر": "nasr",
    "الله": "allah",
    "نصرالله": "nasrallah",
    "عبد": "abdul",
    "عبدالله": "abdullah",
    "الرحمن": "al rahman",
    "عبدالرحمن": "abdul rahman",
    "بغدادي": "baghdadi",
    "البغدادي": "al baghdadi",
    "مصري": "masri",
    "المصري": "al masri",
    "حج": "hajj",
    "الحج": "al hajj",
    "شيخ": "sheikh",
    "الشيخ": "sheikh",
    "بن": "bin",
    "ابن": "ibn",
    "أبو": "abu",
    "ابو": "abu",
    "شركة": "sharikah",
    "النور": "al noor",
    "نور": "noor",
    "للتجارة": "lil tijarah",
    "تجارة": "tijarah",
    "الدولية": "al dawliyah",
    "العالمية": "al alamiyah",
    "البحرية": "al bahriyah",
    "النفط": "al naft",
    "بنك": "bank",
    "فيكتور": "viktor",
    "بوت": "but",
    "سيرغي": "sergei",
    "لافروف": "lavrov",
}


def detect_script(text: str) -> str:
    """Detect the dominant script of the input text."""
    counts = {"devanagari": 0, "arabic": 0, "cyrillic": 0, "latin": 0}
    for ch in text:
        cp = ord(ch)
        if 0x0900 <= cp <= 0x097F:
            counts["devanagari"] += 1
        elif (0x0600 <= cp <= 0x06FF) or (0x0750 <= cp <= 0x077F) or (0xFB50 <= cp <= 0xFDFF) or (0xFE70 <= cp <= 0xFEFF):
            counts["arabic"] += 1
        elif 0x0400 <= cp <= 0x04FF:
            counts["cyrillic"] += 1
        elif ("a" <= ch.lower() <= "z"):
            counts["latin"] += 1

    active = [k for k, v in counts.items() if v > 0]
    if not active:
        return "latin"
    if len(active) == 1:
        return active[0]
    return max(counts.items(), key=lambda kv: kv[1])[0]


def _transliterate_devanagari_word(word: str) -> str:
    """Transliterate a single Devanagari token with word-final schwa deletion."""
    if word in _DEVANAGARI_LEXICON:
        return _DEVANAGARI_LEXICON[word]

    # Pre-compose nukta characters if represented as single codepoints (e.g. \u0958-\u095f)
    word = unicodedata.normalize("NFD", word)
    # Wait: NFD splits matras in some fonts? No, in Devanagari only precomposed nukta
    # letters (\u0958-\u095F) decompose into base consonant + \u093c. Let's NFC first
    # and explicitly decompose \u0958-\u095F.
    word = unicodedata.normalize("NFC", word)
    _precomposed_nukta = {
        "\u0958": "क\u093c", "\u0959": "ख\u093c", "\u095a": "ग\u093c",
        "\u095b": "ज\u093c", "\u095c": "ड\u093c", "\u095d": "ढ\u093c",
        "\u095e": "फ\u093c", "\u095f": "य\u093c",
    }
    for k, v in _precomposed_nukta.items():
        word = word.replace(k, v)

    if word in _DEVANAGARI_LEXICON:
        return _DEVANAGARI_LEXICON[word]

    out: List[str] = []
    n = len(word)
    i = 0
    while i < n:
        ch = word[i]
        # Check consonant (possibly followed by nukta)
        if ch in _DEV_CONSONANTS:
            has_nukta = (i + 1 < n and word[i + 1] == _DEV_NUKTA)
            if has_nukta:
                base_lat = _DEV_NUKTA_CONSONANTS.get(ch, _DEV_CONSONANTS[ch])
                i += 2
            else:
                base_lat = _DEV_CONSONANTS[ch]
                i += 1

            out.append(base_lat)

            # Check what follows the consonant
            if i < n:
                nxt = word[i]
                if nxt == _DEV_VIRAMA:
                    # Halant suppresses inherent vowel
                    i += 1
                elif nxt in _DEV_MATRAS:
                    out.append(_DEV_MATRAS[nxt])
                    i += 1
                elif nxt in _DEV_ANUSVARA:
                    # Inherent 'a' + nasal before next consonant/end
                    out.append("an")
                    i += 1
                else:
                    # Inherent schwa 'a' (medial position)
                    out.append("a")
            else:
                # Word-final consonant: Hindi schwa deletion applies unless the word
                # is a single consonant letter
                if len(out) == 1:
                    out.append("a")
        elif ch in _DEV_VOWELS:
            out.append(_DEV_VOWELS[ch])
            i += 1
        elif ch in _DEV_MATRAS:
            out.append(_DEV_MATRAS[ch])
            i += 1
        elif ch in _DEV_ANUSVARA:
            out.append("n")
            i += 1
        elif ch == _DEV_VISARGA:
            out.append("h")
            i += 1
        elif ch in (_DEV_VIRAMA, _DEV_NUKTA):
            i += 1
        else:
            out.append(ch)
            i += 1

    return "".join(out)


def _transliterate_arabic_word(word: str) -> str:
    """Transliterate a single Arabic token into canonical Latin."""
    clean = _ARABIC_DIACRITICS.sub("", word)
    if not clean:
        return ""

    if clean in _ARABIC_LEXICON:
        return _ARABIC_LEXICON[clean]

    # Handle definite article 'ال' (al-) prefix
    if clean.startswith("ال") and len(clean) > 2:
        stem = clean[2:]
        if stem in _ARABIC_LEXICON:
            return f"al {_ARABIC_LEXICON[stem]}"
        return f"al {_transliterate_arabic_stem(stem)}"

    # Handle 'و' or 'ل' proclitics if attached to 'ال' (e.g., للتجارة -> lil tijarah)
    if clean.startswith("لل") and len(clean) > 3:
        stem = clean[2:]
        if stem in _ARABIC_LEXICON:
            return f"lil {_ARABIC_LEXICON[stem]}"
        return f"lil {_transliterate_arabic_stem(stem)}"

    return _transliterate_arabic_stem(clean)


def _transliterate_arabic_stem(stem: str) -> str:
    """Transliterate an Arabic word stem using morphological pattern rules + char map."""
    if stem in _ARABIC_LEXICON:
        return _ARABIC_LEXICON[stem]

    # Arabic active participle pattern فاعل (4 letters where 2nd letter is ا, e.g. طارق, خالد, صالح)
    # -> C1 + 'a' + C2 + 'i' + C3
    if len(stem) == 4 and stem[1] == "ا" and stem[0] in _ARABIC_CHAR_MAP and stem[2] in _ARABIC_CHAR_MAP and stem[3] in _ARABIC_CHAR_MAP:
        c1 = _ARABIC_CHAR_MAP[stem[0]]
        c2 = _ARABIC_CHAR_MAP[stem[2]]
        c3 = _ARABIC_CHAR_MAP[stem[3]]
        return f"{c1}a{c2}i{c3}"

    # Arabic pattern فعيل (4 letters where 3rd letter is ي, e.g. رشيد, كريم, سليم, حكيم)
    # -> C1 + 'a' + C2 + 'i' + C3
    if len(stem) == 4 and stem[2] in ("ي", "ی") and stem[0] in _ARABIC_CHAR_MAP and stem[1] in _ARABIC_CHAR_MAP and stem[3] in _ARABIC_CHAR_MAP:
        c1 = _ARABIC_CHAR_MAP[stem[0]]
        c2 = _ARABIC_CHAR_MAP[stem[1]]
        c3 = _ARABIC_CHAR_MAP[stem[3]]
        return f"{c1}a{c2}i{c3}"

    out: List[str] = []
    for idx, ch in enumerate(stem):
        if ch in ("و", "ؤ"):
            # Initial 'و' is consonant 'w', medial/final is 'u' or 'o'
            out.append("w" if idx == 0 else "u")
        elif ch in ("ي", "ی", "ئ"):
            out.append("y" if idx == 0 else "i")
        elif ch in _ARABIC_CHAR_MAP:
            out.append(_ARABIC_CHAR_MAP[ch])
        else:
            out.append(ch)
    return "".join(out)


def _transliterate_cyrillic_word(word: str) -> str:
    """Transliterate a single Cyrillic token into canonical Latin."""
    low = word.lower()
    if low in _CYRILLIC_LEXICON:
        return _CYRILLIC_LEXICON[low]

    # Standard endings: -ий / -ый -> -y (e.g. Анатолий -> anatoly)
    if len(low) > 3 and (low.endswith("ий") or low.endswith("ый")):
        prefix = "".join(_CYRILLIC_MAP.get(c, c) for c in low[:-2])
        return prefix + "y"

    return "".join(_CYRILLIC_MAP.get(c, c) for c in low)


@lru_cache(maxsize=200_000)  # pure, and hot when screening a full list
def transliterate(text: str) -> str:
    """
    Deterministically transliterate Multi-Script (Devanagari, Arabic, Cyrillic, Latin)
    strings into canonical lowercase Latin phonetics.

    Examples:
        transliterate("विक्टर बुट") -> "viktor but"
        transliterate("Виктор Бут") -> "viktor but"
        transliterate("طارق الرشيد") -> "tariq al rashid"
        transliterate("तारिक अल रशीद") -> "tariq al rashid"
    """
    if not text:
        return ""

    # Replace punctuation/hyphens with spaces and normalize whitespace
    cleaned = re.sub(r"[-_/.,;:'\"()\[\]{}|\\]+", " ", text.strip())
    raw_tokens = cleaned.split()
    out_tokens: List[str] = []

    for tok in raw_tokens:
        script = detect_script(tok)
        if script == "devanagari":
            lat = _transliterate_devanagari_word(tok)
        elif script == "arabic":
            lat = _transliterate_arabic_word(tok)
        elif script == "cyrillic":
            lat = _transliterate_cyrillic_word(tok)
        else:
            # Strip Latin accents (e.g. é -> e, ü -> u, ł -> l)
            nfkd = unicodedata.normalize("NFKD", tok.lower())
            lat = "".join(c for c in nfkd if not unicodedata.combining(c))

        for sub in lat.lower().split():
            sub_alpha = re.sub(r"[^a-z0-9]", "", sub)
            if sub_alpha:
                out_tokens.append(sub_alpha)

    return " ".join(out_tokens)


def normalize_tokens(text: str, strip_affixes: bool = True) -> List[str]:
    """
    Transliterate text and split into normalized tokens, optionally stripping
    honorifics, titles, patronymic particles, and corporate suffixes.
    """
    trans = transliterate(text)
    raw = trans.split()
    if not strip_affixes:
        return raw

    filtered: List[str] = []
    for tok in CORPORATE_PHRASES.sub(" ", trans).split():
        # Strip attached al- or el- if someone wrote "alrashid"
        if len(tok) > 5 and (tok.startswith("al") or tok.startswith("el")) and tok in ("alrashid", "alassad", "alqaddafi", "alkadhafi", "algaddafi", "albaghdadi", "almasri", "alhussein", "almansour"):
            tok = tok[2:]
        if tok not in STOP_AFFIXES:
            filtered.append(tok)

    # Fallback: if every token was a stopword (e.g. a company literally named "Al Noor LLC"
    # where "noor" survives, or if all were stripped), return raw tokens so we never empty out.
    return filtered if filtered else raw


# Cross-dialectal / historical orthography canonical map before consonant skeletonization
_DIALECT_CANONICAL_MAP: Dict[str, str] = {
    "gaddafi": "qaddafi",
    "ghaddafi": "qaddafi",
    "ghadafi": "qaddafi",
    "gadafi": "qaddafi",
    "kadhafi": "qaddafi",
    "kaddafi": "qaddafi",
    "qadhafi": "qaddafi",
    "mouammar": "muammar",
    "moammar": "muammar",
    "muamar": "muammar",
    "usama": "osama",
    "oussama": "osama",
    "hizballah": "hezbollah",
    "hizbullah": "hezbollah",
    "lukashenka": "lukashenko",
    "aliaksandr": "aleksandr",
    "oleksandr": "aleksandr",
    "mykola": "nikolai",
    "sergii": "sergei",
    "serhiy": "sergei",
}


@lru_cache(maxsize=200_000)
def phonetic_code(token: str) -> str:
    """
    Generate a deterministic Consonant Phonetic Code for a single token.

    Transformations:
    1. Transliterate non-Latin scripts to Latin and lowercase.
    2. Normalize dialectal Arabic/Slavic spelling variants (e.g., Gaddafi/Kadhafi -> Qaddafi).
    3. Normalize digraphs:
       ph -> f, kh -> k, gh -> g, dh -> d, th -> t,
       shch -> s, sch -> s, sh -> s, zh -> s, tch -> s, ch -> s, ts -> s,
       ck -> k, qu -> k
    4. Normalize single consonants:
       c -> s (before e, i, y) else k
       q -> k, x -> ks, z -> s, w -> v
    5. Strip trailing silent 'h' (so Abdullah == Abdulla == Abdallah -> bdl).
    6. Strip all vowels (a, e, i, o, u, y).
    7. Collapse adjacent duplicate consonants (mm -> m, dd -> d, ss -> s).
    """
    if not token:
        return ""

    # If multi-word string was passed, join token codes with space
    if " " in token.strip():
        toks = normalize_tokens(token, strip_affixes=True)
        return " ".join(phonetic_code(t) for t in toks if t)

    lat = transliterate(token).strip()
    if not lat:
        return ""
    # Take first token if transliteration expanded (e.g., "الرشيد" -> "al rashid")
    parts = [p for p in lat.split() if p not in STOP_AFFIXES]
    w = parts[-1] if parts else lat.split()[0]

    w = re.sub(r"[^a-z0-9]", "", w.lower())
    if not w:
        return ""
    if w.isdigit():
        return w

    w = _DIALECT_CANONICAL_MAP.get(w, w)

    # Soft 'c' before front vowels (ce, ci, cy -> se, si, sy)
    w = re.sub(r"c(?=[eiy])", "s", w)

    # Digraph normalizations (order matters)
    digraphs: List[Tuple[str, str]] = [
        ("shch", "s"),
        ("sch", "s"),
        ("tch", "s"),
        ("ph", "f"),
        ("kh", "k"),
        ("gh", "g"),
        ("dh", "d"),
        ("th", "t"),
        ("sh", "s"),
        ("zh", "s"),
        ("ch", "s"),
        ("ts", "s"),
        ("tz", "s"),
        ("ck", "k"),
        ("qu", "k"),
        ("ks", "ks"),
    ]
    for src, dst in digraphs:
        w = w.replace(src, dst)

    # Single-char consonant normalizations
    char_map = {
        "q": "k",
        "c": "k",
        "z": "s",
        "w": "v",
        "x": "ks",
    }
    w = "".join(char_map.get(ch, ch) for ch in w)

    # Strip word-final silent 'h' (e.g. Abdullah / Abdulla, Sarah / Sara, Sharikah / Sharika)
    if len(w) > 2 and w.endswith("h"):
        w = w[:-1]

    # Remove vowels (a, e, i, o, u, y)
    consonants = re.sub(r"[aeiouy]", "", w)

    # Collapse consecutive identical consonants (e.g. mhmd, kdf, srg)
    collapsed: List[str] = []
    for ch in consonants:
        if not collapsed or collapsed[-1] != ch:
            collapsed.append(ch)

    result = "".join(collapsed)
    return result if result else w[:1]


def phonetic_skeleton(name: str, sort_tokens: bool = False) -> str:
    """
    Compute the multi-token phonetic skeleton of a full person or entity name
    after stripping honorifics, titles, particles, and corporate suffixes.
    """
    tokens = normalize_tokens(name, strip_affixes=True)
    codes = [phonetic_code(t) for t in tokens if t]
    codes = [c for c in codes if c]
    if sort_tokens:
        codes.sort()
    return " ".join(codes)
