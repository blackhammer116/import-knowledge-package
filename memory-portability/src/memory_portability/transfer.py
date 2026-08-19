"""
memory_portability.transfer
============================

``MemoryTransfer`` — the main entry point for the memory-portability package.

This class is the only thing agents need to instantiate. It wires the backend
adapter to the exporter, importer, and recovery logic and exposes a clean,
stable public API.

Agents import and use it like this::

    from memory_portability import MemoryTransfer

    transfer = MemoryTransfer(
        backend=MyBackend(),
        transfer_dir=Path("/memory-transfer"),
    )

    # Before the agent loop starts:
    transfer.recover()
    transfer.import_archive("omegaclaw-memory-<timestamp>.tar.gz", mode="overwrite")

    # From a channel command handler (async, non-blocking):
    job_id = transfer.start_export_job("both", on_complete=deliver_to_owner)
    status = transfer.get_export_status(job_id)

    # Or synchronously (blocks until done):
    result = transfer.export("both")
"""

from collections.abc import Callable
from pathlib import Path

from memory_portability.backend import MemoryBackend
from memory_portability import exporter, importer


class MemoryTransfer:
    """Main entry point for memory export, import, and crash recovery.

    Parameters
    ----------
    backend:
        Agent storage adapter implementing ``MemoryBackend``.
    transfer_dir:
        Host-mounted directory from which archives are read and to which
        new archives are published. Must be writable by the process.
    """

    def __init__(self, backend: MemoryBackend, transfer_dir: Path) -> None:
        if not isinstance(backend, MemoryBackend):
            raise TypeError(
                f"backend must be a MemoryBackend instance, got {type(backend)!r}"
            )
        self._backend      = backend
        self._transfer_dir = Path(transfer_dir)

    # ------------------------------------------------------------------
    # Export — synchronous
    # ------------------------------------------------------------------

    def export(self, component: str) -> dict:
        """Export selected memory components and return the result synchronously.

        Blocks until the archive is published. Use ``start_export_job()`` for
        a non-blocking alternative.

        Parameters
        ----------
        component:
            One of ``"history"``, ``"ltm"``, or ``"both"``.

        Returns
        -------
        dict
            Result dict containing:
                ``filename``     -- archive filename (basename only)
                ``size``         -- compressed size in bytes
                ``checksum``     -- SHA-256 hex digest of the archive
                ``record_count`` -- number of vector records exported
                ``components``   -- list of component names included

        Raises
        ------
        ExportError
            If the export fails.
        ValueError
            If ``component`` is not one of the allowed values.
        """
        return exporter.export(
            backend=self._backend,
            transfer_dir=self._transfer_dir,
            component=component,
        )

    # ------------------------------------------------------------------
    # Export — asynchronous
    # ------------------------------------------------------------------

    def start_export_job(
        self,
        component: str,
        on_complete: Callable[[str, dict], None] | None = None,
    ) -> str:
        """Start an asynchronous export and return its job ID immediately.

        The export runs in a daemon thread. Use ``get_export_status()`` to
        poll, or register ``on_complete`` for a push notification.

        Parameters
        ----------
        component:
            One of ``"history"``, ``"ltm"``, or ``"both"``.
        on_complete:
            Optional callback called with ``(job_id, status_dict)`` when the
            job finishes or fails. Called from the background thread; must
            not block.

        Returns
        -------
        str
            Opaque job ID for use with ``get_export_status()``.

        Raises
        ------
        ValueError
            If ``component`` is not one of the allowed values.
        """
        return exporter.start_export_job(
            backend=self._backend,
            transfer_dir=self._transfer_dir,
            component=component,
            on_complete=on_complete,
        )

    def get_export_status(self, job_id: str) -> dict:
        """Return the current status dict for an export job.

        Parameters
        ----------
        job_id:
            Job ID returned by ``start_export_job()``.

        Returns
        -------
        dict
            Status dict with a ``"status"`` key:
                ``"running"``  -- job is in progress
                ``"done"``     -- completed (full result fields included)
                ``"failed"``   -- failed (``"error"`` key included)
                ``"unknown"``  -- job ID not recognised
        """
        return exporter.get_export_status(job_id)

    # ------------------------------------------------------------------
    # Import
    # ------------------------------------------------------------------

    def import_archive(
        self,
        filename: str,
        mode: str = "overwrite",
        include_history: bool = True,
        include_vectors: bool = True,
    ) -> None:
        """Validate and restore a memory archive.

        Must be called before the agent loop starts. Validates the archive
        fully before modifying any live component.

        Parameters
        ----------
        filename:
            Archive filename (basename only) within the transfer directory.
        mode:
            ``"overwrite"`` (default) or ``"append"``.
        include_history:
            Restore the history component if present in the archive.
        include_vectors:
            Restore the vector component if present in the archive.

        Raises
        ------
        FileNotFoundError
            If the archive does not exist in the transfer directory.
        ArchiveValidationError
            If the archive fails validation.
        ImportError
            If the import fails after validation.
        ValueError
            If ``mode`` is invalid or both include flags are ``False``.
        """
        importer.import_archive(
            backend=self._backend,
            transfer_dir=self._transfer_dir,
            filename=filename,
            mode=mode,
            include_history=include_history,
            include_vectors=include_vectors,
        )

    def recover(self) -> None:
        """Recover from an interrupted import transaction, if one exists.

        Must be called before ``import_archive()`` and before the agent loop
        starts. Safe to call when no interrupted transaction exists.

        Raises
        ------
        RecoveryError
            If recovery cannot complete safely. The transaction marker is
            preserved for operator inspection.
        """
        importer.recover(self._backend)
