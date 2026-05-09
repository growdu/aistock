"""Application entry points."""

from aistock.app.cli import app
from aistock.app.logging import get_logger, setup_logging

__all__ = ["app", "setup_logging", "get_logger"]
