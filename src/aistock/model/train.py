"""
模型训练模块。

支持：
- LightGBM / XGBoost 双模型
- 时间序列 split（train / val / test）
- 早停（early stopping）
- 多标签（1d / 3d / 5d 收益预测）
- 模型版本元数据
- 训练报告输出
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score, mean_squared_error, mean_absolute_error

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

MODEL_TYPES = Literal["lightgbm", "xgboost"]
DEFAULT_TAG = "prod"
DATE_FORMAT = "%Y%m%d"


# ---------------------------------------------------------------------------
# 数据类型
# ---------------------------------------------------------------------------


@dataclass
class TimeSplit:
    """时间序列切分结果。"""

    train: pd.DataFrame
    val: pd.DataFrame
    test: pd.DataFrame
    train_period: tuple[str, str]  # (start, end)
    val_period: tuple[str, str]
    test_period: tuple[str, str]


@dataclass
class TrainMetrics:
    """训练/验证/测试指标。"""

    model_type: str
    target_column: str
    train_rows: int
    val_rows: int
    test_rows: int
    # 回归指标
    train_rmse: float
    val_rmse: float
    test_rmse: float
    train_mae: float
    val_mae: float
    test_mae: float
    # 分类指标（方向二分类）
    train_auc: float | None
    val_auc: float | None
    test_auc: float | None
    # 最佳迭代
    best_iteration: int | None
    # IC（预测与实际收益的截面相关性）
    val_ic: float | None
    test_ic: float | None


@dataclass
class TrainResult:
    """训练结果。"""

    model_path: str
    metadata_path: str
    report_path: str
    metrics: TrainMetrics


# ---------------------------------------------------------------------------
# 时间序列切分
# ---------------------------------------------------------------------------


def time_split(
    frame: pd.DataFrame,
    target_column: str,
    train_end: str | None = None,
    val_end: str | None = None,
    test_end: str | None = None,
    min_train_rows: int = 500,
) -> TimeSplit:
    """
    按时间顺序切分训练/验证/测试集。

    Params:
        frame:         已按 trade_date 排序的特征 DataFrame
        target_column: 目标列（需要有此列用于过滤）
        train_end:     训练集截止日期，格式 YYYYMMDD，默认 2 年前
        val_end:       验证集截止日期，默认 1 年前
        test_end:      测试集截止日期，默认当天
        min_train_rows: 训练集最小行数，不足则抛异常

    Returns:
        TimeSplit 对象
    """
    if "trade_date" not in frame.columns:
        raise ValueError("frame must have 'trade_date' column")

    # 默认时间边界：最近 3 年，train=前 2 年，val=第 3 年，test=最近 1 年
    now = datetime.now()
    one_year_ago = (now - timedelta(days=365)).strftime(DATE_FORMAT)
    two_years_ago = (now - timedelta(days=730)).strftime(DATE_FORMAT)
    if test_end is None:
        test_end = now.strftime(DATE_FORMAT)
    if val_end is None:
        val_end = one_year_ago
    if train_end is None:
        train_end = two_years_ago

    # 过滤标签为 NaN 的行（未来数据尚未生成）
    df = frame.dropna(subset=[target_column, "trade_date"]).copy()
    df = df.sort_values("trade_date").reset_index(drop=True)

    train_mask = df["trade_date"] <= train_end
    val_mask = (df["trade_date"] > train_end) & (df["trade_date"] <= val_end)
    test_mask = (df["trade_date"] > val_end) & (df["trade_date"] <= test_end)

    train_df = df[train_mask].copy()
    val_df = df[val_mask].copy()
    test_df = df[test_mask].copy()

    if len(train_df) < min_train_rows:
        raise ValueError(
            f"train set has only {len(train_df)} rows, minimum {min_train_rows} required. "
            f"Check date range or target_column."
        )

    logger.info(
        "time_split: train=%s (%s-%s), val=%s (%s-%s), test=%s (%s-%s)",
        len(train_df), train_df["trade_date"].min(), train_df["trade_date"].max(),
        len(val_df), val_df["trade_date"].min(), val_df["trade_date"].max(),
        len(test_df), test_df["trade_date"].min(), test_df["trade_date"].max(),
    )

    return TimeSplit(
        train=train_df,
        val=val_df,
        test=test_df,
        train_period=(str(train_df["trade_date"].min()), str(train_df["trade_date"].max())),
        val_period=(str(val_df["trade_date"].min()), str(val_df["trade_date"].max())),
        test_period=(str(test_df["trade_date"].min()), str(test_df["trade_date"].max())),
    )


def _drop_non_features(df: pd.DataFrame, target_column: str) -> pd.DataFrame:
    """剔除所有非特征列。"""
    drop_cols = [
        "ts_code", "symbol", "trade_date", "source", "updated_at",
        "name", "area", "industry", "market",
        # 标签列
        target_column,
        "target_return_1d", "target_return_3d", "target_return_5d",
        "target_direction_1d", "target_direction_3d", "target_direction_5d",
        "target_up_1d", "target_up_3d", "target_up_5d",
    ]
    # 只删存在的列
    existing_drop = [c for c in drop_cols if c in df.columns]
    feature_frame = df.drop(columns=existing_drop, errors="ignore")
    # 只保留数值列
    numeric = feature_frame.select_dtypes(include=["number", "bool"]).copy()
    return numeric


# ---------------------------------------------------------------------------
# IC 计算（信息系数）
# ---------------------------------------------------------------------------


def _compute_ic(preds: pd.Series, actuals: pd.Series) -> float:
    """计算预测值与真实值的 Pearson 相关系数（IC）。"""
    valid = ~(preds.isna() | actuals.isna())
    if valid.sum() < 10:
        return 0.0
    return float(preds[valid].corr(actuals[valid]))


# ---------------------------------------------------------------------------
# 训练函数
# ---------------------------------------------------------------------------


def _train_lightgbm_impl(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_val: pd.DataFrame,
    y_val: pd.Series,
    model_type: MODEL_TYPES = "lightgbm",
) -> tuple:
    import lightgbm as lgb

    params = {
        "objective": "regression",
        "metric": "rmse",
        "learning_rate": 0.05,
        "num_leaves": 31,
        "max_depth": 6,
        "min_child_samples": 50,
        "feature_fraction": 0.8,
        "bagging_fraction": 0.8,
        "bagging_freq": 5,
        "reg_alpha": 0.1,
        "reg_lambda": 0.1,
        "verbosity": -1,
        "seed": 7,
    }

    dtrain = lgb.Dataset(X_train, label=y_train)
    dval = lgb.Dataset(X_val, label=y_val, reference=dtrain)

    callbacks = [lgb.early_stopping(stopping_rounds=30, verbose=False)]
    booster = lgb.train(
        params,
        dtrain,
        num_boost_round=500,
        valid_sets=[dval],
        callbacks=callbacks,
    )

    return booster, booster.best_iteration


def _train_xgboost_impl(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_val: pd.DataFrame,
    y_val: pd.Series,
) -> tuple:
    import xgboost as xgb

    params = {
        "objective": "reg:squarederror",
        "eval_metric": "rmse",
        "learning_rate": 0.05,
        "max_depth": 6,
        "min_child_weight": 50,
        "colsample_bytree": 0.8,
        "subsample": 0.8,
        "reg_alpha": 0.1,
        "reg_lambda": 0.1,
        "seed": 7,
        "verbosity": 0,
    }

    dtrain = xgb.DMatrix(X_train, label=y_train)
    dval = xgb.DMatrix(X_val, label=y_val)

    booster = xgb.train(
        params,
        dtrain,
        num_boost_round=500,
        evals=[(dval, "val")],
        early_stopping_rounds=30,
        verbose_eval=False,
    )

    return booster, booster.best_iteration


def _eval_regression(booster, X: pd.DataFrame, y: pd.Series) -> dict:
    preds = booster.predict(X)
    return {
        "rmse": float(np.sqrt(mean_squared_error(y, preds))),
        "mae": float(mean_absolute_error(y, preds)),
    }


def _eval_classification(booster, X: pd.DataFrame, y: pd.Series) -> dict:
    preds = booster.predict(X)
    try:
        auc = float(roc_auc_score(y, preds))
    except ValueError:
        auc = None
    return {"auc": auc}


# ---------------------------------------------------------------------------
# 主训练入口
# ---------------------------------------------------------------------------


def train_model(
    frame: pd.DataFrame,
    target_column: str,
    model_type: MODEL_TYPES = "lightgbm",
    model_dir: str | Path = "data/models",
    train_end: str | None = None,
    val_end: str | None = None,
    test_end: str | None = None,
    model_tag: str = DEFAULT_TAG,
    output_name: str | None = None,
) -> TrainResult:
    """
    完整训练流水线：时间切分 → 训练 → 早停 → 评估 → 保存。

    Params:
        frame:         完整特征 DataFrame（来自 build_daily_features）
        target_column: 目标列名，如 'target_return_1d'
        model_type:    'lightgbm' 或 'xgboost'
        model_dir:     模型文件输出目录
        train_end:     训练集截止日期
        val_end:       验证集截止日期
        test_end:      测试集截止日期
        model_tag:     模型标签，如 'prod' / 'test'
        output_name:   输出文件名（不含扩展名），默认 target_model_type_tag

    Returns:
        TrainResult（含路径和评估指标）
    """
    if target_column not in frame.columns:
        raise ValueError(f"target_column '{target_column}' not found in frame")

    # 1. 时间切分
    split = time_split(
        frame=frame,
        target_column=target_column,
        train_end=train_end,
        val_end=val_end,
        test_end=test_end,
    )

    # 2. 提取特征
    X_train = _drop_non_features(split.train, target_column)
    X_val = _drop_non_features(split.val, target_column)
    X_test = _drop_non_features(split.test, target_column)

    # 对齐特征列（val/test 可能缺少 train 中的列）
    common_cols = sorted(set(X_train.columns) & set(X_val.columns) & set(X_test.columns))
    X_train = X_train[common_cols]
    X_val = X_val[common_cols]
    X_test = X_test[common_cols]

    y_train = split.train[target_column]
    y_val = split.val[target_column]
    y_test = split.test[target_column]

    logger.info(
        "training %s for target=%s, features=%d, train=%d, val=%d, test=%d",
        model_type, target_column, len(common_cols),
        len(X_train), len(X_val), len(X_test),
    )

    # 3. 训练
    if model_type == "lightgbm":
        import lightgbm as lgb

        booster, best_iter = _train_lightgbm_impl(X_train, y_train, X_val, y_val)
        # 保存
        model_path = Path(model_dir) / f"{target_column}_{model_type}_{model_tag}.cbm"
        booster.save_model(str(model_path))
    else:
        import xgboost as xgb

        booster, best_iter = _train_xgboost_impl(X_train, y_train, X_val, y_val)
        model_path = Path(model_dir) / f"{target_column}_{model_type}_{model_tag}.json"
        booster.save_model(str(model_path))

    model_path.parent.mkdir(parents=True, exist_ok=True)

    # 4. 评估
    if model_type == "lightgbm":
        train_pred = booster.predict(X_train)
        val_pred = booster.predict(X_val)
        test_pred = booster.predict(X_test)
    else:
        import xgboost as xgb

        dtrain = xgb.DMatrix(X_train)
        dval = xgb.DMatrix(X_val)
        dtest = xgb.DMatrix(X_test)
        train_pred = booster.predict(dtrain)
        val_pred = booster.predict(dval)
        test_pred = booster.predict(dtest)

    train_eval = _eval_regression(booster if model_type == "lightgbm" else None, X_train, y_train)
    val_eval = _eval_regression(booster if model_type == "lightgbm" else None, X_val, y_val)
    test_eval = _eval_regression(booster if model_type == "lightgbm" else None, X_test, y_test)

    # IC
    val_ic = _compute_ic(pd.Series(val_pred, index=y_val.index), y_val)
    test_ic = _compute_ic(pd.Series(test_pred, index=y_test.index), y_test)

    # 方向分类 AUC（如果标签存在）
    dir_col = target_column.replace("return", "up")
    train_auc = None
    val_auc = None
    test_auc = None
    if dir_col in frame.columns:
        y_train_dir = split.train[dir_col]
        y_val_dir = split.val[dir_col]
        y_test_dir = split.test[dir_col]
        try:
            train_auc = float(roc_auc_score(y_train_dir, train_pred))
            val_auc = float(roc_auc_score(y_val_dir, val_pred))
            test_auc = float(roc_auc_score(y_test_dir, test_pred))
        except ValueError:
            pass

    metrics = TrainMetrics(
        model_type=model_type,
        target_column=target_column,
        train_rows=len(X_train),
        val_rows=len(X_val),
        test_rows=len(X_test),
        train_rmse=train_eval["rmse"],
        val_rmse=val_eval["rmse"],
        test_rmse=test_eval["rmse"],
        train_mae=train_eval["mae"],
        val_mae=val_eval["mae"],
        test_mae=test_eval["mae"],
        train_auc=train_auc,
        val_auc=val_auc,
        test_auc=test_auc,
        best_iteration=best_iter,
        val_ic=val_ic,
        test_ic=test_ic,
    )

    # 5. 元数据
    metadata = {
        "model_type": model_type,
        "target_column": target_column,
        "feature_columns": common_cols,
        "feature_count": len(common_cols),
        "train_period": split.train_period,
        "val_period": split.val_period,
        "test_period": split.test_period,
        "train_rows": len(X_train),
        "val_rows": len(X_val),
        "test_rows": len(X_test),
        "best_iteration": best_iter,
        "metrics": {
            "train_rmse": round(metrics.train_rmse, 6),
            "val_rmse": round(metrics.val_rmse, 6),
            "test_rmse": round(metrics.test_rmse, 6),
            "val_ic": round(metrics.val_ic, 6) if metrics.val_ic else None,
            "test_ic": round(metrics.test_ic, 6) if metrics.test_ic else None,
            "val_auc": round(metrics.val_auc, 4) if metrics.val_auc else None,
        },
        "model_tag": model_tag,
        "trained_at": datetime.now().isoformat(),
    }
    metadata_path = model_path.with_suffix(".json")
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=True, indent=2), encoding="utf-8")

    # 6. 训练报告
    report = {
        "model": str(model_path),
        "metadata": str(metadata_path),
        "model_type": model_type,
        "target": target_column,
        "tag": model_tag,
        "train_period": split.train_period,
        "val_period": split.val_period,
        "test_period": split.test_period,
        "features": len(common_cols),
        "rows": {"train": len(X_train), "val": len(X_val), "test": len(X_test)},
        "rmse": {"train": round(metrics.train_rmse, 6), "val": round(metrics.val_rmse, 6), "test": round(metrics.test_rmse, 6)},
        "mae": {"train": round(metrics.train_mae, 6), "val": round(metrics.val_mae, 6), "test": round(metrics.test_mae, 6)},
        "auc": {
            "train": round(metrics.train_auc, 4) if metrics.train_auc else None,
            "val": round(metrics.val_auc, 4) if metrics.val_auc else None,
            "test": round(metrics.test_auc, 4) if metrics.test_auc else None,
        },
        "ic": {
            "val": round(metrics.val_ic, 4) if metrics.val_ic else None,
            "test": round(metrics.test_ic, 4) if metrics.test_ic else None,
        },
        "best_iteration": best_iter,
    }
    report_path = model_path.with_suffix(".report.json")
    report_path.write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8")

    logger.info(
        "training done: model=%s, val_rmse=%.6f, val_ic=%.4f, val_auc=%.4f",
        model_path.name, metrics.val_rmse, metrics.val_ic or 0.0, metrics.val_auc or 0.0,
    )

    return TrainResult(
        model_path=str(model_path),
        metadata_path=str(metadata_path),
        report_path=str(report_path),
        metrics=metrics,
    )


# ---------------------------------------------------------------------------
# 便捷封装
# ---------------------------------------------------------------------------


def train_lightgbm(
    features: pd.DataFrame,
    target_column: str,
    model_path: str,
    **kwargs,
) -> TrainResult:
    """LGBM 训练（兼容旧 API）。"""
    return train_model(
        frame=features,
        target_column=target_column,
        model_type="lightgbm",
        model_dir=str(Path(model_path).parent),
        output_name=Path(model_path).stem,
        **kwargs,
    )


def train_xgboost(
    features: pd.DataFrame,
    target_column: str,
    model_path: str,
    **kwargs,
) -> TrainResult:
    """XGBoost 训练。"""
    return train_model(
        frame=features,
        target_column=target_column,
        model_type="xgboost",
        model_dir=str(Path(model_path).parent),
        output_name=Path(model_path).stem,
        **kwargs,
    )


def train_all_targets(
    features: pd.DataFrame,
    targets: list[str] | None = None,
    model_dir: str | Path = "data/models",
    model_type: MODEL_TYPES = "lightgbm",
    **kwargs,
) -> dict[str, TrainResult]:
    """
    一次性训练所有标签目标（1d / 3d / 5d 收益预测）。
    默认训练 3 个目标。
    """
    if targets is None:
        targets = ["target_return_1d", "target_return_3d", "target_return_5d"]

    results: dict[str, TrainResult] = {}
    for target in targets:
        if target not in features.columns:
            logger.warning("target '%s' not found in features, skipping", target)
            continue
        try:
            result = train_model(
                frame=features,
                target_column=target,
                model_type=model_type,
                model_dir=str(model_dir),
                **kwargs,
            )
            results[target] = result
        except Exception as exc:
            logger.error("failed to train target '%s': %s", target, exc)

    return results
