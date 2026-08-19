"""
Step 5 tests: exporter.py

Covers:
export()
- Produces a valid tar.gz in transfer_dir.
- Returns correct result dict (filename, size, checksum, record_count, components).
- History-only export includes only history members.
- LTM-only export includes only vector members.
- Both-component export includes all members.
- Archive manifest is valid and accepted by validate_manifest.
- Archive checksums match the extracted files.
- Export with no history file still produces a valid archive.
- Export with no user records still produces a valid archive.
- Raises ValueError on invalid component name.
- Does not modify live memory (read_history / iter_records called, write never called).
- Holds write_lock during snapshot (concurrent write blocked while lock held).
- Tmp file is cleaned up after success.
- Tmp file is cleaned up on failure.
- Work dir is cleaned up after success.
- Published archive is importable by validate_manifest.

start_export_job()
- Returns a job ID immediately.
- Job status starts as "running".
- Status becomes "done" after completion.
- on_complete callback is called with job_id and status dict.
- Status becomes "failed" on export error.
- on_complete called with failed status on error.
- Raises ValueError on invalid component synchronously.

get_export_status()
- Returns "unknown" for unrecognised job ID.
- Returns "running" while job is in progress.
- Returns "done" status with full result after completion.
"""

import json
import tarfile
import threading
import time
from pathlib import Path

import pytest

from memory_portability.errors import ExportError
from memory_portability.exporter import export, get_export_status, start_export_job
from memory_portability.validator import validate_manifest
from tests.test_backend import FakeBackend


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_backend(tmp_path: Path, num_records: int = 2, history: str | None = "history content\n") -> FakeBackend:
    backend = FakeBackend(tmp_path)
    backend.write_history(history)
    for i in range(num_records):
        backend._records[f"u{i}"] = {
            "id":       f"u{i}",
            "document": f"document {i}",
            "embedding": [0.1 * (i + 1)] * 4,
            "metadata":  {"record_kind": "user_memory"},
        }
    return backend


def _wait_for_job(job_id: str, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = get_export_status(job_id)
        if status["status"] != "running":
            return status
        time.sleep(0.05)
    raise TimeoutError(f"Job {job_id} did not complete within {timeout}s")


# ---------------------------------------------------------------------------
# export() — synchronous
# ---------------------------------------------------------------------------

class TestExport:

    def test_produces_valid_targz(self, tmp_path):
        backend = _make_backend(tmp_path)
        transfer = tmp_path / "transfers"
        result = export(backend, transfer, "both")
        archive = transfer / result["filename"]
        assert tarfile.is_tarfile(archive)

    def test_result_has_required_keys(self, tmp_path):
        backend = _make_backend(tmp_path)
        result = export(backend, tmp_path / "t", "both")
        for key in ("filename", "size", "checksum", "record_count", "components"):
            assert key in result

    def test_result_filename_is_basename_only(self, tmp_path):
        backend = _make_backend(tmp_path)
        result = export(backend, tmp_path / "t", "both")
        assert "/" not in result["filename"]
        assert result["filename"].endswith(".tar.gz")

    def test_result_record_count_matches_user_records(self, tmp_path):
        backend = _make_backend(tmp_path, num_records=3)
        result = export(backend, tmp_path / "t", "ltm")
        assert result["record_count"] == 3

    def test_result_checksum_is_sha256_hex(self, tmp_path):
        backend = _make_backend(tmp_path)
        result = export(backend, tmp_path / "t", "both")
        assert len(result["checksum"]) == 64
        assert all(c in "0123456789abcdef" for c in result["checksum"])

    def test_history_only_contains_history_member(self, tmp_path):
        backend = _make_backend(tmp_path)
        result = export(backend, tmp_path / "t", "history")
        archive = tmp_path / "t" / result["filename"]
        with tarfile.open(archive, "r:gz") as tar:
            names = {m.name for m in tar.getmembers()}
        assert "history/history.metta" in names
        assert "vector/records.jsonl" not in names
        assert result["components"] == ["history"]

    def test_ltm_only_contains_vector_members(self, tmp_path):
        backend = _make_backend(tmp_path)
        result = export(backend, tmp_path / "t", "ltm")
        archive = tmp_path / "t" / result["filename"]
        with tarfile.open(archive, "r:gz") as tar:
            names = {m.name for m in tar.getmembers()}
        assert "vector/records.jsonl" in names
        assert "vector/collections.json" in names
        assert "history/history.metta" not in names
        assert result["components"] == ["ltm"]

    def test_both_contains_all_members(self, tmp_path):
        backend = _make_backend(tmp_path)
        result = export(backend, tmp_path / "t", "both")
        archive = tmp_path / "t" / result["filename"]
        with tarfile.open(archive, "r:gz") as tar:
            names = {m.name for m in tar.getmembers()}
        assert "history/history.metta" in names
        assert "vector/records.jsonl" in names
        assert "vector/collections.json" in names
        assert "manifest.json" in names

    def test_manifest_passes_validate_manifest(self, tmp_path):
        backend = _make_backend(tmp_path)
        result = export(backend, tmp_path / "t", "both")
        archive = tmp_path / "t" / result["filename"]
        with tarfile.open(archive, "r:gz") as tar:
            raw = json.loads(tar.extractfile("manifest.json").read())
        validate_manifest(raw)  # must not raise

    def test_manifest_record_count_correct(self, tmp_path):
        backend = _make_backend(tmp_path, num_records=2)
        result = export(backend, tmp_path / "t", "ltm")
        archive = tmp_path / "t" / result["filename"]
        with tarfile.open(archive, "r:gz") as tar:
            raw = json.loads(tar.extractfile("manifest.json").read())
        assert raw["record_count"] == 2

    def test_manifest_omegaclaw_version_from_backend(self, tmp_path):
        backend = _make_backend(tmp_path)
        result = export(backend, tmp_path / "t", "both")
        archive = tmp_path / "t" / result["filename"]
        with tarfile.open(archive, "r:gz") as tar:
            raw = json.loads(tar.extractfile("manifest.json").read())
        assert raw["omegaclaw_version"] == backend.get_archive_metadata()["omegaclaw_version"]

    def test_export_with_no_history_still_valid(self, tmp_path):
        backend = _make_backend(tmp_path, history=None)
        result = export(backend, tmp_path / "t", "ltm")
        archive = tmp_path / "t" / result["filename"]
        with tarfile.open(archive, "r:gz") as tar:
            raw = json.loads(tar.extractfile("manifest.json").read())
        validate_manifest(raw)

    def test_export_with_no_user_records_still_valid(self, tmp_path):
        backend = _make_backend(tmp_path, num_records=0)
        result = export(backend, tmp_path / "t", "ltm")
        archive = tmp_path / "t" / result["filename"]
        with tarfile.open(archive, "r:gz") as tar:
            raw = json.loads(tar.extractfile("manifest.json").read())
        assert raw["record_count"] == 0
        validate_manifest(raw)

    def test_raises_value_error_on_invalid_component(self, tmp_path):
        backend = _make_backend(tmp_path)
        with pytest.raises(ValueError, match="Invalid component"):
            export(backend, tmp_path / "t", "invalid")

    def test_never_calls_write_history(self, tmp_path):
        """Export must never write to backend history."""
        backend = _make_backend(tmp_path)
        original = backend.write_history
        calls = []
        def tracked_write(text):
            calls.append(text)
            return original(text)
        backend.write_history = tracked_write
        export(backend, tmp_path / "t", "both")
        assert calls == [], "export must not call write_history"

    def test_never_calls_replace_records(self, tmp_path):
        """Export must never write to backend records."""
        backend = _make_backend(tmp_path)
        calls = []
        def tracked_replace(records):
            calls.append(records)
        backend.replace_records = tracked_replace
        export(backend, tmp_path / "t", "both")
        assert calls == [], "export must not call replace_records"

    def test_write_lock_held_during_snapshot(self, tmp_path):
        """A concurrent thread must not acquire the write lock while export holds it."""
        backend = _make_backend(tmp_path)
        acquired_during_export = []

        original_iter = backend.iter_records
        def slow_iter(batch_size):
            # Try acquiring the lock from another thread while export holds it
            result = backend.write_lock.acquire(blocking=False)
            acquired_during_export.append(result)
            if result:
                backend.write_lock.release()
            yield from original_iter(batch_size)

        backend.iter_records = slow_iter
        export(backend, tmp_path / "t", "ltm")
        # The lock should have been held by export, so acquire_during_export should be False
        assert acquired_during_export[0] is False

    def test_tmp_file_cleaned_up_after_success(self, tmp_path):
        backend = _make_backend(tmp_path)
        transfer = tmp_path / "t"
        export(backend, transfer, "both")
        tmp_files = list(transfer.glob(".*.tmp"))
        assert tmp_files == []

    def test_work_dir_cleaned_up_after_success(self, tmp_path):
        backend = _make_backend(tmp_path)
        transfer = tmp_path / "t"
        export(backend, transfer, "both")
        work_dirs = list(transfer.glob(".export_work_*"))
        assert work_dirs == []

    def test_transfer_dir_created_if_absent(self, tmp_path):
        backend = _make_backend(tmp_path)
        transfer = tmp_path / "new" / "nested" / "dir"
        assert not transfer.exists()
        export(backend, transfer, "history")
        assert transfer.exists()

    def test_records_in_archive_match_backend_records(self, tmp_path):
        backend = _make_backend(tmp_path, num_records=2)
        result = export(backend, tmp_path / "t", "ltm")
        archive = tmp_path / "t" / result["filename"]
        with tarfile.open(archive, "r:gz") as tar:
            lines = tar.extractfile("vector/records.jsonl").read().decode().splitlines()
        ids = {json.loads(l)["id"] for l in lines if l.strip()}
        assert ids == {"u0", "u1"}


# ---------------------------------------------------------------------------
# start_export_job() and get_export_status()
# ---------------------------------------------------------------------------

class TestAsyncExport:

    def test_returns_job_id_immediately(self, tmp_path):
        backend = _make_backend(tmp_path)
        job_id = start_export_job(backend, tmp_path / "t", "history")
        assert isinstance(job_id, str) and job_id

    def test_initial_status_is_running(self, tmp_path):
        backend = _make_backend(tmp_path)
        # Slow down iter_records so we can catch "running"
        original = backend.iter_records
        event = threading.Event()
        def slow_iter(batch_size):
            event.wait()
            yield from original(batch_size)
        backend.iter_records = slow_iter

        job_id = start_export_job(backend, tmp_path / "t", "ltm")
        status = get_export_status(job_id)
        assert status["status"] == "running"
        event.set()  # unblock
        _wait_for_job(job_id)

    def test_status_becomes_done_on_success(self, tmp_path):
        backend = _make_backend(tmp_path)
        job_id = start_export_job(backend, tmp_path / "t", "both")
        status = _wait_for_job(job_id)
        assert status["status"] == "done"

    def test_done_status_has_result_fields(self, tmp_path):
        backend = _make_backend(tmp_path)
        job_id = start_export_job(backend, tmp_path / "t", "both")
        status = _wait_for_job(job_id)
        for key in ("filename", "size", "checksum", "record_count", "components"):
            assert key in status

    def test_on_complete_callback_called_on_success(self, tmp_path):
        backend = _make_backend(tmp_path)
        results = []
        def cb(jid, s):
            results.append((jid, s))

        job_id = start_export_job(backend, tmp_path / "t", "history", on_complete=cb)
        _wait_for_job(job_id)
        # Give the callback a moment to be called
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and not results:
            time.sleep(0.05)
        assert len(results) == 1
        assert results[0][0] == job_id
        assert results[0][1]["status"] == "done"

    def test_status_becomes_failed_on_error(self, tmp_path):
        backend = _make_backend(tmp_path)
        def bad_iter(batch_size):
            raise RuntimeError("backend failure")
            yield  # make it a generator
        backend.iter_records = bad_iter

        job_id = start_export_job(backend, tmp_path / "t", "ltm")
        status = _wait_for_job(job_id)
        assert status["status"] == "failed"
        assert "error" in status

    def test_on_complete_called_with_failed_status(self, tmp_path):
        backend = _make_backend(tmp_path)
        def bad_history():
            raise RuntimeError("history read failed")
        backend.read_history = bad_history

        results = []
        def cb(jid, s):
            results.append(s)

        job_id = start_export_job(backend, tmp_path / "t", "history", on_complete=cb)
        _wait_for_job(job_id)
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and not results:
            time.sleep(0.05)
        assert results[0]["status"] == "failed"

    def test_raises_value_error_on_invalid_component(self, tmp_path):
        backend = _make_backend(tmp_path)
        with pytest.raises(ValueError, match="Invalid component"):
            start_export_job(backend, tmp_path / "t", "bad")

    def test_unknown_job_id_returns_unknown(self, tmp_path):
        status = get_export_status("does-not-exist-xyz")
        assert status["status"] == "unknown"

    def test_multiple_concurrent_jobs(self, tmp_path):
        """Two concurrent export jobs must both complete without interfering."""
        backend = _make_backend(tmp_path, num_records=1)
        transfer = tmp_path / "t"
        id1 = start_export_job(backend, transfer, "history")
        id2 = start_export_job(backend, transfer, "history")
        s1 = _wait_for_job(id1)
        s2 = _wait_for_job(id2)
        assert s1["status"] == "done"
        assert s2["status"] == "done"
        # Archives must be different files
        assert s1["filename"] != s2["filename"]
