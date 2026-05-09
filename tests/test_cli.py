from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

import pandas as pd
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from aistock.db.models import AccountState, PortfolioPosition, SignalRecord, TradeOrder


class CliSmokeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

        config_dir = self.root / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = config_dir / "settings.yaml"
        self.database_path = self.root / "test.db"
        self.data_dir = self.root / "data"
        self.logs_dir = self.root / "logs"

        with self.config_path.open("w", encoding="utf-8") as handle:
            handle.write(
                "\n".join(
                    [
                        "app:",
                        "  name: aistock-test",
                        f"  data_dir: {self.data_dir}",
                        f"  logs_dir: {self.logs_dir}",
                        "strategy:",
                        "  top_n: 3",
                        "  symbols:",
                        "    - 300750.SZ",
                        "    - 688041.SH",
                        "risk:",
                        "  max_daily_trades: 5",
                        "  max_symbols_per_trade: 3",
                        "  max_single_position_pct: 0.1",
                        "  min_confidence_score: 0.6",
                        "data_source:",
                        "  primary_provider: tushare",
                        "  enable_news: false",
                        "portfolio:",
                        "  initial_cash: 100000",
                        "  transaction_cost_rate: 0.001",
                        "  slippage_rate: 0.0005",
                        "backtest:",
                        "  initial_cash: 100000",
                        "  transaction_cost_rate: 0.001",
                        "  slippage_rate: 0.0005",
                    ]
                )
            )

        self.env = os.environ.copy()
        self.env.update(
            {
                "DATABASE_URL": f"sqlite:///{self.database_path}",
                "CONFIG_PATH": str(self.config_path),
                "LOG_LEVEL": "INFO",
            }
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _load_app(self):
        try:
            from typer.testing import CliRunner
            from aistock.app.cli import app
        except ModuleNotFoundError as exc:
            self.skipTest(f"runtime dependency missing: {exc}")
        return CliRunner(), app

    def test_prepare_runtime_and_health_check(self) -> None:
        runner, app = self._load_app()
        result = runner.invoke(app, ["prepare-runtime"], env=self.env)
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertTrue((self.data_dir / "raw").exists())
        self.assertTrue(self.logs_dir.exists())

        result = runner.invoke(app, ["health-check"], env=self.env)
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("health check passed", result.output)

    def test_signal_generation_flow(self) -> None:
        runner, app = self._load_app()
        for command in (
            ["init-db"],
            ["sync-data"],
            ["build-features"],
            ["train-model"],
            ["generate-signals"],
            ["show-signals"],
            ["paper-trade"],
            ["show-orders"],
            ["show-positions"],
            ["show-account"],
            ["run-backtest"],
        ):
            result = runner.invoke(app, command, env=self.env)
            self.assertEqual(result.exit_code, 0, f"{command}: {result.output}")

        repeat_trade = runner.invoke(app, ["paper-trade"], env=self.env)
        self.assertEqual(repeat_trade.exit_code, 0, repeat_trade.output)
        self.assertIn("no rebalance actions required", repeat_trade.output)

        engine = create_engine(self.env["DATABASE_URL"], future=True)
        with Session(engine) as session:
            session.query(SignalRecord).delete()
            session.add(
                SignalRecord(
                    symbol="300750.SZ",
                    action="BUY",
                    target_weight=0.05,
                    predicted_return=0.02,
                    confidence=0.9,
                    reason="manual rebalance down",
                )
            )
            session.commit()

        rebalance_down = runner.invoke(app, ["paper-trade"], env=self.env)
        self.assertEqual(rebalance_down.exit_code, 0, rebalance_down.output)
        self.assertIn("side=SELL", rebalance_down.output)

        with Session(engine) as session:
            session.query(SignalRecord).delete()
            session.add(
                SignalRecord(
                    symbol="300750.SZ",
                    action="BUY",
                    target_weight=0.08,
                    predicted_return=0.02,
                    confidence=0.9,
                    reason="manual rebalance up",
                )
            )
            session.commit()

        rebalance_up = runner.invoke(app, ["paper-trade"], env=self.env)
        self.assertEqual(rebalance_up.exit_code, 0, rebalance_up.output)
        self.assertIn("side=BUY", rebalance_up.output)

        with Session(engine) as session:
            order_count_before_skip = len(session.execute(select(TradeOrder)).scalars().all())
            session.query(SignalRecord).delete()
            session.add(
                SignalRecord(
                    symbol="688041.SH",
                    action="BUY",
                    target_weight=0.05,
                    predicted_return=0.001,
                    confidence=0.9,
                    reason="low edge should skip",
                )
            )
            session.commit()

        low_edge_trade = runner.invoke(app, ["paper-trade"], env=self.env)
        self.assertEqual(low_edge_trade.exit_code, 0, low_edge_trade.output)
        self.assertIn("skip 688041.SH expected_return=", low_edge_trade.output)

        with Session(engine) as session:
            order_count_after_skip = len(session.execute(select(TradeOrder)).scalars().all())

        self.assertEqual(order_count_before_skip, order_count_after_skip)

        market_path = self.data_dir / "raw" / "market_bar_1d.parquet"
        market_df = pd.read_parquet(market_path)
        latest_idx = market_df[market_df["ts_code"] == "300750.SZ"]["trade_date"].idxmax()
        market_df.loc[latest_idx, "close"] = float(market_df.loc[latest_idx, "close"]) * 1.1
        market_df.to_parquet(market_path, index=False)

        marked_account = runner.invoke(app, ["show-account"], env=self.env)
        self.assertEqual(marked_account.exit_code, 0, marked_account.output)
        self.assertIn("unrealized_pnl=", marked_account.output)

        marked_positions = runner.invoke(app, ["show-positions"], env=self.env)
        self.assertEqual(marked_positions.exit_code, 0, marked_positions.output)
        self.assertIn("market_value=", marked_positions.output)
        self.assertIn("unrealized_pnl=", marked_positions.output)
        self.assertIn("cost=", runner.invoke(app, ["show-orders"], env=self.env).output)
        self.assertIn("predicted_return=", runner.invoke(app, ["show-signals"], env=self.env).output)

        self.assertTrue((self.data_dir / "reports" / "signals.csv").exists())
        self.assertTrue((self.data_dir / "reports" / "backtest_curve.csv").exists())
        self.assertTrue((self.data_dir / "features" / "daily_features.parquet").exists())
        self.assertTrue((self.data_dir / "models" / "lightgbm_daily.txt").exists())
        self.assertTrue((self.data_dir / "models" / "lightgbm_daily.json").exists())
        self.assertTrue((self.logs_dir / "aistock-test.log").exists())

        backtest_curve = pd.read_csv(self.data_dir / "reports" / "backtest_curve.csv")
        for column in (
            "trade_date",
            "selected_count",
            "selected_weight",
            "available_cash",
            "invested_capital",
            "market_value",
            "unrealized_pnl",
            "transaction_cost",
            "slippage_cost",
            "total_cost",
            "day_return",
            "equity",
            "drawdown",
        ):
            self.assertIn(column, backtest_curve.columns)
        self.assertGreater(len(backtest_curve), 0)
        self.assertTrue((backtest_curve["available_cash"] >= 0).all())
        self.assertTrue((backtest_curve["equity"] > 0).all())
        self.assertTrue((backtest_curve["total_cost"] >= 0).all())
        self.assertGreater(backtest_curve["total_cost"].sum(), 0.0)

        with Session(engine) as session:
            orders = session.execute(select(TradeOrder)).scalars().all()
            positions = session.execute(select(PortfolioPosition)).scalars().all()
            account = session.get(AccountState, 1)

        self.assertGreaterEqual(len(orders), 1)
        self.assertGreaterEqual(len(orders), 3)
        self.assertEqual(len(positions), 1)
        self.assertTrue(all(order.status == "FILLED" for order in orders))
        self.assertTrue(any(order.side == "SELL" for order in orders))
        self.assertTrue(any(order.side == "BUY" for order in orders))
        self.assertTrue(all((order.total_cost or 0.0) > 0.0 for order in orders))
        self.assertTrue(all(position.status == "OPEN" for position in positions))
        self.assertAlmostEqual(positions[0].position_weight, 0.08, places=6)
        self.assertGreater(positions[0].market_value, positions[0].allocated_capital)
        self.assertGreater(positions[0].unrealized_pnl, 0.0)
        self.assertIsNotNone(account)
        self.assertLess(account.available_cash, account.initial_cash)
        self.assertEqual(account.daily_trade_count, len(orders))
        self.assertLess(account.realized_pnl, 0.0)
        self.assertGreater(account.unrealized_pnl, 0.0)
        self.assertGreater(account.total_equity, account.initial_cash)
        self.assertAlmostEqual(
            account.total_equity,
            account.available_cash + positions[0].market_value,
            places=6,
        )


if __name__ == "__main__":
    unittest.main()
