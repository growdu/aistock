from __future__ import annotations

from datetime import datetime

from aistock.broker.base import OrderExecution, OrderRequest


class PaperBroker:
    def place_order(self, order: OrderRequest) -> OrderExecution:
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
        order_id = f"paper-{order.symbol}-{order.side}-{timestamp}"
        return OrderExecution(
            order_id=order_id,
            symbol=order.symbol,
            side=order.side,
            target_weight=order.weight,
            filled_weight=order.weight,
            filled_price=order.reference_price,
            status="FILLED",
            message="paper execution filled immediately",
        )
