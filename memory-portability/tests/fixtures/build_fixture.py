"""
Build the v1 OmegaClaw-compatible archive fixture used in tests.

Run once from the repository root to regenerate the fixture:

    python memory-portability/tests/fixtures/build_fixture.py

The output file ``omegaclaw_v1_fixture.tar.gz`` is checked in alongside this
script and loaded by tests via ``conftest.py``.

The fixture content is intentionally minimal:
- One history entry in ``history/history.metta``.
- Two vector records in ``vector/records.jsonl`` with 4-dimensional embeddings.

The manifest uses field names and values identical to those produced by
OmegaClaw's ``src/memory_transfer.py`` (format_version=1, omegaclaw_version,
chromadb_version, etc.) to verify byte-for-byte format compatibility.
"""

import hashlib
import json
import os
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Fixture content
# ---------------------------------------------------------------------------

HISTORY_CONTENT = """\
(EpisodicMemory (Event (time "2026-01-01T00:00:00Z") (content "Fixture history entry one.")))
(EpisodicMemory (Event (time "2026-01-02T00:00:00Z") (content "Fixture history entry two.")))
"""

RECORDS = [
    {
        "id": "fixture-record-001",
        "document": "The sky is blue.",
        "embedding": [0.1, 0.2, 0.3, 0.4],
        "metadata": {"record_kind": "user_memory", "time": "2026-01-01T00:00:00Z"},
    },
    {
        "id": "fixture-record-002",
        "document": "Water boils at 100 degrees Celsius at sea level.",
        "embedding": [0.5, 0.6, 0.7, 0.8],
        "metadata": {"record_kind": "user_memory", "time": "2026-01-02T00:00:00Z"},
    },
]

COLLECTIONS = {
    "name": "memories",
    "embedding_info": {
        "provider": "Local",
        "model": "intfloat/e5-large-v2",
        "vector_dimension": 4,
    },
}

# Matches OmegaClaw's get_archive_metadata() return exactly.
ARCHIVE_METADATA = {
    "omegaclaw_version": "OmegaClaw version=0.1.18",
    "chromadb_version": "0.6.3",
}

EMBEDDING_INFO = COLLECTIONS["embedding_info"]

ALLOWLIST = [
    "manifest.json",
    "history/history.metta",
    "vector/collections.json",
    "vector/records.jsonl",
]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build(dest: Path) -> None:
    history_bytes_content  = HISTORY_CONTENT.encode("utf-8")
    records_lines          = "\n".join(json.dumps(r, ensure_ascii=False) for r in RECORDS) + "\n"
    records_bytes_content  = records_lines.encode("utf-8")
    collections_bytes      = json.dumps(COLLECTIONS, indent=2, ensure_ascii=False).encode("utf-8")

    with tempfile.TemporaryDirectory() as tmp:
        staging = Path(tmp)

        # Write member files
        (staging / "history").mkdir()
        (staging / "vector").mkdir()

        hist_path        = staging / "history" / "history.metta"
        records_path     = staging / "vector"  / "records.jsonl"
        collections_path = staging / "vector"  / "collections.json"

        hist_path.write_bytes(history_bytes_content)
        records_path.write_bytes(records_bytes_content)
        collections_path.write_bytes(collections_bytes)

        checksums = {
            "history/history.metta":  _sha256(history_bytes_content),
            "vector/collections.json": _sha256(collections_bytes),
            "vector/records.jsonl":    _sha256(records_bytes_content),
        }

        manifest = {
            "format_version":    1,
            "omegaclaw_version": ARCHIVE_METADATA["omegaclaw_version"],
            "chromadb_version":  ARCHIVE_METADATA["chromadb_version"],
            "components":        ["history", "ltm"],
            "embedding_info":    EMBEDDING_INFO,
            "record_count":      len(RECORDS),
            "history_bytes":     len(history_bytes_content),
            "created_at":        "2026-01-01T00:00:00+00:00",
            "checksums":         checksums,
        }

        manifest_bytes = json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8")
        (staging / "manifest.json").write_bytes(manifest_bytes)

        # Pack into tar.gz using the allowlist order
        with tarfile.open(dest, "w:gz") as tar:
            for member in sorted(ALLOWLIST):
                p = staging / member
                if p.exists():
                    tar.add(p, arcname=member)

    print(f"Fixture written to: {dest}")
    print(f"  SHA-256: {_sha256(dest.read_bytes())}")


if __name__ == "__main__":
    out = Path(__file__).parent / "omegaclaw_v1_fixture.tar.gz"
    build(out)
