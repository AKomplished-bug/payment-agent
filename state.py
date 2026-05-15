from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Optional


class Phase(Enum):
    GREETING = auto()
    ACCOUNT_LOOKUP = auto()
    IDENTITY_COLLECTION = auto()
    IDENTITY_VERIFICATION = auto()
    BALANCE_DISCLOSURE = auto()
    PAYMENT_COLLECTION = auto()
    PAYMENT_PROCESSING = auto()
    CLOSING = auto()
    TERMINATED = auto()  # verification exhausted or unrecoverable error


@dataclass
class CardDetails:
    card_number: Optional[str] = None
    cvv: Optional[str] = None
    expiry_month: Optional[int] = None
    expiry_year: Optional[int] = None
    cardholder_name: Optional[str] = None

    def is_complete(self) -> bool:
        return all([
            self.card_number,
            self.cvv,
            self.expiry_month,
            self.expiry_year,
            self.cardholder_name,
        ])


@dataclass
class ConversationState:
    phase: Phase = Phase.GREETING

    # Account
    account_id: Optional[str] = None
    account_data: Optional[dict] = None  # raw from API — never sent to LLM

    # Identity collection
    provided_name: Optional[str] = None
    provided_dob: Optional[str] = None          # normalized YYYY-MM-DD
    provided_aadhaar_last4: Optional[str] = None
    provided_pincode: Optional[str] = None
    name_needs_confirmation: bool = False       # True when name came from cache, not this phase
    name_confirmation_asked: bool = False      # True after confirmation question has been sent
    verified: bool = False

    # Retry counters
    account_lookup_attempts: int = 0
    verification_attempts: int = 0

    # Payment
    payment_amount: Optional[float] = None
    card: CardDetails = field(default_factory=CardDetails)
    transaction_id: Optional[str] = None
    payment_error: Optional[str] = None
    payment_attempts: int = 0

    # Limits
    MAX_ACCOUNT_LOOKUP_ATTEMPTS: int = 3
    MAX_VERIFICATION_ATTEMPTS: int = 3
    MAX_PAYMENT_ATTEMPTS: int = 3
