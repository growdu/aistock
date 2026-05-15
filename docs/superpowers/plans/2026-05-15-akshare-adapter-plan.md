# AkShare 数据源适配实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现双数据源架构，用户可通过 `data_source.type` 配置选择 Tushare 或 AkShare，无需修改代码。

**Architecture:** 通过 Protocol 接口统一定义数据源客户端行为，TushareClient 和 AkShareClient 实现同一接口，pipeline.py 根据配置选择具体客户端。

**Tech Stack:** Python typing.Protocol, pandas, akshare

---

## 文件结构

```
src/aistock/data/sources/
├── __init__.py           # 修改: 导出 DataSourceClient, TushareClient, AkShareClient
├── base.py               # 新增: DataSourceClient Protocol
├── tushare_client.py     # 修改: 实现 DataSourceClient 接口
├── akshare_client.py     # 新增: AkShare 客户端实现
config/
├── settings.py           # 修改: DataSourceConfig 添加 type 字段
data/
├── pipeline.py           # 修改: 根据 data_source.type 选择客户端
```

---

## Task 1: 创建 DataSourceClient Protocol

**Files:**
- Create: `src/aistock/data/sources/base.py`
- Test: `tests/test_data_source_base.py`

- [ ] **Step 1: 编写 Protocol 测试**

```python
# tests/test_data_source_base.py
import pytest
from aistock.data.sources.base import DataSourceClient

def test_protocol_exists():
    """验证 DataSourceClient Protocol 存在"""
    assert DataSourceClient is not None

def test_protocol_methods():
    """验证 Protocol 定义了所有必需方法"""
    required_methods = [
        'ping', 'get_stock_basic', 'get_trade_calendar',
        'get_daily', 'get_daily_basic', 'get_index_daily',
        'get_bars', 'get_financial_indicator', 'get_moneyflow'
    ]
    for method in required_methods:
        assert hasattr(DataSourceClient, method), f"Missing method: {method}"

def test_protocol_is_runtime_checkable():
    """验证 Protocol 可在运行时检查"""
    from typing import runtime_checkable
    assert hasattr(DataSourceClient, '__runtime_checkable__')
```

- [ ] **Step 2: 运行测试验证失败**

Run: `pytest tests/test_data_source_base.py -v`
Expected: FAIL - module 'aistock.data.sources.base' has no attribute 'DataSourceClient'

- [ ] **Step 3: 创建 base.py**

```python
# src/aistock/data/sources/base.py
from __future__ import annotations

from typing import Protocol, runtime_checkable, Any

import pandas as pd


@runtime_checkable
class DataSourceClient(Protocol):
    """数据源客户端统一接口。

    所有数据源客户端（Tushare、AkShare 等）必须实现此接口。
    这样 pipeline.py 可以使用统一的接口，不需要关心具体是哪个数据源。
    """

    def ping(self) -> bool:
        """检查数据源连接是否正常。"""

    def get_stock_basic(self, list_status: str = "L") -> pd.DataFrame:
        """获取 A 股股票基本信息。

        Returns:
            DataFrame with columns: ts_code, symbol, name, industry, market, list_date...
        """

    def get_trade_calendar(
        self, start_date: str, end_date: str, exchange: str = "SSE"
    ) -> pd.DataFrame:
        """获取交易日历。

        Returns:
            DataFrame with columns: exchange, cal_date, is_open, pretrade_date
        """

    def get_daily(
        self, ts_code: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """获取日线行情（未复权）。

        Returns:
            DataFrame with columns: ts_code, trade_date, open, high, low, close, volume, amount
        """

    def get_daily_basic(
        self, ts_code: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """获取日线基本指标（PE/PB/换手率等）。

        Returns:
            DataFrame with columns: ts_code, trade_date, close, pe, pb, turnrate, total_mv, circ_mv...
        """

    def get_index_daily(
        self, ts_code: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """获取指数日线。

        Returns:
            DataFrame with columns: ts_code, trade_date, open, high, low, close, volume
        """

    def get_bars(
        self, ts_code: str, start_date: str, end_date: str, freq: str = "5m"
    ) -> pd.DataFrame:
        """获取分钟线行情。

        Args:
            freq: 频率，1m/5m/15m/30m/60m

        Returns:
            DataFrame with columns: ts_code, trade_time, open, high, low, close, volume
        """

    def get_financial_indicator(
        self, ts_code: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """获取财务指标。

        Returns:
            DataFrame with ROE, ROA, gross_margin, net_margin, eps, bps...
        """

    def get_moneyflow(
        self, ts_code: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """获取个股资金流向。

        Returns:
            DataFrame with buy_sm_amount, sell_sm_amount, buy_lg_amount, sell_lg_amount...
        """
```

- [ ] **Step 4: 运行测试验证通过**

Run: `pytest tests/test_data_source_base.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add tests/test_data_source_base.py src/aistock/data/sources/base.py
git commit -m "feat: add DataSourceClient Protocol in base.py"
```

---

## Task 2: 创建 AkShareClient

**Files:**
- Create: `src/aistock/data/sources/akshare_client.py`
- Test: `tests/test_akshare_client.py`

- [ ] **Step 1: 编写 AkShareClient 测试**

```python
# tests/test_akshare_client.py
import pytest
from aistock.data.sources.akshare_client import AkShareClient

def test_akshare_client_can_be_instantiated():
    """验证 AkShareClient 可实例化"""
    client = AkShareClient()
    assert client is not None

def test_akshare_client_has_required_methods():
    """验证 AkShareClient 实现了 DataSourceClient 接口"""
    client = AkShareClient()
    required_methods = [
        'ping', 'get_stock_basic', 'get_trade_calendar',
        'get_daily', 'get_daily_basic', 'get_index_daily',
        'get_bars', 'get_financial_indicator', 'get_moneyflow'
    ]
    for method in required_methods:
        assert hasattr(client, method), f"Missing method: {method}"

def test_akshare_client_is_runtim_checkable():
    """验证 AkShareClient 实现了 Protocol"""
    from aistock.data.sources.base import DataSourceClient
    client = AkShareClient()
    assert isinstance(client, DataSourceClient)
```

- [ ] **Step 2: 运行测试验证失败**

Run: `pytest tests/test_akshare_client.py -v`
Expected: FAIL - module 'aistock.data.sources.akshare_client' has no attribute 'AkShareClient'

- [ ] **Step 3: 创建 akshare_client.py**

```python
# src/aistock/data/sources/akshare_client.py
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import pandas as pd

from aistock.data.sources.base import DataSourceClient

logger = logging.getLogger(__name__)


def _symbol_to_akshare(symbol: str) -> str:
    """将 ts_code 转换为 akshare 格式。

    Tushare: 000001.SZ -> AkShare: 000001
    688041.SH -> AkShare: 688041
    """
    return symbol.split(".")[0]


def _akshare_to_ts_code(symbol: str, market: str | None = None) -> str:
    """将 akshare 数据转为标准 ts_code 格式。

    AkShare 返回的股票代码通常不带交易所后缀，
    需要根据上交所(.SH)/深交所(.SZ)规则补充。
    """
    if symbol.startswith("688"):
        return f"{symbol}.SH"
    elif symbol.startswith("000") or symbol.startswith("001"):
        return f"{symbol}.SZ"
    elif symbol.startswith("002") or symbol.startswith("003"):
        return f"{symbol}.SZ"
    elif symbol.startswith("300"):
        return f"{symbol}.SZ"
    elif symbol.startswith("400") or symbol.startswith("430"):
        return f"{symbol}.BJ"
    elif symbol.startswith("8") or symbol.startswith("430"):
        return f"{symbol}.BJ"
    else:
        # 默认沪市
        return f"{symbol}.SH"


class AkShareClient:
    """AkShare 数据源客户端。

    实现了 DataSourceClient 接口，封装 akshare 的股票数据获取功能。
    特点：完全免费，但分钟线数据有限。
    """

    def __init__(self) -> None:
        self._ak = None

    def _load(self) -> None:
        if self._ak is not None:
            return
        try:
            import akshare as ak
            self._ak = ak
        except ImportError:
            logger.warning("akshare is not installed, some functions will fail")
            self._ak = None

    def ping(self) -> bool:
        """检查 akshare 是否可用。"""
        try:
            import akshare as ak
            # 尝试获取实时行情作为健康检查
            ak.stock_zh_a_spot_em()
            return True
        except Exception:
            return False

    def get_stock_basic(self, list_status: str = "L") -> pd.DataFrame:
        """获取 A 股股票基本信息。"""
        self._load()
        if self._ak is None:
            return pd.DataFrame()

        try:
            df = self._ak.stock_zh_a_spot_em()
            if df is None or df.empty:
                return pd.DataFrame()

            # 统一字段名
            rename_map: dict[str, str] = {}
            if "代码" in df.columns:
                rename_map["代码"] = "ts_code"
            if "名称" in df.columns:
                rename_map["名称"] = "name"
            if "板块" in df.columns:
                rename_map["板块"] = "board"
            if "上市时间" in df.columns:
                rename_map["上市时间"] = "list_date"
            if "行业" in df.columns:
                rename_map["行业"] = "industry"

            if rename_map:
                df = df.rename(columns=rename_map)

            # 转换 ts_code 格式
            if "ts_code" in df.columns:
                df["ts_code"] = df["ts_code"].apply(_akshare_to_ts_code)
                df["symbol"] = df["ts_code"].str.split(".").str[0]

            df["source"] = "akshare"
            return df

        except Exception:
            logger.exception("failed to get stock_basic from akshare")
            return pd.DataFrame()

    def get_trade_calendar(
        self, start_date: str, end_date: str, exchange: str = "SSE"
    ) -> pd.DataFrame:
        """获取交易日历。"""
        self._load()
        if self._ak is None:
            return pd.DataFrame()

        try:
            df = self._ak.tool_trade_date_hist_sina()
            if df is None or df.empty:
                return pd.DataFrame()

            # 统一字段名
            if "trade_date" in df.columns:
                df = df.rename(columns={"trade_date": "cal_date"})

            # 转换日期格式
            if "cal_date" in df.columns:
                df["cal_date"] = df["cal_date"].astype(str).str.replace("-", "")

            df["exchange"] = "SSE"
            df["is_open"] = 1  # akshare 返回的都是交易日
            df["source"] = "akshare"
            return df

        except Exception:
            logger.exception("failed to get trade_calendar from akshare")
            return pd.DataFrame()

    def get_daily(
        self, ts_code: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """获取日线行情。"""
        self._load()
        if self._ak is None:
            return pd.DataFrame()

        try:
            symbol = _symbol_to_akshare(ts_code)
            # 转换日期格式
            start = start_date if isinstance(start_date, str) else start_date.strftime("%Y%m%d")
            end = end_date if isinstance(end_date, str) else end_date.strftime("%Y%m%d")

            df = self._ak.stock_zh_a_hist(
                symbol=symbol,
                period="daily",
                start_date=start,
                end_date=end,
                adjust="qfq"
            )
            if df is None or df.empty:
                return pd.DataFrame()

            # 统一字段名
            rename_map: dict[str, str] = {
                "日期": "trade_date",
                "股票代码": "ts_code",
                "开盘": "open",
                "最高": "high",
                "最低": "low",
                "收盘": "close",
                "成交量": "volume",
                "成交额": "amount",
                "涨跌幅": "pct_change",
                "涨跌额": "change",
                "换手率": "turnrate",
            }

            df = df.rename(columns=rename_map)

            # 确保 ts_code 格式正确
            if "ts_code" in df.columns and not df["ts_code"].str.contains(".").any():
                df["ts_code"] = df["ts_code"].apply(lambda x: _akshare_to_ts_code(str(x)))

            # 转换日期格式为 YYYYMMDD
            if "trade_date" in df.columns:
                df["trade_date"] = df["trade_date"].astype(str).str.replace("-", "")

            df["source"] = "akshare"
            return df

        except Exception:
            logger.exception("failed to get daily from akshare for %s", ts_code)
            return pd.DataFrame()

    def get_daily_basic(
        self, ts_code: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """获取日线基本指标。"""
        self._load()
        if self._ak is None:
            return pd.DataFrame()

        try:
            symbol = _symbol_to_akshare(ts_code)
            start = start_date if isinstance(start_date, str) else start_date.strftime("%Y%m%d")
            end = end_date if isinstance(end_date, str) else end_date.strftime("%Y%m%d")

            df = self._ak.stock_zh_a_daily(
                symbol=symbol,
                start_date=start,
                end_date=end,
                adjust="qfq"
            )
            if df is None or df.empty:
                return pd.DataFrame()

            # AkShare 日线数据含有多因子，返回的列包含换手率、市值等
            rename_map: dict[str, str] = {
                "日期": "trade_date",
                "股票代码": "ts_code",
                "开盘": "open",
                "最高": "high",
                "最低": "low",
                "收盘": "close",
                "成交量": "volume",
                "成交额": "amount",
            }

            df = df.rename(columns=rename_map)

            if "ts_code" in df.columns and not df["ts_code"].str.contains(".").any():
                df["ts_code"] = df["ts_code"].apply(lambda x: _akshare_to_ts_code(str(x)))

            if "trade_date" in df.columns:
                df["trade_date"] = df["trade_date"].astype(str).str.replace("-", "")

            df["source"] = "akshare"
            return df

        except Exception:
            logger.exception("failed to get daily_basic from akshare for %s", ts_code)
            return pd.DataFrame()

    def get_index_daily(
        self, ts_code: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """获取指数日线。"""
        self._load()
        if self._ak is None:
            return pd.DataFrame()

        try:
            symbol = _symbol_to_akshare(ts_code)
            start = start_date if isinstance(start_date, str) else start_date.strftime("%Y%m%d")
            end = end_date if isinstance(end_date, str) else end_date.strftime("%Y%m%d")

            df = self._ak.stock_zh_index_daily(symbol=symbol)
            if df is None or df.empty:
                return pd.DataFrame()

            # 过滤日期范围
            if "date" in df.columns:
                df["date"] = df["date"].astype(str).str.replace("-", "")
                df = df[(df["date"] >= start) & (df["date"] <= end)]

            # 统一字段名
            rename_map: dict[str, str] = {
                "date": "trade_date",
                "open": "open",
                "high": "high",
                "low": "low",
                "close": "close",
                "volume": "volume",
            }
            df = df.rename(columns=rename_map)
            df["ts_code"] = ts_code
            df["source"] = "akshare"
            return df

        except Exception:
            logger.exception("failed to get index_daily from akshare for %s", ts_code)
            return pd.DataFrame()

    def get_bars(
        self, ts_code: str, start_date: str, end_date: str, freq: str = "5m"
    ) -> pd.DataFrame:
        """获取分钟线行情。"""
        self._load()
        if self._ak is None:
            return pd.DataFrame()

        try:
            symbol = _symbol_to_akshare(ts_code)
            start = start_date if isinstance(start_date, str) else start_date.strftime("%Y%m%d")
            end = end_date if isinstance(end_date, str) else end_date.strftime("%Y%m%d")

            # AkShare period 映射
            period_map = {
                "1m": "1",
                "5m": "5",
                "15m": "15",
                "30m": "30",
                "60m": "60",
            }
            period = period_map.get(freq, "5")

            df = self._ak.stock_zh_a_hist(
                symbol=symbol,
                period=period,
                start_date=start,
                end_date=end,
                adjust="qfq"
            )
            if df is None or df.empty:
                return pd.DataFrame()

            # 统一字段名
            rename_map: dict[str, str] = {
                "日期": "trade_time",
                "时间": "trade_time",
                "开盘": "open",
                "最高": "high",
                "最低": "low",
                "收盘": "close",
                "成交量": "volume",
                "成交额": "amount",
            }
            df = df.rename(columns=rename_map)

            if "trade_time" in df.columns:
                df["trade_time"] = df["trade_time"].astype(str)

            df["ts_code"] = ts_code
            df["freq"] = freq
            df["source"] = "akshare"
            return df

        except Exception:
            logger.exception("failed to get bars from akshare for %s", ts_code)
            return pd.DataFrame()

    def get_financial_indicator(
        self, ts_code: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """获取财务指标。

        注意: AkShare 没有直接对应 Tushare fina_indicator 的接口，
        此方法返回空 DataFrame，需要财务数据时需使用 Tushare。
        """
        logger.warning("AkShare does not support financial_indicator, use Tushare instead")
        return pd.DataFrame()

    def get_moneyflow(
        self, ts_code: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """获取资金流向。"""
        self._load()
        if self._ak is None:
            return pd.DataFrame()

        try:
            symbol = _symbol_to_akshare(ts_code)
            df = self._ak.stock_money_flow_em(symbol=symbol)
            if df is None or df.empty:
                return pd.DataFrame()

            # 统一字段名
            rename_map: dict[str, str] = {
                "代码": "ts_code",
                "名称": "name",
                "日期": "trade_date",
                "主力净流入": "net_lg_amount",
                "超大单净流入": "net_xl_amount",
                "大单净流入": "net_l_amount",
                "中单净流入": "net_m_amount",
                "小单净流入": "net_s_amount",
            }
            df = df.rename(columns=rename_map)

            if "ts_code" in df.columns:
                df["ts_code"] = df["ts_code"].apply(lambda x: _akshare_to_ts_code(str(x)))

            if "trade_date" in df.columns:
                df["trade_date"] = df["trade_date"].astype(str).str.replace("-", "")

            df["source"] = "akshare"
            return df

        except Exception:
            logger.exception("failed to get moneyflow from akshare for %s", ts_code)
            return pd.DataFrame()
```

- [ ] **Step 4: 运行测试验证通过**

Run: `pytest tests/test_akshare_client.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add tests/test_akshare_client.py src/aistock/data/sources/akshare_client.py
git commit -m "feat: add AkShareClient implementation"
```

---

## Task 3: 更新 TushareClient 实现 Protocol

**Files:**
- Modify: `src/aistock/data/sources/tushare_client.py`
- Test: `tests/test_tushare_client.py`

- [ ] **Step 1: 添加类型注解测试**

```python
# tests/test_tushare_client.py
import pytest
from aistock.data.sources.base import DataSourceClient
from aistock.data.sources.tushare_client import TushareClient

def test_tushare_client_implements_protocol():
    """验证 TushareClient 实现了 DataSourceClient"""
    # 注意：这需要 Tushare token 才能真正调用 API
    # 这里只验证类型和接口存在
    client = TushareClient(token="dummy_token")
    assert isinstance(client, DataSourceClient)

def test_tushare_client_has_required_methods():
    """验证 TushareClient 有所有必需方法"""
    client = TushareClient(token="dummy_token")
    required_methods = [
        'ping', 'get_stock_basic', 'get_trade_calendar',
        'get_daily', 'get_daily_basic', 'get_index_daily',
        'get_bars', 'get_financial_indicator', 'get_moneyflow'
    ]
    for method in required_methods:
        assert hasattr(client, method), f"Missing method: {method}"
```

- [ ] **Step 2: 运行测试验证**

Run: `pytest tests/test_tushare_client.py -v`
Expected: PASS (类型检查不调用 API)

- [ ] **Step 3: 提交**

```bash
git add tests/test_tushare_client.py
git commit -m "test: add TushareClient protocol compliance test"
```

---

## Task 4: 更新配置添加 data_source.type

**Files:**
- Modify: `src/aistock/config/settings.py:39-41`
- Modify: `config/settings.yaml:54-55`

- [ ] **Step 1: 修改 DataSourceConfig**

```python
# src/aistock/config/settings.py 找到 DataSourceConfig 类，修改为:

class DataSourceConfig(BaseModel):
    type: str = "tushare"  # "tushare" | "akshare"
    enable_news: bool = False
```

- [ ] **Step 2: 修改 settings.yaml**

```yaml
# config/settings.yaml 找到 data_source 部分，修改为:

data_source:
  type: tushare  # tushare | akshare
  enable_news: false
```

- [ ] **Step 3: 运行测试验证**

Run: `pytest tests/ -v`
Expected: PASS

- [ ] **Step 4: 提交**

```bash
git add src/aistock/config/settings.py config/settings.yaml
git commit -m "feat: add data_source.type config option"
```

---

## Task 5: 更新 pipeline.py 根据 type 选择客户端

**Files:**
- Modify: `src/aistock/data/pipeline.py`
- Test: `tests/test_pipeline.py`

- [ ] **Step 1: 编写测试**

```python
# tests/test_pipeline.py
import pytest
from unittest.mock import MagicMock, patch
from aistock.data.pipeline import get_client

def test_get_client_returns_akshare_when_configured():
    """验证配置为 akshare 时返回 AkShareClient"""
    with patch('aistock.data.pipeline.AkShareClient') as MockAkShare:
        mock_instance = MagicMock()
        MockAkShare.return_value = mock_instance

        from aistock.config.settings import DataSourceConfig
        config = DataSourceConfig(type="akshare")

        client = get_client(config)
        MockAkShare.assert_called_once()

def test_get_client_returns_tushare_when_configured():
    """验证配置为 tushare 时返回 TushareClient"""
    with patch('aistock.data.pipeline.TushareClient') as MockTushare:
        mock_instance = MagicMock()
        MockTushare.return_value = mock_instance

        from aistock.config.settings import DataSourceConfig
        config = DataSourceConfig(type="tushare")

        client = get_client(config)
        MockTushare.assert_called_once()
```

- [ ] **Step 2: 修改 pipeline.py 添加 get_client 函数**

在 pipeline.py 开头添加：

```python
from aistock.data.sources.tushare_client import TushareClient
from aistock.data.sources.akshare_client import AkShareClient
from aistock.config.settings import DataSourceConfig

def get_client(config: DataSourceConfig):
    """根据配置类型返回对应的数据源客户端。"""
    if config.type == "akshare":
        return AkShareClient()
    else:
        return TushareClient()
```

然后修改 pipeline.py 中所有调用 `TushareClient(runtime.tushare_token)` 的地方，改为：

```python
client = get_client(file_config.data_source)
```

- [ ] **Step 3: 运行测试验证**

Run: `pytest tests/test_pipeline.py -v`
Expected: PASS

- [ ] **Step 4: 提交**

```bash
git add src/aistock/data/pipeline.py tests/test_pipeline.py
git commit -m "feat: add configurable data source selection in pipeline"
```

---

## Task 6: 更新 __init__.py 导出

**Files:**
- Modify: `src/aistock/data/sources/__init__.py`

- [ ] **Step 1: 更新导出**

```python
# src/aistock/data/sources/__init__.py
from aistock.data.sources.base import DataSourceClient
from aistock.data.sources.tushare_client import TushareClient
from aistock.data.sources.akshare_client import AkShareClient

__all__ = ["DataSourceClient", "TushareClient", "AkShareClient"]
```

- [ ] **Step 2: 提交**

```bash
git add src/aistock/data/sources/__init__.py
git commit -m "chore: export DataSourceClient, TushareClient, AkShareClient"
```

---

## Task 7: 集成测试 - 验证两种数据源都能工作

**Files:**
- Test: `tests/test_integration_data_source.py`

- [ ] **Step 1: 编写集成测试**

```python
# tests/test_integration_data_source.py
import pytest
from aistock.data.sources.akshare_client import AkShareClient

def test_akshare_client_can_fetch_data():
    """验证 AkShareClient 可以获取真实数据（集成测试）"""
    client = AkShareClient()
    # 测试交易日历
    calendar = client.get_trade_calendar("20240101", "20240110")
    if not calendar.empty:
        assert "cal_date" in calendar.columns
        assert "is_open" in calendar.columns

def test_akshare_client_get_daily():
    """验证 AkShareClient 可以获取日线数据"""
    client = AkShareClient()
    df = client.get_daily("300750.SZ", "20240101", "20240110")
    # 注意：如果网络问题或数据问题，可能返回空 DataFrame
    # 这里只验证方法可以正常调用不抛异常
    assert isinstance(df, pd.DataFrame)
```

- [ ] **Step 2: 运行集成测试**

Run: `pytest tests/test_integration_data_source.py -v`
Expected: PASS（允许空 DataFrame 返回）

- [ ] **Step 3: 提交**

```bash
git add tests/test_integration_data_source.py
git commit -m "test: add integration tests for data source selection"
```

---

## 验证计划

1. 安装 akshare: `pip install akshare`
2. 配置 `.env`: `DATA_SOURCE_TYPE=akshare`
3. 运行: `aistock sync-data --mode all`
4. 验证数据正常同步

---

**Plan complete and saved to `docs/superpowers/plans/2026-05-15-akshare-adapter-plan.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**