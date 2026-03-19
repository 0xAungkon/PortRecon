from datetime import datetime
from enum import Enum
import asyncio
import json
from pathlib import Path
from typing import Optional


class ScanStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Scan:
    ROOT_DIR = Path("scans")
    META_FILE = "scan.json"
    LOCK_FILE = "scan.lock"

    def __init__(
        self,
        id: str,
        name: str,
        ip_range: str,
        ports: str,
        workers: int,
        retries: int,
        status: ScanStatus = ScanStatus.PENDING,
        progress: int = 0,
        total_targets: int = 0,
        results_file: Optional[str] = None,
        error_message: Optional[str] = None,
        created_at: Optional[datetime] = None,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
    ):
        self.id = id
        self.name = name
        self.ip_range = ip_range
        self.ports = ports
        self.workers = workers
        self.retries = retries
        self.status = status
        self.progress = progress
        self.total_targets = total_targets
        self.results_file = results_file
        self.error_message = error_message
        self.created_at = created_at or datetime.utcnow()
        self.started_at = started_at
        self.completed_at = completed_at

    @classmethod
    def scan_dir(cls, scan_id: str) -> Path:
        return cls.ROOT_DIR / scan_id

    @classmethod
    def meta_path(cls, scan_id: str) -> Path:
        return cls.scan_dir(scan_id) / cls.META_FILE

    @classmethod
    def lock_path(cls, scan_id: str) -> Path:
        return cls.scan_dir(scan_id) / cls.LOCK_FILE

    @staticmethod
    def _to_iso(value: Optional[datetime]) -> Optional[str]:
        return value.isoformat() if value else None

    @staticmethod
    def _from_iso(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        return datetime.fromisoformat(value)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "ip_range": self.ip_range,
            "ports": self.ports,
            "workers": self.workers,
            "retries": self.retries,
            "status": self.status.value,
            "progress": self.progress,
            "total_targets": self.total_targets,
            "results_file": self.results_file,
            "error_message": self.error_message,
            "created_at": self._to_iso(self.created_at),
            "started_at": self._to_iso(self.started_at),
            "completed_at": self._to_iso(self.completed_at),
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "Scan":
        return cls(
            id=payload["id"],
            name=payload["name"],
            ip_range=payload["ip_range"],
            ports=payload["ports"],
            workers=payload["workers"],
            retries=payload["retries"],
            status=ScanStatus(payload.get("status", ScanStatus.PENDING.value)),
            progress=payload.get("progress", 0),
            total_targets=payload.get("total_targets", 0),
            results_file=payload.get("results_file"),
            error_message=payload.get("error_message"),
            created_at=cls._from_iso(payload.get("created_at")),
            started_at=cls._from_iso(payload.get("started_at")),
            completed_at=cls._from_iso(payload.get("completed_at")),
        )

    @classmethod
    async def create(cls, **kwargs) -> "Scan":
        scan = cls(**kwargs)
        await scan.save()
        return scan

    @classmethod
    async def get(cls, id: str) -> "Scan":
        meta_path = cls.meta_path(id)
        if not meta_path.exists():
            raise FileNotFoundError(f"Scan {id} not found")

        def _read() -> dict:
            with open(meta_path, "r") as handle:
                return json.load(handle)

        payload = await asyncio.to_thread(_read)
        return cls.from_dict(payload)

    @classmethod
    async def all(cls) -> list["Scan"]:
        cls.ROOT_DIR.mkdir(parents=True, exist_ok=True)
        scan_dirs = [d for d in cls.ROOT_DIR.iterdir() if d.is_dir()]

        scans: list[Scan] = []
        for directory in scan_dirs:
            meta_path = directory / cls.META_FILE
            if not meta_path.exists():
                continue
            try:
                scans.append(await cls.get(directory.name))
            except Exception:
                continue

        return scans

    async def save(self) -> None:
        scan_dir = self.scan_dir(self.id)
        scan_dir.mkdir(parents=True, exist_ok=True)
        meta_path = self.meta_path(self.id)
        payload = self.to_dict()

        def _write() -> None:
            with open(meta_path, "w") as handle:
                json.dump(payload, handle, indent=2)

        await asyncio.to_thread(_write)

    @classmethod
    async def set_lock(cls, scan_id: str, state: str) -> None:
        scan_dir = cls.scan_dir(scan_id)
        scan_dir.mkdir(parents=True, exist_ok=True)
        lock_path = cls.lock_path(scan_id)
        payload = {
            "scan_id": scan_id,
            "state": state,
            "updated_at": datetime.utcnow().isoformat(),
        }

        def _write_lock() -> None:
            with open(lock_path, "w") as handle:
                json.dump(payload, handle, indent=2)

        await asyncio.to_thread(_write_lock)

    @classmethod
    async def clear_lock(cls, scan_id: str) -> None:
        lock_path = cls.lock_path(scan_id)

        def _remove_lock() -> None:
            if lock_path.exists():
                lock_path.unlink()

        await asyncio.to_thread(_remove_lock)

    def __str__(self):
        return f"Scan(id={self.id}, name={self.name}, status={self.status})"
