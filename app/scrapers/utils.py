import re


def parse_number(raw: str) -> float | None:
    """Parse a number string handling US (1,234.56) and European (1.234,56) formats.

    Heuristic:
    - If both comma and dot present: whichever comes last is the decimal separator.
    - If only comma: comma is decimal if <= 2 digits after it, else thousands.
    - If only dot: dot is decimal if <= 2 digits after it, else thousands.
    """
    cleaned = raw.strip().replace("\xa0", "").replace("\u202f", "").replace(" ", "")
    if not cleaned or cleaned in ("-", "N/A", "n/a", ""):
        return None
    try:
        if "," in cleaned and "." in cleaned:
            if cleaned.rfind(".") > cleaned.rfind(","):
                # US format: 1,234.56
                return float(cleaned.replace(",", ""))
            else:
                # European format: 1.234,56
                return float(cleaned.replace(".", "").replace(",", "."))
        elif "," in cleaned:
            parts = cleaned.split(",")
            if len(parts[-1]) <= 2:
                # decimal comma: "4,69" -> 4.69
                return float(cleaned.replace(",", "."))
            else:
                # thousands comma: "1,367" -> 1367
                return float(cleaned.replace(",", ""))
        elif "." in cleaned:
            parts = cleaned.split(".")
            if len(parts[-1]) <= 2:
                # decimal dot: "6.32" or "40.21"
                return float(cleaned)
            else:
                # thousands dot: "6.320" -> 6320
                return float(cleaned.replace(".", ""))
        else:
            return float(cleaned)
    except (ValueError, AttributeError):
        return None


def extract_currency_code(text: str) -> str | None:
    """Extract a 3-letter ISO 4217 currency code from a string."""
    match = re.search(r"\b([A-Z]{3})\b", text)
    return match.group(1) if match else None


# Mapping of BCP full Spanish currency names to ISO 4217 codes.
# BCP displays full names like "Dólar Estadounidense" without the code in some table variants.
BCP_NAME_TO_CODE: dict[str, str] = {
    "dolar estadounidense": "USD",
    "yen japones": "JPY",
    "libra esterlina": "GBP",
    "franco suizo": "CHF",
    "corona sueca": "SEK",
    "corona danesa": "DKK",
    "corona noruega": "NOK",
    "real brasileno": "BRL",
    "real brasileño": "BRL",
    "peso argentino": "ARS",
    "dolar canadiense": "CAD",
    "dólar canadiense": "CAD",
    "rand sudafricano": "ZAR",
    "derechos especiales de giro": "XDR",
    "onza de oro": "XAU",
    "peso chileno": "CLP",
    "euro": "EUR",
    "peso uruguayo": "UYU",
    "dolar australiano": "AUD",
    "dólar australiano": "AUD",
    "yuan renminbi": "CNY",
    "dolar de singapur": "SGD",
    "dólar de singapur": "SGD",
    "boliviano": "BOB",
    "sol peruano": "PEN",
    "dolar neozelandes": "NZD",
    "dólar neozelandés": "NZD",
    "peso mexicano": "MXN",
    "peso colombiano": "COP",
    "dolar taiwanese": "TWD",
    "dólar taiwanés": "TWD",
    "dirham emiratos": "AED",
    "dírham emiratos": "AED",
    "dolar estadounidense": "USD",
    "dólar estadounidense": "USD",
}


def bcp_name_to_code(name: str) -> str:
    """Normalize a BCP currency full name to its ISO 4217 code."""
    normalized = name.strip().lower()
    # Remove accent variants for lookup
    normalized = (
        normalized
        .replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
        .replace("ñ", "n")
    )
    return BCP_NAME_TO_CODE.get(normalized, BCP_NAME_TO_CODE.get(name.strip().lower(), name.upper()[:3]))
