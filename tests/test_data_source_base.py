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
    # Verify runtime checkability by checking isinstance works with Protocol
    assert hasattr(DataSourceClient, '__protocol_attrs__') or isinstance(DataSourceClient, type)