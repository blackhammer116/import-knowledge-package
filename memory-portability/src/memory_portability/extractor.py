"""
memory_portability.extractor
============================

Reading and normalising JSONL records from an extracted archive staging
directory.

Responsibilities
----------------
- Streaming JSONL records from ``vector/records.jsonl`` in bounded batches
  so large collections are never fully loaded into RAM.
- Normalising each raw record into a clean dict with scalar-safe metadata
  (ChromaDB requires scalar metadata values; lists and dicts are
  JSON-serialised to strings).
- Providing a helper to read the history file content from staging.

This module operates on already-extracted and already-validated staging
directories. It does not open tar archives or validate manifests.
"""

import json
from collections.abc import Iterator
from pathlib import Path

from memory_portability.errors import ArchiveValidationError


def iter_staged_records(staging: Path, batch_size: int = 500) -> Iterator[list[dict]]:
    """Yield validated, normalised records from staging in batches.

    Reads ``vector/records.jsonl`` line by line, normalises each record's
    metadata into scalar-safe form, and yields non-empty batches of at most
    ``batch_size`` records.

    Each yielded record dict contains:
        ``id``        -- non-empty string
        ``document``  -- string
        ``embedding`` -- list of floats
        ``metadata``  -- dict with only str, int, float, or bool values

    Parameters
    ----------
    staging:
        Directory into which the archive was extracted.
    batch_size:
        Maximum number of records per yielded batch.

    Yields
    ------
    list[dict]
        Batches of normalised record dicts.

    Raises
    ------
    ArchiveValidationError
        If a line cannot be parsed or a record fails normalisation.
    """
    records_path = staging / "vector" / "records.jsonl"
    batch: list[dict] = []

    with records_path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ArchiveValidationError(
                    f"Invalid JSONL on line {line_no}: {exc}"
                ) from exc

            batch.append(_normalise_record(raw, line_no))
            if len(batch) == batch_size:
                yield batch
                batch = []

    if batch:
        yield batch


def read_staged_history(staging: Path) -> str | None:
    """Return the content of ``history/history.metta`` from staging.

    Returns ``None`` if the file does not exist in staging.

    Parameters
    ----------
    staging:
        Directory into which the archive was extracted.
    """
    path = staging / "history" / "history.metta"
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def normalise_metadata(metadata: object) -> dict:
    """Convert a raw metadata value into ChromaDB-compatible scalar form.

    ChromaDB accepts only ``str``, ``int``, ``float``, and ``bool`` metadata
    values. This function converts:
    - ``None``        → ``"null"``
    - ``list``/``dict`` → JSON-encoded string (sorted keys for determinism)
    - Other types     → ``str(value)``

    Parameters
    ----------
    metadata:
        Raw metadata object from an archive record (must be a dict).

    Returns
    -------
    dict
        Metadata dict containing only scalar values.

    Raises
    ------
    ArchiveValidationError
        If ``metadata`` is not a dict or contains non-string keys.
    """
    if not isinstance(metadata, dict):
        raise ArchiveValidationError(
            "Archive record metadata must be a JSON object"
        )

    normalised: dict = {}
    for key, value in metadata.items():
        if not isinstance(key, str) or not key:
            raise ArchiveValidationError(
                "Archive record metadata keys must be non-empty strings"
            )
        if isinstance(value, (str, int, float, bool)):
            normalised[key] = value
        elif value is None:
            normalised[key] = "null"
        elif isinstance(value, (list, dict)):
            normalised[key] = json.dumps(value, ensure_ascii=False, sort_keys=True)
        else:
            normalised[key] = str(value)

    return normalised


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _normalise_record(raw: object, line_no: int) -> dict:
    """Validate and normalise a single decoded record from JSONL."""
    if not isinstance(raw, dict):
        raise ArchiveValidationError(
            f"Archive record on line {line_no} must be a JSON object"
        )

    record_id = raw.get("id")
    document  = raw.get("document")
    embedding = raw.get("embedding", [])

    if not isinstance(record_id, str) or not record_id:
        raise ArchiveValidationError(
            f"Archive record on line {line_no} has an invalid or missing id"
        )
    if not isinstance(document, str):
        raise ArchiveValidationError(
            f"Archive record {record_id!r} on line {line_no} has a non-string document"
        )
    if not isinstance(embedding, list) or not all(
        isinstance(v, (int, float)) and not isinstance(v, bool)
        for v in embedding
    ):
        raise ArchiveValidationError(
            f"Archive record {record_id!r} on line {line_no} has an invalid embedding"
        )

    return {
        "id":       record_id,
        "document": document,
        "embedding": [float(v) for v in embedding],
        "metadata":  normalise_metadata(raw.get("metadata", {})),
    }
