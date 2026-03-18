from __future__ import annotations

import unittest

from account_service import process_monthly_invoice
from ledger import Ledger
from persistence import AccountStore


class AccountFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ledger = Ledger({"u1": 10000})
        self.store = AccountStore()

    def test_success_total_uses_consistent_money_units_and_spec_order(self) -> None:
        lines = [
            {"sku": "A", "qty": 2, "unit_price": 12.50},
            {"sku": "B", "qty": 1, "unit_price": 5.00},
        ]
        result = process_monthly_invoice(
            user_id="u1",
            invoice_id="inv-1",
            lines=lines,
            ledger=self.ledger,
            store=self.store,
            discount_rate=0.10,
            tax_rate=0.10,
            payment_should_fail=False,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["total_cents"], 2970)
        self.assertEqual(self.ledger.balances["u1"], 7030)
        self.assertIsNotNone(self.store.get_db("inv-1"))

    def test_payment_failure_rolls_back_ledger_and_preserves_error(self) -> None:
        lines = [{"sku": "A", "qty": 1, "unit_price": 10.00}]
        result = process_monthly_invoice(
            user_id="u1",
            invoice_id="inv-2",
            lines=lines,
            ledger=self.ledger,
            store=self.store,
            discount_rate=0.0,
            tax_rate=0.0,
            payment_should_fail=True,
        )

        self.assertFalse(result["ok"])
        self.assertIn("payment", str(result.get("error", "")).lower())
        self.assertEqual(self.ledger.balances["u1"], 10000)
        self.assertIsNone(self.store.get_db("inv-2"))

    def test_persistence_consistency_on_write_failure(self) -> None:
        self.store.fail_next_write = True
        lines = [{"sku": "A", "qty": 1, "unit_price": 1.00}]
        result = process_monthly_invoice(
            user_id="u1",
            invoice_id="inv-3",
            lines=lines,
            ledger=self.ledger,
            store=self.store,
            discount_rate=0.0,
            tax_rate=0.0,
            payment_should_fail=False,
        )

        self.assertFalse(result["ok"])
        self.assertIsNone(self.store.get_db("inv-3"))
        self.assertIsNone(self.store.get_cache("inv-3"))
        self.assertEqual(self.ledger.balances["u1"], 10000)


if __name__ == "__main__":
    unittest.main()
