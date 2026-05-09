from __future__ import annotations

from aistock.broker.base import OrderRequest


class PaperBroker:
    def place_order(self, order: OrderRequest) -> str:
        return f"paper-{order.symbol}-{order.side}-{int(order.weight * 10000)}"
