"""Normalization for entity names: Unicode NFC folding + Cyrillic->Latin.

Ported from the AML-GT project (engine/normalize.py). Cyrillic translit matters
for Cyrillic sources (ua-edr, ru-egrul): plain ascii-collapse would drop the
whole name. Store this norm into entity.name_normalized; queries run through
the same transform before pg_trgm matching.
"""

import re
import unicodedata

_CYRILLIC = {
    "а": "a", "б": "b", "в": "v", "г": "g", "ґ": "g", "д": "d", "е": "e",
    "ё": "e", "є": "ye", "ж": "zh", "з": "z", "и": "i", "і": "i", "ї": "yi",
    "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p",
    "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts",
    "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "", "э": "e",
    "ю": "yu", "я": "ya",
}


def norm(s: str) -> str:
    """Lowercase, fold diacritics (NFKD), transliterate Cyrillic, collapse space."""
    s = unicodedata.normalize("NFKD", str(s or "")).lower()
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = "".join(_CYRILLIC.get(ch, ch) for ch in s)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()