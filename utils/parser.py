import re

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


def detect_currency(token: str) -> str | None:
    """Return the ISO currency code if *token* matches a known currency alias."""
    return _CURRENCY_ALIASES.get(token.lower().strip())


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


def format_currency(value: float) -> str:
    """Format a float as a pt-BR currency string: 1.234,56"""
    formatted = f"{value:,.2f}"
    return formatted.replace(",", "X").replace(".", ",").replace("X", ".")
