import os
import shutil
from collections.abc import Iterator
from contextlib import AbstractContextManager
from pathlib import Path

import chromadb


class OmegaClawMemory:
    def __init__(self) -> None:
        self._memory_dir = Path(os.environ.get("MEMORY_DIR", Path.cwd() / "memory")).resolve()
        self._client = None
        self._collection = None

    @property
    def write_lock(self) -> AbstractContextManager:
        from src.memory_gateway import _write_lock
        return _write_lock

    @property
    def state_dir(self) -> Path:
        self._memory_dir.mkdir(parents=True, exist_ok=True)
        return self._memory_dir

    @property
    def _history_path(self) -> Path:
        return self._memory_dir / "history.metta"

    @property
    def _database_path(self) -> Path:
        return self._memory_dir / "chroma_db"

    def _get_collection(self):
        if self._collection is None:
            self._client = chromadb.PersistentClient(path=str(self._database_path))
            self._collection = self._client.get_or_create_collection(
                name="memories", embedding_function=None
            )
        return self._collection

    def read_history(self) -> str | None:
        return self._history_path.read_text(encoding="utf-8") if self._history_path.exists() else None

    def write_history(self, text: str | None) -> None:
        if text is None:
            self._history_path.unlink(missing_ok=True)
        else:
            self.state_dir
            self._history_path.write_text(text, encoding="utf-8")

    def append_history(self, text: str) -> None:
        self.state_dir
        with self._history_path.open("a", encoding="utf-8") as history:
            history.write(text)

    def iter_records(self, batch_size: int) -> Iterator[list[dict]]:
        collection = self._get_collection()
        for offset in range(0, collection.count(), batch_size):
            result = collection.get(
                limit=batch_size,
                offset=offset,
                include=["documents", "metadatas", "embeddings"],
            )
            records = []
            for index, record_id in enumerate(result["ids"]):
                metadata = (result.get("metadatas") or [])[index] or {}
                if _is_user_record(metadata):
                    embeddings = result.get("embeddings")
                    records.append({
                        "id": record_id,
                        "document": (result.get("documents") or [])[index],
                        "embedding": list(embeddings[index]) if embeddings is not None else [],
                        "metadata": dict(metadata),
                    })
            if records:
                yield records

    def replace_records(self, records: Iterator[list[dict]]) -> None:
        collection = self._get_collection()
        existing = collection.get(include=["metadatas"])
        ids = [
            record_id for record_id, metadata in zip(
                existing["ids"], existing.get("metadatas") or []
            ) if _is_user_record(metadata)
        ]
        if ids:
            collection.delete(ids=ids)
        for batch in records:
            if batch:
                collection.add(
                    ids=[record["id"] for record in batch],
                    documents=[record["document"] for record in batch],
                    embeddings=[record["embedding"] for record in batch],
                    metadatas=[record["metadata"] for record in batch],
                )

    def vector_store_exists(self) -> bool:
        return self._database_path.exists()

    def remove_vector_store(self) -> None:
        self._client = None
        self._collection = None
        shutil.rmtree(self._database_path, ignore_errors=True)

    def upsert_records(self, records: list[dict]) -> None:
        self._get_collection().upsert(
            ids=[record["id"] for record in records],
            documents=[record["document"] for record in records],
            embeddings=[record["embedding"] for record in records],
            metadatas=[record["metadata"] for record in records],
        )

    def delete_records(self, ids: list[str]) -> None:
        if ids:
            self._get_collection().delete(ids=ids)

    def embed(self, texts: list[str]) -> list[list[float]]:
        from src.rag import local_embed_batch, openai_embed_batch
        embed = openai_embed_batch if os.environ.get("EMBEDDING_PROVIDER") == "OpenAI" else local_embed_batch
        return embed(texts)

    def get_embedding_profile(self) -> dict:
        provider = os.environ.get("EMBEDDING_PROVIDER", "Local")
        model = os.environ.get(
            "SENTENCE_TRANSFORMERS_MODEL",
            "text-embedding-3-large" if provider == "OpenAI" else "intfloat/e5-large-v2",
        )
        try:
            embeddings = self._get_collection().get(
                limit=1, include=["embeddings"]
            ).get("embeddings")
            dimension = len(embeddings[0]) if embeddings is not None and len(embeddings) else None
        except Exception:
            dimension = None
        dimension = dimension or {"intfloat/e5-large-v2": 1024, "text-embedding-3-large": 3072}.get(model)
        return {"provider": provider, "model": model, "vector_dimension": dimension}

    def get_archive_metadata(self) -> dict:
        from src.helper import omegaclaw_version
        return {"omegaclaw_version": omegaclaw_version(), "chromadb_version": chromadb.__version__}

    def smoke_test(self, include_history: bool, include_vectors: bool) -> None:
        if include_history:
            self.read_history()
        if include_vectors:
            self._get_collection().get(limit=1)


def _is_user_record(metadata: object) -> bool:
    return isinstance(metadata, dict) and (
        metadata.get("record_kind") == "user_memory"
        or ("record_kind" not in metadata and "type" not in metadata)
    )
