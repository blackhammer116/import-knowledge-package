"""
Public API tests for transfer.py.

MemoryTransfer class
- Can be instantiated with a valid backend and transfer_dir.
- Raises TypeError when backend is not a MemoryBackend instance.
- transfer_dir is coerced to Path.
- export() runs synchronously and returns result dict.
- start_export_job() returns job ID and eventually "done".
- get_export_status() returns correct status.
- import_archive() restores archive correctly.
- recover() is a no-op when no marker exists.
- All public methods delegate to the correct underlying module functions.
"""

import time
from pathlib import Path

import pytest

from memory_portability import MemoryTransfer, MemoryBackend
from memory_portability.exporter import export
from tests.test_backend import FakeBackend


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_backend(tmp_path: Path, num_records: int = 2,
                  history: str = "history\n") -> FakeBackend:
    backend = FakeBackend(tmp_path)
    backend.write_history(history)
    for i in range(num_records):
        backend._records[f"u{i}"] = {
            "id":        f"u{i}",
            "document":  f"doc {i}",
            "embedding": [0.1 * (i + 1)] * 4,
            "metadata":  {"record_kind": "user_memory"},
        }
    return backend


def _export_archive(backend: FakeBackend, transfer: Path,
                    component: str = "both") -> str:
    result = export(backend, transfer, component)
    return result["filename"]


def _wait_done(transfer: MemoryTransfer, job_id: str, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        s = transfer.get_export_status(job_id)
        if s["status"] != "running":
            return s
        time.sleep(0.05)
    raise TimeoutError(f"Job {job_id} did not complete in {timeout}s")


# ---------------------------------------------------------------------------
# MemoryTransfer — construction
# ---------------------------------------------------------------------------

class TestMemoryTransferConstruction:

    def test_instantiates_with_valid_backend(self, tmp_path):
        backend = _make_backend(tmp_path)
        transfer = MemoryTransfer(backend=backend, transfer_dir=tmp_path / "t")
        assert transfer is not None

    def test_raises_type_error_on_invalid_backend(self, tmp_path):
        with pytest.raises(TypeError, match="MemoryBackend"):
            MemoryTransfer(backend="not a backend", transfer_dir=tmp_path)

    def test_transfer_dir_coerced_to_path(self, tmp_path):
        backend = _make_backend(tmp_path)
        transfer = MemoryTransfer(backend=backend, transfer_dir=str(tmp_path / "t"))
        assert isinstance(transfer._transfer_dir, Path)


# ---------------------------------------------------------------------------
# MemoryTransfer — export (synchronous)
# ---------------------------------------------------------------------------

class TestMemoryTransferExport:

    def test_export_returns_result_dict(self, tmp_path):
        backend  = _make_backend(tmp_path)
        transfer = MemoryTransfer(backend=backend, transfer_dir=tmp_path / "t")
        result   = transfer.export("both")
        for key in ("filename", "size", "checksum", "record_count", "components"):
            assert key in result

    def test_export_produces_archive_in_transfer_dir(self, tmp_path):
        backend  = _make_backend(tmp_path)
        transfer_dir = tmp_path / "t"
        transfer = MemoryTransfer(backend=backend, transfer_dir=transfer_dir)
        result   = transfer.export("history")
        assert (transfer_dir / result["filename"]).exists()

    def test_export_raises_value_error_on_bad_component(self, tmp_path):
        backend  = _make_backend(tmp_path)
        transfer = MemoryTransfer(backend=backend, transfer_dir=tmp_path / "t")
        with pytest.raises(ValueError, match="Invalid component"):
            transfer.export("invalid")


# ---------------------------------------------------------------------------
# MemoryTransfer — async export
# ---------------------------------------------------------------------------

class TestMemoryTransferAsyncExport:

    def test_start_export_job_returns_string(self, tmp_path):
        backend  = _make_backend(tmp_path)
        transfer = MemoryTransfer(backend=backend, transfer_dir=tmp_path / "t")
        job_id   = transfer.start_export_job("history")
        assert isinstance(job_id, str) and job_id

    def test_job_completes_with_done_status(self, tmp_path):
        backend  = _make_backend(tmp_path)
        transfer = MemoryTransfer(backend=backend, transfer_dir=tmp_path / "t")
        job_id   = transfer.start_export_job("history")
        status   = _wait_done(transfer, job_id)
        assert status["status"] == "done"

    def test_get_export_status_unknown_for_bad_id(self, tmp_path):
        backend  = _make_backend(tmp_path)
        transfer = MemoryTransfer(backend=backend, transfer_dir=tmp_path / "t")
        assert transfer.get_export_status("no-such-id")["status"] == "unknown"

    def test_on_complete_callback_called(self, tmp_path):
        backend  = _make_backend(tmp_path)
        transfer = MemoryTransfer(backend=backend, transfer_dir=tmp_path / "t")
        results  = []
        job_id   = transfer.start_export_job("history", on_complete=lambda jid, s: results.append(s))
        _wait_done(transfer, job_id)
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and not results:
            time.sleep(0.05)
        assert results[0]["status"] == "done"


# ---------------------------------------------------------------------------
# MemoryTransfer — import_archive
# ---------------------------------------------------------------------------

class TestMemoryTransferImport:

    def test_import_archive_restores_records(self, tmp_path):
        src      = _make_backend(tmp_path / "src")
        transfer_dir = tmp_path / "t"
        filename = _export_archive(src, transfer_dir, "ltm")

        dst      = _make_backend(tmp_path / "dst", num_records=0)
        mt       = MemoryTransfer(backend=dst, transfer_dir=transfer_dir)
        mt.import_archive(filename, mode="overwrite", include_history=False)

        dst_ids = {r["id"] for b in dst.iter_records(500) for r in b}
        src_ids = {r["id"] for b in src.iter_records(500) for r in b}
        assert dst_ids == src_ids

    def test_import_archive_raises_on_missing_file(self, tmp_path):
        backend  = _make_backend(tmp_path)
        transfer = MemoryTransfer(backend=backend, transfer_dir=tmp_path / "t")
        with pytest.raises(FileNotFoundError):
            transfer.import_archive("nonexistent.tar.gz")

    def test_import_archive_raises_on_invalid_mode(self, tmp_path):
        backend  = _make_backend(tmp_path)
        transfer = MemoryTransfer(backend=backend, transfer_dir=tmp_path)
        with pytest.raises(ValueError, match="Invalid mode"):
            transfer.import_archive("x.tar.gz", mode="bad")


# ---------------------------------------------------------------------------
# MemoryTransfer — recover
# ---------------------------------------------------------------------------

class TestMemoryTransferRecover:

    def test_recover_noop_when_no_marker(self, tmp_path):
        backend  = _make_backend(tmp_path)
        transfer = MemoryTransfer(backend=backend, transfer_dir=tmp_path / "t")
        transfer.recover()  # must not raise

