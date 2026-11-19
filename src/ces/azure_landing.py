"""Land the layers in Azure Data Lake Storage Gen2.

Off unless ``CES_TARGET=azure``. The storage account comes from
``CES_AZURE_STORAGE_ACCOUNT``; authentication is the account key in
``CES_AZURE_STORAGE_KEY`` when set, otherwise ``DefaultAzureCredential``
(``az login`` locally, a federated identity in Actions).

One filesystem (container) per layer, so RBAC can differ per layer: bronze is
identified data and gets the narrowest reader set; gold and published are what
analysts and the public page read.

    bronze/<table>/<cohort>.parquet        bronze/quarantine/<cohort>.parquet
    silver/<table>/<cohort>.parquet        silver/_meta/<cohort>.json
    gold/<table>.parquet                   published/summary.json, weekly.json
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Protocol

from ces.config import Settings

LAYERS = ("bronze", "silver", "gold", "published")


class Uploader(Protocol):
    def upload(self, filesystem: str, remote_path: str, local_path: Path) -> None: ...


class AdlsUploader:
    def __init__(self, account: str, key: str | None):
        from azure.storage.filedatalake import DataLakeServiceClient

        url = f"https://{account}.dfs.core.windows.net"
        if key:
            self._svc = DataLakeServiceClient(account_url=url, credential=key)
        else:
            from azure.identity import DefaultAzureCredential

            self._svc = DataLakeServiceClient(account_url=url, credential=DefaultAzureCredential())
        self._fs_ready: set[str] = set()

    def upload(self, filesystem: str, remote_path: str, local_path: Path) -> None:
        fs = self._svc.get_file_system_client(filesystem)
        if filesystem not in self._fs_ready:
            if not fs.exists():
                fs.create_file_system()
            self._fs_ready.add(filesystem)
        f = fs.get_file_client(remote_path)
        with local_path.open("rb") as data:
            f.upload_data(data, overwrite=True)


def plan(cfg: Settings, site_data_dir: Path | None = None) -> list[tuple[str, str, Path]]:
    """(filesystem, remote path, local file) for everything that should land."""
    items: list[tuple[str, str, Path]] = []
    for layer, root in (("bronze", cfg.bronze_dir), ("silver", cfg.silver_dir), ("gold", cfg.gold_dir)):
        if not root.exists():
            continue
        for p in sorted(root.rglob("*")):
            if p.is_file() and p.suffix in (".parquet", ".json"):
                items.append((layer, p.relative_to(root).as_posix(), p))
    site_data = site_data_dir or (cfg.site_dir / "data")
    if site_data.exists():
        for p in sorted(site_data.glob("*.json")):
            items.append(("published", p.name, p))
    return items


def land(cfg: Settings, uploader: Uploader | None = None, log=print, only: Iterable[str] | None = None) -> int:
    if cfg.target != "azure":
        log("target is local; nothing landed in Azure (set CES_TARGET=azure)")
        return 0
    if uploader is None:
        if not cfg.azure_storage_account:
            raise RuntimeError("CES_AZURE_STORAGE_ACCOUNT is required when CES_TARGET=azure")
        uploader = AdlsUploader(cfg.azure_storage_account, cfg.azure_storage_key or None)
    wanted = set(only) if only else set(LAYERS)
    n = 0
    for fs, remote, local in plan(cfg):
        if fs not in wanted:
            continue
        uploader.upload(fs, remote, local)
        n += 1
    log(f"landed {n} files in ADLS Gen2 account {cfg.azure_storage_account or '<fake>'}")
    return n
