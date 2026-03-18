from __future__ import annotations


class Ledger:
    def __init__(self, balances: dict[str, int]):
        self.balances = dict(balances)

    def debit(self, user_id: str, amount_cents: int) -> None:
        current = self.balances.get(user_id, 0)
        if current < amount_cents:
            raise ValueError("insufficient funds")
        self.balances[user_id] = current - amount_cents

    def credit(self, user_id: str, amount_cents: int) -> None:
        self.balances[user_id] = self.balances.get(user_id, 0) + amount_cents
