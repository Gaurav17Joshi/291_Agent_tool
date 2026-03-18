from __future__ import annotations


class OrderStore:
    def __init__(self) -> None:
        self._db: dict[str, dict] = {}
        self._cache: dict[str, dict] = {}
        self.fail_next_write = False

    def save_order(self, order_id: str, payload: dict) -> None:
        """BUGGY: cache is written before DB; failure leaves cache-only state."""
        self._cache[order_id] = dict(payload)
        if self.fail_next_write:
            self.fail_next_write = False
            raise IOError("disk write failed")
        self._db[order_id] = dict(payload)

    def get_db(self, order_id: str) -> dict | None:
        return self._db.get(order_id)

    def get_cache(self, order_id: str) -> dict | None:
        return self._cache.get(order_id)
