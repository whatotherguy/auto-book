import re
import unicodedata


def normalize_text(text: str) -> str:
    text = text.lower()
    text = text.replace("\u2019", "'").replace("\u2018", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\u2014", " ").replace("\u2013", " ")
    text = re.sub(r"[^\w'\s]", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


_HONORIFICS = {
    "dr": "doctor",
    "mr": "mister",
    "mrs": "missus",
    "ms": "miss",
    "st": "saint",
    "jr": "junior",
    "sr": "senior",
    "prof": "professor",
}

_ORDINALS = {
    1: "first",
    2: "second",
    3: "third",
    4: "fourth",
    5: "fifth",
    6: "sixth",
    7: "seventh",
    8: "eighth",
    9: "ninth",
    10: "tenth",
    11: "eleventh",
    12: "twelfth",
    13: "thirteenth",
    14: "fourteenth",
    15: "fifteenth",
    16: "sixteenth",
    17: "seventeenth",
    18: "eighteenth",
    19: "nineteenth",
    20: "twentieth",
}

_ONES = [
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
    "sixteen", "seventeen", "eighteen", "nineteen",
]

_TENS = [
    "", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy",
    "eighty", "ninety",
]

# Maps expanded forms to contracted forms (canonical for Whisper alignment).
_CONTRACTIONS = [
    ("do not", "don't"),
    ("will not", "won't"),
    ("it is", "it's"),
    ("they are", "they're"),
    ("he is", "he's"),
    ("she is", "she's"),
    ("we are", "we're"),
    ("you are", "you're"),
    ("i am", "i'm"),
    ("cannot", "can't"),
    ("would not", "wouldn't"),
    ("could not", "couldn't"),
    ("should not", "shouldn't"),
    ("did not", "didn't"),
    ("does not", "doesn't"),
    ("has not", "hasn't"),
    ("have not", "haven't"),
    ("is not", "isn't"),
    ("was not", "wasn't"),
    ("were not", "weren't"),
    ("are not", "aren't"),
]


def _expand_honorifics(text: str) -> str:
    pattern = re.compile(r"\b(dr|mr|mrs|ms|st|jr|sr|prof)\.?(?=\W|$)", re.IGNORECASE)

    def repl(match: re.Match[str]) -> str:
        return _HONORIFICS[match.group(1).lower()]

    return pattern.sub(repl, text)


def _expand_ordinals(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        number = int(match.group(1))
        return _ORDINALS.get(number, match.group(1))

    return re.sub(r"\b(\d+)(st|nd|rd|th)\b", repl, text, flags=re.IGNORECASE)


def _number_to_words(n: int) -> str:
    """Convert an integer 0-9999 to English words."""
    if n < 0:
        return "negative " + _number_to_words(-n)
    if n < 20:
        return _ONES[n]
    if n < 100:
        tens, ones = divmod(n, 10)
        return _TENS[tens] if ones == 0 else f"{_TENS[tens]} {_ONES[ones]}"
    if n < 1000:
        hundreds, remainder = divmod(n, 100)
        if remainder == 0:
            return f"{_ONES[hundreds]} hundred"
        return f"{_ONES[hundreds]} hundred {_number_to_words(remainder)}"
    if n < 10000:
        thousands, remainder = divmod(n, 1000)
        if remainder == 0:
            return f"{_ONES[thousands]} thousand"
        if remainder < 100:
            return f"{_ONES[thousands]} thousand {_number_to_words(remainder)}"
        return f"{_ONES[thousands]} thousand {_number_to_words(remainder)}"
    return str(n)


def _expand_cardinals(text: str) -> str:
    """Replace digit strings with their English word equivalents."""

    def repl(match: re.Match[str]) -> str:
        s = match.group(0)
        n = int(s)
        # Year-like four-digit numbers (1100-1999, 2000-2099)
        if len(s) == 4 and 1100 <= n <= 1999:
            hi, lo = divmod(n, 100)
            if lo == 0:
                return f"{_number_to_words(hi)} hundred"
            return f"{_number_to_words(hi)} {_number_to_words(lo)}"
        if n <= 9999:
            return _number_to_words(n)
        return s  # leave very large numbers as-is

    return re.sub(r"\b\d+\b", repl, text)


def _normalize_contractions(text: str) -> str:
    """Normalize expanded forms to contracted forms (Whisper canonical)."""
    for expanded, contracted in _CONTRACTIONS:
        # Replace the expanded form with the contracted form (case-insensitive)
        text = re.sub(
            r"\b" + re.escape(expanded) + r"\b",
            contracted,
            text,
            flags=re.IGNORECASE,
        )
    return text


def normalize_for_alignment(text: str) -> str:
    # 1. Expand honorifics
    text = _expand_honorifics(text)
    # 2. Currency symbols and comma removal
    text = text.replace("$", "").replace("\u00a3", "").replace(",", "")
    # 3. a.m./p.m. normalization
    text = re.sub(r"\ba\.m\.(?=\W|$)", "am", text, flags=re.IGNORECASE)
    text = re.sub(r"\bp\.m\.(?=\W|$)", "pm", text, flags=re.IGNORECASE)
    # 4. Expand ordinals
    text = _expand_ordinals(text)
    # 5. Expand cardinal numbers
    text = _expand_cardinals(text)
    # 6. Normalize contractions (expanded → contracted)
    text = _normalize_contractions(text)
    # 7. Lowercase
    text = text.lower()
    # 8. Hyphen normalization (replace hyphens between word characters with spaces)
    text = re.sub(r"(?<=\w)-(?=\w)", " ", text)
    # 9. Normalize Unicode curly quotes and dashes to ASCII equivalents
    text = text.replace("\u2019", "'").replace("\u2018", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\u2014", " ").replace("\u2013", " ")
    # 10. Final regex cleanup
    text = re.sub(r"[^\w'\s]", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()
    return text
