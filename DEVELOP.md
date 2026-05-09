# 开发指南

本文档面向希望继续扩展 AIStock 系统的开发者。

## 1. 项目结构概览

```
src/aistock/
├── app/           # CLI 入口、日志
├── config/        # Pydantic 配置加载
├── db/            # SQLAlchemy 模型和连接
├── data/          # Tushare 客户端 + 数据管道
│   └── sources/
│       └── tushare_client.py
├── feature/       # 因子计算（81 特征）
│   └── factors.py
├── model/         # 训练 + 推理
│   ├── train.py
│   └── predict.py
├── strategy/      # 信号生成 + 仓位分配
│   └── engine.py
├── risk/          # 风控规则
│   └── engine.py
├── backtest/      # 回测引擎
│   └── engine.py
├── broker/        # 券商适配
│   ├── base.py    # BrokerAdapter 协议
│   ├── paper.py   # SimBroker
│   └── qmt.py     # QMTBroker
├── execution/     # 信号 → 订单执行层
│   └── engine.py
├── report/        # 报告和可视化
│   └── dashboard_app.py
└── common/        # 公共类型
    └── types.py
```

## 2. 添加新的数据源

参考 `data/sources/tushare_client.py` 的接口设计：

```python
class MyDataSource:
    def get_daily_bars(self, symbol: str, start: str, end: str) -> pd.DataFrame:
        # 返回标准格式 DataFrame：
        # trade_date, ts_code, open, high, low, close, volume, amount
        ...
```

然后在 `data/pipeline.py` 的 `sync_market_daily()` 中添加对应调用。

## 3. 添加新的因子

在 `feature/factors.py` 中新增函数，遵循以下规范：

```python
def add_my_factor(frame: pd.DataFrame) -> pd.DataFrame:
    """新增因子说明。

    因子计算必须使用 per-stock groupby 或 loop，
    禁止使用依赖 Series.name 的 transform lambda。
    """
    result = frame.copy()
    for tc, grp in result.groupby("symbol"):
        # 计算逻辑...
        pass
    return result
```

并在 `build_daily_features()` 和 `build_inference_features()` 中调用。

## 4. 添加新的模型

参考 `model/train.py` 的 `train_model()` 接口：

```python
def train_model(
    feature_df: pd.DataFrame,
    target_col: str,
    model_type: str = "lightgbm",
    ...) -> TrainResult
```

保存格式：
- `.cbm`：joblib 序列化的模型
- `.json`：元数据（特征列表、目标、分隔日期、metrics）
- `.report.json`：完整训练指标报告

## 5. 添加新的券商适配器

在 `broker/` 下新增文件，继承 `BrokerAdapter`：

```python
from aistock.broker.base import BrokerAdapter, OrderRequest, OrderExecution, Position, AccountInfo

class MyBroker(BrokerAdapter):
    def place_order(self, order: OrderRequest) -> OrderExecution:
        ...

    def get_positions(self) -> list[Position]:
        ...

    def get_account(self) -> AccountInfo:
        ...

    @property
    def broker_type(self) -> str:
        return "mybroker"
```

## 6. 添加新的回测指标

在 `backtest/engine.py` 的 `_compute_metrics()` 中添加：

```python
def _compute_metrics(snapshots: list[DailySnapshot], ...) -> dict[str, float]:
    metrics = {...}
    metrics["my_new_metric"] = computed_value
    return metrics
```

## 7. 添加新的风控规则

在 `risk/engine.py` 的 `RiskEngine` 类中新增检查方法：

```python
def _check_my_rule(self, signal: TradeSignal, ...) -> RiskCheckList:
    checks = RiskCheckList()
    if condition:
        checks.add("my_rule", RiskDecision.REJECT, "reason")
    return checks
```

然后在 `evaluate()` 中调用并合并结果。

## 8. 运行测试

```bash
# 单元测试
pytest tests/ -v

# 导入验证
python -c "from aistock.broker import SimBroker; from aistock.strategy import generate_signals; print('OK')"

# 端到端验证
aistock sync-data --mode all
aistock build-features
aistock train-model --train-all
aistock run-backtest
aistock paper-trade
```

## 9. 代码规范

- 类型注解：所有公开函数必须标注返回类型
- Pydantic：配置类使用 `pydantic.BaseModel`
- Dataclass slots：数据传输对象使用 `@dataclass(slots=True)`
- 日志：使用 `logging.getLogger(__name__)`
- 异常：自定义异常继承 `ValueError` 或 `RuntimeError`
- 路径：使用 `pathlib.Path`，禁止硬编码字符串路径

## 10. 版本规范

- 主版本：破坏性 API 变更
- 次版本：新功能向后兼容
- 修订版：bug 修复和文档更新

提交时请在 `CHANGELOG.md` 中添加变更记录。
