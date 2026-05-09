from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(slots=True)
class OrderRequest:
    symbol: str
    side: str
    weight: float
    reference_price: float | None = None
    reason: str = ""


@dataclass(slots=True)
class OrderExecution:
    order_id: str
    symbol: str
    side: str
    target_weight: float
    filled_weight: float
    filled_price: float | None
    status: str
    message: str = ""


class BrokerAdapter(Protocol):
    def place_order(self, order: OrderRequest) -> OrderExecution:
        ...
