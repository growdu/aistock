# tests/test_pipeline.py
import pytest
from unittest.mock import MagicMock, patch
from aistock.data.pipeline import get_client


class TestGetClient:
    """Test the get_client factory function."""

    def test_returns_akshare_client_when_configured(self):
        """Verify returns AkShareClient when config type is akshare."""
        from aistock.config.settings import DataSourceConfig, FileConfig, RuntimeSettings

        file_config = MagicMock(spec=FileConfig)
        runtime = MagicMock(spec=RuntimeSettings)
        file_config.data_source = DataSourceConfig(type="akshare")

        with patch("aistock.data.pipeline.AkShareClient") as MockAkShare:
            mock_instance = MagicMock()
            MockAkShare.return_value = mock_instance

            result = get_client(file_config, runtime)

            MockAkShare.assert_called_once()
            assert result == mock_instance

    def test_returns_tushare_client_when_configured(self):
        """Verify returns TushareClient when config type is tushare."""
        from aistock.config.settings import DataSourceConfig, FileConfig, RuntimeSettings

        file_config = MagicMock(spec=FileConfig)
        runtime = MagicMock(spec=RuntimeSettings)
        runtime.tushare_token = "test_token_123"
        file_config.data_source = DataSourceConfig(type="tushare")

        with patch("aistock.data.pipeline.TushareClient") as MockTushare:
            mock_instance = MagicMock()
            MockTushare.return_value = mock_instance

            result = get_client(file_config, runtime)

            MockTushare.assert_called_once_with("test_token_123")
            assert result == mock_instance

    def test_returns_tushare_client_by_default(self):
        """Verify returns TushareClient when config type is unspecified."""
        from aistock.config.settings import DataSourceConfig, FileConfig, RuntimeSettings

        file_config = MagicMock(spec=FileConfig)
        runtime = MagicMock(spec=RuntimeSettings)
        runtime.tushare_token = "test_token_456"
        file_config.data_source = DataSourceConfig(type="unknown")

        with patch("aistock.data.pipeline.TushareClient") as MockTushare:
            mock_instance = MagicMock()
            MockTushare.return_value = mock_instance

            result = get_client(file_config, runtime)

            MockTushare.assert_called_once_with("test_token_456")
            assert result == mock_instance