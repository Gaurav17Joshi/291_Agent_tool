from __future__ import annotations


def compute_subtotal_cents(lines: list[dict]) -> int:
    """BUGGY: mixes dollars and cents."""
    subtotal = 0
    for line in lines:
        subtotal += int(line["unit_price"]) * int(line["qty"])
    return subtotal


def apply_discount_then_tax(subtotal_cents: int, discount_rate: float, tax_rate: float) -> int:
    """BUGGY: applies tax first, then discount with truncation."""
    taxed = int(subtotal_cents * (1.0 + tax_rate))
    discounted = int(taxed * (1.0 - discount_rate))
    return discounted
