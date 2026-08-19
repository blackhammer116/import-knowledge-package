import tarfile
import time

import pytest

from memory_portability.errors import ImportError as MemoryImportError
from memory_portability.importer import import_archive
from memory_portability.transfer import MemoryTransfer

from conftest import FakeBackend, record, user_records
def export_archive(tmp_path, component="both"):
    source = FakeBackend(tmp_path / "source")
    source.upsert_records([record("source-1", "portable memory")])
    transfer_dir = tmp_path / "transfer"
    result = MemoryTransfer(source, transfer_dir).export(component)
    return source, transfer_dir, result
def test_round_trip_exports_expected_archive_and_restores_both_components(tmp_path):
    source, transfer_dir, result = export_archive(tmp_path)
    with tarfile.open(transfer_dir / result["filename"], "r:gz") as archive:
        assert set(archive.getnames()) == {
            "manifest.json",
            "history/history.metta",
            "vector/collections.json",
            "vector/records.jsonl",
        }
    target = FakeBackend(tmp_path / "target", history="old\n")
    MemoryTransfer(target, transfer_dir).import_archive(result["filename"])
    assert target.read_history() == source.read_history()
    assert user_records(target) == user_records(source)
def test_history_import_leaves_vectors_untouched(tmp_path):
    _, transfer_dir, result = export_archive(tmp_path, "history")
    target = FakeBackend(tmp_path / "target")
    target.upsert_records([record("keep")])
    import_archive(target, transfer_dir, result["filename"], include_vectors=False)
    assert [item["id"] for item in user_records(target)] == ["keep"]
def test_receipt_prevents_repeat_import(tmp_path):
    _, transfer_dir, result = export_archive(tmp_path)
    target = FakeBackend(tmp_path / "target")
    transfer = MemoryTransfer(target, transfer_dir)
    transfer.import_archive(result["filename"])
    target.write_history("changed after import\n")
    transfer.import_archive(result["filename"])
    assert target.read_history() == "changed after import\n"
def test_overwrite_failure_restores_absent_history_and_records(tmp_path):
    _, transfer_dir, result = export_archive(tmp_path)
    target = FakeBackend(tmp_path / "target", history=None)
    target.upsert_records([record("keep")])
    target.fail_smoke = True
    with pytest.raises(MemoryImportError):
        import_archive(target, transfer_dir, result["filename"])
    assert target.read_history() is None
    assert [item["id"] for item in user_records(target)] == ["keep"]
def test_overwrite_failure_removes_new_vector_store(tmp_path):
    _, transfer_dir, result = export_archive(tmp_path)
    target = FakeBackend(tmp_path / "target", history=None)
    target.fail_smoke = True
    with pytest.raises(MemoryImportError):
        import_archive(target, transfer_dir, result["filename"])
    assert target.vector_store_exists() is False
def test_append_failure_removes_partial_records(tmp_path):
    _, transfer_dir, result = export_archive(tmp_path, "ltm")
    target = FakeBackend(tmp_path / "target")
    target.upsert_records([record("keep")])
    target.fail_smoke = True
    with pytest.raises(MemoryImportError):
        import_archive(target, transfer_dir, result["filename"], mode="append", include_history=False)
    assert [item["id"] for item in user_records(target)] == ["keep"]
def test_mismatched_embedding_profile_reembeds_before_import(tmp_path):
    _, transfer_dir, result = export_archive(tmp_path, "ltm")
    target = FakeBackend(tmp_path / "target")
    target.profile = {"provider": "OpenAI", "model": "model-b", "vector_dimension": 2}
    import_archive(target, transfer_dir, result["filename"], include_history=False)
    assert target.embed_calls == [["portable memory"]]
    assert user_records(target)[0]["embedding"] == [0.5, 0.5]
def test_async_export_reaches_done_status(tmp_path):
    transfer = MemoryTransfer(FakeBackend(tmp_path), tmp_path / "transfer")
    job_id = transfer.start_export_job("history")
    for _ in range(50):
        status = transfer.get_export_status(job_id)
        if status["status"] != "running":
            break
        time.sleep(0.01)
    assert status["status"] == "done"
