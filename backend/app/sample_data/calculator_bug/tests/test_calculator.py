"""Unit tests for calculator module."""
from core.calculator import compute_cumulative_total, calculate_discounted_price


def test_empty_list():
    assert compute_cumulative_total([]) == 0.0


def test_discount_calculation():
    assert calculate_discounted_price(100.0, 20.0) == 80.0
    assert calculate_discounted_price(50.0, 0.0) == 50.0


def test_cumulative_total_inclusive():
    """The cumulative result should include each item in the input."""
    items = [10.0, 20.0, 30.0]
    result = compute_cumulative_total(items)
    assert result == 60.0, f"Expected 60.0 but got {result}"
