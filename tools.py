import httpx
from logger import logger

BASE_URL = "https://se-payment-verification-api.service.external.usea2.aws.prodigaltech.com"
TIMEOUT = 10.0


def lookup_account(account_id: str) -> dict:
    """
    POST /api/lookup-account
    Returns account data on success, or raises with error_code on failure.
    """
    logger.info(f"lookup_account | account_id={account_id}")
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            resp = client.post(
                f"{BASE_URL}/api/lookup-account",
                json={"account_id": account_id},
            )
        if resp.status_code == 200:
            logger.info(f"lookup_account | success | account_id={account_id}")
            return {"success": True, "data": resp.json()}
        elif resp.status_code == 404:
            logger.warning(f"lookup_account | not found | account_id={account_id}")
            return {"success": False, "error_code": "account_not_found"}
        else:
            logger.error(f"lookup_account | unexpected status={resp.status_code}")
            return {"success": False, "error_code": "api_error", "status": resp.status_code}
    except httpx.TimeoutException:
        logger.error("lookup_account | timeout")
        return {"success": False, "error_code": "timeout"}
    except Exception as e:
        logger.error(f"lookup_account | network_error | {e}")
        return {"success": False, "error_code": "network_error", "detail": str(e)}


def process_payment(
    account_id: str,
    amount: float,
    cardholder_name: str,
    card_number: str,
    cvv: str,
    expiry_month: int,
    expiry_year: int,
) -> dict:
    """
    POST /api/process-payment
    Returns transaction_id on success, or error_code on failure.
    """
    payload = {
        "account_id": account_id,
        "amount": round(amount, 2),
        "payment_method": {
            "type": "card",
            "card": {
                "cardholder_name": cardholder_name,
                "card_number": card_number,
                "cvv": cvv,
                "expiry_month": expiry_month,
                "expiry_year": expiry_year,
            },
        },
    }
    logger.info(f"process_payment | account_id={account_id} | amount={amount}")
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            resp = client.post(f"{BASE_URL}/api/process-payment", json=payload)
        data = resp.json()
        if resp.status_code == 200 and data.get("success"):
            logger.info(f"process_payment | success | txn_id={data['transaction_id']}")
            return {"success": True, "transaction_id": data["transaction_id"]}
        else:
            error_code = data.get("error_code", "unknown_error")
            logger.warning(f"process_payment | failed | error_code={error_code}")
            return {"success": False, "error_code": error_code}
    except httpx.TimeoutException:
        logger.error("process_payment | timeout")
        return {"success": False, "error_code": "timeout"}
    except Exception as e:
        logger.error(f"process_payment | network_error | {e}")
        return {"success": False, "error_code": "network_error", "detail": str(e)}
