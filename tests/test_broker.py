"""Tests for SimBroker."""

from __future__ import annotations

import unittest

from aistock.broker.base import OrderSide, OrderStatus, OrderType, OrderRequest
from aistock.broker.paper import SimBroker, TradeConfig


class SimBrokerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.broker = SimBroker(
            TradeConfig(initial_cash=100_000.0, transaction_cost_rate=0.001, slippage_rate=0.0005)
        )
        # Set price so 100 shares cost ~50 per share
        self.broker.batch_update_prices({"300750.SZ": 50.0})

    def test_buy_fills_market_order(self) -> None:
        """Test BUY market order fills at reference price + slippage."""
        result = self.broker.place_order(
            OrderRequest(
                symbol="300750.SZ",
                side=OrderSide.BUY,
                volume=100,
                price=0.0,
                order_type=OrderType.MARKET,
                reference_price=50.0,
            )
        )
        self.assertEqual(result.status, OrderStatus.FILLED)
        self.assertEqual(result.filled_volume, 100)
        # Slippage adds cost: 50 * 1.0005 = 50.025
        self.assertAlmostEqual(result.avg_fill_price, 50.025, places=4)

    def test_sell_fills_market_order(self) -> None:
        """Test SELL market order fills at reference price - slippage."""
        # First buy to establish position
        self.broker.place_order(
            OrderRequest(
                symbol="300750.SZ",
                side=OrderSide.BUY,
                volume=100,
                price=0.0,
                order_type=OrderType.MARKET,
                reference_price=50.0,
            )
        )
        # Now sell
        result = self.broker.place_order(
            OrderRequest(
                symbol="300750.SZ",
                side=OrderSide.SELL,
                volume=100,
                price=0.0,
                order_type=OrderType.MARKET,
                reference_price=50.0,
            )
        )
        self.assertEqual(result.status, OrderStatus.FILLED)
        self.assertEqual(result.filled_volume, 100)
        # Slippage deducts: 50 * (1 - 0.0005) = 49.975
        self.assertAlmostEqual(result.avg_fill_price, 49.975, places=4)

    def test_insufficient_cash_rejected(self) -> None:
        """Test BUY rejected when cash is insufficient."""
        broker = SimBroker(TradeConfig(initial_cash=1000.0, transaction_cost_rate=0.001, slippage_rate=0.0005))
        broker.batch_update_prices({"300750.SZ": 50.0})
        result = broker.place_order(
            OrderRequest(
                symbol="300750.SZ",
                side=OrderSide.BUY,
                volume=1000,  # 1000 * 50 = 50,000 >> 1000 cash
                price=0.0,
                order_type=OrderType.MARKET,
                reference_price=50.0,
            )
        )
        self.assertEqual(result.status, OrderStatus.REJECTED)

    def test_batch_update_prices(self) -> None:
        """Test batch price update."""
        self.broker.batch_update_prices({"300750.SZ": 60.0, "688041.SH": 40.0})
        self.assertEqual(self.broker._market_prices.get("300750.SZ"), 60.0)
        self.assertEqual(self.broker._market_prices.get("688041.SH"), 40.0)

    def test_get_trade_log_after_trade(self) -> None:
        """Test trade log records filled orders."""
        self.broker.place_order(
            OrderRequest(
                symbol="300750.SZ",
                side=OrderSide.BUY,
                volume=100,
                price=0.0,
                order_type=OrderType.MARKET,
                reference_price=50.0,
            )
        )
        log = self.broker.get_trade_log()
        self.assertEqual(len(log), 1)
        self.assertEqual(log[0]["side"], "BUY")
        self.assertEqual(log[0]["symbol"], "300750.SZ")


if __name__ == "__main__":
    unittest.main()