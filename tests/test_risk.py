"""Tests for RiskEngine."""

from __future__ import annotations

import unittest

from aistock.common.types import RiskDecision, SignalAction, TradeSignal
from aistock.risk.engine import RiskCheckList, RiskEngine


class RiskCheckListTest(unittest.TestCase):
    def test_worst_decision_reject_wins(self) -> None:
        checks = RiskCheckList()
        checks.add("a", RiskDecision.ALLOW, "ok")
        checks.add("b", RiskDecision.REJECT, "bad")
        checks.add("c", RiskDecision.ADJUST, "ok")
        self.assertEqual(checks.worst_decision(), RiskDecision.REJECT)

    def test_worst_decision_adjust_wins_when_no_reject(self) -> None:
        checks = RiskCheckList()
        checks.add("a", RiskDecision.ALLOW, "ok")
        checks.add("b", RiskDecision.ADJUST, "reduce")
        self.assertEqual(checks.worst_decision(), RiskDecision.ADJUST)

    def test_adjusted_weight_zero_on_reject(self) -> None:
        checks = RiskCheckList()
        checks.add("a", RiskDecision.REJECT, "blocked")
        self.assertEqual(checks.adjusted_weight(0.5), 0.0)

    def test_adjusted_weight_unchanged_on_allow(self) -> None:
        checks = RiskCheckList()
        checks.add("a", RiskDecision.ALLOW, "ok")
        self.assertEqual(checks.adjusted_weight(0.5), 0.5)


class RiskEngineTest(unittest.TestCase):
    def setUp(self) -> None:
        from aistock.config.settings import FileConfig

        self.config = FileConfig()
        self.engine = RiskEngine(self.config)

    def test_evaluate_signal_allows_valid_signal(self) -> None:
        signal = TradeSignal(
            symbol="300750.SZ",
            action=SignalAction.BUY,
            target_weight=0.08,
            predicted_return=0.03,
            confidence=0.8,
            reason="test",
        )
        result = self.engine.evaluate(signal, daily_trade_count=0)
        self.assertIn(result.decision, [RiskDecision.ALLOW, RiskDecision.ADJUST])

    def test_evaluate_signal_rejects_low_confidence(self) -> None:
        self.config.risk.min_confidence_score = 0.9
        engine = RiskEngine(self.config)
        signal = TradeSignal(
            symbol="300750.SZ",
            action=SignalAction.BUY,
            target_weight=0.08,
            predicted_return=0.03,
            confidence=0.5,  # below 0.9 threshold
            reason="test",
        )
        result = engine.evaluate(signal, daily_trade_count=0)
        self.assertEqual(result.decision, RiskDecision.REJECT)

    def test_evaluate_signal_rejects_daily_trade_limit(self) -> None:
        self.config.risk.max_daily_trades = 3
        engine = RiskEngine(self.config)
        signal = TradeSignal(
            symbol="300750.SZ",
            action=SignalAction.BUY,
            target_weight=0.08,
            predicted_return=0.03,
            confidence=0.9,
            reason="test",
        )
        result = engine.evaluate(signal, daily_trade_count=3)
        self.assertEqual(result.decision, RiskDecision.REJECT)


if __name__ == "__main__":
    unittest.main()