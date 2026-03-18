from __future__ import annotations

from typing import Union

from billing import apply_discount_then_tax, compute_subtotal_cents
from ledger import Ledger
from notifier import send_invoice
from persistence import AccountStore


def process_monthly_invoice(
    user_id: str,
    invoice_id: str,
    lines: list[dict[str, Union[str, int, float]]],
    ledger: Ledger,
    store: AccountStore,
    discount_rate: float,
    tax_rate: float,
    payment_should_fail: bool = False,
) -> dict[str, Union[bool, str, int]]:
    """BUGGY: does not rollback debit and swallows root cause."""
    try:
        subtotal_cents = compute_subtotal_cents(lines)
        total_cents = apply_discount_then_tax(subtotal_cents, discount_rate, tax_rate)

        ledger.debit(user_id, total_cents)

        if payment_should_fail:
            raise RuntimeError("payment processor declined")

        payload = {
            "invoice_id": invoice_id,
            "user_id": user_id,
            "subtotal_cents": subtotal_cents,
            "total_cents": total_cents,
            "lines": lines,
        }
        store.save_invoice(invoice_id, payload)
        send_invoice(user_id, invoice_id, total_cents)
        return {"ok": True, "invoice_id": invoice_id, "total_cents": total_cents}
    except Exception:
        return {"ok": False, "error": "billing failed"}
