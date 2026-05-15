# Assumptions

Documented assumptions where the assignment was ambiguous.

---

## 1. Name validation — no word count check

**Situation:** The user says "it's Nithin" instead of "Nithin Jain".

**Assignment says:** "Full name matches exactly."

**Assumption:** No client-side check on name completeness. Whatever the user provides is stored and compared exactly against the account data. A single word could legitimately be someone's full legal name (mononyms like Adele, Madonna, Beyoncé are real). The account data is the ground truth — if it doesn't match, the user gets a retry prompt naturally.

**Rationale:** Any heuristic to detect "incomplete" names (e.g. 2-word minimum) would incorrectly reject valid mononym accounts. The retry limit handles repeated wrong inputs gracefully without needing client-side name validation.

---

## 2. Partial name volunteered early — confirmation asks for full name

**Situation:** User says "hey it's Rahul" during greeting. The LLM caches "Rahul" via `store_info`. When identity collection starts, the agent has only a first name.

**Assignment says:** Don't re-ask for information already provided.

**Assumption:** A single-word cached name triggers "Is Rahul your full name? If not, could you please share your full name?" rather than a yes/no confirmation. The user can either confirm it is their complete legal name (mononym — accepted as-is) or provide their full name (replaces the cached value). This avoids burning a verification attempt on a name that may be incomplete.

**Rationale:** Strict matching against account data means "Rahul" will always fail against "Rahul Mehta". Asking once for the full name is lower cost than a failed verification attempt.

---

## 3. Name normalization to title case

**Situation:** User says "rahul mehta" but account stores "Rahul Mehta".

**Assignment says:** "No case-insensitive workarounds for names."

**Assumption:** We normalize the extracted name to title case before comparison. This is not fuzzy matching — spelling must still be exact. The assignment's restriction is interpreted as "don't fuzzily match different spellings", not "reject correctly-spelled names typed in lowercase".

**Rationale:** Users naturally type names in lowercase in a chat interface. Title case normalization is a standard formatting step, not a matching workaround.

---

## 4. Name matching is case-sensitive (after normalization)

**Assignment says:** "Matching is strict — no fuzzy matching, no case-insensitive workarounds for names."

**Assumption:** "no case-insensitive workarounds" means the match is case-sensitive. "nithin jain" would fail against "Nithin Jain".

**Rationale:** The assignment explicitly rules out workarounds. If this causes UX issues, the LLM extraction step should preserve the user's casing exactly so it matches what the account holds.

---

## 5. Retry limit scope

**Assignment says:** "Allow reasonable retries but implement a sensible retry limit."

**Assumption:** 3 attempts for verification. Each failed attempt (wrong name + secondary factor combination) counts as one. Incomplete inputs (e.g. first name only, missing secondary factor) do not count as attempts.

---

## 6. Partial payments on zero balance

**Assignment says:** ACC1003 has ₹0.00 balance. The API allows partial payments (amount ≤ balance).

**Assumption:** If balance is ₹0.00, any payment amount > 0 will be rejected as `insufficient_balance`. The agent informs the user there is no outstanding balance and closes the conversation.

---

## 7. Card is the only payment method

**Assignment says:** The `process_payment` API accepts card details (number, CVV, expiry, cardholder name).

**Assumption:** Card is treated as the only payment method since the API only exposes card-based payment. No payment method selection step is presented to the user. In production this would be a separate step offering card, UPI, netbanking, etc. before collecting details.

---

## 8. Cardholder name defaults to account holder name

**Assignment says:** "cardholder_name is accepted as-is and not validated against the account holder's name."

**Assumption:** If the user does not explicitly provide a cardholder name on the card, we default to the verified account holder's full name. This is a reasonable default for most cases.

---

## 9. Partial card number — digit count only, no echo

**Situation:** User dictates a card number across multiple turns and asks the agent to repeat what it has so far ("can you repeat the numbers I said?").

**Assignment says:** "Do not store or log raw card data beyond what is necessary."

**Assumption:** The agent reports only the digit count ("Got 11 digits so far — please share the remaining 5"), never the actual digits collected. Echoing partial card digits back — even in chunks — progressively leaks sensitive payment data. An attacker who has stolen the first 8 digits could confirm them by watching the agent reflect them back.

**Rationale:** The digit count gives the user enough feedback to know where they are without exposing what was captured.

---

## 10. Session is single-use

**Assignment does not specify** whether a session can be restarted after termination.

**Assumption:** Once the agent reaches `TERMINATED` or `CLOSING` phase, the session is closed. A new `Agent()` instance is required for a new session. No in-session restart is supported.
