import os
from collections.abc import Callable
from pathlib import Path

from . import exporter, importer
from .backend import OmegaClawMemory


class MemoryTransfer:
    def __init__(self, transfer_dir: Path | None = None) -> None:
        self._backend = OmegaClawMemory()
        self._transfer_dir = Path(
            transfer_dir or os.environ.get("MEMORY_TRANSFER_DIR", "/memory-transfer")
        )

    def export(self, component: str) -> dict:
        return exporter.export(self._backend, self._transfer_dir, component)

    def start_export_job(
        self, component: str, on_complete: Callable[[str, dict], None] | None = None
    ) -> str:
        return exporter.start_export_job(
            self._backend, self._transfer_dir, component, on_complete
        )

    def get_export_status(self, job_id: str) -> dict:
        return exporter.get_export_status(job_id)

    def import_archive(
        self,
        filename: str,
        mode: str = "overwrite",
        include_history: bool = True,
        include_vectors: bool = True,
    ) -> None:
        importer.import_archive(
            self._backend,
            self._transfer_dir,
            filename,
            mode,
            include_history,
            include_vectors,
        )

    def recover(self) -> None:
        importer.recover(self._backend)
