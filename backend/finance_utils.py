SUPPORTED_CURRENCIES = ["INR", "USD"]
EXPENSE_TYPES = ["personal_withdrawal", "business_expense", "unclassified"]
BASE_CURRENCY = "INR"


def to_base(amount: float, conversion_rate: float = None) -> float:
    """Convert a transaction amount into the company base currency (INR) using its
    per-transaction conversion_rate (defaults to 1.0, i.e. already in base currency)."""
    return (amount or 0) * (conversion_rate if conversion_rate else 1.0)
