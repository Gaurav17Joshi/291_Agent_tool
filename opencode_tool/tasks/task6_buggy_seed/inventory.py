from __future__ import annotations


class InventoryManager:
    def __init__(self, stock: dict[str, int]):
        self.stock = dict(stock)
        self.reserved: dict[str, int] = {}

    def reserve(self, sku: str, qty: int) -> None:
        available = self.stock.get(sku, 0)
        if available < qty:
            raise ValueError(f"insufficient stock for {sku}")
        self.stock[sku] = available - qty
        self.reserved[sku] = self.reserved.get(sku, 0) + qty

    def release(self, sku: str, qty: int) -> None:
        self.stock[sku] = self.stock.get(sku, 0) + qty
        self.reserved[sku] = max(0, self.reserved.get(sku, 0) - qty)
