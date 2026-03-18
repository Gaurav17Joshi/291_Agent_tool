from __future__ import annotations

from typing import Union

from discounts import apply_discount_and_tax
from inventory import InventoryManager
from persistence import OrderStore
from pricing import calculate_subtotal_cents


def place_order(
    order_id: str,
    items: list[dict[str, Union[str, int, float]]],
    inventory: InventoryManager,
    store: OrderStore,
    discount_rate: float,
    tax_rate: float,
    payment_should_fail: bool = False,
) -> dict[str, Union[bool, str, int]]:
    """BUGGY: incorrect rollback and coarse error handling."""
    try:
        for item in items:
            inventory.reserve(item["sku"], item["qty"])

        subtotal_cents = calculate_subtotal_cents(items)
        total_cents = apply_discount_and_tax(subtotal_cents, discount_rate, tax_rate)

        if payment_should_fail:
            raise RuntimeError("payment gateway rejected charge")

        payload = {
            "order_id": order_id,
            "subtotal_cents": subtotal_cents,
            "total_cents": total_cents,
            "items": items,
        }
        store.save_order(order_id, payload)
        return {"ok": True, "order_id": order_id, "total_cents": total_cents}
    except Exception:
        # BUGGY: swallows root cause and does not rollback inventory
        return {"ok": False, "error": "order failed"}
