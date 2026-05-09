from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil
import tarfile


ROOT = Path(__file__).resolve().parent.parent
BACKUP_DIR = ROOT / "data" / "backups"


def copy_if_exists(source: Path, target_dir: Path) -> None:
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

    targets = [
        ROOT / ".env",
        ROOT / "config" / "settings.yaml",
        ROOT / "aistock.db",
        ROOT / "data" / "models",
        ROOT / "data" / "reports",
    ]

    for target in targets:
        copy_if_exists(target, staging_dir)

    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(staging_dir, arcname=staging_dir.name)

    shutil.rmtree(staging_dir, ignore_errors=True)
    return archive_path


if __name__ == "__main__":
    archive = create_backup()
    print(f"backup created: {archive}")
