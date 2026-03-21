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


def parse_action_value(text: str) -> tuple[str, float]:
    """
    Parse user input into (action_description, numeric_value).

    The last whitespace-separated token must be a number;
    everything before it is the action description.
    """
    parts = text.strip().split()
    if len(parts) < 2:
        raise ValueError("Expected: <action> <value>")

    value = parse_number_ptbr(parts[-1])
    action = " ".join(parts[:-1]).strip()
    if not action:
        raise ValueError("Action is empty")
    return action, value


def format_currency(value: float) -> str:
    """Format a float as a pt-BR currency string: 1.234,56"""
    formatted = f"{value:,.2f}"
    return formatted.replace(",", "X").replace(".", ",").replace("X", ".")
