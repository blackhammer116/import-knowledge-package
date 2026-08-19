"""
memory_portability.validator
============================

Manifest schema validation, checksum verification, and record-level
validation for memory archives.

Responsibilities
----------------
- Validating the structure and field types of ``manifest.json``.
- Verifying SHA-256 checksums of extracted files against the manifest.
- Validating ``collections.json`` structure and embedding-info consistency.
- Validating individual JSONL records (types, required fields, embedding
  dimension against manifest).
- Confirming that record counts and history byte sizes match the manifest.

This module operates on already-extracted files. It never opens a tar archive;
that is the responsibility of ``archive.py``.
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from memory_portability.archive import ARCHIVE_FORMAT_VERSION, COMPONENT_FILES
from memory_portability.errors import ArchiveValidationError


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_manifest(raw: object) -> dict:
    """Parse and validate a raw manifest object loaded from ``manifest.json``.

    Checks all required fields, their types, value constraints, and internal
    consistency (e.g. checksums keys match components, record_count is zero
    when ``ltm`` is not in components).

    Parameters
    ----------
    raw:
        Python object produced by ``json.loads`` on ``manifest.json`` content.

    Returns
    -------
    dict
        The validated manifest dict, unchanged.

    Raises
    ------
    ArchiveValidationError
        If any field is missing, has the wrong type, or is internally
        inconsistent.
    """
    if not isinstance(raw, dict):
        raise ArchiveValidationError("Archive manifest must be a JSON object")

    # format_version — must be an int (not bool) equal to the supported version
    if type(raw.get("format_version")) is not int:
        raise ArchiveValidationError("Archive manifest has invalid format_version")
    if raw["format_version"] != ARCHIVE_FORMAT_VERSION:
        raise ArchiveValidationError(
            f"Unsupported format_version: {raw['format_version']!r}. "
            f"Expected {ARCHIVE_FORMAT_VERSION}."
        )

    # String fields that must be non-empty
    for field in ("omegaclaw_version", "chromadb_version", "created_at"):
        if not isinstance(raw.get(field), str) or not raw[field]:
            raise ArchiveValidationError(f"Archive manifest has invalid {field!r}")

    # created_at must be a valid UTC ISO-8601 timestamp
    try:
        created_at = datetime.fromisoformat(raw["created_at"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise ArchiveValidationError(
            "Archive manifest created_at is not a valid ISO-8601 timestamp"
        ) from exc
    if created_at.tzinfo is None or created_at.utcoffset() != timezone.utc.utcoffset(created_at):
        raise ArchiveValidationError("Archive manifest created_at must be UTC")

    # components — list of known component names, no duplicates
    components = raw.get("components")
    if (
        not isinstance(components, list)
        or any(c not in ("history", "ltm") for c in components)
        or len(components) != len(set(components))
    ):
        raise ArchiveValidationError("Archive manifest has invalid components")

    # record_count — non-negative int (not bool)
    if (
        not isinstance(raw.get("record_count"), int)
        or isinstance(raw["record_count"], bool)
        or raw["record_count"] < 0
    ):
        raise ArchiveValidationError("Archive manifest has invalid record_count")

    # history_bytes — non-negative int (not bool)
    if (
        not isinstance(raw.get("history_bytes"), int)
        or isinstance(raw["history_bytes"], bool)
        or raw["history_bytes"] < 0
    ):
        raise ArchiveValidationError("Archive manifest has invalid history_bytes")

    # Internal consistency: records require ltm; history_bytes require history
    if "ltm" not in components and raw["record_count"]:
        raise ArchiveValidationError(
            "Archive manifest has record_count > 0 without the ltm component"
        )
    if "history" not in components and raw["history_bytes"]:
        raise ArchiveValidationError(
            "Archive manifest has history_bytes > 0 without the history component"
        )

    # checksums — dict of str→64-char lowercase hex strings
    checksums = raw.get("checksums")
    if not isinstance(checksums, dict):
        raise ArchiveValidationError("Archive manifest checksums must be a JSON object")
    for name, digest in checksums.items():
        if not isinstance(name, str) or not isinstance(digest, str):
            raise ArchiveValidationError(
                "Archive manifest checksums must map strings to strings"
            )
        if len(digest) != 64 or not all(c in "0123456789abcdef" for c in digest.lower()):
            raise ArchiveValidationError(
                f"Archive manifest checksum for {name!r} is not a valid SHA-256 hex digest"
            )

    # checksums keys must match exactly the files belonging to declared components
    expected_files: set[str] = set()
    for component in components:
        expected_files |= COMPONENT_FILES[component]
    if set(checksums) != expected_files:
        raise ArchiveValidationError(
            "Archive manifest checksums keys do not match its components"
        )

    # embedding_info — required when ltm present, must be empty dict otherwise
    if "ltm" in components:
        _validate_embedding_info(raw)
    elif raw.get("embedding_info") not in ({}, None):
        raise ArchiveValidationError(
            "Archive manifest has embedding_info without the ltm component"
        )

    return raw


def validate_checksums(staging: Path, manifest: dict) -> None:
    """Verify SHA-256 checksums of extracted files against ``manifest``.

    Computes the SHA-256 of every file listed in ``manifest["checksums"]``
    and raises if any computed digest does not match.

    Parameters
    ----------
    staging:
        Directory into which the archive was extracted.
    manifest:
        Validated manifest dict (output of ``validate_manifest``).

    Raises
    ------
    ArchiveValidationError
        If any file's checksum does not match or a listed file is absent.
    """
    for member_name, expected in manifest["checksums"].items():
        path = staging / member_name
        if not path.exists():
            raise ArchiveValidationError(
                f"Checksummed file missing from staging: {member_name!r}"
            )
        actual = _sha256(path)
        if actual != expected:
            raise ArchiveValidationError(
                f"Checksum mismatch for {member_name!r}: "
                f"expected {expected}, got {actual}"
            )


def validate_collections(staging: Path, manifest: dict) -> None:
    """Validate ``vector/collections.json`` against the manifest.

    Checks that the collection name is ``"memories"`` and that its
    ``embedding_info`` matches ``manifest["embedding_info"]``.

    Parameters
    ----------
    staging:
        Directory into which the archive was extracted.
    manifest:
        Validated manifest dict.

    Raises
    ------
    ArchiveValidationError
        If ``collections.json`` is missing, malformed, or inconsistent with
        the manifest.
    """
    path = staging / "vector" / "collections.json"
    if not path.exists():
        raise ArchiveValidationError("Archive is missing vector/collections.json")

    try:
        collections = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ArchiveValidationError(
            f"Archive vector/collections.json is not valid JSON: {exc}"
        ) from exc

    if not isinstance(collections, dict):
        raise ArchiveValidationError(
            "Archive vector/collections.json must be a JSON object"
        )
    if collections.get("name") != "memories":
        raise ArchiveValidationError(
            "Archive vector/collections.json must have name 'memories'"
        )
    if collections.get("embedding_info") != manifest["embedding_info"]:
        raise ArchiveValidationError(
            "Archive vector/collections.json embedding_info does not match manifest"
        )


def validate_history(staging: Path, manifest: dict) -> None:
    """Validate the history member and its declared byte length."""
    path = staging / "history" / "history.metta"
    if not path.is_file():
        raise ArchiveValidationError("Archive is missing history/history.metta")
    if path.stat().st_size != manifest["history_bytes"]:
        raise ArchiveValidationError(
            "Archive history byte count does not match manifest"
        )


def validate_records(staging: Path, manifest: dict) -> bool:
    """Validate every record in ``vector/records.jsonl`` against the manifest.

    Checks that:
    - Each line is valid JSON representing an object.
    - Each record has a non-empty string ``id``, a string ``document``, a
      list-of-numbers ``embedding``, and a dict ``metadata``.
    - Each embedding has exactly
      ``manifest["embedding_info"]["vector_dimension"]`` dimensions.
    - The total record count matches ``manifest["record_count"]``.

    Parameters
    ----------
    staging:
        Directory into which the archive was extracted.
    manifest:
        Validated manifest dict.

    Returns
    -------
    bool
        ``True`` when one or more records have no embedding and therefore
        require staged re-embedding before import.

    Raises
    ------
    ArchiveValidationError
        If any record is malformed, has the wrong embedding dimension, or the
        total count does not match the manifest.
    """
    path = staging / "vector" / "records.jsonl"
    if not path.exists():
        raise ArchiveValidationError("Archive is missing vector/records.jsonl")

    expected_count = manifest["record_count"]
    dimension      = manifest["embedding_info"]["vector_dimension"]
    count          = 0
    missing_embeddings = False

    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ArchiveValidationError(
                    f"Invalid JSONL on line {line_no}: {exc}"
                ) from exc

            missing_embeddings |= _validate_record(record, line_no, dimension)
            count += 1

    if count != expected_count:
        raise ArchiveValidationError(
            f"Archive record count mismatch: manifest says {expected_count}, "
            f"found {count}"
        )
    return missing_embeddings


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _validate_embedding_info(manifest: dict) -> None:
    """Validate ``embedding_info`` inside a manifest dict."""
    info = manifest.get("embedding_info")
    if (
        not isinstance(info, dict)
        or not isinstance(info.get("provider"), str)
        or not info["provider"]
        or not isinstance(info.get("model"), str)
        or not info["model"]
        or type(info.get("vector_dimension")) is not int
        or info["vector_dimension"] <= 0
    ):
        raise ArchiveValidationError(
            "Archive manifest has invalid or missing embedding_info"
        )


def _validate_record(record: object, line_no: int, dimension: int) -> bool:
    """Validate a single decoded JSONL record."""
    if not isinstance(record, dict):
        raise ArchiveValidationError(
            f"Archive record on line {line_no} must be a JSON object"
        )

    record_id = record.get("id")
    document  = record.get("document")
    embedding = record.get("embedding", [])

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
    if embedding and len(embedding) != dimension:
        raise ArchiveValidationError(
            f"Archive record {record_id!r} embedding dimension {len(embedding)} "
            f"does not match manifest dimension {dimension}"
        )
    if not isinstance(record.get("metadata", {}), dict):
        raise ArchiveValidationError(
            f"Archive record {record_id!r} on line {line_no} has invalid metadata"
        )
    return not embedding


def _sha256(path: Path) -> str:
    """Return the lowercase hex SHA-256 digest of a file."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
