import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Currency aliases
# ---------------------------------------------------------------------------

_CURRENCY_ALIASES: dict[str, str] = {
    "brl": "BRL", "real": "BRL", "reais": "BRL", "r$": "BRL",
    "usd": "USD", "dollar": "USD", "dollars": "USD", "dolar": "USD",
    "dolares": "USD", "dólares": "USD", "dólar": "USD", "$": "USD",
    "eur": "EUR", "euro": "EUR", "euros": "EUR", "€": "EUR",
    "jpy": "JPY", "yen": "JPY", "iene": "JPY", "ienes": "JPY",
    "円": "JPY", "¥": "JPY",
    "gbp": "GBP", "pound": "GBP", "pounds": "GBP", "libra": "GBP",
    "libras": "GBP", "£": "GBP",
}

_CURRENCY_TOKEN_RE = re.compile(
    r"^(?:" + "|".join(re.escape(k) for k in sorted(_CURRENCY_ALIASES, key=len, reverse=True)) + r")$",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Date expression aliases  (value = day offset from today, negative = past)
# ---------------------------------------------------------------------------

_DATE_ALIASES: dict[str, int] = {
    # Portuguese
    "hoje": 0, "ontem": -1, "anteontem": -2,
    # English
    "today": 0, "yesterday": -1,
    # Japanese
    "今日": 0, "きょう": 0, "昨日": -1, "きのう": -1, "一昨日": -2, "おととい": -2,
}

# Multi-word date expressions (checked before tokenizing)
_DATE_PHRASES: dict[str, int] = {
    "day before yesterday": -2,
    "antes de ontem": -2,
}

# ---------------------------------------------------------------------------
# Noise / filler words to strip from descriptions
# ---------------------------------------------------------------------------

_NOISE_WORDS: set[str] = {
    # Portuguese prepositions / articles
    "no", "na", "nos", "nas", "do", "da", "dos", "das", "de", "em", "o", "a",
    "os", "as", "um", "uma", "uns", "umas", "pelo", "pela", "pro", "pra",
    "com", "para", "por", "ao", "à", "que", "e",
    # English prepositions / articles
    "at", "the", "in", "on", "for", "to", "of", "and", "my", "some",
    "paid", "spent", "bought", "got",
    # Japanese particles
    "で", "に", "の", "を", "は", "が", "と", "も", "へ",
}

# ---------------------------------------------------------------------------
# Number parser
# ---------------------------------------------------------------------------

_NUMBER_RE = re.compile(
    r"^[0-9]{1,3}(?:[.,][0-9]{3})*(?:[.,][0-9]{1,2})?$"
    r"|^[0-9]+(?:[.,][0-9]+)?$"
)


def parse_number_ptbr(raw: str) -> float:
    """
    Parse a number string accepting pt-BR decimal comma.

    Supports:
        "12,50"     -> 12.5
        "1.234,56"  -> 1234.56   (pt-BR thousands "." + decimal ",")
        "1,234.56"  -> 1234.56   (en-US thousands "," + decimal ".")
        "20"        -> 20.0
        "20.5"      -> 20.5
    """
    s = raw.strip().replace(" ", "")
    if not s:
        raise ValueError("Value is empty")

    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", "")

    return float(s)


def _is_numeric(token: str) -> bool:
    """Check if a token looks like a number (without actually parsing it)."""
    try:
        parse_number_ptbr(token)
        return True
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# Currency detection
# ---------------------------------------------------------------------------

def detect_currency(token: str) -> str | None:
    """Return the ISO currency code if *token* matches a known currency alias."""
    return _CURRENCY_ALIASES.get(token.lower().strip())


# ---------------------------------------------------------------------------
# Date detection
# ---------------------------------------------------------------------------

def detect_date_offset(text: str) -> tuple[int | None, str]:
    """Extract a date expression from *text*.

    Returns (day_offset, cleaned_text) where day_offset is 0 for today,
    -1 for yesterday, etc.  None means no date expression found.
    """
    lower = text.lower()

    for phrase, offset in _DATE_PHRASES.items():
        if phrase in lower:
            idx = lower.index(phrase)
            cleaned = text[:idx] + text[idx + len(phrase):]
            return offset, " ".join(cleaned.split())

    parts = text.split()
    for i, token in enumerate(parts):
        offset = _DATE_ALIASES.get(token.lower())
        if offset is not None:
            remaining = parts[:i] + parts[i + 1:]
            return offset, " ".join(remaining)

    return None, text


# ---------------------------------------------------------------------------
# Noise word cleanup
# ---------------------------------------------------------------------------

def clean_description(raw: str) -> str:
    """Remove filler/noise words and normalize whitespace."""
    parts = raw.split()
    cleaned = [p for p in parts if p.lower() not in _NOISE_WORDS]
    result = " ".join(cleaned).strip()
    return result if result else raw.strip()


# ---------------------------------------------------------------------------
# Parse result dataclass
# ---------------------------------------------------------------------------

@dataclass
class ParseResult:
    description: str
    value: float
    currency: str | None = None
    date_offset: int | None = None
    raw_description: str = ""


# ---------------------------------------------------------------------------
# Main parser (enhanced)
# ---------------------------------------------------------------------------

def parse_action_value(text: str) -> tuple[str, float, str | None]:
    """
    Parse user input into (description, numeric_value, currency_code | None).

    Accepted formats:
        "jantar 20,50"            -> ("jantar", 20.5, None)
        "dinner 30 usd"           -> ("dinner", 30.0, "USD")
        "dinner 30 dollars"       -> ("dinner", 30.0, "USD")
        "夕食 3000 yen"           -> ("夕食", 3000.0, "JPY")
    """
    parts = text.strip().split()
    if len(parts) < 2:
        raise ValueError("Expected: <action> <value>")

    currency: str | None = None
    last = parts[-1]
    detected = detect_currency(last)

    if detected and len(parts) >= 3:
        value = parse_number_ptbr(parts[-2])
        action = " ".join(parts[:-2]).strip()
        currency = detected
    else:
        value = parse_number_ptbr(last)
        action = " ".join(parts[:-1]).strip()

    if not action:
        raise ValueError("Action is empty")
    return action, value, currency


def parse_smart(text: str) -> ParseResult:
    """Enhanced parser with date detection, flexible value position, and noise removal.

    Tries these strategies in order:
    1. Extract date expression from text
    2. Try standard parse (value at end, optional currency after)
    3. Try flexible parse (scan for numeric token anywhere)
    """
    date_offset, cleaned = detect_date_offset(text)

    # Strategy 1: standard parse on cleaned text
    try:
        desc, value, currency = parse_action_value(cleaned)
        return ParseResult(
            description=clean_description(desc),
            value=value,
            currency=currency,
            date_offset=date_offset,
            raw_description=desc,
        )
    except ValueError:
        pass

    # Strategy 2: flexible position — find a numeric token anywhere
    parts = cleaned.strip().split()
    numeric_idx = None
    for i, token in enumerate(parts):
        if _is_numeric(token):
            numeric_idx = i
            break

    if numeric_idx is not None:
        value = parse_number_ptbr(parts[numeric_idx])
        rest = parts[:numeric_idx] + parts[numeric_idx + 1:]

        currency = None
        if rest and detect_currency(rest[-1]):
            currency = detect_currency(rest[-1])
            rest = rest[:-1]
        elif rest and detect_currency(rest[0]):
            currency = detect_currency(rest[0])
            rest = rest[1:]

        desc_raw = " ".join(rest).strip()
        if desc_raw:
            return ParseResult(
                description=clean_description(desc_raw),
                value=value,
                currency=currency,
                date_offset=date_offset,
                raw_description=desc_raw,
            )

    raise ValueError("Could not parse input")


def format_currency(value: float) -> str:
    """Format a float as a pt-BR currency string: 1.234,56"""
    formatted = f"{value:,.2f}"
    return formatted.replace(",", "X").replace(".", ",").replace("X", ".")
