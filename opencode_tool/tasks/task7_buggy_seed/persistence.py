from __future__ import annotations


class AccountStore:
    def __init__(self) -> None:
        self._db: dict[str, dict] = {}
        self._cache: dict[str, dict] = {}
        self.fail_next_write = False

    def save_invoice(self, invoice_id: str, payload: dict) -> None:
        """BUGGY: cache is mutated before DB write."""
        self._cache[invoice_id] = dict(payload)
        if self.fail_next_write:
            self.fail_next_write = False
            raise IOError("db write failed")
        self._db[invoice_id] = dict(payload)

    def get_db(self, invoice_id: str) -> dict | None:
        return self._db.get(invoice_id)

    def get_cache(self, invoice_id: str) -> dict | None:
        return self._cache.get(invoice_id)
