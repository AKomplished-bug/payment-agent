from datetime import date
from typing import Optional


def luhn_check(card_number: str) -> bool:
    """Validate card number via Luhn algorithm."""
    digits = "".join(c for c in card_number if c.isdigit())
    if len(digits) < 13 or len(digits) > 19:
        return False
    total = 0
    reverse = digits[::-1]
    for i, d in enumerate(reverse):
        n = int(d)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def normalize_card_number(raw: str) -> Optional[str]:
    if not raw:
        return None
    digits = "".join(c for c in raw if c.isdigit())
    return digits if digits else None


def normalize_cvv(raw: str) -> Optional[str]:
    if not raw:
        return None
    digits = "".join(c for c in raw if c.isdigit())
    return digits if len(digits) in (3, 4) else None


def normalize_expiry(raw_month, raw_year) -> tuple[Optional[int], Optional[int]]:
    """Return (month, year) as ints or (None, None) on failure."""
    try:
        month = int(raw_month)
        year = int(raw_year)
        if year < 100:
            year += 2000
        if not (1 <= month <= 12):
            return None, None
        return month, year
    except (TypeError, ValueError):
        return None, None


def is_card_expired(month: int, year: int) -> bool:
    today = date.today()
    return date(today.year, today.month, 1) > date(year, month, 1)


def validate_payment_amount(amount: float, balance: float) -> Optional[str]:
    """Returns error code string or None if valid."""
    if amount is None:
        return "invalid_amount"
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return "invalid_amount"
    if amount <= 0:
        return "invalid_amount"
    if round(amount, 2) != amount:
        return "invalid_amount"
    if amount > balance:
        return "insufficient_balance"
    return None


def validate_card(card_number: str, cvv: str, expiry_month: int, expiry_year: int) -> Optional[str]:
    """Returns error code string or None if all card fields valid."""
    digits = normalize_card_number(card_number)
    if not digits or not luhn_check(digits):
        return "invalid_card"

    cvv_clean = normalize_cvv(cvv)
    if not cvv_clean:
        return "invalid_cvv"

    month, year = normalize_expiry(expiry_month, expiry_year)
    if month is None:
        return "invalid_expiry"
    if is_card_expired(month, year):
        return "invalid_expiry"

    return None


PAYMENT_ERROR_MESSAGES = {
    "account_not_found": "I couldn't find that account. Please double-check your account ID.",
    "invalid_amount": "The payment amount is invalid. Please enter a positive amount with up to 2 decimal places.",
    "insufficient_balance": "The amount you entered exceeds your outstanding balance. Please enter an amount up to ₹{balance}.",
    "invalid_card": "The card number doesn't appear to be valid. Please check and re-enter it.",
    "invalid_cvv": "The CVV is incorrect. It should be 3 digits (4 for Amex). Please re-enter.",
    "invalid_expiry": "The card expiry is invalid or the card has expired. Please use a different card.",
    "invalid_args": "Some of the payment details appear to be invalid. Please check your card details and try again.",
    "unknown_error": "Something went wrong processing your payment. Please try again.",
}


def friendly_error(error_code: str, balance: float = 0) -> str:
    msg = PAYMENT_ERROR_MESSAGES.get(error_code, PAYMENT_ERROR_MESSAGES["unknown_error"])
    return msg.format(balance=f"{balance:,.2f}")
