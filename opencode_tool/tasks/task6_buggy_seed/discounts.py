from __future__ import annotations


def apply_discount_and_tax(subtotal_cents: int, discount_rate: float, tax_rate: float) -> int:
    """BUGGY: uses wrong order and integer truncation."""
    discounted = int(subtotal_cents * (1.0 - discount_rate))
    taxed = int(discounted * (1.0 + tax_rate))
    return taxed
