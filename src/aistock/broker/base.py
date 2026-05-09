from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(slots=True)
class OrderRequest:
    symbol: str
    side: str
    weight: float


class BrokerAdapter(Protocol):
    def place_order(self, order: OrderRequest) -> str:
        ...
