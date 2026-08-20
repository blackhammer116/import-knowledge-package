"""Small synchronous facade for OmegaClaw's CLI and skill layers."""

from __future__ import annotations

import os
from pathlib import Path

from .exporter import export_memory
from .importer import import_archive, recover
from .storage import MemoryStore


class MemoryTransfer:
    def __init__(
        self,
        transfer_dir: Path | None = None,
        store: MemoryStore | None = None,
    ) -> None:
        self.store = store or MemoryStore()
        self.transfer_dir = Path(
            transfer_dir or os.environ.get("MEMORY_TRANSFER_DIR", "/memory-transfer")
        )

    def export(
        self,
        component: str = "both",
        include_embeddings: bool = True,
        filename: str | None = None,
    ) -> dict:
        return export_memory(
            self.store,
            self.transfer_dir,
            component,
            include_embeddings,
            filename,
        )

    def import_archive(
        self,
        filename: str,
        mode: str = "overwrite",
        include_history: bool = True,
        include_vectors: bool = True,
    ) -> dict:
        return import_archive(
            self.store,
            self.transfer_dir,
            filename,
            mode,
            include_history,
            include_vectors,
        )

    def recover(self) -> dict:
        return recover(self.store)
