def charge_cents(account_id: str, amount_cents: int) -> str:
    if amount_cents <= 0:
        raise ValueError("amount_cents must be positive")
    return f"charged:{account_id}:{amount_cents}"
