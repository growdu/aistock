from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from aistock.model.predict import predict_feature_frame


def run_backtest(df: pd.DataFrame) -> dict[str, float]:
    if df.empty:
        return {"total_return": 0.0, "max_drawdown": 0.0}

    total_return = float(df["return_1"].fillna(0.0).sum()) if "return_1" in df.columns else 0.0
    return {"total_return": total_return, "max_drawdown": 0.0}


@dataclass(slots=True)
class BacktestResult:
    metrics: dict[str, float]
    curve: pd.DataFrame


def _position_weight_from_confidence(confidence: float, max_single_position_pct: float = 0.1) -> float:
    return min(max_single_position_pct, max(0.0, confidence) / 10.0)


def run_model_backtest(
    feature_df: pd.DataFrame,
    model_path: str,
    metadata_path: str,
    top_n: int,
    min_confidence_score: float,
    initial_cash: float = 100000.0,
    transaction_cost_rate: float = 0.001,
    slippage_rate: float = 0.0005,
) -> BacktestResult:
    if feature_df.empty:
        return BacktestResult(metrics={"total_return": 0.0, "max_drawdown": 0.0, "days": 0}, curve=pd.DataFrame())

    frame = feature_df.dropna(subset=["target_return_1d"]).copy()
    scored = predict_feature_frame(frame, model_path=model_path, metadata_path=metadata_path)

    daily_rows: list[dict[str, float | str | int]] = []
    grouped = scored.sort_values(["trade_date", "score"], ascending=[True, False]).groupby("trade_date")
    equity = initial_cash
    peak_equity = equity

    for trade_date, group in grouped:
        selected = group[group["confidence"] >= min_confidence_score].head(top_n)
        if selected.empty:
            selected_count = 0
            selected_weight = 0.0
            invested_capital = 0.0
            available_cash = equity
            market_value = 0.0
            unrealized_pnl = 0.0
            transaction_cost = 0.0
            slippage_cost = 0.0
            total_cost = 0.0
            day_return = 0.0
        else:
            selected_count = int(len(selected))
            weighted = selected.copy()
            weighted["target_weight"] = weighted["confidence"].apply(_position_weight_from_confidence)
            weighted["allocated_capital"] = weighted["target_weight"] * equity
            weighted["gross_end_market_value"] = weighted["allocated_capital"] * (1.0 + weighted["target_return_1d"])

            selected_weight = float(weighted["target_weight"].sum())
            invested_capital = float(weighted["allocated_capital"].sum())
            available_cash = float(max(equity - invested_capital, 0.0))
            transaction_cost = invested_capital * transaction_cost_rate
            slippage_cost = invested_capital * slippage_rate
            total_cost = transaction_cost + slippage_cost
            market_value = float(max(weighted["gross_end_market_value"].sum() - total_cost, 0.0))
            unrealized_pnl = float(market_value - invested_capital)
            end_equity = available_cash + market_value
            day_return = float(end_equity / equity - 1.0) if equity > 0 else 0.0
            equity = end_equity

        if selected.empty:
            end_equity = equity
        peak_equity = max(peak_equity, end_equity)
        drawdown = end_equity / peak_equity - 1.0 if peak_equity > 0 else 0.0
        daily_rows.append(
            {
                "trade_date": trade_date,
                "selected_count": selected_count,
                "selected_weight": selected_weight,
                "available_cash": available_cash,
                "invested_capital": invested_capital,
                "market_value": market_value,
                "unrealized_pnl": unrealized_pnl,
                "transaction_cost": transaction_cost,
                "slippage_cost": slippage_cost,
                "total_cost": total_cost,
                "day_return": day_return,
                "equity": end_equity,
                "drawdown": drawdown,
            }
        )

    curve = pd.DataFrame(daily_rows)
    total_return = float(equity / initial_cash - 1.0) if initial_cash > 0 else 0.0
    max_drawdown = float(curve["drawdown"].min()) if not curve.empty else 0.0
    avg_day_return = float(curve["day_return"].mean()) if not curve.empty else 0.0
    final_available_cash = float(curve["available_cash"].iloc[-1]) if not curve.empty else initial_cash
    final_market_value = float(curve["market_value"].iloc[-1]) if not curve.empty else 0.0
    final_unrealized_pnl = float(curve["unrealized_pnl"].iloc[-1]) if not curve.empty else 0.0
    total_transaction_cost = float(curve["transaction_cost"].sum()) if not curve.empty else 0.0
    total_slippage_cost = float(curve["slippage_cost"].sum()) if not curve.empty else 0.0
    total_cost = float(curve["total_cost"].sum()) if not curve.empty else 0.0

    return BacktestResult(
        metrics={
            "total_return": total_return,
            "max_drawdown": max_drawdown,
            "days": float(len(curve)),
            "avg_day_return": avg_day_return,
            "final_available_cash": final_available_cash,
            "final_market_value": final_market_value,
            "final_unrealized_pnl": final_unrealized_pnl,
            "final_equity": float(equity),
            "total_transaction_cost": total_transaction_cost,
            "total_slippage_cost": total_slippage_cost,
            "total_cost": total_cost,
        },
        curve=curve,
    )
