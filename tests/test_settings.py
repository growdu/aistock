from __future__ import annotations

from pathlib import Path
import tempfile
import unittest


class SettingsLoadTest(unittest.TestCase):
    def test_load_file_config_reads_logs_dir(self) -> None:
        try:
            from aistock.config.settings import load_file_config
        except ModuleNotFoundError as exc:
            self.skipTest(f"runtime dependency missing: {exc}")

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "settings.yaml"
            with path.open("w", encoding="utf-8") as handle:
                handle.write(
                    "\n".join(
                        [
                            "app:",
                            "  name: demo",
                            "  data_dir: data-test",
                            "  logs_dir: logs-test",
                            "strategy:",
                            "  top_n: 2",
                        ]
                    )
                )

            config = load_file_config(path)
            self.assertEqual(config.app.name, "demo")
            self.assertEqual(config.app.data_dir, "data-test")
            self.assertEqual(config.app.logs_dir, "logs-test")
            self.assertEqual(config.strategy.top_n, 2)


if __name__ == "__main__":
    unittest.main()
