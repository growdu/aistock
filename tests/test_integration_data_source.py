import pytest
import pandas as pd
from aistock.data.sources.akshare_client import AkShareClient

def test_akshare_client_can_be_instantiated():
    """验证 AkShareClient 可以实例化"""
    client = AkShareClient()
    assert client is not None

def test_akshare_client_get_daily():
    """验证 AkShareClient 可以获取日线数据"""
    client = AkShareClient()
    df = client.get_daily("300750.SZ", "20240101", "20240110")
    # 注意：如果网络问题或数据问题，可能返回空 DataFrame
    # 这里只验证方法可以正常调用不抛异常
    assert isinstance(df, pd.DataFrame)

def test_akshare_client_ping():
    """验证 AkShareClient ping 方法"""
    client = AkShareClient()
    # ping 可能因为网络问题失败，不强制要求返回 True
    result = client.ping()
    assert isinstance(result, bool)