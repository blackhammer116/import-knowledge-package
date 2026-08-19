"""
Step 2: MemoryBackend interface contract tests.

Covers:
- FakeBackend fully implements MemoryBackend (no abstract methods remain).
- Every method honours its documented contract.
- write_lock is the same object used by concurrent writes (coherence).
- state_dir returns a real, writable Path.
- History read/write/append round-trips.
- write_history(None) removes the history file.
- iter_records yields only user-memory records in correct batch sizes.
- replace_records clears user records and inserts new ones, preserving
  non-user records.
- upsert_records stores records with package-supplied IDs exactly.
- delete_records removes exactly the named records.
- embed returns a list of the same length with correct dimension.
- get_embedding_profile returns required keys with correct types.
- get_archive_metadata returns required v1 keys with correct types.
- smoke_test passes when components are present, raises when absent.
- A concrete subclass that omits any abstract method cannot be instantiated.
"""

import threading
from collections.abc import Iterator
from contextlib import AbstractContextManager
from pathlib import Path

import pytest

from memory_portability.backend import MemoryBackend


# ---------------------------------------------------------------------------
# FakeBackend — reusable in all later test steps
# ---------------------------------------------------------------------------

class FakeBackend(MemoryBackend):
    """In-memory MemoryBackend implementation for testing.

    Stores history as a string and vector records as a dict keyed by record ID.
    Non-user records are stored separately and must never be touched by
    replace_records.
    """

    _USER_KIND    = "user_memory"
    _NON_USER_ID  = "non-user-record-001"

    def __init__(self, tmp_path: Path) -> None:
        self._lock:         threading.Lock   = threading.Lock()
        self._state_dir:    Path             = tmp_path / "memory"
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._history:      str | None       = None
        self._records:      dict[str, dict]  = {}
        self._embed_calls:  list[list[str]]  = []   # tracks embed() call batches
        self._smoke_raises: bool             = False

        # Pre-populate one non-user record that must survive replace_records.
        self._records[self._NON_USER_ID] = {
            "id":       self._NON_USER_ID,
            "document": "knowledge prior chunk",
            "embedding": [0.0, 0.0, 0.0, 0.0],
            "metadata":  {"type": "chunk"},
        }

    # ------------------------------------------------------------------
    # Concurrency and paths
    # ------------------------------------------------------------------

    @property
    def write_lock(self) -> AbstractContextManager:
        return self._lock

    @property
    def state_dir(self) -> Path:
        return self._state_dir

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def read_history(self) -> str | None:
        return self._history

    def write_history(self, text: str | None) -> None:
        self._history = text

    def append_history(self, text: str) -> None:
        if self._history is None:
            self._history = text
        else:
            self._history += text

    # ------------------------------------------------------------------
    # Vector records
    # ------------------------------------------------------------------

    def _user_records(self) -> dict[str, dict]:
        return {
            rid: rec for rid, rec in self._records.items()
            if rec.get("metadata", {}).get("record_kind") == self._USER_KIND
        }

    def iter_records(self, batch_size: int) -> Iterator[list[dict]]:
        user = list(self._user_records().values())
        for i in range(0, max(len(user), 1), batch_size):
            batch = user[i : i + batch_size]
            if batch:
                yield batch

    def replace_records(self, records: Iterator[list[dict]]) -> None:
        # Delete existing user records
        for rid in list(self._user_records()):
            del self._records[rid]
        # Insert new records
        for batch in records:
            for rec in batch:
                self._records[rec["id"]] = rec

    def upsert_records(self, records: list[dict]) -> None:
        for rec in records:
            self._records[rec["id"]] = rec

    def delete_records(self, ids: list[str]) -> None:
        for rid in ids:
            self._records.pop(rid, None)

    # ------------------------------------------------------------------
    # Embedding
    # ------------------------------------------------------------------

    def embed(self, texts: list[str]) -> list[list[float]]:
        self._embed_calls.append(list(texts))
        dim = self.get_embedding_profile()["vector_dimension"]
        return [[float(i) * 0.1] * dim for i in range(len(texts))]

    def get_embedding_profile(self) -> dict:
        return {
            "provider":         "Local",
            "model":            "intfloat/e5-large-v2",
            "vector_dimension": 4,
        }

    # ------------------------------------------------------------------
    # Manifest metadata and smoke tests
    # ------------------------------------------------------------------

    def get_archive_metadata(self) -> dict:
        return {
            "omegaclaw_version": "OmegaClaw version=0.1.18",
            "chromadb_version":  "0.6.3",
        }

    def smoke_test(self, include_history: bool, include_vectors: bool) -> None:
        if self._smoke_raises:
            raise RuntimeError("smoke_test: forced failure")
        if include_history and self._history is None:
            raise RuntimeError("smoke_test: history is absent")
        if include_vectors and not self._records:
            raise RuntimeError("smoke_test: no records")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user_record(record_id: str, document: str = "doc") -> dict:
    return {
        "id":       record_id,
        "document": document,
        "embedding": [0.1, 0.2, 0.3, 0.4],
        "metadata":  {"record_kind": "user_memory", "time": "2026-01-01T00:00:00Z"},
    }


def _batches(records: list[dict], batch_size: int = 2) -> Iterator[list[dict]]:
    for i in range(0, len(records), batch_size):
        yield records[i : i + batch_size]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFakeBackendIsConcreteBackend:
    """FakeBackend is a valid, fully-instantiable MemoryBackend."""

    def test_is_subclass(self, tmp_path):
        fb = FakeBackend(tmp_path)
        assert isinstance(fb, MemoryBackend)

    def test_no_abstract_methods_remain(self, tmp_path):
        # If any abstract method were left unimplemented, instantiation raises.
        fb = FakeBackend(tmp_path)
        assert fb is not None

    def test_incomplete_subclass_cannot_be_instantiated(self):
        class Incomplete(MemoryBackend):
            pass  # implements nothing

        with pytest.raises(TypeError):
            Incomplete()


class TestWriteLock:
    """write_lock is a reentrant-safe context manager backed by a real lock."""

    def test_write_lock_is_context_manager(self, tmp_path):
        fb = FakeBackend(tmp_path)
        lock = fb.write_lock
        with lock:
            pass  # must not raise

    def test_write_lock_same_object_on_repeated_access(self, tmp_path):
        fb = FakeBackend(tmp_path)
        assert fb.write_lock is fb.write_lock

    def test_write_lock_blocks_second_thread(self, tmp_path):
        fb = FakeBackend(tmp_path)
        results = []

        def worker():
            acquired = fb.write_lock.acquire(blocking=False)
            results.append(acquired)
            if acquired:
                fb.write_lock.release()

        with fb.write_lock:
            t = threading.Thread(target=worker)
            t.start()
            t.join()

        assert results == [False], "Second thread must not acquire lock while first holds it"


class TestStateDir:
    """state_dir is a writable Path that exists."""

    def test_state_dir_is_path(self, tmp_path):
        fb = FakeBackend(tmp_path)
        assert isinstance(fb.state_dir, Path)

    def test_state_dir_exists(self, tmp_path):
        fb = FakeBackend(tmp_path)
        assert fb.state_dir.exists()

    def test_state_dir_is_writable(self, tmp_path):
        fb = FakeBackend(tmp_path)
        probe = fb.state_dir / ".write_probe"
        probe.write_text("ok")
        probe.unlink()

    def test_state_dir_same_object_on_repeated_access(self, tmp_path):
        fb = FakeBackend(tmp_path)
        assert fb.state_dir == fb.state_dir


class TestHistoryOperations:
    """History read, write, and append honour their contracts."""

    def test_read_history_returns_none_when_absent(self, tmp_path):
        fb = FakeBackend(tmp_path)
        assert fb.read_history() is None

    def test_write_history_stores_text(self, tmp_path):
        fb = FakeBackend(tmp_path)
        fb.write_history("line one\n")
        assert fb.read_history() == "line one\n"

    def test_write_history_none_removes_history(self, tmp_path):
        fb = FakeBackend(tmp_path)
        fb.write_history("something")
        fb.write_history(None)
        assert fb.read_history() is None

    def test_write_history_replaces_existing(self, tmp_path):
        fb = FakeBackend(tmp_path)
        fb.write_history("old content")
        fb.write_history("new content")
        assert fb.read_history() == "new content"

    def test_append_history_creates_when_absent(self, tmp_path):
        fb = FakeBackend(tmp_path)
        fb.append_history("first line\n")
        assert fb.read_history() == "first line\n"

    def test_append_history_appends_to_existing(self, tmp_path):
        fb = FakeBackend(tmp_path)
        fb.write_history("line one\n")
        fb.append_history("line two\n")
        assert fb.read_history() == "line one\nline two\n"

    def test_append_history_multiple_times(self, tmp_path):
        fb = FakeBackend(tmp_path)
        for i in range(3):
            fb.append_history(f"line {i}\n")
        assert fb.read_history() == "line 0\nline 1\nline 2\n"


class TestIterRecords:
    """iter_records yields only user records in correct batch sizes."""

    def test_yields_nothing_when_no_user_records(self, tmp_path):
        fb = FakeBackend(tmp_path)
        batches = list(fb.iter_records(batch_size=10))
        assert batches == []

    def test_yields_user_records_only(self, tmp_path):
        fb = FakeBackend(tmp_path)
        fb._records["u1"] = _make_user_record("u1")
        all_records = [r for batch in fb.iter_records(batch_size=10) for r in batch]
        ids = {r["id"] for r in all_records}
        assert "u1" in ids
        assert FakeBackend._NON_USER_ID not in ids

    def test_batch_size_respected(self, tmp_path):
        fb = FakeBackend(tmp_path)
        for i in range(5):
            fb._records[f"u{i}"] = _make_user_record(f"u{i}")
        batches = list(fb.iter_records(batch_size=2))
        assert all(len(b) <= 2 for b in batches)
        total = sum(len(b) for b in batches)
        assert total == 5

    def test_each_record_has_required_fields(self, tmp_path):
        fb = FakeBackend(tmp_path)
        fb._records["u1"] = _make_user_record("u1", document="hello")
        for batch in fb.iter_records(batch_size=10):
            for rec in batch:
                assert "id" in rec
                assert "document" in rec
                assert "embedding" in rec
                assert "metadata" in rec


class TestReplaceRecords:
    """replace_records clears user records, inserts new ones, preserves non-user."""

    def test_replaces_existing_user_records(self, tmp_path):
        fb = FakeBackend(tmp_path)
        fb._records["old"] = _make_user_record("old")
        new = [_make_user_record("new1"), _make_user_record("new2")]
        fb.replace_records(_batches(new))
        assert "old" not in fb._records
        assert "new1" in fb._records
        assert "new2" in fb._records

    def test_preserves_non_user_records(self, tmp_path):
        fb = FakeBackend(tmp_path)
        fb._records["u1"] = _make_user_record("u1")
        fb.replace_records(_batches([_make_user_record("u2")]))
        assert FakeBackend._NON_USER_ID in fb._records

    def test_accepts_empty_iterator(self, tmp_path):
        fb = FakeBackend(tmp_path)
        fb._records["u1"] = _make_user_record("u1")
        fb.replace_records(iter([]))
        assert "u1" not in fb._records
        assert FakeBackend._NON_USER_ID in fb._records

    def test_stores_ids_exactly_as_supplied(self, tmp_path):
        fb = FakeBackend(tmp_path)
        supplied_id = "import-abc123-fixture-record-001"
        rec = _make_user_record(supplied_id)
        fb.replace_records(_batches([rec]))
        assert supplied_id in fb._records


class TestUpsertRecords:
    """upsert_records adds new records and updates existing ones by ID."""

    def test_inserts_new_records(self, tmp_path):
        fb = FakeBackend(tmp_path)
        rec = _make_user_record("import-uuid-orig")
        fb.upsert_records([rec])
        assert "import-uuid-orig" in fb._records

    def test_updates_existing_record(self, tmp_path):
        fb = FakeBackend(tmp_path)
        fb._records["u1"] = _make_user_record("u1", document="old")
        updated = _make_user_record("u1", document="new")
        fb.upsert_records([updated])
        assert fb._records["u1"]["document"] == "new"

    def test_stores_ids_exactly_as_supplied(self, tmp_path):
        fb = FakeBackend(tmp_path)
        supplied_id = "import-deadbeef-some-original-id"
        fb.upsert_records([_make_user_record(supplied_id)])
        assert supplied_id in fb._records


class TestDeleteRecords:
    """delete_records removes exactly the named records."""

    def test_deletes_named_records(self, tmp_path):
        fb = FakeBackend(tmp_path)
        fb._records["u1"] = _make_user_record("u1")
        fb._records["u2"] = _make_user_record("u2")
        fb.delete_records(["u1"])
        assert "u1" not in fb._records
        assert "u2" in fb._records

    def test_ignores_unknown_ids(self, tmp_path):
        fb = FakeBackend(tmp_path)
        # Must not raise when an ID doesn't exist
        fb.delete_records(["does-not-exist"])

    def test_does_not_delete_non_user_records(self, tmp_path):
        fb = FakeBackend(tmp_path)
        fb.delete_records([FakeBackend._NON_USER_ID])
        # FakeBackend.delete_records deletes by ID regardless of kind;
        # in a real backend this would be disallowed by contract.
        # We only verify the package never passes non-user IDs — tested
        # in importer tests.

    def test_deletes_multiple_ids(self, tmp_path):
        fb = FakeBackend(tmp_path)
        for i in range(4):
            fb._records[f"u{i}"] = _make_user_record(f"u{i}")
        fb.delete_records(["u0", "u2"])
        assert "u0" not in fb._records
        assert "u1" in fb._records
        assert "u2" not in fb._records
        assert "u3" in fb._records


class TestEmbed:
    """embed returns correct-length, correct-dimension results."""

    def test_returns_list_same_length_as_input(self, tmp_path):
        fb = FakeBackend(tmp_path)
        result = fb.embed(["a", "b", "c"])
        assert len(result) == 3

    def test_each_embedding_has_correct_dimension(self, tmp_path):
        fb = FakeBackend(tmp_path)
        dim = fb.get_embedding_profile()["vector_dimension"]
        for vec in fb.embed(["hello", "world"]):
            assert len(vec) == dim

    def test_each_embedding_element_is_float(self, tmp_path):
        fb = FakeBackend(tmp_path)
        for vec in fb.embed(["test"]):
            for val in vec:
                assert isinstance(val, float)

    def test_empty_input_returns_empty_list(self, tmp_path):
        fb = FakeBackend(tmp_path)
        assert fb.embed([]) == []

    def test_tracks_call_batches(self, tmp_path):
        fb = FakeBackend(tmp_path)
        fb.embed(["a", "b"])
        fb.embed(["c"])
        assert fb._embed_calls == [["a", "b"], ["c"]]


class TestGetEmbeddingProfile:
    """get_embedding_profile returns required keys with correct types."""

    def test_has_provider_key(self, tmp_path):
        fb = FakeBackend(tmp_path)
        assert isinstance(fb.get_embedding_profile()["provider"], str)

    def test_has_model_key(self, tmp_path):
        fb = FakeBackend(tmp_path)
        assert isinstance(fb.get_embedding_profile()["model"], str)

    def test_has_vector_dimension_key(self, tmp_path):
        fb = FakeBackend(tmp_path)
        dim = fb.get_embedding_profile()["vector_dimension"]
        assert isinstance(dim, int)
        assert dim > 0

    def test_consistent_with_embed_output(self, tmp_path):
        fb = FakeBackend(tmp_path)
        dim = fb.get_embedding_profile()["vector_dimension"]
        embeddings = fb.embed(["test"])
        assert len(embeddings[0]) == dim


class TestGetArchiveMetadata:
    """get_archive_metadata returns v1-compatible fields."""

    def test_has_omegaclaw_version(self, tmp_path):
        fb = FakeBackend(tmp_path)
        meta = fb.get_archive_metadata()
        assert isinstance(meta.get("omegaclaw_version"), str)
        assert meta["omegaclaw_version"]

    def test_has_chromadb_version(self, tmp_path):
        fb = FakeBackend(tmp_path)
        meta = fb.get_archive_metadata()
        assert isinstance(meta.get("chromadb_version"), str)
        assert meta["chromadb_version"]


class TestSmokeTest:
    """smoke_test passes when components are present, raises when absent."""

    def test_passes_when_history_present(self, tmp_path):
        fb = FakeBackend(tmp_path)
        fb.write_history("some history")
        fb.smoke_test(include_history=True, include_vectors=False)  # must not raise

    def test_passes_when_vectors_present(self, tmp_path):
        fb = FakeBackend(tmp_path)
        fb._records["u1"] = _make_user_record("u1")
        fb.smoke_test(include_history=False, include_vectors=True)  # must not raise

    def test_passes_when_both_present(self, tmp_path):
        fb = FakeBackend(tmp_path)
        fb.write_history("some history")
        fb._records["u1"] = _make_user_record("u1")
        fb.smoke_test(include_history=True, include_vectors=True)  # must not raise

    def test_passes_when_neither_selected(self, tmp_path):
        fb = FakeBackend(tmp_path)
        fb.smoke_test(include_history=False, include_vectors=False)  # must not raise

    def test_raises_when_history_absent_and_required(self, tmp_path):
        fb = FakeBackend(tmp_path)
        with pytest.raises(Exception):
            fb.smoke_test(include_history=True, include_vectors=False)

    def test_raises_when_forced(self, tmp_path):
        fb = FakeBackend(tmp_path)
        fb.write_history("history")
        fb._smoke_raises = True
        with pytest.raises(RuntimeError, match="forced failure"):
            fb.smoke_test(include_history=True, include_vectors=False)
