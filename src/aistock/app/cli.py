from __future__ import annotations

import logging
from pathlib import Path
from datetime import date, timedelta

import pandas as pd
import typer
from sqlalchemy import select, text

from aistock.app.logging import setup_logging
from aistock.backtest.engine import run_backtest
from aistock.broker.base import OrderRequest
from aistock.broker.paper import PaperBroker
from aistock.config.settings import load_settings
from aistock.data.pipeline import ensure_runtime_dirs, sync_market_data
from aistock.db.base import build_engine, build_session_factory, initialize_database
from aistock.db.models import SignalRecord
from aistock.feature.factors import build_basic_features
from aistock.model.predict import score_candidates
from aistock.report.dashboard import write_signal_report
from aistock.risk.engine import evaluate_signal
from aistock.strategy.engine import generate_signals

app = typer.Typer(help="Personal AI-assisted quant trading system.")
logger = logging.getLogger(__name__)


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
) -> None:
    runtime, file_config = load_settings()
    today = date.today()
    resolved_end_date = end_date or today.strftime("%Y%m%d")
    resolved_start_date = start_date or (today - timedelta(days=120)).strftime("%Y%m%d")
    resolved_symbols = [item.strip() for item in symbols.split(",") if item.strip()] or file_config.strategy.symbols

    sync_market_data(
        runtime,
        file_config,
        symbols=resolved_symbols,
        start_date=resolved_start_date,
        end_date=resolved_end_date,
    )
    typer.echo(
        f"market data synced for {len(resolved_symbols)} symbols "
        f"from {resolved_start_date} to {resolved_end_date}"
    )


@app.command("generate-signals")
def generate_signals_command() -> None:
    runtime, file_config = load_settings()
    ensure_runtime_dirs(file_config)
    initialize_database(runtime.database_url)

    predictions = score_candidates(["300750", "688041", "688111", "300308"])
    signals = generate_signals(predictions, file_config)

    session_factory = build_session_factory(runtime.database_url)
    with session_factory() as session:
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
                    confidence=min(1.0, risk.adjusted_weight * 10),
                    reason=risk.message,
                )
            )
        session.commit()

    output = Path(file_config.app.data_dir) / "reports" / "signals.csv"
    write_signal_report(
        [
            {"symbol": signal.symbol, "action": signal.action.value, "target_weight": signal.target_weight}
            for signal in signals
        ],
        str(output),
    )
    typer.echo(f"signals written to {output}")


@app.command("show-signals")
def show_signals() -> None:
    runtime, _ = load_settings()
    initialize_database(runtime.database_url)
    session_factory = build_session_factory(runtime.database_url)
    with session_factory() as session:
        rows = session.execute(select(SignalRecord)).scalars().all()
        for row in rows:
            typer.echo(f"{row.symbol} {row.action} weight={row.target_weight:.3f} reason={row.reason}")


@app.command("paper-trade")
def paper_trade() -> None:
    runtime, _ = load_settings()
    initialize_database(runtime.database_url)
    session_factory = build_session_factory(runtime.database_url)
    broker = PaperBroker()

    with session_factory() as session:
        rows = session.execute(select(SignalRecord)).scalars().all()
        for row in rows:
            if row.action != "BUY":
                continue
            order_id = broker.place_order(OrderRequest(symbol=row.symbol, side=row.action, weight=row.target_weight))
            typer.echo(f"submitted {order_id}")


@app.command("run-backtest")
def run_backtest_command() -> None:
    _, file_config = load_settings()
    data_path = Path(file_config.app.data_dir) / "raw" / "market_snapshot.parquet"
    if not data_path.exists():
        raise typer.BadParameter("run sync-data before backtest")

    df = pd.read_parquet(data_path)
    features = build_basic_features(df)
    result = run_backtest(features)
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
