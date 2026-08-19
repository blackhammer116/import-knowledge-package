import threading
from collections.abc import Iterator
from pathlib import Path

from memory_portability.backend import MemoryBackend
def record(record_id: str, document: str = "memory") -> dict:
    return {
        "id": record_id,
        "document": document,
        "embedding": [0.1, 0.2, 0.3, 0.4],
        "metadata": {"record_kind": "user_memory"},
    }
class FakeBackend(MemoryBackend):
    def __init__(self, tmp_path: Path, history: str | None = "history\n") -> None:
        self._lock = threading.Lock()
        self._state_dir = tmp_path / "memory"
        self._state_dir.mkdir(parents=True)
        self._history = history
        self._records: dict[str, dict] = {}
        self._vector_store_exists = False
        self.profile = {"provider": "Local", "model": "model-a", "vector_dimension": 4}
        self.embed_calls: list[list[str]] = []
        self.fail_smoke = False

    @property
    def write_lock(self):
        return self._lock

    @property
    def state_dir(self) -> Path:
        return self._state_dir

    def read_history(self) -> str | None:
        return self._history

    def write_history(self, text: str | None) -> None:
        self._history = text

    def append_history(self, text: str) -> None:
        self._history = (self._history or "") + text

    def iter_records(self, batch_size: int) -> Iterator[list[dict]]:
        records = [r for r in self._records.values() if r["metadata"].get("record_kind") == "user_memory"]
        for start in range(0, len(records), batch_size):
            yield records[start : start + batch_size]

    def replace_records(self, batches: Iterator[list[dict]]) -> None:
        self._vector_store_exists = True
        self._records = {key: value for key, value in self._records.items() if value["metadata"].get("record_kind") != "user_memory"}
        for batch in batches:
            self.upsert_records(batch)

    def upsert_records(self, records: list[dict]) -> None:
        self._vector_store_exists = True
        self._records.update({item["id"]: item for item in records})

    def vector_store_exists(self) -> bool:
        return self._vector_store_exists

    def remove_vector_store(self) -> None:
        self._records.clear()
        self._vector_store_exists = False

    def delete_records(self, ids: list[str]) -> None:
        for record_id in ids:
            self._records.pop(record_id, None)

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.embed_calls.append(texts)
        return [[0.5] * self.profile["vector_dimension"] for _ in texts]

    def get_embedding_profile(self) -> dict:
        return self.profile

    def get_archive_metadata(self) -> dict:
        return {"omegaclaw_version": "OmegaClaw version=1.0", "chromadb_version": "1.0"}

    def smoke_test(self, include_history: bool, include_vectors: bool) -> None:
        if self.fail_smoke:
            raise RuntimeError("forced smoke failure")
def user_records(backend: FakeBackend) -> list[dict]:
    return [record for batch in backend.iter_records(100) for record in batch]
