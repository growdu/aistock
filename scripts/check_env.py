from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    required = [
        ROOT / ".env.example",
        ROOT / "config" / "settings.example.yaml",
        ROOT / "src" / "aistock" / "app" / "cli.py",
        ROOT / "pyproject.toml",
    ]

    missing = [path for path in required if not path.exists()]
    if missing:
        for path in missing:
            print(f"missing: {path}")
        return 1

    print("environment files look ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
