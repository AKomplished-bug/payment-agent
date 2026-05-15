from info_cache import InfoCache
from verification import normalize_dob, normalize_aadhaar_last4, normalize_pincode, normalize_account_id, is_valid_date
from logger import logger

# Tool schema passed to LLM
STORE_INFO_TOOL = {
    "type": "function",
    "function": {
        "name": "store_info",
        "description": (
            "Store any user-volunteered information into the session cache for later use. "
            "Call this whenever the user mentions their name, date of birth, Aadhaar last 4, "
            "pincode, or account ID — even if you haven't asked for it yet."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "full_name": {
                    "type": "string",
                    "description": "User's full name as stated. Will be title-cased automatically."
                },
                "dob": {
                    "type": "string",
                    "description": "Date of birth in any format. Will be normalized to YYYY-MM-DD."
                },
                "aadhaar_last4": {
                    "type": "string",
                    "description": "Last 4 digits of Aadhaar number."
                },
                "pincode": {
                    "type": "string",
                    "description": "6-digit residential pincode."
                },
                "account_id": {
                    "type": "string",
                    "description": "Account ID mentioned by the user."
                },
            },
            "required": [],
        },
    },
}


def handle_store_info(args: dict, cache: InfoCache) -> str:
    """
    Execute the store_info tool call — normalize and persist values into cache.
    Returns a tool result string for the LLM.
    """
    stored = []

    if args.get("full_name") and not cache.full_name:
        cache.full_name = args["full_name"].strip().title()
        stored.append(f"full_name={cache.full_name}")
        logger.debug(f"cache | stored full_name={cache.full_name}")

    if args.get("dob") and not cache.dob:
        normalized = normalize_dob(args["dob"])
        if normalized and is_valid_date(normalized):
            cache.dob = normalized
            stored.append("dob=<stored>")
            logger.debug("cache | stored dob")

    if args.get("aadhaar_last4") and not cache.aadhaar_last4:
        norm = normalize_aadhaar_last4(str(args["aadhaar_last4"]))
        if norm:
            cache.aadhaar_last4 = norm
            stored.append("aadhaar_last4=<stored>")
            logger.debug("cache | stored aadhaar_last4")

    if args.get("pincode") and not cache.pincode:
        norm = normalize_pincode(str(args["pincode"]))
        if norm:
            cache.pincode = norm
            stored.append("pincode=<stored>")
            logger.debug("cache | stored pincode")

    if args.get("account_id") and not cache.account_id:
        norm = normalize_account_id(args["account_id"])
        if norm:
            cache.account_id = norm
            stored.append(f"account_id={cache.account_id}")
            logger.debug(f"cache | stored account_id={cache.account_id}")

    if stored:
        return f"Stored: {', '.join(stored)}"
    return "Nothing new to store."
