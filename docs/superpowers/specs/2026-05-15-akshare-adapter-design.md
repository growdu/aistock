# AkShare 数据源适配设计

## 1. 背景

当前项目使用 Tushare 作为数据源，但 Tushare 需要积分才能调用大部分接口，成本较高。
AkShare 是开源免费的数据源，可作为替代方案。

## 2. 目标

实现双数据源架构，用户可通过配置选择使用 Tushare 或 AkShare，无需修改代码。

## 3. 架构设计

```
┌─────────────────────────────────────────────────────┐
│                   pipeline.py                        │
│              (数据同步入口)                          │
└─────────────────────┬───────────────────────────────┘
                      │
           ┌──────────▼──────────┐
           │   DataSourceClient   │  ← 统一定义接口
           │    (Protocol)        │
           └──────────┬──────────┘
                      │
         ┌────────────┴────────────┐
         │                         │
   ┌─────▼──────┐            ┌────▼────────┐
   │ Tushare    │            │  AkShare     │
   │ Client     │            │  Client      │
   └───────────┘            └─────────────┘
```

## 4. 文件变更

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `data/sources/base.py` | 新增 | `DataSourceClient` Protocol 定义 |
| `data/sources/akshare_client.py` | 新增 | AkShare 客户端实现 |
| `data/sources/tushare_client.py` | 修改 | 实现 `DataSourceClient` Protocol |
| `data/sources/__init__.py` | 修改 | 导出客户端类 |
| `config/settings.py` | 修改 | 添加 `data_source.type` 配置 |
| `data/pipeline.py` | 修改 | 根据配置选择客户端 |

## 5. 接口定义

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class DataSourceClient(Protocol):
    """数据源客户端统一接口"""

    def ping(self) -> bool:
        """检查数据源连接"""

    def get_stock_basic(self, list_status: str = "L") -> pd.DataFrame:
        """获取股票基本信息"""

    def get_trade_calendar(self, start_date: str, end_date: str, exchange: str = "SSE") -> pd.DataFrame:
        """获取交易日历"""

    def get_daily(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """获取日线行情"""

    def get_daily_basic(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """获取日线指标"""

    def get_index_daily(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """获取指数日线"""

    def get_bars(self, ts_code: str, start_date: str, end_date: str, freq: str = "5m") -> pd.DataFrame:
        """获取分钟线"""

    def get_financial_indicator(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """获取财务指标"""

    def get_moneyflow(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """获取资金流向"""
```

## 6. AkShare 接口映射

| DataSourceClient 方法 | AkShare 函数 |
|---------------------|-------------|
| `get_stock_basic` | `ak.stock_zh_a_spot_em()` |
| `get_trade_calendar` | `ak.tool_trade_date_hist_sina()` |
| `get_daily` | `ak.stock_zh_a_hist(symbol, period="daily", start_date, end_date)` |
| `get_daily_basic` | `ak.stock_zh_a_daily(symbol, start_date, end_date, adjust="qfq")` |
| `get_index_daily` | `ak.stock_zh_index_daily(symbol)` |
| `get_bars` | `ak.stock_zh_a_hist(symbol, period="5min", start_date, end_date)` |
| `get_financial_indicator` | 暂不支持（需手动处理） |
| `get_moneyflow` | `ak.stock_money_flow_em()` |

## 7. 配置设计

### settings.yaml
```yaml
data_source:
  type: tushare  # tushare | akshare
```

### .env
```bash
DATA_SOURCE_TYPE=akshare
```

### 字段映射

Tushare 返回字段可能与 AkShare 不同，需在客户端内部统一字段名：

| 统一字段 | Tushare | AkShare |
|---------|---------|---------|
| 股票代码 | ts_code | ts_code (需构造) |
| 交易日期 | trade_date | trade_date |
| 开盘价 | open | open |
| 最高价 | high | high |
| 最低价 | low | low |
| 收盘价 | close | close |
| 成交量 | volume | volume |
| 成交额 | amount | amount |

股票代码格式统一：`000001.SZ`（上交所 `.SH`，深交所 `.SZ`）

## 8. 实现顺序

1. 创建 `base.py` 定义 Protocol 接口
2. 创建 `akshare_client.py` 实现 AkShare 客户端
3. 修改 `tushare_client.py` 确保实现同一接口
4. 修改 `config/settings.py` 添加 `data_source.type`
5. 修改 `pipeline.py` 根据 type 选择客户端
6. 添加单元测试验证两种数据源

## 9. 风险与限制

- AkShare 分钟线数据有限，不支持 1min
- AkShare 无财务指标接口，需要降级或跳过
- 部分接口可能失败，需添加错误处理和日志