from __future__ import annotations


def send_invoice(user_id: str, invoice_id: str, total_cents: int) -> dict[str, str | int]:
    return {
        "user_id": user_id,
        "invoice_id": invoice_id,
        "total_cents": total_cents,
        "status": "sent",
    }
