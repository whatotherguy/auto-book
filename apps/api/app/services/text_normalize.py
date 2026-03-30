import re


def normalize_text(text: str) -> str:
    text = text.lower()
    text = text.replace("’", "'").replace("‘", "'")
    text = text.replace("“", '"').replace("”", '"')
    text = text.replace("—", " ").replace("–", " ")
    text = re.sub(r"[^a-z0-9'\s]", " ", text)
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


def normalize_for_alignment(text: str) -> str:
    text = _expand_honorifics(text)
    text = text.replace("$", "").replace("£", "").replace(",", "")
    text = re.sub(r"\ba\.m\.(?=\W|$)", "am", text, flags=re.IGNORECASE)
    text = re.sub(r"\bp\.m\.(?=\W|$)", "pm", text, flags=re.IGNORECASE)
    text = _expand_ordinals(text)
    text = text.lower()
    text = text.replace("â€™", "'").replace("â€˜", "'")
    text = text.replace("â€œ", '"').replace("â€", '"')
    text = text.replace("â€”", " ").replace("â€“", " ")
    text = re.sub(r"[^a-z0-9'\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text
