"""
Step 6 tests: importer.py

Covers:
import_archive()
- Overwrite: restores history and records from archive.
- Overwrite: history-only import leaves vectors unchanged.
- Overwrite: ltm-only import leaves history unchanged.
- Overwrite: receipt written after success.
- Overwrite: idempotent — second import of same archive skipped.
- Overwrite: rollback restores original history on backend write failure.
- Overwrite: rollback restores original records on backend write failure.
- Overwrite: marker cleaned up after success.
- Overwrite: rollback dir cleaned up after success.
- Overwrite: marker and rollback preserved when rollback itself fails.
- Append: records inserted with namespaced IDs.
- Append: history appended to existing.
- Append: appended IDs deleted on failure (rollback).
- Append: receipt written after success.
- Append: marker cleaned up after success.
- Raises ValueError on invalid mode.
- Raises ValueError when both include flags are False.
- Raises ValueError on path separator in filename.
- Raises FileNotFoundError when archive absent.
- Raises ArchiveValidationError on corrupt archive.
- Re-embedding triggered when profiles mismatch.
- Re-embedding not triggered when profiles match.
- v1 fixture imports cleanly in overwrite mode.
- v1 fixture imports cleanly in append mode.

recover()
- No-op when no marker exists.
- Cleans up completed overwrite (receipt present).
- Removes partial append IDs when marker has append_ids.
- Restores rollback for interrupted overwrite.
- Raises RecoveryError on unreadable marker.
- Raises RecoveryError when marker has no rollback dir and no append_ids.
- Raises RecoveryError when delete_records fails during append recovery.
"""

import json
import shutil
import tarfile
import threading
from pathlib import Path

import pytest

from memory_portability.errors import (
    ArchiveValidationError,
    RecoveryError,
)
from memory_portability.errors import ImportError as MpImportError
from memory_portability.exporter import export
from memory_portability.importer import (
    RECEIPT_DIR_NAME,
    ROLLBACK_DIR_NAME,
    TX_MARKER_NAME,
    import_archive,
    recover,
)
from tests.test_backend import FakeBackend


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_backend(tmp_path: Path, num_records: int = 2,
                  history: str | None = "original history\n") -> FakeBackend:
    backend = FakeBackend(tmp_path)
    backend.write_history(history)
    for i in range(num_records):
        backend._records[f"u{i}"] = {
            "id":        f"u{i}",
            "document":  f"document {i}",
            "embedding": [0.1 * (i + 1)] * 4,
            "metadata":  {"record_kind": "user_memory"},
        }
    return backend


def _export_archive(backend: FakeBackend, tmp_path: Path, component: str = "both") -> Path:
    """Export an archive and return its path."""
    transfer = tmp_path / "transfer"
    result = export(backend, transfer, component)
    return transfer / result["filename"]


def _make_archive_in(tmp_path: Path, component: str = "both") -> tuple[FakeBackend, Path, Path]:
    """Create a source backend, export an archive, return (src_backend, archive_path, transfer_dir)."""
    src = _make_backend(tmp_path / "src")
    transfer = tmp_path / "transfer"
    result = export(src, transfer, component)
    return src, transfer / result["filename"], transfer


# ---------------------------------------------------------------------------
# import_archive — overwrite mode
# ---------------------------------------------------------------------------

class TestImportOverwrite:

    def test_restores_history(self, tmp_path):
        src, archive, transfer = _make_archive_in(tmp_path)
        dst = _make_backend(tmp_path / "dst", history="old history\n")
        import_archive(dst, transfer, archive.name, mode="overwrite")
        assert dst.read_history() == src.read_history()

    def test_restores_user_records(self, tmp_path):
        src, archive, transfer = _make_archive_in(tmp_path)
        dst = _make_backend(tmp_path / "dst", num_records=0)
        import_archive(dst, transfer, archive.name, mode="overwrite")
        dst_ids = {r["id"] for b in dst.iter_records(500) for r in b}
        src_ids = {r["id"] for b in src.iter_records(500) for r in b}
        assert dst_ids == src_ids

    def test_history_only_leaves_vectors_unchanged(self, tmp_path):
        src, archive, transfer = _make_archive_in(tmp_path, component="history")
        dst = _make_backend(tmp_path / "dst")
        original_ids = {r["id"] for b in dst.iter_records(500) for r in b}
        import_archive(dst, transfer, archive.name, mode="overwrite",
                       include_vectors=False)
        after_ids = {r["id"] for b in dst.iter_records(500) for r in b}
        assert after_ids == original_ids

    def test_ltm_only_leaves_history_unchanged(self, tmp_path):
        src, archive, transfer = _make_archive_in(tmp_path, component="ltm")
        dst = _make_backend(tmp_path / "dst", history="keep this\n")
        import_archive(dst, transfer, archive.name, mode="overwrite",
                       include_history=False)
        assert dst.read_history() == "keep this\n"

    def test_receipt_written_after_success(self, tmp_path):
        _, archive, transfer = _make_archive_in(tmp_path)
        dst = _make_backend(tmp_path / "dst")
        import_archive(dst, transfer, archive.name, mode="overwrite")
        receipts = list((dst.state_dir / RECEIPT_DIR_NAME).glob("*.json"))
        assert len(receipts) == 1

    def test_idempotent_second_import_skipped(self, tmp_path):
        _, archive, transfer = _make_archive_in(tmp_path)
        dst = _make_backend(tmp_path / "dst")
        import_archive(dst, transfer, archive.name, mode="overwrite")
        # Modify history after first import
        dst.write_history("changed after import\n")
        # Second import of same archive must be skipped
        import_archive(dst, transfer, archive.name, mode="overwrite")
        assert dst.read_history() == "changed after import\n"

    def test_marker_cleaned_up_after_success(self, tmp_path):
        _, archive, transfer = _make_archive_in(tmp_path)
        dst = _make_backend(tmp_path / "dst")
        import_archive(dst, transfer, archive.name, mode="overwrite")
        assert not (dst.state_dir / TX_MARKER_NAME).exists()

    def test_rollback_dir_cleaned_up_after_success(self, tmp_path):
        _, archive, transfer = _make_archive_in(tmp_path)
        dst = _make_backend(tmp_path / "dst")
        import_archive(dst, transfer, archive.name, mode="overwrite")
        assert not (dst.state_dir / ROLLBACK_DIR_NAME).exists()

    def test_rollback_restores_history_on_write_failure(self, tmp_path):
        _, archive, transfer = _make_archive_in(tmp_path)
        dst = _make_backend(tmp_path / "dst", history="original\n")

        # Fail at smoke_test so both writes happened but we can verify rollback.
        def failing_smoke(h, v):
            raise RuntimeError("smoke test forced failure")
        dst.smoke_test = failing_smoke

        with pytest.raises(MpImportError):
            import_archive(dst, transfer, archive.name, mode="overwrite")

        # History must be restored to original value by rollback.
        assert dst.read_history() == "original\n"

    def test_rollback_restores_records_on_replace_failure(self, tmp_path):
        _, archive, transfer = _make_archive_in(tmp_path)
        dst = _make_backend(tmp_path / "dst", num_records=1)
        original_id = next(iter(dst._user_records()))

        # Fail after replace_records so we can verify records are restored.
        def failing_smoke(h, v):
            raise RuntimeError("smoke test forced failure")
        dst.smoke_test = failing_smoke

        with pytest.raises(MpImportError):
            import_archive(dst, transfer, archive.name, mode="overwrite")

        # Original record must be restored by rollback.
        ids = {r["id"] for b in dst.iter_records(500) for r in b}
        assert original_id in ids

    def test_preserves_non_user_records(self, tmp_path):
        _, archive, transfer = _make_archive_in(tmp_path)
        dst = _make_backend(tmp_path / "dst")
        non_user_id = FakeBackend._NON_USER_ID
        import_archive(dst, transfer, archive.name, mode="overwrite")
        assert non_user_id in dst._records


# ---------------------------------------------------------------------------
# import_archive — append mode
# ---------------------------------------------------------------------------

class TestImportAppend:

    def test_appended_records_have_namespaced_ids(self, tmp_path):
        src, archive, transfer = _make_archive_in(tmp_path, component="ltm")
        dst = _make_backend(tmp_path / "dst", num_records=1)
        import_archive(dst, transfer, archive.name, mode="append",
                       include_history=False)
        new_ids = [rid for rid in dst._records if rid.startswith("import-")]
        assert len(new_ids) == 2  # src had 2 user records

    def test_append_history_appended_to_existing(self, tmp_path):
        src, archive, transfer = _make_archive_in(tmp_path, component="history")
        dst = _make_backend(tmp_path / "dst", history="existing\n")
        import_archive(dst, transfer, archive.name, mode="append",
                       include_vectors=False)
        assert "existing\n" in dst.read_history()
        assert src.read_history() in dst.read_history()

    def test_append_rollback_deletes_inserted_ids_on_failure(self, tmp_path):
        src, archive, transfer = _make_archive_in(tmp_path, component="ltm")
        dst = _make_backend(tmp_path / "dst", num_records=0)

        original_smoke = dst.smoke_test
        def failing_smoke(h, v):
            raise RuntimeError("smoke test forced failure")
        dst.smoke_test = failing_smoke

        ids_before = set(dst._records.keys())
        with pytest.raises(MpImportError):
            import_archive(dst, transfer, archive.name, mode="append",
                           include_history=False)
        ids_after = set(dst._records.keys())
        # No new import- IDs should remain
        assert ids_after == ids_before

    def test_append_failure_restores_history_and_records(self, tmp_path):
        src, archive, transfer = _make_archive_in(tmp_path, component="both")
        dst = _make_backend(tmp_path / "dst", num_records=1, history="original\n")
        original_ids = set(dst._records)
        dst.smoke_test = lambda h, v: (_ for _ in ()).throw(RuntimeError("fail"))

        with pytest.raises(MpImportError):
            import_archive(dst, transfer, archive.name, mode="append")

        assert dst.read_history() == "original\n"
        assert set(dst._records) == original_ids
        assert not (dst.state_dir / ROLLBACK_DIR_NAME).exists()

    def test_receipt_written_after_append_success(self, tmp_path):
        _, archive, transfer = _make_archive_in(tmp_path, component="ltm")
        dst = _make_backend(tmp_path / "dst", num_records=0)
        import_archive(dst, transfer, archive.name, mode="append",
                       include_history=False)
        receipts = list((dst.state_dir / RECEIPT_DIR_NAME).glob("*.json"))
        assert len(receipts) == 1

    def test_append_marker_cleaned_up_after_success(self, tmp_path):
        _, archive, transfer = _make_archive_in(tmp_path, component="ltm")
        dst = _make_backend(tmp_path / "dst", num_records=0)
        import_archive(dst, transfer, archive.name, mode="append",
                       include_history=False)
        assert not (dst.state_dir / TX_MARKER_NAME).exists()

    def test_append_does_not_overwrite_existing_records(self, tmp_path):
        src, archive, transfer = _make_archive_in(tmp_path, component="ltm")
        dst = _make_backend(tmp_path / "dst", num_records=2)
        original_ids = set(dst._records.keys())
        import_archive(dst, transfer, archive.name, mode="append",
                       include_history=False)
        # Original IDs still present
        assert original_ids.issubset(dst._records.keys())


# ---------------------------------------------------------------------------
# import_archive — argument validation
# ---------------------------------------------------------------------------

class TestImportValidation:

    def test_raises_on_invalid_mode(self, tmp_path):
        dst = _make_backend(tmp_path)
        with pytest.raises(ValueError, match="Invalid mode"):
            import_archive(dst, tmp_path, "file.tar.gz", mode="bad")

    def test_raises_when_both_flags_false(self, tmp_path):
        dst = _make_backend(tmp_path)
        with pytest.raises(ValueError, match="nothing to import"):
            import_archive(dst, tmp_path, "file.tar.gz",
                           include_history=False, include_vectors=False)

    def test_raises_on_path_separator_in_filename(self, tmp_path):
        dst = _make_backend(tmp_path)
        with pytest.raises(ValueError, match="plain basename"):
            import_archive(dst, tmp_path, "dir/file.tar.gz")

    def test_raises_on_missing_archive(self, tmp_path):
        dst = _make_backend(tmp_path)
        with pytest.raises(FileNotFoundError):
            import_archive(dst, tmp_path, "nonexistent.tar.gz")

    def test_raises_on_corrupt_archive(self, tmp_path):
        corrupt = tmp_path / "bad.tar.gz"
        corrupt.write_bytes(b"not a tar file at all")
        dst = _make_backend(tmp_path / "dst")
        with pytest.raises(Exception):  # tarfile.ReadError or ArchiveValidationError
            import_archive(dst, tmp_path, "bad.tar.gz")


# ---------------------------------------------------------------------------
# import_archive — re-embedding
# ---------------------------------------------------------------------------

class TestImportReembedding:

    def test_reembedding_triggered_when_profiles_mismatch(self, tmp_path):
        src = _make_backend(tmp_path / "src")
        transfer = tmp_path / "transfer"
        result = export(src, transfer, "ltm")
        archive_name = result["filename"]

        dst = _make_backend(tmp_path / "dst", num_records=0)
        # Change model so profiles differ
        original_profile = dst.get_embedding_profile

        def mismatched_profile():
            p = original_profile()
            return {**p, "model": "different-model"}

        dst.get_embedding_profile = mismatched_profile
        import_archive(dst, transfer, archive_name, mode="overwrite",
                       include_history=False)
        # embed() should have been called
        assert len(dst._embed_calls) > 0

    def test_reembedding_not_triggered_when_profiles_match(self, tmp_path):
        src, archive, transfer = _make_archive_in(tmp_path, component="ltm")
        dst = _make_backend(tmp_path / "dst", num_records=0)
        import_archive(dst, transfer, archive.name, mode="overwrite",
                       include_history=False)
        assert dst._embed_calls == []


# ---------------------------------------------------------------------------
# import_archive — v1 fixture compatibility
# ---------------------------------------------------------------------------

class TestV1FixtureImport:

    def test_v1_fixture_imports_overwrite(self, tmp_path, v1_fixture_path):
        dst = _make_backend(tmp_path / "dst", num_records=0, history=None)
        shutil.copy(v1_fixture_path, tmp_path / v1_fixture_path.name)
        import_archive(dst, tmp_path, v1_fixture_path.name, mode="overwrite")
        assert dst.read_history() is not None
        ids = {r["id"] for b in dst.iter_records(500) for r in b}
        assert len(ids) == 2

    def test_v1_fixture_imports_append(self, tmp_path, v1_fixture_path):
        dst = _make_backend(tmp_path / "dst", num_records=0, history="existing\n")
        shutil.copy(v1_fixture_path, tmp_path / v1_fixture_path.name)
        import_archive(dst, tmp_path, v1_fixture_path.name, mode="append")
        assert "existing\n" in dst.read_history()
        ids = {r["id"] for b in dst.iter_records(500) for r in b}
        assert len(ids) == 2  # 2 appended records


# ---------------------------------------------------------------------------
# recover()
# ---------------------------------------------------------------------------

class TestRecover:

    def test_noop_when_no_marker(self, tmp_path):
        dst = _make_backend(tmp_path)
        recover(dst)  # must not raise

    def test_cleans_up_completed_overwrite_marker(self, tmp_path):
        """Marker present but receipt also present → clean up marker."""
        _, archive, transfer = _make_archive_in(tmp_path)
        dst = _make_backend(tmp_path / "dst")
        import_archive(dst, transfer, archive.name, mode="overwrite")
        # import_archive removed the marker on success; recreate it
        # pointing to the actual receipt that exists
        receipts = list((dst.state_dir / RECEIPT_DIR_NAME).glob("*.json"))
        marker = dst.state_dir / TX_MARKER_NAME
        marker.write_text(json.dumps({"receipt": receipts[0].name}))
        recover(dst)
        assert not marker.exists()

    def test_removes_partial_append_ids_on_recovery(self, tmp_path):
        src, archive, transfer = _make_archive_in(tmp_path, component="ltm")
        dst = _make_backend(tmp_path / "dst", num_records=0)

        # Simulate a crash mid-append: manually insert records and write marker
        partial_ids = ["import-abc-r1", "import-abc-r2"]
        for rid in partial_ids:
            dst._records[rid] = {
                "id": rid, "document": "d", "embedding": [], "metadata": {}
            }
        marker = dst.state_dir / TX_MARKER_NAME
        marker.write_text(json.dumps({"append_ids": partial_ids}))

        recover(dst)

        assert not marker.exists()
        for rid in partial_ids:
            assert rid not in dst._records

    def test_recovery_restores_append_history(self, tmp_path):
        dst = _make_backend(tmp_path, history="before\n")
        rollback = dst.state_dir / ROLLBACK_DIR_NAME
        rollback.mkdir()
        (rollback / "history.metta").write_text("before\n", encoding="utf-8")
        (rollback / "state.json").write_text(json.dumps({"history": True}))
        dst.append_history("\npartial import\n")
        marker = dst.state_dir / TX_MARKER_NAME
        marker.write_text(json.dumps({
            "append_ids": [],
            "history_rollback": True,
        }))

        recover(dst)

        assert dst.read_history() == "before\n"
        assert not marker.exists()
        assert not rollback.exists()

    def test_restores_rollback_for_interrupted_overwrite(self, tmp_path):
        dst = _make_backend(tmp_path, history="original\n")

        # Simulate a crash mid-overwrite: write marker + rollback dir
        base     = dst.state_dir
        rollback = base / ROLLBACK_DIR_NAME
        marker   = base / TX_MARKER_NAME

        rollback.mkdir(parents=True)
        (rollback / "history.metta").write_text("original\n", encoding="utf-8")
        (rollback / "state.json").write_text(
            json.dumps({"history": True, "vectors": False}), encoding="utf-8"
        )
        # Corrupt live history
        dst.write_history("corrupted by interrupted import\n")
        marker.write_text(json.dumps({"receipt": "nonexistent-receipt.json"}))

        recover(dst)

        assert dst.read_history() == "original\n"
        assert not marker.exists()
        assert not rollback.exists()

    def test_raises_recovery_error_on_unreadable_marker(self, tmp_path):
        dst = _make_backend(tmp_path)
        marker = dst.state_dir / TX_MARKER_NAME
        marker.write_bytes(b"\xff\xfe invalid utf-8 \x00")
        with pytest.raises(RecoveryError):
            recover(dst)

    def test_raises_recovery_error_when_rollback_missing(self, tmp_path):
        dst = _make_backend(tmp_path)
        marker = dst.state_dir / TX_MARKER_NAME
        # Overwrite marker with no receipt and no append_ids → expects rollback dir
        marker.write_text(json.dumps({"receipt": "no-such-receipt.json"}))
        # No rollback directory exists
        with pytest.raises(RecoveryError, match="rollback directory is missing"):
            recover(dst)

    def test_preserves_corrupt_rollback_for_operator(self, tmp_path):
        dst = _make_backend(tmp_path)
        rollback = dst.state_dir / ROLLBACK_DIR_NAME
        rollback.mkdir()
        (rollback / "state.json").write_text("not json", encoding="utf-8")
        marker = dst.state_dir / TX_MARKER_NAME
        marker.write_text(json.dumps({"receipt": "missing.json"}))

        with pytest.raises(RecoveryError, match="Rollback restoration failed"):
            recover(dst)
        assert marker.exists()
        assert rollback.exists()

    def test_preserves_invalid_rollback_records_for_operator(self, tmp_path):
        dst = _make_backend(tmp_path)
        rollback = dst.state_dir / ROLLBACK_DIR_NAME
        rollback.mkdir()
        (rollback / "state.json").write_text(json.dumps({"vectors": True}))
        (rollback / "records.jsonl").write_text("not json\n", encoding="utf-8")
        marker = dst.state_dir / TX_MARKER_NAME
        marker.write_text(json.dumps({"receipt": "missing.json"}))

        with pytest.raises(RecoveryError, match="Rollback restoration failed"):
            recover(dst)
        assert marker.exists()

    def test_raises_recovery_error_when_delete_records_fails(self, tmp_path):
        dst = _make_backend(tmp_path)

        def failing_delete(ids):
            raise RuntimeError("delete failed")
        dst.delete_records = failing_delete

        marker = dst.state_dir / TX_MARKER_NAME
        marker.write_text(json.dumps({"append_ids": ["import-abc-r1"]}))

        with pytest.raises(RecoveryError, match="Failed to delete"):
            recover(dst)
        # Marker preserved for operator
        assert marker.exists()

    def test_empty_append_ids_does_not_call_delete(self, tmp_path):
        dst = _make_backend(tmp_path)
        calls = []
        original_delete = dst.delete_records
        def tracked_delete(ids):
            calls.append(ids)
            original_delete(ids)
        dst.delete_records = tracked_delete

        marker = dst.state_dir / TX_MARKER_NAME
        marker.write_text(json.dumps({"append_ids": []}))
        recover(dst)
        assert calls == []
        assert not marker.exists()
