"""
memory_portability.exporter
============================

Export logic: snapshot, manifest building, atomic publication, and async
job management.

Responsibilities
----------------
- Acquiring the backend write lock and snapshotting history and vector
  records into a staging directory.
- Building ``manifest.json`` with checksums, embedding info, record counts,
  history bytes, and agent/store metadata from the backend.
- Packing the staging directory into a validated ``.tar.gz``.
- Publishing the archive atomically to the transfer directory (write to a
  hidden temp file, then rename).
- Running export jobs asynchronously in daemon threads and tracking their
  status by job ID so callers can poll or register a completion callback.

The exporter never modifies live memory. It only reads from the backend
(via ``iter_records`` and ``read_history``) while holding ``write_lock``.
"""

import hashlib
import json
import os
import shutil
import threading
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from memory_portability.archive import (
    ALLOWLIST,
    ARCHIVE_FORMAT_VERSION,
    COMPONENT_FILES,
    pack,
    unpack,
)
from memory_portability.backend import MemoryBackend
from memory_portability.errors import ExportError
from memory_portability.validator import (
    validate_checksums,
    validate_collections,
    validate_history,
    validate_manifest,
    validate_records,
)

# ---------------------------------------------------------------------------
# Module-level job registry (in-process, daemon-thread-backed)
# ---------------------------------------------------------------------------

_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()

_VALID_COMPONENTS = frozenset({"history", "ltm", "both"})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def export(
    backend: MemoryBackend,
    transfer_dir: Path,
    component: str,
) -> dict:
    """Export selected memory components and publish a validated archive.

    Runs synchronously. Acquires the backend write lock, snapshots the
    selected components, builds and validates the archive, and publishes it
    atomically to ``transfer_dir``.

    Parameters
    ----------
    backend:
        Agent storage adapter.
    transfer_dir:
        Directory where the finished archive is published. Must be writable.
    component:
        One of ``"history"``, ``"ltm"``, or ``"both"``.

    Returns
    -------
    dict
        Result dict containing:
            ``filename``     -- archive filename (basename only)
            ``size``         -- compressed size in bytes
            ``checksum``     -- SHA-256 hex digest of the published archive
            ``record_count`` -- number of vector records exported
            ``components``   -- list of component names included

    Raises
    ------
    ExportError
        If any step of the export fails.
    ValueError
        If ``component`` is not one of the allowed values.
    """
    if component not in _VALID_COMPONENTS:
        raise ValueError(
            f"Invalid component: {component!r}. Use 'history', 'ltm', or 'both'."
        )

    include_history = component in ("history", "both")
    include_vectors = component in ("ltm", "both")

    archive_name = _archive_name()
    transfer_dir.mkdir(parents=True, exist_ok=True)

    # Staging lives inside a hidden work dir inside the transfer directory
    # so that the final atomic rename stays on the same filesystem.
    work_dir = transfer_dir / f".export_work_{archive_name}"
    staging  = work_dir / "staging"
    tmp_archive = transfer_dir / f".{archive_name}.tmp"

    try:
        work_dir.mkdir(parents=True, exist_ok=True)
        staging.mkdir()

        record_count:   int  = 0
        embedding_info: dict = {}
        components:     list[str] = []

        # Hold the write lock only during the snapshot phase so live writes
        # are blocked for the minimum possible time.
        with backend.write_lock:
            if include_history:
                _snapshot_history(backend, staging)
                components.append("history")

            if include_vectors:
                record_count, embedding_info = _snapshot_vectors(backend, staging)
                components.append("ltm")

        _build_manifest(backend, staging, components, record_count, embedding_info)
        pack(staging, tmp_archive)
        _verify_packed_archive(tmp_archive, work_dir / "verify")

        dest = transfer_dir / archive_name
        os.replace(tmp_archive, dest)

    except ExportError:
        raise
    except Exception as exc:
        raise ExportError(f"Export failed: {exc}") from exc
    finally:
        tmp_archive.unlink(missing_ok=True)
        shutil.rmtree(work_dir, ignore_errors=True)

    size     = dest.stat().st_size
    checksum = _sha256_file(dest)

    return {
        "filename":     archive_name,
        "size":         size,
        "checksum":     checksum,
        "record_count": record_count,
        "components":   components,
    }


def start_export_job(
    backend: MemoryBackend,
    transfer_dir: Path,
    component: str,
    on_complete: Callable[[str, dict], None] | None = None,
) -> str:
    """Start an asynchronous export and return its job ID immediately.

    The export runs in a daemon thread. When complete, ``on_complete`` is
    called with ``(job_id, status_dict)`` if provided. The status dict has
    the same shape as the return value of ``export()``, plus a ``"status"``
    key (``"done"`` or ``"failed"``) and an ``"error"`` key on failure.

    Parameters
    ----------
    backend:
        Agent storage adapter.
    transfer_dir:
        Directory where the finished archive is published.
    component:
        One of ``"history"``, ``"ltm"``, or ``"both"``.
    on_complete:
        Optional callback called with ``(job_id, status_dict)`` when the job
        finishes or fails. Called from the background thread; must not block.

    Returns
    -------
    str
        Opaque job ID for use with ``get_export_status()``.

    Raises
    ------
    ValueError
        If ``component`` is not one of the allowed values.
    """
    if component not in _VALID_COMPONENTS:
        raise ValueError(
            f"Invalid component: {component!r}. Use 'history', 'ltm', or 'both'."
        )

    job_id = uuid.uuid4().hex
    with _jobs_lock:
        _jobs[job_id] = {"status": "running"}

    threading.Thread(
        target=_run_export_job,
        args=(job_id, backend, transfer_dir, component, on_complete),
        daemon=True,
    ).start()

    return job_id


def get_export_status(job_id: str) -> dict:
    """Return the current status of an export job.

    Parameters
    ----------
    job_id:
        Job ID returned by ``start_export_job()``.

    Returns
    -------
    dict
        Status dict with at least a ``"status"`` key:
            ``"running"``  -- job is in progress
            ``"done"``     -- job completed successfully (full result included)
            ``"failed"``   -- job failed (``"error"`` key contains message)
            ``"unknown"``  -- job ID not recognised
    """
    with _jobs_lock:
        return _jobs.get(job_id, {"status": "unknown"}).copy()


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _run_export_job(
    job_id: str,
    backend: MemoryBackend,
    transfer_dir: Path,
    component: str,
    on_complete: Callable[[str, dict], None] | None,
) -> None:
    """Background thread target: run export and update job registry."""
    try:
        result = export(backend, transfer_dir, component)
        status = {"status": "done", **result}
    except Exception as exc:
        status = {"status": "failed", "error": str(exc)}

    with _jobs_lock:
        _jobs[job_id] = status

    if on_complete is not None:
        try:
            on_complete(job_id, status.copy())
        except Exception:
            pass  # callback errors must never crash the background thread


def _snapshot_history(backend: MemoryBackend, staging: Path) -> int:
    """Write history content into staging. Returns byte size written."""
    content = backend.read_history()
    dst = staging / "history" / "history.metta"
    dst.parent.mkdir(parents=True, exist_ok=True)
    if content is not None:
        dst.write_text(content, encoding="utf-8")
        return dst.stat().st_size
    dst.touch()
    return 0


def _snapshot_vectors(
    backend: MemoryBackend, staging: Path
) -> tuple[int, dict]:
    """Write vector records and collections.json into staging."""
    vector_dir   = staging / "vector"
    vector_dir.mkdir(parents=True, exist_ok=True)
    records_path = vector_dir / "records.jsonl"

    record_count = 0
    dimension    = 0

    with records_path.open("w", encoding="utf-8") as f:
        for batch in backend.iter_records(batch_size=500):
            for record in batch:
                embedding = record.get("embedding") or []
                if not dimension and embedding:
                    dimension = len(embedding)
                f.write(json.dumps({
                    "id":        record["id"],
                    "document":  record["document"],
                    "metadata":  record.get("metadata", {}),
                    "embedding": list(embedding),
                }, ensure_ascii=False) + "\n")
                record_count += 1

    active_profile = backend.get_embedding_profile()
    dimension = dimension or active_profile.get("vector_dimension")
    if type(dimension) is not int or dimension <= 0:
        raise ExportError(
            "backend.get_embedding_profile() must provide a positive "
            "vector_dimension when exporting LTM"
        )
    embedding_info = {
        "provider":         active_profile["provider"],
        "model":            active_profile["model"],
        "vector_dimension": dimension,
    }

    (vector_dir / "collections.json").write_text(
        json.dumps({"name": "memories", "embedding_info": embedding_info}, indent=2),
        encoding="utf-8",
    )

    return record_count, embedding_info


def _build_manifest(
    backend: MemoryBackend,
    staging: Path,
    components: list[str],
    record_count: int,
    embedding_info: dict,
) -> None:
    """Write manifest.json into staging."""
    checksums: dict[str, str] = {}
    for member in ALLOWLIST:
        p = staging / member
        if p.exists():
            checksums[member] = _sha256_file(p)

    history_path = staging / "history" / "history.metta"
    history_bytes = history_path.stat().st_size if history_path.exists() else 0

    agent_meta = backend.get_archive_metadata()

    manifest = {
        "format_version":    ARCHIVE_FORMAT_VERSION,
        "omegaclaw_version": agent_meta.get("omegaclaw_version", ""),
        "chromadb_version":  agent_meta.get("chromadb_version", ""),
        "components":        components,
        "embedding_info":    embedding_info if "ltm" in components else {},
        "record_count":      record_count,
        "history_bytes":     history_bytes,
        "created_at":        _utc_now(),
        "checksums":         checksums,
    }

    (staging / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _verify_packed_archive(archive: Path, staging: Path) -> None:
    """Fully validate the final archive before publishing it."""
    unpack(archive, staging)
    try:
        manifest = validate_manifest(
            json.loads((staging / "manifest.json").read_text(encoding="utf-8"))
        )
        validate_checksums(staging, manifest)
        if "history" in manifest["components"]:
            validate_history(staging, manifest)
        if "ltm" in manifest["components"]:
            validate_collections(staging, manifest)
            validate_records(staging, manifest)
    except Exception as exc:
        raise ExportError(f"Packed archive validation failed: {exc}") from exc


def _archive_name() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"omegaclaw-memory-{timestamp}.tar.gz"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
