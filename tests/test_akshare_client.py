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

def test_akshare_client_is_runtime_checkable():
    """验证 AkShareClient 实现了 Protocol"""
    from aistock.data.sources.base import DataSourceClient
    client = AkShareClient()
    assert isinstance(client, DataSourceClient)