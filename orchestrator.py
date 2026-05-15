from logger import logger
from state import ConversationState, Phase
from prompts import get_system_prompt
from llm_client import extract_and_respond
from info_cache import InfoCache
from cache_tool import STORE_INFO_TOOL, handle_store_info
from guardrails import (
    sanitize_input,
    check_response_safety,
    scan_for_data_leakage,
    validate_critical_values,
    get_safe_fallback,
)
from verification import (
    verify_identity,
    normalize_dob,
    normalize_account_id,
    normalize_aadhaar_last4,
    normalize_pincode,
    is_valid_date,
)
from validators import (
    validate_payment_amount,
    validate_card,
    normalize_card_number,
    normalize_cvv,
    normalize_expiry,
    friendly_error,
)
from tools import lookup_account, process_payment

_CONFIRM_YES = {"yes", "yeah", "yep", "yup", "correct", "right", "that's right", "thats right",
                "confirmed", "confirm", "sure", "ok", "okay", "affirmative", "exactly", "yea"}
# I mean not a great approach but we can expand this list as needed and it should cover most common confirmations in English (I just like these small tweaks that help to reduce llm tokens and make it more likely to correctly interpret user intent :))


def _user_confirmed(text: str) -> bool:
    return text.strip().lower().rstrip(".,!") in _CONFIRM_YES


def _extract_name_correction(extracted: dict) -> str | None:
    name = extracted.get("full_name")
    if name and name.strip():
        return name.strip().title()
    return None


class ConversationOrchestrator:
    def __init__(self):
        self.state = ConversationState()
        self._history: list[dict] = []
        self._cache = InfoCache()

    def process_turn(self, user_input: str) -> str:
        # Sanitize input against prompt injection
        safe_input = sanitize_input(user_input)

        # Route to the appropriate phase handler
        handler = {
            Phase.GREETING: self._handle_greeting,
            Phase.ACCOUNT_LOOKUP: self._handle_account_lookup,
            Phase.IDENTITY_COLLECTION: self._handle_identity_collection,
            Phase.IDENTITY_VERIFICATION: self._handle_identity_verification,
            Phase.BALANCE_DISCLOSURE: self._handle_balance_disclosure,
            Phase.PAYMENT_COLLECTION: self._handle_payment_collection,
            Phase.PAYMENT_PROCESSING: self._handle_payment_processing,
            Phase.CLOSING: self._handle_closing,
            Phase.TERMINATED: self._handle_terminated,
        }.get(self.state.phase)

        if handler is None:
            return "I'm sorry, something went wrong. Please try again."

        logger.debug(f"turn | phase={self.state.phase.name} | input={user_input[:80]}")
        response = handler(safe_input)

        # Guard: scan response for data leakage before returning
        if scan_for_data_leakage(response, self.state.account_data):
            logger.warning(f"data leakage detected in response — using fallback | phase={self.state.phase.name}")
            response = get_safe_fallback(self.state.phase)

        # Guard: check response is appropriate for current phase
        if not check_response_safety(response, self.state.phase):
            logger.warning(f"phase safety check failed — using fallback | phase={self.state.phase.name}")
            response = get_safe_fallback(self.state.phase)

        # Update conversation history with safe content only
        self._history.append({"role": "user", "content": user_input})
        self._history.append({"role": "assistant", "content": response})

        return response

    # ─── Phase Handlers ───────────────────────────────────────────────

    def _handle_greeting(self, user_input: str) -> str:
        result = self._llm_call(Phase.GREETING, user_input, use_tools=True)
        extracted = result.get("extracted", {})
        response = result.get("response", "")

        # Check extracted first, then fall back to cache
        raw_account_id = extracted.get("account_id") or self._cache.account_id
        if raw_account_id:
            normalized = normalize_account_id(raw_account_id)
            if normalized:
                self.state.account_id = normalized
                self.state.phase = Phase.ACCOUNT_LOOKUP
                return self._handle_account_lookup(user_input)

        return response

    def _handle_account_lookup(self, user_input: str) -> str:
        self.state.account_lookup_attempts += 1

        result = lookup_account(self.state.account_id)

        if result["success"]:
            self.state.account_data = result["data"]
            self.state.phase = Phase.IDENTITY_COLLECTION
            return self._handle_identity_collection(user_input)
        else:
            error_code = result.get("error_code")
            if error_code == "account_not_found":
                if self.state.account_lookup_attempts >= self.state.MAX_ACCOUNT_LOOKUP_ATTEMPTS:
                    self.state.phase = Phase.TERMINATED
                    return (
                        "I wasn't able to find an account with that ID after multiple attempts. "
                        "Please contact our support team for assistance. Thank you."
                    )
                self.state.account_id = None
                self.state.phase = Phase.GREETING
                return "I couldn't find an account with that ID. Could you double-check and try again?"
            elif error_code in ("timeout", "network_error"):
                return "I'm having trouble connecting to our systems right now. Could you try again in a moment?"
            else:
                return "Something went wrong on our end. Please try again or contact support."

    def _handle_identity_collection(self, user_input: str) -> str:
        # Seed state from cache on first entry
        if not self.state.provided_name and self._cache.full_name:
            self.state.provided_name = self._cache.full_name
            self.state.name_needs_confirmation = True
            logger.debug(f"cache | seeded name (pending confirmation): {self._cache.full_name}")
        if not self.state.provided_dob and self._cache.dob:
            self.state.provided_dob = self._cache.dob
            logger.debug("cache | seeded dob")
        if not self.state.provided_aadhaar_last4 and self._cache.aadhaar_last4:
            self.state.provided_aadhaar_last4 = self._cache.aadhaar_last4
            logger.debug("cache | seeded aadhaar_last4")
        if not self.state.provided_pincode and self._cache.pincode:
            self.state.provided_pincode = self._cache.pincode
            logger.debug("cache | seeded pincode")

        # If name came from cache, ask for confirmation before proceeding
        if self.state.name_needs_confirmation:
            cached_name = self.state.provided_name
            if not self.state.name_confirmation_asked:
                self.state.name_confirmation_asked = True
                if len(cached_name.split()) == 1:
                    # Single word — could be just a first name, ask for full name
                    return f"Is {cached_name} your full name? If not, could you please share your full name?"
                return f"Could you confirm — is your full name {cached_name}?"

            # User has responded to the confirmation question — reuse this LLM call
            result = self._llm_call(Phase.IDENTITY_COLLECTION, user_input, use_tools=True)
            extracted = result.get("extracted", {})
            correction = _extract_name_correction(extracted)

            if correction:
                self.state.provided_name = correction
                self.state.name_needs_confirmation = False
                logger.debug(f"cache | name corrected to: {correction}")
            elif _user_confirmed(user_input):
                self.state.name_needs_confirmation = False
                logger.debug("cache | name confirmed by user")
            else:
                return f"Sorry, I didn't catch that. Is your full name {cached_name}? Please say yes or provide the correct name."

            # Use the response from this call — don't make another LLM call for the same turn
            response = result.get("response", "")
            field_error = self._merge_identity_fields(extracted)
            if field_error:
                return field_error
            has_name = bool(self.state.provided_name)
            has_secondary = any([
                self.state.provided_dob,
                self.state.provided_aadhaar_last4,
                self.state.provided_pincode,
            ])
            if has_name and has_secondary:
                self.state.phase = Phase.IDENTITY_VERIFICATION
                return self._handle_identity_verification(user_input)
            return response

        result = self._llm_call(Phase.IDENTITY_COLLECTION, user_input, use_tools=True)
        extracted = result.get("extracted", {})
        response = result.get("response", "")

        field_error = self._merge_identity_fields(extracted)
        if field_error:
            return field_error

        has_name = bool(self.state.provided_name)
        has_secondary = any([
            self.state.provided_dob,
            self.state.provided_aadhaar_last4,
            self.state.provided_pincode,
        ])

        if has_name and has_secondary:
            self.state.phase = Phase.IDENTITY_VERIFICATION
            return self._handle_identity_verification(user_input)

        return response

    def _handle_identity_verification(self, _user_input: str) -> str:
        self.state.verification_attempts += 1

        verified = verify_identity(
            account_data=self.state.account_data,
            provided_name=self.state.provided_name,
            provided_dob=self.state.provided_dob,
            provided_aadhaar_last4=self.state.provided_aadhaar_last4,
            provided_pincode=self.state.provided_pincode,
        )

        if verified:
            logger.info(f"identity verified | account_id={self.state.account_id}")
            self.state.verified = True
            self.state.phase = Phase.BALANCE_DISCLOSURE
            balance = self.state.account_data["balance"]
            name = self.state.account_data["full_name"]
            return (
                f"Identity verified successfully. "
                f"Welcome, {name}! Your outstanding balance is ₹{balance:,.2f}. "
                f"How much would you like to pay today? You can pay the full amount or a partial amount."
            )
        else:
            # Clear secondary factors for re-entry, keep name if it might be right
            self.state.provided_dob = None
            self.state.provided_aadhaar_last4 = None
            self.state.provided_pincode = None
            self.state.phase = Phase.IDENTITY_COLLECTION

            logger.warning(f"verification failed | attempt={self.state.verification_attempts} | account_id={self.state.account_id}")
            if self.state.verification_attempts >= self.state.MAX_VERIFICATION_ATTEMPTS:
                logger.warning(f"verification max attempts reached | account_id={self.state.account_id}")
                self.state.phase = Phase.TERMINATED
                return (
                    "I'm sorry, I wasn't able to verify your identity after multiple attempts. "
                    "For your security, this session has been closed. "
                    "Please contact our support team for assistance."
                )

            remaining = self.state.MAX_VERIFICATION_ATTEMPTS - self.state.verification_attempts
            return (
                f"I wasn't able to verify your identity with the information provided. "
                f"Please double-check your details and try again. "
                f"You have {remaining} attempt(s) remaining. "
                f"Could you confirm your full name and one of: date of birth, Aadhaar last 4, or pincode?"
            )

    def _handle_balance_disclosure(self, user_input: str) -> str:
        balance = self.state.account_data["balance"]

        context = {
            "account_holder_name": self.state.account_data["full_name"],
            "outstanding_balance": f"₹{balance:,.2f}",
        }
        result = self._llm_call(Phase.BALANCE_DISCLOSURE, user_input, context)
        extracted = result.get("extracted", {})
        response = result.get("response", "")

        raw_amount = extracted.get("payment_amount")

        if raw_amount is not None:
            if raw_amount == "FULL" or str(raw_amount).upper() == "FULL":
                amount = balance
            else:
                try:
                    amount = round(float(raw_amount), 2)
                except (TypeError, ValueError):
                    return response  # LLM already generated a clarifying message

            error = validate_payment_amount(amount, balance)
            if error:
                return friendly_error(error, balance)

            self.state.payment_amount = amount
            self.state.phase = Phase.PAYMENT_COLLECTION
            return (
                f"Great, I'll process a payment of ₹{amount:,.2f}. "
                f"I'll need your card details to proceed. "
                f"Please share your card number."
            )

        # Post-LLM guardrail: ensure balance value is present in response
        _, response = validate_critical_values(response, {"outstanding balance": f"₹{balance:,.2f}"})
        return response

    def _handle_payment_collection(self, user_input: str) -> str:
        result = self._llm_call(Phase.PAYMENT_COLLECTION, user_input)
        extracted = result.get("extracted", {})
        response = result.get("response", "")

        card = self.state.card

        # Merge card fields — normalize as we go
        if extracted.get("card_number"):
            new_digits = normalize_card_number(extracted["card_number"])
            if new_digits:
                existing = card.card_number or ""
                combined = existing + new_digits
                if len(new_digits) >= 16:
                    # Full number provided — use as-is (user may be correcting)
                    card.card_number = new_digits
                elif len(combined) >= 16:
                    # Accumulated enough digits
                    card.card_number = combined[:16]
                else:
                    # Still partial — accumulate and prompt for the rest
                    card.card_number = combined
                    got = len(combined)
                    need = 16 - got
                    return f"Got {got} digits so far — please share the remaining {need} digits."

        if extracted.get("cvv"):
            cvv = normalize_cvv(str(extracted["cvv"]))
            if cvv:
                card.cvv = cvv
            else:
                return friendly_error("invalid_cvv", self.state.account_data["balance"])

        if extracted.get("expiry_month") and extracted.get("expiry_year"):
            month, year = normalize_expiry(extracted["expiry_month"], extracted["expiry_year"])
            if month:
                card.expiry_month = month
                card.expiry_year = year

        if extracted.get("cardholder_name"):
            card.cardholder_name = extracted["cardholder_name"].strip()
        elif not card.cardholder_name:
            # Default to verified account holder name
            card.cardholder_name = self.state.account_data["full_name"]

        if card.is_complete():
            # Pre-validate card before calling API
            error = validate_card(card.card_number, card.cvv, card.expiry_month, card.expiry_year)
            if error:
                balance = self.state.account_data["balance"]
                self.state.payment_attempts += 1
                if self.state.payment_attempts >= self.state.MAX_PAYMENT_ATTEMPTS:
                    self.state.phase = Phase.TERMINATED
                    return (
                        "I'm sorry, I wasn't able to process your payment after multiple attempts. "
                        "Please contact your bank or our support team for assistance. Thank you."
                    )
                # Reset the bad field so user can retry
                if error == "invalid_card":
                    card.card_number = None
                elif error == "invalid_cvv":
                    card.cvv = None
                elif error == "invalid_expiry":
                    card.expiry_month = None
                    card.expiry_year = None
                return friendly_error(error, balance)

            self.state.phase = Phase.PAYMENT_PROCESSING
            return self._handle_payment_processing(user_input)

        return response

    def _handle_payment_processing(self, user_input: str) -> str:
        self.state.payment_attempts += 1
        card = self.state.card
        balance = self.state.account_data["balance"]

        result = process_payment(
            account_id=self.state.account_id,
            amount=self.state.payment_amount,
            cardholder_name=card.cardholder_name,
            card_number=card.card_number,
            cvv=card.cvv,
            expiry_month=card.expiry_month,
            expiry_year=card.expiry_year,
        )

        if result["success"]:
            self.state.transaction_id = result["transaction_id"]
            self.state.phase = Phase.CLOSING
            return self._handle_closing(user_input)
        else:
            error_code = result.get("error_code", "unknown_error")
            retryable_errors = {"invalid_card", "invalid_cvv", "invalid_expiry", "invalid_amount", "invalid_args"}

            if error_code in retryable_errors:
                if self.state.payment_attempts >= self.state.MAX_PAYMENT_ATTEMPTS:
                    self.state.phase = Phase.TERMINATED
                    return (
                        "I'm sorry, I wasn't able to process your payment after multiple attempts. "
                        "Please contact your bank or our support team for assistance. Thank you."
                    )
                # Reset bad card field and go back to collection
                self.state.phase = Phase.PAYMENT_COLLECTION
                if error_code == "invalid_card":
                    self.state.card.card_number = None
                elif error_code == "invalid_cvv":
                    self.state.card.cvv = None
                elif error_code == "invalid_expiry":
                    self.state.card.expiry_month = None
                    self.state.card.expiry_year = None
                return friendly_error(error_code, balance)

            # Terminal
            self.state.phase = Phase.TERMINATED
            return (
                friendly_error(error_code, balance) + " "
                "This issue cannot be resolved automatically. Please contact our support team."
            )

    def _handle_closing(self, user_input: str) -> str:
        amount_str = f"₹{self.state.payment_amount:,.2f}"
        txn_id = self.state.transaction_id
        context = {
            "transaction_id": txn_id,
            "amount_paid": amount_str,
            "account_holder_name": self.state.account_data["full_name"],
        }
        result = self._llm_call(Phase.CLOSING, user_input, context)
        response = result.get("response", (
            f"Your payment of {amount_str} has been processed successfully. "
            f"Your transaction ID is {txn_id}. Thank you and have a great day!"
        ))
        # Post-LLM guardrail: ensure transaction ID and amount are present in response
        _, response = validate_critical_values(response, {
            "transaction ID": txn_id,
            "amount paid": amount_str,
        })
        return response

    def _handle_terminated(self, _user_input: str) -> str:
        return (
            "This session has been closed. Please contact our support team for further assistance. "
            "Thank you."
        )

    # ─── Helpers ──────────────────────────────────────────────────────

    def _merge_identity_fields(self, extracted: dict) -> str | None:
        """Merge extracted identity fields into state. Returns an error message if a field was invalid."""
        if extracted.get("full_name") and not self.state.provided_name:
            self.state.provided_name = extracted["full_name"].strip().title()

        if extracted.get("dob") and not self.state.provided_dob:
            normalized = normalize_dob(extracted["dob"])
            if normalized and is_valid_date(normalized):
                self.state.provided_dob = normalized
            else:
                return "That doesn't look like a valid date. Could you please provide your date of birth again?"

        if extracted.get("aadhaar_last4") and not self.state.provided_aadhaar_last4:
            norm = normalize_aadhaar_last4(str(extracted["aadhaar_last4"]))
            if norm:
                self.state.provided_aadhaar_last4 = norm

        if extracted.get("pincode") and not self.state.provided_pincode:
            norm = normalize_pincode(str(extracted["pincode"]))
            if norm:
                self.state.provided_pincode = norm

        return None

    # ─── LLM Call Wrapper ─────────────────────────────────────────────

    def _llm_call(self, phase: Phase, user_input: str, context: dict = None, use_tools: bool = False) -> dict:
        system_prompt = get_system_prompt(phase, context)
        try:
            return extract_and_respond(
                system_prompt=system_prompt,
                conversation_history=self._history[-10:],
                user_input=user_input,
                tools=[STORE_INFO_TOOL] if use_tools else None,
                tool_handler=self._handle_tool_call if use_tools else None,
            )
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return {"extracted": {}, "response": get_safe_fallback(phase)}

    def _handle_tool_call(self, tool_name: str, args: dict) -> str:
        if tool_name == "store_info":
            return handle_store_info(args, self._cache)
        return "unknown tool"
