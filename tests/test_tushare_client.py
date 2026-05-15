import pytest
from aistock.data.sources.base import DataSourceClient
from aistock.data.sources.tushare_client import TushareClient

def test_tushare_client_implements_protocol():
    """验证 TushareClient 实现了 DataSourceClient"""
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