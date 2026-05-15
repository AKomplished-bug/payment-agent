from dataclasses import dataclass
from typing import Optional


@dataclass
class InfoCache:
    """
    Temporary per-session cache for user-volunteered information.
    Populated by the LLM via tool calls at any phase.
    Read by identity collection to avoid re-asking.
    """
    full_name: Optional[str] = None
    dob: Optional[str] = None
    aadhaar_last4: Optional[str] = None
    pincode: Optional[str] = None
    account_id: Optional[str] = None

    def has_identity_info(self) -> bool:
        return any([self.full_name, self.dob, self.aadhaar_last4, self.pincode])

    def to_dict(self) -> dict:
        return {
            "full_name": self.full_name,
            "dob": self.dob,
            "aadhaar_last4": self.aadhaar_last4,
            "pincode": self.pincode,
            "account_id": self.account_id,
        }
