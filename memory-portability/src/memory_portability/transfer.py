from collections.abc import Callable
from pathlib import Path

from memory_portability.backend import MemoryBackend
from memory_portability import exporter, importer

class MemoryTransfer:
    """Coordinate export, import, and recovery for one storage backend."""

    def __init__(self, backend: MemoryBackend, transfer_dir: Path) -> None:
        if not isinstance(backend, MemoryBackend):
            raise TypeError(
                f"backend must be a MemoryBackend instance, got {type(backend)!r}"
            )
        self._backend      = backend
        self._transfer_dir = Path(transfer_dir)

    def export(self, component: str) -> dict:
        """Export components synchronously."""
        return exporter.export(
            backend=self._backend,
            transfer_dir=self._transfer_dir,
            component=component,
        )

    def start_export_job(
        self,
        component: str,
        on_complete: Callable[[str, dict], None] | None = None,
    ) -> str:
        """Start a background export and return its job ID."""
        return exporter.start_export_job(
            backend=self._backend,
            transfer_dir=self._transfer_dir,
            component=component,
            on_complete=on_complete,
        )

    def get_export_status(self, job_id: str) -> dict:
        """Return the current status for an export job."""
        return exporter.get_export_status(job_id)

    def import_archive(
        self,
        filename: str,
        mode: str = "overwrite",
        include_history: bool = True,
        include_vectors: bool = True,
    ) -> None:
        """Validate and restore an archive before the agent loop starts."""
        importer.import_archive(
            backend=self._backend,
            transfer_dir=self._transfer_dir,
            filename=filename,
            mode=mode,
            include_history=include_history,
            include_vectors=include_vectors,
        )

    def recover(self) -> None:
        """Recover an interrupted import transaction, if present."""
        importer.recover(self._backend)
