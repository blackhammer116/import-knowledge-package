import io
import tarfile

import pytest

from import_knowledge.memory_portability.archive import unpack
from import_knowledge.memory_portability.errors import (
    ArchiveValidationError,
    MemoryImportError,
)
from import_knowledge.memory_portability.storage import MemoryStore
from import_knowledge.memory_portability.transfer import MemoryTransfer


PROFILE = {"provider": "Local", "model": "test-model", "vector_dimension": 2}


def make_store(tmp_path, name, embed_batch=None, store_class=MemoryStore):
    return store_class(
        memory_dir=tmp_path / name / "memory",
        chroma_path=tmp_path / name / "chroma",
        embed_batch=embed_batch,
        embedding_profile=PROFILE,
    )


def record(record_id, document, embedding=None, metadata=None):
    return {
        "id": record_id,
        "document": document,
        "embedding": embedding or [0.25, 0.75],
        "metadata": metadata or {"time": "2026-08-20 10:00:00"},
    }


def user_records(store):
    return [item for batch in store.iter_user_records() for item in batch]


def test_round_trip_restores_user_memory_and_preserves_knowledge(tmp_path):
    source = make_store(tmp_path, "source")
    source.write_history("source history\n")
    source.upsert_records([record("source-memory", "remember me")])

    transfer = MemoryTransfer(tmp_path / "transfer", source)
    exported = transfer.export("both", filename="memory.tar.gz")

    with tarfile.open(tmp_path / "transfer" / exported["filename"], "r:gz") as archive:
        assert set(archive.getnames()) == {
            "manifest.json",
            "history/history.metta",
            "vector/collections.json",
            "vector/records.jsonl",
        }

    target = make_store(tmp_path, "target")
    target.write_history("old history\n")
    target.upsert_records(
        [
            record("old-memory", "replace me"),
            record(
                "knowledge-prior",
                "keep me",
                metadata={"type": "chunk", "source": "knowledge.md"},
            ),
        ]
    )

    result = MemoryTransfer(tmp_path / "transfer", target).import_archive(
        "memory.tar.gz", mode="overwrite"
    )

    assert result["status"] == "imported"
    assert target.read_history() == "source history\n"
    assert [item["id"] for item in user_records(target)] == ["source-memory"]
    assert target.collection().get(ids=["knowledge-prior"])["ids"] == ["knowledge-prior"]


def test_export_without_embeddings_reembeds_on_import(tmp_path):
    source = make_store(tmp_path, "source")
    source.upsert_records([record("source-memory", "portable text")])
    transfer_dir = tmp_path / "transfer"
    MemoryTransfer(transfer_dir, source).export(
        "ltm", include_embeddings=False, filename="without-embeddings.tar.gz"
    )

    calls = []

    def embed_batch(documents):
        calls.append(documents)
        return [[0.5, 0.5] for _ in documents]

    target = make_store(tmp_path, "target", embed_batch=embed_batch)
    result = MemoryTransfer(transfer_dir, target).import_archive(
        "without-embeddings.tar.gz", include_history=False
    )

    assert result["reembedded"] is True
    assert calls == [["portable text"]]
    assert user_records(target)[0]["embedding"] == pytest.approx([0.5, 0.5])


def test_append_namespaces_ids_and_preserves_existing_records(tmp_path):
    source = make_store(tmp_path, "source")
    source.write_history("imported history\n")
    source.upsert_records([record("shared-id", "imported")])
    transfer_dir = tmp_path / "transfer"
    MemoryTransfer(transfer_dir, source).export("both", filename="append.tar.gz")

    target = make_store(tmp_path, "target")
    target.write_history("existing history\n")
    target.upsert_records([record("shared-id", "existing")])
    MemoryTransfer(transfer_dir, target).import_archive("append.tar.gz", mode="append")

    records = user_records(target)
    assert len(records) == 2
    assert {item["document"] for item in records} == {"existing", "imported"}
    assert any(item["id"].startswith("import-") for item in records)
    assert target.read_history() == "existing history\nimported history\n"


def test_unpack_rejects_unsafe_member(tmp_path):
    archive_path = tmp_path / "unsafe.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        info = tarfile.TarInfo("../history.metta")
        payload = b"private"
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))

    with pytest.raises(ArchiveValidationError, match="Unexpected archive member"):
        unpack(archive_path, tmp_path / "unpacked")


class FailOnceStore(MemoryStore):
    fail_next_smoke_test = True

    def smoke_test(self, history, vectors):
        if self.fail_next_smoke_test:
            self.fail_next_smoke_test = False
            raise RuntimeError("simulated post-import failure")
        super().smoke_test(history, vectors)


class CrashOnceStore(MemoryStore):
    crash_next_smoke_test = True

    def smoke_test(self, history, vectors):
        if self.crash_next_smoke_test:
            self.crash_next_smoke_test = False
            raise KeyboardInterrupt("simulated process interruption")
        super().smoke_test(history, vectors)


def test_failed_overwrite_restores_previous_memory(tmp_path):
    source = make_store(tmp_path, "source")
    source.write_history("source history\n")
    source.upsert_records([record("source-memory", "source")])
    transfer_dir = tmp_path / "transfer"
    MemoryTransfer(transfer_dir, source).export("both", filename="rollback.tar.gz")

    target = make_store(tmp_path, "target", store_class=FailOnceStore)
    target.write_history("target history\n")
    target.upsert_records([record("target-memory", "target")])

    with pytest.raises(MemoryImportError, match="rolled back"):
        MemoryTransfer(transfer_dir, target).import_archive("rollback.tar.gz")

    assert target.read_history() == "target history\n"
    assert [item["id"] for item in user_records(target)] == ["target-memory"]


def test_recover_rolls_back_an_interrupted_overwrite(tmp_path):
    source = make_store(tmp_path, "source")
    source.write_history("source history\n")
    source.upsert_records([record("source-memory", "source")])
    transfer_dir = tmp_path / "transfer"
    MemoryTransfer(transfer_dir, source).export("both", filename="recovery.tar.gz")

    target = make_store(tmp_path, "target", store_class=CrashOnceStore)
    target.write_history("target history\n")
    target.upsert_records([record("target-memory", "target")])
    transfer = MemoryTransfer(transfer_dir, target)

    with pytest.raises(KeyboardInterrupt):
        transfer.import_archive("recovery.tar.gz")

    assert transfer.recover() == {"status": "rolled-back"}
    assert target.read_history() == "target history\n"
    assert [item["id"] for item in user_records(target)] == ["target-memory"]
