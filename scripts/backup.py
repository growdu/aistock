"""
数据备份脚本。

备份内容：
- .env（密钥和配置）
- config/settings.yaml（策略/风控/模型参数）
- 数据库文件（从 DATABASE_URL 解析路径）
- data/models/（训练好的模型）
- data/reports/（回测报告）
- data/features/（最新特征快照）

保留策略：保留最近 30 个备份，超出删除。
"""

from __future__ import annotations

import os
import re
import shutil
import tarfile
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
BACKUP_DIR = ROOT / "data" / "backups"
MAX_BACKUPS = 30


def _parse_db_path_from_url(url: str | None = None) -> Path | None:
    """从 DATABASE_URL 解析本地数据库文件路径。"""
    url = url or os.getenv("DATABASE_URL", "sqlite:///./aistock.db")
    # sqlite:///./aistock.db 或 sqlite:////abs/path/aistock.db
    m = re.match(r"sqlite:///(.+)", url)
    if m:
        path = m.group(1)
        # 相对路径：以 ./ 开头
        if path.startswith("./") or not path.startswith("/"):
            return ROOT / path.lstrip("./")
        return Path(path)
    return None


def _copy_if_exists(source: Path, target_dir: Path) -> None:
    if not source.exists():
        return
    if source.is_dir():
        shutil.copytree(source, target_dir / source.name, dirs_exist_ok=True)
    else:
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target_dir / source.name)


def create_backup() -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    staging_dir = BACKUP_DIR / f"backup_{timestamp}"
    archive_path = BACKUP_DIR / f"backup_{timestamp}.tar.gz"

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    staging_dir.mkdir(parents=True, exist_ok=True)

    # 从环境变量解析数据库路径
    db_path = _parse_db_path_from_url()

    targets: list[tuple[str, Path | None]] = [
        (".env", ROOT / ".env"),
        ("config/settings.yaml", ROOT / "config" / "settings.yaml"),
        ("aistock.db", db_path),
        ("data/models", ROOT / "data" / "models"),
        ("data/reports", ROOT / "data" / "reports"),
        ("data/features", ROOT / "data" / "features"),
    ]

    for label, path in targets:
        if path is not None:
            _copy_if_exists(path, staging_dir)

    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(staging_dir, arcname=staging_dir.name)

    shutil.rmtree(staging_dir, ignore_errors=True)

    _cleanup_old_backups()

    print(f"backup created: {archive_path}")
    return archive_path


def _cleanup_old_backups() -> None:
    """删除超出数量限制的旧备份。"""
    if not BACKUP_DIR.exists():
        return
    backups = sorted(BACKUP_DIR.glob("backup_*.tar.gz"), key=lambda p: p.name)
    for old in backups[:-MAX_BACKUPS]:
        old.unlink()
        print(f"removed old backup: {old.name}")


def list_backups() -> list[Path]:
    if not BACKUP_DIR.exists():
        return []
    return sorted(BACKUP_DIR.glob("backup_*.tar.gz"), reverse=True)


if __name__ == "__main__":
    create_backup()
