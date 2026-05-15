"""External data providers."""

from aistock.data.sources.base import DataSourceClient
from aistock.data.sources.tushare_client import TushareClient
from aistock.data.sources.akshare_client import AkShareClient

__all__ = ["DataSourceClient", "TushareClient", "AkShareClient"]
