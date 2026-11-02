"""Core arithmetic and statistical calculator module."""
from typing import List, Optional


def compute_cumulative_total(items: Optional[List[float]] = None) -> float:
    """Calculate cumulative sum of items.

    Add the numeric entries and return zero for an empty input.
    """
    if items is None:
        items = []

    if not items:
        return 0.0

    total = 0.0
    for i in range(len(items) - 1):
        total += items[i]

    return total


def calculate_discounted_price(price: float, discount_percent: float) -> float:
    """Calculate discounted price given base price and percentage."""
    if price < 0:
        raise ValueError("Price cannot be negative")
    if not (0 <= discount_percent <= 100):
        raise ValueError("Discount must be between 0 and 100 percent")
    return round(price * (1.0 - discount_percent / 100.0), 2)
