"""
memory_portability.backend
==========================

Abstract storage adapter interface that agents must implement.

The package owns archive validation, receipts, and transaction orchestration.
The backend owns all live storage operations: reading and writing history,
reading and writing vector records, providing embeddings, and running smoke
tests after a restore.

Agents implement ``MemoryBackend`` and pass an instance to ``MemoryTransfer``.
The package never imports ChromaDB, torch, or any embedding library directly.
"""

from abc import ABC, abstractmethod
from collections.abc import Iterator
from contextlib import AbstractContextManager
from pathlib import Path


class MemoryBackend(ABC):
    """Abstract interface between the portability package and agent storage.

    Implement all abstract methods and properties. Pass an instance to
    ``MemoryTransfer``.

    Thread safety
    -------------
    The package holds ``write_lock`` briefly during export snapshots. All live
    history and vector writes in the agent must also acquire this lock, so that
    the snapshot is coherent across history and vector components.
    """

    # ------------------------------------------------------------------
    # Concurrency and paths
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def write_lock(self) -> AbstractContextManager:
        """Context manager that blocks live memory writes during export.

        Must be the same lock object used by all history appends and vector
        ``remember`` calls in the agent. The package holds it only during the
        snapshot phase of export; it is never held during import.
        """
        ...

    @property
    @abstractmethod
    def state_dir(self) -> Path:
        """Persistent directory where the package may create its own state.

        Must exist, be writable, and reside on the same filesystem as the live
        memory components so that atomic renames work. The package creates only
        its reserved hidden children here:

        - ``.import_staging``     — extracted archive content
        - ``.import_rollback``    — pre-import snapshot for overwrite restore
        - ``.import_in_progress`` — transaction marker file
        - ``.memory_import_receipts`` — per-archive import receipts

        The backend may also keep live history and vector-store paths under
        this directory. The package never modifies any path that is not one of
        the four reserved children listed above.
        """
        ...

    # ------------------------------------------------------------------
    # History operations
    # ------------------------------------------------------------------

    @abstractmethod
    def read_history(self) -> str | None:
        """Return the full content of the history file, or None if absent."""
        ...

    @abstractmethod
    def write_history(self, text: str | None) -> None:
        """Replace the history file with ``text``, or remove it when ``None``."""
        ...

    @abstractmethod
    def append_history(self, text: str) -> None:
        """Append ``text`` to the history file, creating it if absent."""
        ...

    # ------------------------------------------------------------------
    # Vector record operations
    # ------------------------------------------------------------------

    @abstractmethod
    def iter_records(self, batch_size: int) -> Iterator[list[dict]]:
        """Yield batches of portable user memory records for export.

        Each record dict must contain:
            ``id``        -- non-empty string
            ``document``  -- string document text
            ``embedding`` -- list of floats (may be empty list)
            ``metadata``  -- dict with scalar or JSON-serialisable values

        Must exclude knowledge-prior chunks, hash sentinels, and any record
        that does not belong to portable user memory.
        """
        ...

    @abstractmethod
    def replace_records(self, records: Iterator[list[dict]]) -> None:
        """Replace portable user records from a one-pass batch iterator.

        Delete all existing portable user records first, then insert the
        supplied records. Preserve all non-user records (knowledge-prior
        chunks, hash sentinels, etc.) throughout.

        The package serialises the original portable records to its rollback
        directory before calling this method. If a restore is needed, it calls
        this method again with the rollback batches.

        The backend must accept and store every package-supplied ID exactly
        as provided without modification.
        """
        ...

    @abstractmethod
    def vector_store_exists(self) -> bool:
        """Return whether the physical vector store exists."""
        ...

    @abstractmethod
    def remove_vector_store(self) -> None:
        """Remove the physical vector store when rollback restores absence."""
        ...

    @abstractmethod
    def upsert_records(self, records: list[dict]) -> None:
        """Add or update a batch of records, preserving package-supplied IDs.

        Used during append imports. Append record IDs have the form
        ``import-<uuid>-<original-id>`` and are generated by the package.
        The backend must store them exactly as provided.
        """
        ...

    @abstractmethod
    def delete_records(self, ids: list[str]) -> None:
        """Delete exactly the records identified by ``ids``.

        Used to roll back a partial append import. The package passes the
        exact IDs it generated during the import attempt.
        """
        ...

    # ------------------------------------------------------------------
    # Embedding
    # ------------------------------------------------------------------

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return embeddings for ``texts`` using the agent's active model.

        Called only when the archive's embedding profile differs from the
        runtime profile. The package calls this in batches from staging and
        writes the results back to staged records; live memory is never
        modified during re-embedding.

        Must return a list of the same length as ``texts``. Each inner list
        must have the configured embedding dimension. When that dimension is
        unavailable because the live store is empty, the package infers it
        from the first returned embedding and validates later batches.
        """
        ...

    @abstractmethod
    def get_embedding_profile(self) -> dict:
        """Return the active embedding profile.

        Must return a dict with exactly these keys:
            ``provider``         -- str, e.g. ``"Local"`` or ``"OpenAI"``
            ``model``            -- str, e.g. ``"intfloat/e5-large-v2"``
            ``vector_dimension`` -- positive int when known, otherwise ``None``

        Written into the manifest on export, where a positive dimension is
        required. On import an unknown dimension triggers staged re-embedding.
        """
        ...

    # ------------------------------------------------------------------
    # Manifest metadata and smoke tests
    # ------------------------------------------------------------------

    @abstractmethod
    def get_archive_metadata(self) -> dict:
        """Return format-v1 producer and store metadata for the manifest.

        For OmegaClaw format version 1 compatibility, must return exactly:
            ``omegaclaw_version`` -- str, the running agent version
            ``chromadb_version``  -- str, e.g. ``chromadb.__version__``

        A different agent targeting a future generic format version should
        return fields appropriate for that version.
        """
        ...

    @abstractmethod
    def smoke_test(self, include_history: bool, include_vectors: bool) -> None:
        """Verify that the selected live components are readable after restore.

        Raise any exception if a component is unreadable or the vector store
        is not queryable. The package calls this after restore and before
        writing the import receipt. A failure triggers rollback.
        """
        ...
