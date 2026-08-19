import json
import os
from pathlib import Path

from memory_portability.backend import MemoryBackend
from memory_portability.errors import ImportError as MpImportError

def needs_reembedding(
    manifest: dict, backend: MemoryBackend, embeddings_missing: bool = False
) -> bool:
    """Return whether staged records require re-embedding."""
    archive_info = manifest.get("embedding_info", {})
    active_info  = backend.get_embedding_profile()

    active_dimension = active_info.get("vector_dimension")
    if type(active_dimension) is not int or active_dimension <= 0:
        return True

    if embeddings_missing or not archive_info.get("vector_dimension"):
        return True

    return (
        archive_info.get("provider")         != active_info.get("provider")
        or archive_info.get("model")         != active_info.get("model")
        or archive_info.get("vector_dimension") != active_info.get("vector_dimension")
    )

def reembed_staged_records(
    staging: Path,
    backend: MemoryBackend,
    batch_size: int = 64,
) -> None:
    """Re-embed staged records atomically before live records are replaced."""
    records_path = staging / "vector" / "records.jsonl"
    tmp_path     = records_path.with_suffix(".jsonl.tmp")

    expected_dim = backend.get_embedding_profile().get("vector_dimension")
    if type(expected_dim) is not int or expected_dim <= 0:
        expected_dim = None

    try:
        with records_path.open("r", encoding="utf-8") as src, \
             tmp_path.open("w", encoding="utf-8") as dst:

            batch_records: list[dict] = []
            batch_lines:   list[str]  = []  # raw lines for non-record lines

            def _flush_batch() -> None:
                nonlocal expected_dim
                if not batch_records:
                    return
                texts      = [r["document"] for r in batch_records]
                embeddings = backend.embed(texts)

                if len(embeddings) != len(batch_records):
                    raise MpImportError(
                        f"backend.embed() returned {len(embeddings)} embeddings "
                        f"for {len(batch_records)} texts"
                    )
                for embedding in embeddings:
                    if not embedding:
                        raise MpImportError("backend.embed() returned an empty embedding")
                    if expected_dim is None:
                        expected_dim = len(embedding)
                    elif len(embedding) != expected_dim:
                        raise MpImportError(
                            f"backend.embed() returned dimension {len(embedding)}, "
                            f"expected {expected_dim}"
                        )

                for record, embedding in zip(batch_records, embeddings):
                    record["embedding"] = [float(v) for v in embedding]
                    dst.write(json.dumps(record, ensure_ascii=False) + "\n")

                batch_records.clear()

            for line in src:
                if not line.strip():
                    dst.write(line)
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    dst.write(line)
                    continue

                batch_records.append(record)
                if len(batch_records) == batch_size:
                    _flush_batch()

            _flush_batch()

        os.replace(tmp_path, records_path)

    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
