from __future__ import annotations

import unittest

from inventory import InventoryManager
from order_service import place_order
from persistence import OrderStore


class OrderFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.inventory = InventoryManager({"A": 10, "B": 5})
        self.store = OrderStore()

    def test_success_total_uses_consistent_money_units_and_spec_order(self) -> None:
        items = [
            {"sku": "A", "qty": 2, "price": 12.50},
            {"sku": "B", "qty": 1, "price": 5.00}
        ]
        result = place_order(
            order_id="order-1",
            items=items,
            inventory=self.inventory,
            store=self.store,
            discount_rate=0.10,
            tax_rate=0.10,
            payment_should_fail=False
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["total_cents"], 2970)
        self.assertIsNotNone(self.store.get_db("order-1"))

    def test_payment_failure_rolls_back_inventory_and_preserves_error(self) -> None:
        items = [{"sku": "A", "qty": 3, "price": 10.00}]
        result = place_order(
            order_id="order-2",
            items=items,
            inventory=self.inventory,
            store=self.store,
            discount_rate=0.0,
            tax_rate=0.0,
            payment_should_fail=True
        )

        self.assertFalse(result["ok"])
        self.assertIn("payment", str(result.get("error", "")).lower())
        self.assertEqual(self.inventory.stock["A"], 10)

    def test_persistence_consistency_on_write_failure(self) -> None:
        self.store.fail_next_write = True
        items = [{"sku": "A", "qty": 1, "price": 1.00}]
        result = place_order(
            order_id="order-3",
            items=items,
            inventory=self.inventory,
            store=self.store,
            discount_rate=0.0,
            tax_rate=0.0,
            payment_should_fail=False
        )

        self.assertFalse(result["ok"])
        self.assertIsNone(self.store.get_db("order-3"))
        self.assertIsNone(self.store.get_cache("order-3"))
        self.assertEqual(self.inventory.stock["A"], 10)


if __name__ == "__main__":
    unittest.main()
