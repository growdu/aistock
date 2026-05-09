from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfig(BaseModel):
    name: str = "aistock"
    market_timezone: str = "Asia/Shanghai"
    data_dir: str = "data"
    logs_dir: str = "logs"


class StrategyConfig(BaseModel):
    watchlist_size: int = 100
    rebalance_interval_minutes: int = 15
    top_n: int = 3
    symbols: list[str] = Field(default_factory=lambda: ["300750.SZ", "688041.SH", "688111.SH"])


class RiskConfig(BaseModel):
    max_daily_trades: int = 5
    max_symbols_per_trade: int = 3
    max_single_position_pct: float = 0.1
    max_daily_loss_pct: float = 0.03
    min_confidence_score: float = 0.6


class ModelConfig(BaseModel):
    primary_model: str = "lightgbm"
    llm_enabled: bool = False
    llm_model_name: str = ""


class DataSourceConfig(BaseModel):
    primary_provider: str = "tushare"
    enable_news: bool = False


class FileConfig(BaseModel):
    app: AppConfig = Field(default_factory=AppConfig)
    strategy: StrategyConfig = Field(default_factory=StrategyConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    model: ModelConfig = Field(default_factory=ModelConfig)
    data_source: DataSourceConfig = Field(default_factory=DataSourceConfig)


class RuntimeSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "dev"
    log_level: str = "INFO"
    database_url: str = "sqlite:///./aistock.db"
    tushare_token: str = ""
    broker_api_key: str = ""
    broker_api_secret: str = ""
    broker_account_id: str = ""
    alert_webhook: str = ""
    config_path: str = ""


def load_file_config(path: str | Path) -> FileConfig:
    config_path = Path(path)
    if not config_path.exists():
        return FileConfig()

    with config_path.open("r", encoding="utf-8") as handle:
        data: dict[str, Any] = yaml.safe_load(handle) or {}
    return FileConfig.model_validate(data)


def load_settings() -> tuple[RuntimeSettings, FileConfig]:
    runtime = RuntimeSettings()
    config_path = runtime.config_path.strip()
    if not config_path:
        default_path = Path("config/settings.yaml")
        config_path = str(default_path if default_path.exists() else Path("config/settings.example.yaml"))

    file_config = load_file_config(config_path)
    return runtime, file_config
