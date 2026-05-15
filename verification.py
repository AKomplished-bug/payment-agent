import re
from datetime import date, datetime
from typing import Optional


def normalize_dob(raw: str) -> Optional[str]:
    """
    Parse a date string in any reasonable format and return YYYY-MM-DD.
    Returns None if unparseable.
    """
    if not raw:
        return None

    raw = raw.strip()

    # Strip ordinal suffixes: 29th → 29, 1st → 1, 2nd → 2, 3rd → 3
    raw = re.sub(r"(\d+)(st|nd|rd|th)\b", r"\1", raw, flags=re.IGNORECASE)

    # Already in YYYY-MM-DD
    if len(raw) == 10 and raw[4] == "-" and raw[7] == "-":
        try:
            datetime.strptime(raw, "%Y-%m-%d")
            return raw
        except ValueError:
            pass

    formats = [
        "%d-%m-%Y", "%d/%m/%Y", "%d %m %Y",
        "%d-%m-%y", "%d/%m/%y",
        "%B %d, %Y", "%b %d, %Y",
        "%B %d, %y", "%b %d, %y",
        "%d %B %Y", "%d %b %Y",
        "%B %d %Y", "%b %d %Y",
        "%d %B, %Y", "%d %b, %Y",
        "%d %B %y", "%d %b %y",
        "%m/%d/%Y", "%m-%d-%Y",
        "%Y/%m/%d",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(raw, fmt)
            # strptime maps 2-digit years: 00-68 → 2000-2068, 69-99 → 1969-1999
            # But DOBs should always be in the past — cap at today
            if dt.year > date.today().year:
                dt = dt.replace(year=dt.year - 100)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    return None


def is_valid_date(dob_str: str) -> bool:
    """Validate that a YYYY-MM-DD string is a real calendar date (handles leap years)."""
    try:
        datetime.strptime(dob_str, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def normalize_aadhaar_last4(raw: str) -> Optional[str]:
    digits = "".join(c for c in (raw or "") if c.isdigit())
    return digits if len(digits) == 4 else None


def normalize_pincode(raw: str) -> Optional[str]:
    digits = "".join(c for c in (raw or "") if c.isdigit())
    return digits if len(digits) == 6 else None


def normalize_account_id(raw: str) -> Optional[str]:
    """Strip spaces, uppercase, normalize ACC 1001 → ACC1001."""
    if not raw:
        return None
    normalized = "".join(raw.upper().split())
    # Accept ACCxxxx pattern
    if normalized.startswith("ACC") and normalized[3:].isdigit():
        return normalized
    return None


def verify_identity(
    account_data: dict,
    provided_name: str,
    provided_dob: Optional[str] = None,
    provided_aadhaar_last4: Optional[str] = None,
    provided_pincode: Optional[str] = None,
) -> bool:
    """
    Pure deterministic verification. LLM has no involvement here.
    Rule: exact name match AND at least one secondary factor matches.
    """
    if not account_data or not provided_name:
        return False

    # Exact name match — case-sensitive, no fuzzy
    if account_data.get("full_name") != provided_name:
        return False

    # Check secondary factors
    if provided_dob and is_valid_date(provided_dob):
        if account_data.get("dob") == provided_dob:
            return True

    if provided_aadhaar_last4:
        norm = normalize_aadhaar_last4(provided_aadhaar_last4)
        if norm and account_data.get("aadhaar_last4") == norm:
            return True

    if provided_pincode:
        norm = normalize_pincode(provided_pincode)
        if norm and account_data.get("pincode") == norm:
            return True

    return False
