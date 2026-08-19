"""
memory_portability.reembedder
=============================

Staged re-embedding of archive records when the archive's embedding profile
differs from the agent's active profile.

Responsibilities
----------------
- Comparing archive and runtime embedding profiles to decide whether
  re-embedding is needed.
- Reading staged ``records.jsonl`` in batches, calling the backend's
  ``embed()`` method for document text, verifying returned batch length
  and vector dimension, and writing updated records back to the staged file.
- Ensuring that live memory is never touched during re-embedding: all
  mutations happen on the staged file only.

After this module completes, ``staging/vector/records.jsonl`` contains
embeddings compatible with the agent's active profile and the importer
can proceed directly to ``replace_records``.

The backend supplies the embedding function only. It never mutates archive
or staged records.
"""

import json
import os
from pathlib import Path

from memory_portability.backend import MemoryBackend
from memory_portability.errors import ImportError as MpImportError


def needs_reembedding(
    manifest: dict, backend: MemoryBackend, embeddings_missing: bool = False
) -> bool:
    """Return whether staged records must be re-embedded before import.

    Compares ``manifest["embedding_info"]`` against
    ``backend.get_embedding_profile()``. Re-embedding is required when the
    provider, model, or vector dimension differs, or when the manifest
    contains records without embeddings.

    Parameters
    ----------
    manifest:
        Validated manifest dict (output of ``validator.validate_manifest``).
    backend:
        Agent storage adapter providing the active embedding profile.

    Returns
    -------
    bool
        ``True`` when re-embedding is required before import.
    """
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
    """Re-embed all records in ``staging/vector/records.jsonl`` in-place.

    Reads the staged JSONL file in batches of ``batch_size`` documents,
    calls ``backend.embed()`` for each batch, verifies that the returned
    list length and vector dimension match expectations, and writes the
    updated records back to the staged file.

    The staged file is rewritten atomically: a temporary sibling file is
    written and then renamed over the original so that a crash mid-rewrite
    leaves either the original or the fully re-embedded file, never a
    partial file.

    After this function returns, every record in the staged file has an
    embedding compatible with ``backend.get_embedding_profile()``.

    Parameters
    ----------
    staging:
        Directory into which the archive was extracted. Must contain
        ``vector/records.jsonl``.
    backend:
        Agent storage adapter. Its ``embed()`` and ``get_embedding_profile()``
        methods are called; no other backend methods are used here.
    batch_size:
        Number of documents to embed per ``backend.embed()`` call.

    Raises
    ------
    ImportError
        If ``backend.embed()`` returns a batch of the wrong length or
        wrong vector dimension.
    """
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
                    # Pass non-JSON lines through unchanged (shouldn't exist
                    # in validated staging, but be defensive).
                    dst.write(line)
                    continue

                batch_records.append(record)
                if len(batch_records) == batch_size:
                    _flush_batch()

            _flush_batch()

        # Atomic rename: replaces records.jsonl only after full rewrite succeeds.
        os.replace(tmp_path, records_path)

    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
