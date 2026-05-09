from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest


class CliSmokeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

        config_dir = self.root / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = config_dir / "settings.yaml"
        self.database_path = self.root / "test.db"
        self.data_dir = self.root / "data"
        self.logs_dir = self.root / "logs"

        with self.config_path.open("w", encoding="utf-8") as handle:
            handle.write(
                "\n".join(
                    [
                        "app:",
                        "  name: aistock-test",
                        f"  data_dir: {self.data_dir}",
                        f"  logs_dir: {self.logs_dir}",
                        "strategy:",
                        "  top_n: 3",
                        "  symbols:",
                        "    - 300750.SZ",
                        "    - 688041.SH",
                        "risk:",
                        "  max_daily_trades: 5",
                        "  max_single_position_pct: 0.1",
                        "  min_confidence_score: 0.6",
                        "data_source:",
                        "  primary_provider: tushare",
                        "  enable_news: false",
                    ]
                )
            )

        self.env = os.environ.copy()
        self.env.update(
            {
                "DATABASE_URL": f"sqlite:///{self.database_path}",
                "CONFIG_PATH": str(self.config_path),
                "LOG_LEVEL": "INFO",
            }
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _load_app(self):
        try:
            from typer.testing import CliRunner
            from aistock.app.cli import app
        except ModuleNotFoundError as exc:
            self.skipTest(f"runtime dependency missing: {exc}")
        return CliRunner(), app

    def test_prepare_runtime_and_health_check(self) -> None:
        runner, app = self._load_app()
        result = runner.invoke(app, ["prepare-runtime"], env=self.env)
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertTrue((self.data_dir / "raw").exists())
        self.assertTrue(self.logs_dir.exists())

        result = runner.invoke(app, ["health-check"], env=self.env)
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("health check passed", result.output)

    def test_signal_generation_flow(self) -> None:
        runner, app = self._load_app()
        for command in (
            ["init-db"],
            ["sync-data"],
            ["generate-signals"],
            ["show-signals"],
            ["paper-trade"],
            ["run-backtest"],
        ):
            result = runner.invoke(app, command, env=self.env)
            self.assertEqual(result.exit_code, 0, f"{command}: {result.output}")

        self.assertTrue((self.data_dir / "reports" / "signals.csv").exists())
        self.assertTrue((self.logs_dir / "aistock-test.log").exists())


if __name__ == "__main__":
    unittest.main()
