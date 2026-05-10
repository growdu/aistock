from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import typer
from sqlalchemy import select, text

from aistock.app.logging import setup_logging
from aistock.backtest.engine import run_backtest, run_model_backtest
from aistock.broker import SimBroker, TradeConfig
from aistock.broker.base import OrderSide, OrderStatus, OrderType, OrderRequest
from aistock.execution import create_execution_engine
from aistock.config.settings import load_settings
from aistock.data.pipeline import DEFAULT_WATCHLIST, ensure_runtime_dirs, sync_all, sync_market_data
from aistock.db.base import build_engine, build_session_factory, initialize_database
from aistock.db.models import AccountState, PortfolioPosition, SignalRecord, TradeOrder
from aistock.feature.factors import build_daily_features
from aistock.model.predict import predict_from_model, score_candidates
from aistock.model.train import train_model, train_all_targets
from aistock.report.dashboard import write_backtest_curve, write_signal_report
from aistock.risk.engine import evaluate_signal
from aistock.strategy.engine import generate_signals

app = typer.Typer(help="Personal AI-assisted quant trading system.")
logger = logging.getLogger(__name__)
ACCOUNT_STATE_ID = 1


@dataclass(slots=True)
class RebalancePlan:
    symbol: str
    side: str
    desired_weight: float
    current_weight: float
    trade_weight: float
    confidence: float
    predicted_return: float
    reason: str


def _load_latest_prices(data_root: Path) -> dict[str, float]:
    market_path = data_root / "raw" / "market_bar_1d.parquet"
    if not market_path.exists():
        return {}

    market_df = pd.read_parquet(market_path)
    if market_df.empty:
        return {}

    latest_rows = (
        market_df.sort_values(["ts_code", "trade_date"])
        .groupby("ts_code", as_index=False)
        .tail(1)
        .reset_index(drop=True)
    )
    return {
        str(row["ts_code"]): float(row["close"])
        for _, row in latest_rows.iterrows()
        if pd.notna(row["close"])
    }


def _today_str() -> str:
    return date.today().strftime("%Y%m%d")


def _load_or_create_account(session, initial_cash: float) -> AccountState:
    account = session.get(AccountState, ACCOUNT_STATE_ID)
    if account is not None:
        return account

    account = AccountState(
        id=ACCOUNT_STATE_ID,
        initial_cash=initial_cash,
        available_cash=initial_cash,
        invested_capital=0.0,
        total_equity=initial_cash,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
        daily_trade_count=0,
        last_trade_date="",
    )
    session.add(account)
    session.flush()
    return account


def _reset_daily_trade_counter(account: AccountState) -> None:
    if account.last_trade_date != _today_str():
        account.daily_trade_count = 0
        account.last_trade_date = _today_str()


def _estimate_market_value(position: PortfolioPosition, latest_prices: dict[str, float] | None = None) -> float:
    allocated_capital = position.allocated_capital or 0.0
    price = None
    if latest_prices is not None:
        price = latest_prices.get(position.symbol)
    if price is None:
        price = position.last_price

    if price is not None:
        position.last_price = price

    # 有成本价时用成本比例估算（allocated_capital 已按成本记录）
    # 无成本价时用 allocated_capital 本身
    if position.entry_price and position.entry_price > 0 and price is not None:
        return allocated_capital * float(price / position.entry_price)
    # 无 entry_price 时：如果 allocated_capital > 0，说明是按资金分配的历史持仓，用当前价格重算
    # 否则返回 0
    if allocated_capital > 0 and price is not None:
        return allocated_capital
    return 0.0


def _refresh_account_snapshot(
    session,
    account: AccountState,
    latest_prices: dict[str, float] | None = None,
) -> None:
    positions = session.execute(select(PortfolioPosition)).scalars().all()
    invested_capital = 0.0
    market_value_total = 0.0
    unrealized_pnl_total = 0.0
    for position in positions:
        if position.status != "OPEN":
            position.market_value = 0.0
            position.unrealized_pnl = 0.0
            continue

        allocated_capital = position.allocated_capital
        if allocated_capital is None:
            allocated_capital = position.position_weight * account.initial_cash
            position.allocated_capital = allocated_capital

        market_value = _estimate_market_value(position, latest_prices)
        unrealized_pnl = float(market_value - allocated_capital)

        position.market_value = market_value
        position.unrealized_pnl = unrealized_pnl

        invested_capital += float(allocated_capital)
        market_value_total += market_value
        unrealized_pnl_total += unrealized_pnl

    if invested_capital > 0 and account.available_cash == account.initial_cash:
        account.available_cash = max(account.initial_cash + account.realized_pnl - invested_capital, 0.0)

    account.invested_capital = invested_capital
    account.unrealized_pnl = unrealized_pnl_total
    account.total_equity = account.available_cash + market_value_total


def _build_rebalance_plans(session) -> list[RebalancePlan]:
    signal_rows = session.execute(select(SignalRecord)).scalars().all()
    positions = {
        position.symbol: position
        for position in session.execute(select(PortfolioPosition)).scalars().all()
        if position.status == "OPEN"
    }
    desired_by_symbol = {
        row.symbol: row
        for row in signal_rows
        if row.action == "BUY" and row.target_weight > 0
    }
    symbols = sorted(set(positions) | set(desired_by_symbol))

    plans: list[RebalancePlan] = []
    for symbol in symbols:
        position = positions.get(symbol)
        current_weight = position.position_weight if position is not None else 0.0
        signal_row = desired_by_symbol.get(symbol)
        desired_weight = signal_row.target_weight if signal_row is not None else 0.0
        delta_weight = desired_weight - current_weight

        if abs(delta_weight) < 1e-6:
            continue

        if delta_weight > 0:
            side = "BUY"
            trade_weight = delta_weight
            confidence = signal_row.confidence if signal_row is not None else 0.0
            reason = signal_row.reason if signal_row is not None else "increase to target weight"
        else:
            side = "SELL"
            trade_weight = abs(delta_weight)
            confidence = signal_row.confidence if signal_row is not None else 1.0
            reason = "liquidate missing signal" if signal_row is None else "reduce to target weight"

        plan = RebalancePlan(
            symbol=symbol,
            side=side,
            desired_weight=desired_weight,
            current_weight=current_weight,
            trade_weight=trade_weight,
            confidence=confidence,
            predicted_return=float(signal_row.predicted_return or 0.0) if signal_row is not None else 0.0,
            reason=reason,
        )
        plans.append(plan)

    sells = sorted(
        [plan for plan in plans if plan.side == "SELL"],
        key=lambda plan: plan.trade_weight,
        reverse=True,
    )
    buys = sorted(
        [plan for plan in plans if plan.side == "BUY"],
        key=lambda plan: (plan.confidence, plan.trade_weight),
        reverse=True,
    )
    return sells + buys


@app.callback()
def main() -> None:
    runtime, file_config = load_settings()
    setup_logging(runtime.log_level, logs_dir=file_config.app.logs_dir, app_name=file_config.app.name)


@app.command("prepare-runtime")
def prepare_runtime() -> None:
    _, file_config = load_settings()
    runtime_dirs = ensure_runtime_dirs(file_config)
    typer.echo(f"logs directory ready: {runtime_dirs['logs_path']}")
    for path in runtime_dirs["data_paths"]:
        typer.echo(f"data directory ready: {path}")


@app.command("show-config")
def show_config() -> None:
    runtime, file_config = load_settings()
    typer.echo(f"env={runtime.env}")
    typer.echo(f"database_url={runtime.database_url}")
    typer.echo(f"data_dir={file_config.app.data_dir}")
    typer.echo(f"logs_dir={file_config.app.logs_dir}")
    typer.echo(f"provider={file_config.data_source.primary_provider}")
    typer.echo(f"llm_enabled={file_config.model.llm_enabled}")
    typer.echo(f"initial_cash={file_config.portfolio.initial_cash}")
    typer.echo(f"portfolio_transaction_cost_rate={file_config.portfolio.transaction_cost_rate}")
    typer.echo(f"portfolio_slippage_rate={file_config.portfolio.slippage_rate}")
    typer.echo(f"portfolio_min_expected_excess_return={file_config.portfolio.min_expected_excess_return}")
    typer.echo(f"backtest_initial_cash={file_config.backtest.initial_cash}")
    typer.echo(f"backtest_transaction_cost_rate={file_config.backtest.transaction_cost_rate}")
    typer.echo(f"backtest_slippage_rate={file_config.backtest.slippage_rate}")


@app.command("init-db")
def init_db() -> None:
    runtime, _ = load_settings()
    initialize_database(runtime.database_url)
    typer.echo("database initialized")


@app.command("sync-data")
def sync_data(
    symbols: str = typer.Option("", help="Comma-separated ts_code list, e.g. 300750.SZ,688041.SH"),
    start_date: str = typer.Option("", help="Start date in YYYYMMDD"),
    end_date: str = typer.Option("", help="End date in YYYYMMDD"),
    mode: str = typer.Option("daily", help="Sync mode: daily (default) or all (full dataset including financials/minute)"),
    include_minute: bool = typer.Option(False, help="Include minute-level bars (5m freq)"),
    skip_financial: bool = typer.Option(False, help="Skip financial indicators (faster for daily sync)"),
) -> None:
    """
    Synchronize market data from Tushare.

    Modes:
        daily   - Only daily bars and daily basics (fast, suitable for daily cron)
        all     - Full sync: daily + index + moneyflow + financials + optional minute bars

    Examples:
        aistock sync-data  # use configured watchlist, last 120 trading days
        aistock sync-data --symbols 300750.SZ,688041.SH --start-date 20240101 --end-date 20241231
        aistock sync-data --mode all --include-minute  # full sync with minute bars
    """
    runtime, file_config = load_settings()
    initialize_database(runtime.database_url)
    today = date.today()
    resolved_end_date = end_date or today.strftime("%Y%m%d")
    resolved_start_date = start_date or (today - timedelta(days=730)).strftime("%Y%m%d")
    resolved_symbols = [item.strip() for item in symbols.split(",") if item.strip()] or file_config.strategy.symbols or DEFAULT_WATCHLIST

    if mode == "all":
        results = sync_all(
            runtime=runtime,
            file_config=file_config,
            symbols=resolved_symbols,
            start_date=resolved_start_date,
            end_date=resolved_end_date,
            include_minute=include_minute,
            sync_financial=not skip_financial,
        )
        typer.echo(f"full sync completed: {results}")
    else:
        sync_market_data(
            runtime=runtime,
            file_config=file_config,
            symbols=resolved_symbols,
            start_date=resolved_start_date,
            end_date=resolved_end_date,
        )
        typer.echo(
            f"daily data synced for {len(resolved_symbols)} symbols "
            f"from {resolved_start_date} to {resolved_end_date}"
        )


@app.command("build-features")
def build_features_command() -> None:
    _, file_config = load_settings()
    ensure_runtime_dirs(file_config)

    data_root = Path(file_config.app.data_dir)
    market_path = data_root / "raw" / "market_bar_1d.parquet"
    daily_basic_path = data_root / "raw" / "daily_basic_1d.parquet"
    output_path = data_root / "features" / "daily_features.parquet"

    if not market_path.exists():
        raise typer.BadParameter("run sync-data before build-features")

    market_df = pd.read_parquet(market_path)
    daily_basic_df = pd.read_parquet(daily_basic_path) if daily_basic_path.exists() else pd.DataFrame()
    features = build_daily_features(market_df, daily_basic_df)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    features.to_parquet(output_path, index=False)
    typer.echo(f"features written to {output_path}")


@app.command("train-model")
def train_model_command(
    target: str = typer.Option("target_return_1d", help="Target column: target_return_1d / 3d / 5d"),
    model_name: str = typer.Option("", help="Output model name (without extension). Default: target_modeltype_tag"),
    model_type: str = typer.Option("lightgbm", help="Model type: lightgbm or xgboost"),
    train_all: bool = typer.Option(False, help="Train all targets (1d, 3d, 5d) at once"),
    tag: str = typer.Option("prod", help="Model tag (e.g. prod, test)"),
) -> None:
    """
    Train a LightGBM or XGBoost model on the feature set.

    Examples:
        aistock train-model                          # train target_return_1d with lightgbm
        aistock train-model --target target_return_3d --model-type xgboost
        aistock train-model --train-all              # train 1d + 3d + 5d targets
    """
    _, file_config = load_settings()
    ensure_runtime_dirs(file_config)

    features_path = Path(file_config.app.data_dir) / "features" / "daily_features.parquet"
    if not features_path.exists():
        raise typer.BadParameter("run build-features before train-model")

    feature_df = pd.read_parquet(features_path)
    model_dir = Path(file_config.app.data_dir) / "models"

    if train_all:
        results = train_all_targets(
            features=feature_df,
            model_dir=str(model_dir),
            model_type=model_type,  # type: ignore[arg-type]
            model_tag=tag,
        )
        for name, result in results.items():
            typer.echo(
                f"trained {name}: {result.model_path} "
                f"(val_rmse={result.metrics.val_rmse:.6f}, val_ic={result.metrics.val_ic:.4f})"
            )
    else:
        result = train_model(
            frame=feature_df,
            target_column=target,
            model_type=model_type,  # type: ignore[arg-type]
            model_dir=str(model_dir),
            model_tag=tag,
            output_name=model_name or None,
        )
        typer.echo(
            f"model trained: {result.model_path}\n"
            f"  metadata : {result.metadata_path}\n"
            f"  report   : {result.report_path}\n"
            f"  target   : {result.metrics.target_column}\n"
            f"  type     : {result.metrics.model_type}\n"
            f"  features : {result.metrics.val_rmse:.6f}\n"
            f"  val_rmse : {result.metrics.val_rmse:.6f}\n"
            f"  val_ic   : {result.metrics.val_ic:.4f}\n"
            f"  best_iter: {result.metrics.best_iteration}\n"
            f"  rows     : train={result.metrics.train_rows}, val={result.metrics.val_rows}, test={result.metrics.test_rows}"
        )


@app.command("generate-signals")
def generate_signals_command() -> None:
    runtime, file_config = load_settings()
    ensure_runtime_dirs(file_config)
    initialize_database(runtime.database_url)

    data_root = Path(file_config.app.data_dir)
    features_path = data_root / "features" / "daily_features.parquet"
    model_path = data_root / "models" / "lightgbm_daily.txt"
    metadata_path = data_root / "models" / "lightgbm_daily.json"

    if features_path.exists() and model_path.exists() and metadata_path.exists():
        feature_df = pd.read_parquet(features_path)
        predictions = predict_from_model(feature_df, model_path=model_path, metadata_path=metadata_path)
        logger.info("generated predictions from trained model")
    else:
        fallback_symbols = [item.split(".")[0] for item in file_config.strategy.symbols]
        predictions = score_candidates(fallback_symbols)
        logger.info("trained model artifacts missing, using fallback ranking")

    signals = generate_signals(predictions, file_config)

    session_factory = build_session_factory(runtime.database_url)
    with session_factory() as session:
        session.query(SignalRecord).delete()
        for signal in signals:
            risk = evaluate_signal(signal, file_config, daily_trade_count=0)
            if risk.decision.value == "REJECT":
                logger.info("signal rejected for %s: %s", signal.symbol, risk.message)
                continue

            session.add(
                SignalRecord(
                    symbol=signal.symbol,
                    action=signal.action.value,
                    target_weight=risk.adjusted_weight,
                    predicted_return=signal.predicted_return,
                    confidence=min(1.0, risk.adjusted_weight * 10),
                    reason=risk.message,
                )
            )
        session.commit()

    output = Path(file_config.app.data_dir) / "reports" / "signals.csv"
    write_signal_report(
        [
            {
                "symbol": signal.symbol,
                "action": signal.action.value,
                "target_weight": signal.target_weight,
                "predicted_return": signal.predicted_return,
            }
            for signal in signals
        ],
        str(output),
    )
    typer.echo(f"signals written to {output}")
    buy_count = sum(1 for s in signals if s.action.value == "BUY")
    sell_count = sum(1 for s in signals if s.action.value == "SELL")
    total_weight = sum(s.target_weight for s in signals)
    typer.echo(f"summary: {len(signals)} signals ({buy_count} BUY, {sell_count} SELL), total_weight={total_weight:.3f}")


@app.command("show-signals")
def show_signals() -> None:
    runtime, _ = load_settings()
    initialize_database(runtime.database_url)
    session_factory = build_session_factory(runtime.database_url)
    with session_factory() as session:
        rows = session.execute(select(SignalRecord)).scalars().all()
        if not rows:
            typer.echo("no signals found (run generate-signals first)")
            return
        for row in rows:
            predicted_return_text = f"{(row.predicted_return or 0.0):.4f}"
            typer.echo(
                f"{row.symbol} {row.action} weight={row.target_weight:.3f} "
                f"predicted_return={predicted_return_text} reason={row.reason}"
            )


@app.command("show-orders")
def show_orders() -> None:
    runtime, _ = load_settings()
    initialize_database(runtime.database_url)
    session_factory = build_session_factory(runtime.database_url)
    with session_factory() as session:
        rows = session.execute(select(TradeOrder).order_by(TradeOrder.created_at.desc())).scalars().all()
        if not rows:
            typer.echo("no orders found (run paper-trade first)")
            return
        for row in rows:
            price_text = f"{row.filled_price:.3f}" if row.filled_price is not None else "NA"
            cost_text = f"{(row.total_cost or 0.0):.2f}"
            typer.echo(
                f"{row.order_id} {row.symbol} {row.side} "
                f"weight={row.filled_weight:.3f} status={row.status} price={price_text} cost={cost_text}"
            )


@app.command("show-positions")
def show_positions() -> None:
    runtime, file_config = load_settings()
    initialize_database(runtime.database_url)
    session_factory = build_session_factory(runtime.database_url)
    latest_prices = _load_latest_prices(Path(file_config.app.data_dir))
    with session_factory() as session:
        account = _load_or_create_account(session, file_config.portfolio.initial_cash)
        _refresh_account_snapshot(session, account, latest_prices)
        session.commit()
        rows = session.execute(select(PortfolioPosition).order_by(PortfolioPosition.symbol)).scalars().all()
        for row in rows:
            price_text = f"{row.last_price:.3f}" if row.last_price is not None else "NA"
            capital_text = f"{(row.allocated_capital or 0.0):.2f}"
            market_value_text = f"{(row.market_value or 0.0):.2f}"
            pnl_text = f"{(row.unrealized_pnl or 0.0):.2f}"
            typer.echo(
                f"{row.symbol} weight={row.position_weight:.3f} "
                f"capital={capital_text} market_value={market_value_text} "
                f"unrealized_pnl={pnl_text} status={row.status} last_price={price_text}"
            )


@app.command("show-account")
def show_account() -> None:
    runtime, file_config = load_settings()
    initialize_database(runtime.database_url)
    session_factory = build_session_factory(runtime.database_url)
    latest_prices = _load_latest_prices(Path(file_config.app.data_dir))
    with session_factory() as session:
        account = _load_or_create_account(session, file_config.portfolio.initial_cash)
        _reset_daily_trade_counter(account)
        _refresh_account_snapshot(session, account, latest_prices)
        session.commit()
        typer.echo(f"initial_cash={account.initial_cash:.2f}")
        typer.echo(f"available_cash={account.available_cash:.2f}")
        typer.echo(f"invested_capital={account.invested_capital:.2f}")
        typer.echo(f"realized_pnl={account.realized_pnl:.2f}")
        typer.echo(f"unrealized_pnl={(account.unrealized_pnl or 0.0):.2f}")
        typer.echo(f"total_equity={account.total_equity:.2f}")
        typer.echo(f"daily_trade_count={account.daily_trade_count}")
        typer.echo(f"last_trade_date={account.last_trade_date or 'NA'}")


@app.command("paper-trade")
def paper_trade() -> None:
    """
    Run paper trading based on current signals.

    Reads signals from DB, computes share counts from weights,
    executes through SimBroker, records orders and positions.
    """
    runtime, file_config = load_settings()
    initialize_database(runtime.database_url)
    session_factory = build_session_factory(runtime.database_url)
    latest_prices = _load_latest_prices(Path(file_config.app.data_dir))

    # Inject latest prices into SimBroker so it can compute fills
    broker = SimBroker(
        TradeConfig(
            initial_cash=file_config.portfolio.initial_cash,
            transaction_cost_rate=file_config.portfolio.transaction_cost_rate,
            slippage_rate=file_config.portfolio.slippage_rate,
            test_mode=runtime.paper_test_mode,
        )
    )
    broker.batch_update_prices(latest_prices)

    # Sync existing positions from DB into broker state so SELL orders work on re-runs
    with session_factory() as db_session:
        for pos in db_session.execute(select(PortfolioPosition).where(PortfolioPosition.status == "OPEN")).scalars():
            price = latest_prices.get(pos.symbol, 0.0)
            if price > 0 and pos.allocated_capital and pos.allocated_capital > 0:
                shares = round(pos.allocated_capital / price)
                if shares >= 100:
                    broker._positions[pos.symbol] = {
                        "volume": shares,
                        "avg_cost": pos.entry_price or price,
                        "realized_pnl": pos.unrealized_pnl or 0.0,
                        "today_volume": 0,
                    }

    with session_factory() as session:
        account = _load_or_create_account(session, file_config.portfolio.initial_cash)
        _reset_daily_trade_counter(account)
        _refresh_account_snapshot(session, account, latest_prices)
        remaining_trade_slots = max(0, file_config.risk.max_daily_trades - account.daily_trade_count)
        max_orders = min(remaining_trade_slots, file_config.risk.max_symbols_per_trade)
        portfolio_base = max(account.total_equity, 1.0)
        plans = _build_rebalance_plans(session)
        submitted = 0

        for plan in plans:
            if submitted >= max_orders:
                break

            # Get current position from DB
            position = session.get(PortfolioPosition, plan.symbol)
            price = latest_prices.get(plan.symbol)
            if price is None or price <= 0:
                typer.echo(f"skip {plan.symbol}: no valid price")
                continue

            # ------------------------------------------------------------------
            # BUY branch
            # ------------------------------------------------------------------
            if plan.side == "BUY":
                required_return = (
                    file_config.portfolio.transaction_cost_rate
                    + file_config.portfolio.slippage_rate
                    + file_config.portfolio.min_expected_excess_return
                )
                if plan.predicted_return <= required_return:
                    typer.echo(
                        f"skip {plan.symbol} expected_return={plan.predicted_return:.4f} "
                        f"< required={required_return:.4f}"
                    )
                    continue

                target_notional = plan.trade_weight * portfolio_base
                # A-shares trade in 100-share lots; round UP so small notionals don't truncate to 0
                import math
                target_shares = math.ceil(target_notional / price / 100) * 100
                if target_shares < 100:
                    typer.echo(f"skip {plan.symbol}: notional={target_notional:.2f} below 1-lot cost={price * 100:.2f}")
                    continue

                # Cap by available cash
                max_affordable = account.available_cash / (
                    1 + file_config.portfolio.transaction_cost_rate + file_config.portfolio.slippage_rate
                )
                target_shares = min(target_shares, math.floor(max_affordable / price / 100) * 100)
                if target_shares < 100:
                    typer.echo(f"skip {plan.symbol}: insufficient cash")
                    continue

                order_exec = broker.place_order(
                    OrderRequest(
                        symbol=plan.symbol,
                        side=OrderSide.BUY,
                        volume=target_shares,
                        price=0.0,
                        order_type=OrderType.MARKET,
                        reference_price=price,
                        comment=plan.reason,
                    )
                )

                if order_exec.status == OrderStatus.FILLED and order_exec.filled_volume > 0:
                    exec_price = order_exec.avg_fill_price or price
                    exec_notional = order_exec.filled_volume * exec_price
                    exec_cost = (
                        exec_notional * file_config.portfolio.transaction_cost_rate
                        + exec_notional * file_config.portfolio.slippage_rate
                    )

                    if position is None:
                        session.add(
                            PortfolioPosition(
                                symbol=order_exec.symbol,
                                position_weight=order_exec.filled_volume * exec_price / portfolio_base,
                                allocated_capital=exec_notional,
                                entry_price=exec_price,
                                last_price=exec_price,
                                market_value=exec_notional,
                                unrealized_pnl=0.0,
                                status="OPEN",
                                source="paper",
                            )
                        )
                    else:
                        old_capital = position.allocated_capital or 0.0
                        old_shares = old_capital / position.entry_price if position.entry_price and position.entry_price > 0 else 0
                        new_shares = exec_notional / exec_price
                        combined_notional = old_capital + exec_notional
                        position.entry_price = combined_notional / (old_shares + new_shares) if (old_shares + new_shares) > 0 else exec_price
                        position.position_weight = combined_notional / portfolio_base
                        position.allocated_capital = combined_notional
                        position.last_price = exec_price
                        position.market_value = exec_notional
                        position.status = "OPEN"

                    account.available_cash -= exec_notional + exec_cost
                    account.invested_capital += exec_notional
                    account.realized_pnl -= exec_cost
                    account.daily_trade_count += 1
                    account.last_trade_date = _today_str()

                    session.add(
                        TradeOrder(
                            order_id=order_exec.order_id,
                            symbol=order_exec.symbol,
                            side=order_exec.side.value,
                            target_weight=plan.desired_weight,
                            filled_weight=order_exec.filled_volume * exec_price / portfolio_base,
                            requested_notional=target_notional,
                            filled_notional=exec_notional,
                            transaction_cost=exec_notional * file_config.portfolio.transaction_cost_rate,
                            slippage_cost=exec_notional * file_config.portfolio.slippage_rate,
                            total_cost=exec_cost,
                            filled_price=exec_price,
                            status=order_exec.status.value,
                            broker="paper",
                            note=f"{plan.reason}",
                        )
                    )
                    submitted += 1
                    typer.echo(
                        f"FILLED BUY  {order_exec.symbol} {order_exec.filled_volume} shares @ {exec_price:.3f} "
                        f"(notional={exec_notional:.2f}, cost={exec_cost:.2f})"
                    )

            elif plan.side == "SELL":
                if position is None or position.status != "OPEN" or position.position_weight <= 0:
                    continue

                # 获取 broker 中的实际持仓股数（避免 DB market_value 含成本导致卖超）
                broker_pos = broker._positions.get(plan.symbol, {})
                current_shares = broker_pos.get("volume", 0)
                if current_shares <= 0:
                    typer.echo(f"skip {plan.symbol}: no broker position")
                    continue

                # 卖出股数：A-shares 100 股整数倍，上限为实际持仓
                sell_shares = math.ceil(plan.trade_weight * portfolio_base / price / 100) * 100
                sell_shares = min(sell_shares, current_shares)
                if sell_shares < 100:
                    typer.echo(f"skip {plan.symbol}: trade_weight={plan.trade_weight:.4f} too small for 1 lot")
                    continue

                order_exec = broker.place_order(
                    OrderRequest(
                        symbol=plan.symbol,
                        side=OrderSide.SELL,
                        volume=sell_shares,
                        price=0.0,
                        order_type=OrderType.MARKET,
                        reference_price=price,
                        comment=plan.reason,
                    )
                )

                if order_exec.status == OrderStatus.FILLED and order_exec.filled_volume > 0:
                    exec_price = order_exec.avg_fill_price or price
                    exec_notional = order_exec.filled_volume * exec_price
                    stamp_tax = exec_notional * 0.001
                    exec_cost = (
                        exec_notional * file_config.portfolio.transaction_cost_rate
                        + exec_notional * file_config.portfolio.slippage_rate
                        + stamp_tax
                    )
                    released_notional = order_exec.filled_volume * (position.entry_price or price)

                    new_weight = max(position.position_weight - order_exec.filled_volume * exec_price / portfolio_base, 0.0)
                    position.position_weight = new_weight
                    position.allocated_capital = max(
                        (position.allocated_capital or 0.0) - released_notional, 0.0
                    )
                    position.last_price = exec_price
                    position.market_value = order_exec.filled_volume * exec_price
                    position.status = "OPEN" if new_weight > 1e-6 else "CLOSED"
                    if position.status == "CLOSED":
                        position.position_weight = 0.0
                        position.allocated_capital = 0.0
                        position.market_value = 0.0
                        position.unrealized_pnl = 0.0

                    account.available_cash += exec_notional - exec_cost
                    account.invested_capital = max(account.invested_capital - released_notional, 0.0)
                    account.realized_pnl += exec_notional - released_notional - exec_cost
                    account.daily_trade_count += 1
                    account.last_trade_date = _today_str()

                    session.add(
                        TradeOrder(
                            order_id=order_exec.order_id,
                            symbol=order_exec.symbol,
                            side=order_exec.side.value,
                            target_weight=plan.desired_weight,
                            filled_weight=order_exec.filled_volume * exec_price / portfolio_base,
                            requested_notional=plan.trade_weight * portfolio_base,
                            filled_notional=exec_notional,
                            transaction_cost=exec_notional * file_config.portfolio.transaction_cost_rate,
                            slippage_cost=exec_notional * file_config.portfolio.slippage_rate,
                            total_cost=exec_cost,
                            filled_price=exec_price,
                            status=order_exec.status.value,
                            broker="paper",
                            note=f"{plan.reason}",
                        )
                    )
                    submitted += 1
                    typer.echo(
                        f"FILLED SELL {order_exec.symbol} {order_exec.filled_volume} shares @ {exec_price:.3f} "
                        f"(notional={exec_notional:.2f}, cost={exec_cost:.2f})"
                    )

        session.flush()
        _refresh_account_snapshot(session, account, latest_prices)
        session.commit()

        if submitted == 0:
            typer.echo("no rebalance actions required")
        else:
            typer.echo(
                f"paper trade completed: {submitted} orders, "
                f"available_cash={account.available_cash:.2f}, total_equity={account.total_equity:.2f}"
            )


@app.command("run-backtest")
def run_backtest_command() -> None:
    _, file_config = load_settings()
    data_root = Path(file_config.app.data_dir)
    features_path = data_root / "features" / "daily_features.parquet"
    model_path = data_root / "models" / "lightgbm_daily.txt"
    metadata_path = data_root / "models" / "lightgbm_daily.json"
    report_path = data_root / "reports" / "backtest_curve.csv"

    if features_path.exists() and model_path.exists() and metadata_path.exists():
        feature_df = pd.read_parquet(features_path)
        result = run_model_backtest(
            feature_df,
            model_path=str(model_path),
            metadata_path=str(metadata_path),
            top_n=file_config.strategy.top_n,
            min_confidence_score=file_config.risk.min_confidence_score,
            initial_cash=file_config.backtest.initial_cash,
            transaction_cost_rate=file_config.backtest.transaction_cost_rate,
            slippage_rate=file_config.backtest.slippage_rate,
        )
        write_backtest_curve(result.curve, str(report_path))
        typer.echo(result.metrics)
        typer.echo(f"backtest curve written to {report_path}")
        return

    data_path = data_root / "raw" / "market_snapshot.parquet"
    if not data_path.exists():
        raise typer.BadParameter("run sync-data before backtest")

    df = pd.read_parquet(data_path)
    features = build_daily_features(df, pd.DataFrame())
    result = run_backtest(features, initial_cash=file_config.backtest.initial_cash)
    typer.echo(result)


@app.command("health-check")
def health_check() -> None:
    runtime, file_config = load_settings()
    ensure_runtime_dirs(file_config)
    initialize_database(runtime.database_url)

    engine = build_engine(runtime.database_url)
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))

    typer.echo("health check passed")
    typer.echo(f"database_url={runtime.database_url}")
    typer.echo(f"data_dir={file_config.app.data_dir}")
    typer.echo(f"logs_dir={file_config.app.logs_dir}")
    typer.echo(f"provider={file_config.data_source.primary_provider}")
