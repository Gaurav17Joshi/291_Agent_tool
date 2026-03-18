from __future__ import annotations


def calculate_subtotal_cents(items: list[dict]) -> int:
    """BUGGY: treats dollars as cents and drops precision."""
    subtotal = 0
    for item in items:
        subtotal += int(item["price"]) * int(item["qty"])
    return subtotal
