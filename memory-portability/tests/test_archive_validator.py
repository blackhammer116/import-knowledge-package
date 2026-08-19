"""
Step 3 tests: archive.py and validator.py.

Covers:
archive.py
- pack: produces a valid tar.gz with sorted allowlisted members only.
- pack: raises FileExistsError when dest already exists.
- unpack: extracts all members correctly into dest.
- unpack: raises ArchiveValidationError for non-allowlisted members.
- unpack: raises ArchiveValidationError for duplicate members.
- unpack: raises ArchiveValidationError for non-regular members (symlink).
- unpack: raises ArchiveValidationError for path traversal.
- unpack: raises ArchiveValidationError when compressed size exceeds limit.
- unpack: raises ArchiveValidationError when extracted size exceeds limit.
- pack + unpack round-trip: extracted content matches original.
- v1 fixture unpacks cleanly.

validator.py — validate_manifest
- Accepts a valid v1 manifest.
- Rejects non-dict input.
- Rejects wrong format_version type (bool, str).
- Rejects unsupported format_version value.
- Rejects missing/empty string fields (omegaclaw_version, chromadb_version, created_at).
- Rejects non-UTC created_at.
- Rejects invalid components (unknown name, duplicate, non-list).
- Rejects negative or bool record_count / history_bytes.
- Rejects record_count > 0 without ltm component.
- Rejects history_bytes > 0 without history component.
- Rejects invalid checksums (bad length, non-hex).
- Rejects checksums keys that don't match components.
- Rejects missing or invalid embedding_info when ltm present.
- Rejects embedding_info when ltm absent.

validator.py — validate_checksums
- Passes when checksums match.
- Raises on mismatch.
- Raises when a listed file is absent.

validator.py — validate_collections
- Passes for valid collections.json.
- Raises when file is missing.
- Raises when name is not 'memories'.
- Raises when embedding_info does not match manifest.

validator.py — validate_records
- Passes for valid records.jsonl.
- Raises on invalid JSON.
- Raises when id is missing or empty.
- Raises when document is not a string.
- Raises when embedding contains non-numbers.
- Raises on embedding dimension mismatch.
- Raises when record count does not match manifest.
- Accepts records with empty embedding list.
"""

import hashlib
import io
import json
import tarfile
import tempfile
from pathlib import Path

import pytest

from memory_portability.archive import (
    ALLOWLIST,
    MAX_COMPRESSED_BYTES,
    MAX_EXTRACTED_BYTES,
    pack,
    unpack,
)
from memory_portability.errors import ArchiveValidationError
from memory_portability.validator import (
    validate_checksums,
    validate_collections,
    validate_manifest,
    validate_records,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _make_staging(tmp_path: Path, include_history: bool = True, include_ltm: bool = True) -> Path:
    """Create a minimal valid staging directory."""
    staging = tmp_path / "staging"
    staging.mkdir()

    history_bytes   = b"(EpisodicMemory (content \"test\"))\n"
    records_bytes   = (
        json.dumps({
            "id": "rec-1",
            "document": "hello",
            "embedding": [0.1, 0.2, 0.3, 0.4],
            "metadata": {"record_kind": "user_memory"},
        }, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    collections_bytes = json.dumps({
        "name": "memories",
        "embedding_info": {
            "provider": "Local",
            "model": "intfloat/e5-large-v2",
            "vector_dimension": 4,
        },
    }, indent=2).encode("utf-8")

    components = []
    checksums  = {}

    if include_history:
        (staging / "history").mkdir()
        (staging / "history" / "history.metta").write_bytes(history_bytes)
        checksums["history/history.metta"] = _sha256(history_bytes)
        components.append("history")

    if include_ltm:
        (staging / "vector").mkdir()
        (staging / "vector" / "records.jsonl").write_bytes(records_bytes)
        (staging / "vector" / "collections.json").write_bytes(collections_bytes)
        checksums["vector/records.jsonl"]    = _sha256(records_bytes)
        checksums["vector/collections.json"] = _sha256(collections_bytes)
        components.append("ltm")

    manifest = {
        "format_version":    1,
        "omegaclaw_version": "OmegaClaw version=0.1.18",
        "chromadb_version":  "0.6.3",
        "components":        components,
        "embedding_info":    {
            "provider": "Local",
            "model": "intfloat/e5-large-v2",
            "vector_dimension": 4,
        } if include_ltm else {},
        "record_count":  1 if include_ltm else 0,
        "history_bytes": len(history_bytes) if include_history else 0,
        "created_at":    "2026-01-01T00:00:00+00:00",
        "checksums":     checksums,
    }
    (staging / "manifest.json").write_bytes(
        json.dumps(manifest, indent=2).encode("utf-8")
    )
    return staging


def _valid_manifest(
    components=None,
    record_count=1,
    history_bytes=32,
    embedding_info=None,
) -> dict:
    """Return a valid manifest dict for unit-testing validate_manifest."""
    if components is None:
        components = ["history", "ltm"]
    if embedding_info is None:
        embedding_info = {
            "provider": "Local",
            "model": "intfloat/e5-large-v2",
            "vector_dimension": 4,
        }
    checksums = {}
    for c in components:
        from memory_portability.archive import COMPONENT_FILES
        for f in COMPONENT_FILES[c]:
            checksums[f] = "a" * 64
    return {
        "format_version":    1,
        "omegaclaw_version": "OmegaClaw version=0.1.18",
        "chromadb_version":  "0.6.3",
        "components":        components,
        "embedding_info":    embedding_info if "ltm" in components else {},
        "record_count":      record_count if "ltm" in components else 0,
        "history_bytes":     history_bytes if "history" in components else 0,
        "created_at":        "2026-01-01T00:00:00+00:00",
        "checksums":         checksums,
    }


# ---------------------------------------------------------------------------
# archive.pack tests
# ---------------------------------------------------------------------------

class TestPack:

    def test_produces_valid_targz(self, tmp_path):
        staging = _make_staging(tmp_path)
        dest = tmp_path / "out.tar.gz"
        pack(staging, dest)
        assert tarfile.is_tarfile(dest)

    def test_contains_only_allowlisted_present_members(self, tmp_path):
        staging = _make_staging(tmp_path)
        dest = tmp_path / "out.tar.gz"
        pack(staging, dest)
        with tarfile.open(dest, "r:gz") as tar:
            names = {m.name for m in tar.getmembers()}
        assert names <= ALLOWLIST

    def test_members_in_sorted_order(self, tmp_path):
        staging = _make_staging(tmp_path)
        dest = tmp_path / "out.tar.gz"
        pack(staging, dest)
        with tarfile.open(dest, "r:gz") as tar:
            names = [m.name for m in tar.getmembers()]
        assert names == sorted(names)

    def test_history_only_staging(self, tmp_path):
        staging = _make_staging(tmp_path, include_ltm=False)
        dest = tmp_path / "out.tar.gz"
        pack(staging, dest)
        with tarfile.open(dest, "r:gz") as tar:
            names = {m.name for m in tar.getmembers()}
        assert "history/history.metta" in names
        assert "vector/records.jsonl" not in names

    def test_raises_file_exists_error_when_dest_exists(self, tmp_path):
        staging = _make_staging(tmp_path)
        dest = tmp_path / "out.tar.gz"
        dest.write_bytes(b"existing")
        with pytest.raises(FileExistsError):
            pack(staging, dest)

    def test_all_members_are_regular_files(self, tmp_path):
        staging = _make_staging(tmp_path)
        dest = tmp_path / "out.tar.gz"
        pack(staging, dest)
        with tarfile.open(dest, "r:gz") as tar:
            for member in tar.getmembers():
                assert member.isfile()


# ---------------------------------------------------------------------------
# archive.unpack tests
# ---------------------------------------------------------------------------

class TestUnpack:

    def test_extracts_all_members(self, tmp_path):
        staging = _make_staging(tmp_path)
        archive = tmp_path / "out.tar.gz"
        pack(staging, archive)
        dest = tmp_path / "extracted"
        unpack(archive, dest)
        assert (dest / "manifest.json").exists()
        assert (dest / "history" / "history.metta").exists()
        assert (dest / "vector" / "records.jsonl").exists()
        assert (dest / "vector" / "collections.json").exists()

    def test_creates_dest_if_absent(self, tmp_path):
        staging = _make_staging(tmp_path)
        archive = tmp_path / "out.tar.gz"
        pack(staging, archive)
        dest = tmp_path / "brand_new_dir"
        assert not dest.exists()
        unpack(archive, dest)
        assert dest.exists()

    def test_raises_on_non_allowlisted_member(self, tmp_path):
        archive = tmp_path / "bad.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            info = tarfile.TarInfo(name="evil.sh")
            data = b"rm -rf /"
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        with pytest.raises(ArchiveValidationError, match="Unexpected"):
            unpack(archive, tmp_path / "dest")

    def test_raises_on_duplicate_member(self, tmp_path):
        archive = tmp_path / "dup.tar.gz"
        data = b"content"
        with tarfile.open(archive, "w:gz") as tar:
            for _ in range(2):
                info = tarfile.TarInfo(name="manifest.json")
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
        with pytest.raises(ArchiveValidationError, match="Duplicate"):
            unpack(archive, tmp_path / "dest")

    def test_raises_on_path_traversal(self, tmp_path):
        archive = tmp_path / "traversal.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            info = tarfile.TarInfo(name="../etc/passwd")
            data = b"root:x:0:0"
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        with pytest.raises(ArchiveValidationError):
            unpack(archive, tmp_path / "dest")

    def test_raises_when_compressed_size_exceeds_limit(self, tmp_path):
        staging = _make_staging(tmp_path)
        archive = tmp_path / "out.tar.gz"
        pack(staging, archive)
        # Fake the file size by monkey-patching stat
        import unittest.mock as mock
        fake_stat = mock.MagicMock()
        fake_stat.st_size = MAX_COMPRESSED_BYTES + 1
        with mock.patch.object(Path, "stat", return_value=fake_stat):
            with pytest.raises(ArchiveValidationError, match="too large"):
                unpack(archive, tmp_path / "dest")

    def test_raises_when_extracted_size_exceeds_limit(self, tmp_path):
        # Build a real valid archive, then patch the TarInfo.size attribute
        # seen during the validation pass so the cumulative total exceeds the
        # limit without actually writing 2 GB of data.
        staging = _make_staging(tmp_path)
        archive = tmp_path / "out.tar.gz"
        pack(staging, archive)

        import unittest.mock as mock

        original_open = tarfile.open

        def patched_open(path, mode):
            tf = original_open(path, mode)
            members = tf.getmembers()
            if members:
                # Make the first member appear huge in the header
                members[0].size = MAX_EXTRACTED_BYTES + 1
            original_getmembers = tf.getmembers
            tf.getmembers = lambda: members
            return tf

        with mock.patch("memory_portability.archive.tarfile.open", side_effect=patched_open):
            with pytest.raises(ArchiveValidationError, match="exceeds limit"):
                unpack(archive, tmp_path / "dest")

    def test_raises_on_symlink_member(self, tmp_path):
        archive = tmp_path / "sym.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            info = tarfile.TarInfo(name="manifest.json")
            info.type = tarfile.SYMTYPE
            info.linkname = "/etc/passwd"
            tar.addfile(info)
        with pytest.raises(ArchiveValidationError, match="Non-regular"):
            unpack(archive, tmp_path / "dest")

    def test_round_trip_content_matches(self, tmp_path):
        staging = _make_staging(tmp_path)
        archive = tmp_path / "out.tar.gz"
        pack(staging, archive)
        dest = tmp_path / "extracted"
        unpack(archive, dest)
        original = (staging / "history" / "history.metta").read_bytes()
        restored = (dest   / "history" / "history.metta").read_bytes()
        assert original == restored

    def test_v1_fixture_unpacks_cleanly(self, tmp_path, v1_fixture_path):
        dest = tmp_path / "fixture_extracted"
        unpack(v1_fixture_path, dest)
        assert (dest / "manifest.json").exists()
        assert (dest / "history" / "history.metta").exists()
        assert (dest / "vector" / "records.jsonl").exists()
        assert (dest / "vector" / "collections.json").exists()


# ---------------------------------------------------------------------------
# validator.validate_manifest tests
# ---------------------------------------------------------------------------

class TestValidateManifest:

    def test_accepts_valid_manifest(self):
        m = _valid_manifest()
        assert validate_manifest(m) is m

    def test_accepts_history_only_manifest(self):
        m = _valid_manifest(components=["history"], record_count=0, history_bytes=32)
        assert validate_manifest(m) is m

    def test_accepts_ltm_only_manifest(self):
        m = _valid_manifest(components=["ltm"], record_count=1, history_bytes=0)
        assert validate_manifest(m) is m

    def test_rejects_non_dict(self):
        with pytest.raises(ArchiveValidationError, match="JSON object"):
            validate_manifest([])

    def test_rejects_bool_format_version(self):
        m = _valid_manifest()
        m["format_version"] = True
        with pytest.raises(ArchiveValidationError, match="format_version"):
            validate_manifest(m)

    def test_rejects_string_format_version(self):
        m = _valid_manifest()
        m["format_version"] = "1"
        with pytest.raises(ArchiveValidationError, match="format_version"):
            validate_manifest(m)

    def test_rejects_unsupported_format_version(self):
        m = _valid_manifest()
        m["format_version"] = 99
        with pytest.raises(ArchiveValidationError, match="Unsupported format_version"):
            validate_manifest(m)

    @pytest.mark.parametrize("field", ["omegaclaw_version", "chromadb_version"])
    def test_rejects_empty_string_fields(self, field):
        m = _valid_manifest()
        m[field] = ""
        with pytest.raises(ArchiveValidationError, match=field):
            validate_manifest(m)

    def test_rejects_invalid_created_at(self):
        m = _valid_manifest()
        m["created_at"] = "not-a-date"
        with pytest.raises(ArchiveValidationError):
            validate_manifest(m)

    def test_rejects_non_utc_created_at(self):
        m = _valid_manifest()
        m["created_at"] = "2026-01-01T00:00:00+03:00"
        with pytest.raises(ArchiveValidationError, match="UTC"):
            validate_manifest(m)

    def test_rejects_unknown_component(self):
        m = _valid_manifest()
        m["components"] = ["history", "unknown"]
        with pytest.raises(ArchiveValidationError, match="components"):
            validate_manifest(m)

    def test_rejects_duplicate_component(self):
        m = _valid_manifest()
        m["components"] = ["history", "history"]
        with pytest.raises(ArchiveValidationError, match="components"):
            validate_manifest(m)

    def test_rejects_bool_record_count(self):
        m = _valid_manifest()
        m["record_count"] = True
        with pytest.raises(ArchiveValidationError, match="record_count"):
            validate_manifest(m)

    def test_rejects_negative_record_count(self):
        m = _valid_manifest()
        m["record_count"] = -1
        with pytest.raises(ArchiveValidationError, match="record_count"):
            validate_manifest(m)

    def test_rejects_record_count_without_ltm(self):
        m = _valid_manifest(components=["history"], record_count=0, history_bytes=32)
        m["record_count"] = 1
        with pytest.raises(ArchiveValidationError, match="record_count"):
            validate_manifest(m)

    def test_rejects_history_bytes_without_history(self):
        m = _valid_manifest(components=["ltm"], record_count=1, history_bytes=0)
        m["history_bytes"] = 100
        with pytest.raises(ArchiveValidationError, match="history_bytes"):
            validate_manifest(m)

    def test_rejects_bad_checksum_length(self):
        m = _valid_manifest()
        key = next(iter(m["checksums"]))
        m["checksums"][key] = "abc123"
        with pytest.raises(ArchiveValidationError, match="SHA-256"):
            validate_manifest(m)

    def test_rejects_non_hex_checksum(self):
        m = _valid_manifest()
        key = next(iter(m["checksums"]))
        m["checksums"][key] = "z" * 64
        with pytest.raises(ArchiveValidationError, match="SHA-256"):
            validate_manifest(m)

    def test_rejects_extra_checksum_key(self):
        m = _valid_manifest()
        m["checksums"]["extra/file.txt"] = "a" * 64
        with pytest.raises(ArchiveValidationError, match="checksums keys"):
            validate_manifest(m)

    def test_rejects_missing_embedding_info_when_ltm_present(self):
        m = _valid_manifest()
        del m["embedding_info"]
        with pytest.raises(ArchiveValidationError, match="embedding_info"):
            validate_manifest(m)

    def test_rejects_zero_vector_dimension(self):
        m = _valid_manifest()
        m["embedding_info"]["vector_dimension"] = 0
        with pytest.raises(ArchiveValidationError, match="embedding_info"):
            validate_manifest(m)

    def test_rejects_embedding_info_when_ltm_absent(self):
        m = _valid_manifest(components=["history"], record_count=0, history_bytes=32)
        m["embedding_info"] = {"provider": "Local", "model": "x", "vector_dimension": 4}
        with pytest.raises(ArchiveValidationError, match="embedding_info"):
            validate_manifest(m)


# ---------------------------------------------------------------------------
# validator.validate_checksums tests
# ---------------------------------------------------------------------------

class TestValidateChecksums:

    def test_passes_when_checksums_match(self, tmp_path):
        staging = _make_staging(tmp_path)
        manifest = json.loads((staging / "manifest.json").read_text())
        # validate_checksums does not check manifest.json itself
        validate_checksums(staging, manifest)  # must not raise

    def test_raises_on_checksum_mismatch(self, tmp_path):
        staging = _make_staging(tmp_path)
        manifest = json.loads((staging / "manifest.json").read_text())
        # Corrupt one file after building the manifest
        (staging / "history" / "history.metta").write_bytes(b"corrupted")
        with pytest.raises(ArchiveValidationError, match="Checksum mismatch"):
            validate_checksums(staging, manifest)

    def test_raises_when_listed_file_absent(self, tmp_path):
        staging = _make_staging(tmp_path)
        manifest = json.loads((staging / "manifest.json").read_text())
        (staging / "history" / "history.metta").unlink()
        with pytest.raises(ArchiveValidationError, match="missing from staging"):
            validate_checksums(staging, manifest)


# ---------------------------------------------------------------------------
# validator.validate_collections tests
# ---------------------------------------------------------------------------

class TestValidateCollections:

    def _manifest_with_ltm(self) -> dict:
        return _valid_manifest(components=["ltm"], record_count=1, history_bytes=0)

    def test_passes_for_valid_collections(self, tmp_path):
        staging = _make_staging(tmp_path, include_history=False)
        manifest = json.loads((staging / "manifest.json").read_text())
        validate_collections(staging, manifest)  # must not raise

    def test_raises_when_file_missing(self, tmp_path):
        staging = _make_staging(tmp_path, include_history=False)
        manifest = json.loads((staging / "manifest.json").read_text())
        (staging / "vector" / "collections.json").unlink()
        with pytest.raises(ArchiveValidationError, match="missing"):
            validate_collections(staging, manifest)

    def test_raises_when_name_not_memories(self, tmp_path):
        staging = _make_staging(tmp_path, include_history=False)
        manifest = json.loads((staging / "manifest.json").read_text())
        data = json.loads((staging / "vector" / "collections.json").read_text())
        data["name"] = "other"
        (staging / "vector" / "collections.json").write_text(json.dumps(data))
        with pytest.raises(ArchiveValidationError, match="'memories'"):
            validate_collections(staging, manifest)

    def test_raises_when_embedding_info_mismatch(self, tmp_path):
        staging = _make_staging(tmp_path, include_history=False)
        manifest = json.loads((staging / "manifest.json").read_text())
        data = json.loads((staging / "vector" / "collections.json").read_text())
        data["embedding_info"]["provider"] = "OpenAI"
        (staging / "vector" / "collections.json").write_text(json.dumps(data))
        with pytest.raises(ArchiveValidationError, match="embedding_info"):
            validate_collections(staging, manifest)

    def test_raises_on_invalid_json(self, tmp_path):
        staging = _make_staging(tmp_path, include_history=False)
        manifest = json.loads((staging / "manifest.json").read_text())
        (staging / "vector" / "collections.json").write_bytes(b"not json {{{")
        with pytest.raises(ArchiveValidationError, match="not valid JSON"):
            validate_collections(staging, manifest)


# ---------------------------------------------------------------------------
# validator.validate_records tests
# ---------------------------------------------------------------------------

class TestValidateRecords:

    def _manifest(self, record_count=1, dimension=4) -> dict:
        return {
            "record_count":  record_count,
            "embedding_info": {"vector_dimension": dimension},
        }

    def _write_records(self, staging: Path, records: list[dict]) -> None:
        (staging / "vector").mkdir(parents=True, exist_ok=True)
        lines = "\n".join(json.dumps(r) for r in records) + "\n"
        (staging / "vector" / "records.jsonl").write_text(lines, encoding="utf-8")

    def test_passes_for_valid_records(self, tmp_path):
        staging = _make_staging(tmp_path, include_history=False)
        manifest = json.loads((staging / "manifest.json").read_text())
        validate_records(staging, manifest)  # must not raise

    def test_accepts_empty_embedding_list(self, tmp_path):
        records = [{"id": "r1", "document": "doc", "embedding": [], "metadata": {}}]
        self._write_records(tmp_path, records)
        validate_records(tmp_path, self._manifest(record_count=1, dimension=4))

    def test_raises_on_invalid_json_line(self, tmp_path):
        (tmp_path / "vector").mkdir(parents=True, exist_ok=True)
        (tmp_path / "vector" / "records.jsonl").write_text("not json\n")
        with pytest.raises(ArchiveValidationError, match="Invalid JSONL"):
            validate_records(tmp_path, self._manifest())

    def test_raises_when_id_missing(self, tmp_path):
        records = [{"document": "doc", "embedding": [0.1]*4, "metadata": {}}]
        self._write_records(tmp_path, records)
        with pytest.raises(ArchiveValidationError, match="invalid or missing id"):
            validate_records(tmp_path, self._manifest())

    def test_raises_when_id_is_empty_string(self, tmp_path):
        records = [{"id": "", "document": "doc", "embedding": [0.1]*4, "metadata": {}}]
        self._write_records(tmp_path, records)
        with pytest.raises(ArchiveValidationError, match="invalid or missing id"):
            validate_records(tmp_path, self._manifest())

    def test_raises_when_document_is_not_string(self, tmp_path):
        records = [{"id": "r1", "document": 123, "embedding": [0.1]*4, "metadata": {}}]
        self._write_records(tmp_path, records)
        with pytest.raises(ArchiveValidationError, match="non-string document"):
            validate_records(tmp_path, self._manifest())

    def test_raises_when_embedding_contains_string(self, tmp_path):
        records = [{"id": "r1", "document": "doc", "embedding": ["bad"], "metadata": {}}]
        self._write_records(tmp_path, records)
        with pytest.raises(ArchiveValidationError, match="invalid embedding"):
            validate_records(tmp_path, self._manifest())

    def test_raises_on_embedding_dimension_mismatch(self, tmp_path):
        records = [{"id": "r1", "document": "doc", "embedding": [0.1, 0.2], "metadata": {}}]
        self._write_records(tmp_path, records)
        with pytest.raises(ArchiveValidationError, match="dimension"):
            validate_records(tmp_path, self._manifest(dimension=4))

    def test_raises_when_record_count_mismatch(self, tmp_path):
        records = [
            {"id": "r1", "document": "a", "embedding": [0.1]*4, "metadata": {}},
            {"id": "r2", "document": "b", "embedding": [0.2]*4, "metadata": {}},
        ]
        self._write_records(tmp_path, records)
        with pytest.raises(ArchiveValidationError, match="record count mismatch"):
            validate_records(tmp_path, self._manifest(record_count=1))

    def test_raises_when_file_missing(self, tmp_path):
        (tmp_path / "vector").mkdir(parents=True, exist_ok=True)
        with pytest.raises(ArchiveValidationError, match="missing"):
            validate_records(tmp_path, self._manifest(record_count=0))
