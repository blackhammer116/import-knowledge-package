"""
Step 1 scaffold smoke tests.

These tests verify that:
- The package is importable.
- The public API symbols are accessible from the top-level namespace.
- The v1 OmegaClaw archive fixture is a valid tar.gz containing the
  expected members and a well-formed manifest.
- The fixture manifest fields match the v1 format contract exactly.
"""

import json
import tarfile

import pytest

from memory_portability.archive import ALLOWLIST, ARCHIVE_FORMAT_VERSION, COMPONENT_FILES


class TestPackageImports:
    """Package and public API are importable."""

    def test_import_memory_portability(self):
        import memory_portability  # noqa: F401

    def test_memory_backend_importable(self):
        from memory_portability import MemoryBackend
        assert MemoryBackend is not None

    def test_memory_transfer_importable(self):
        from memory_portability import MemoryTransfer
        assert MemoryTransfer is not None

    def test_errors_importable(self):
        from memory_portability import (
            MemoryPortabilityError,
            ArchiveValidationError,
            ExportError,
            RecoveryError,
        )
        # ImportError shadows builtins — confirm it is our subclass
        from memory_portability import ImportError as MpImportError
        assert issubclass(MpImportError, MemoryPortabilityError)

    def test_error_hierarchy(self):
        from memory_portability import (
            MemoryPortabilityError,
            ArchiveValidationError,
            ExportError,
            ImportError as MpImportError,
            RecoveryError,
        )
        for cls in (ArchiveValidationError, ExportError, MpImportError, RecoveryError):
            assert issubclass(cls, MemoryPortabilityError)


class TestArchiveConstants:
    """Archive constants match the OmegaClaw v1 format contract."""

    def test_format_version_is_one(self):
        assert ARCHIVE_FORMAT_VERSION == 1

    def test_allowlist_members(self):
        assert ALLOWLIST == frozenset([
            "manifest.json",
            "history/history.metta",
            "vector/collections.json",
            "vector/records.jsonl",
        ])

    def test_component_files_history(self):
        assert COMPONENT_FILES["history"] == {"history/history.metta"}

    def test_component_files_ltm(self):
        assert COMPONENT_FILES["ltm"] == {"vector/collections.json", "vector/records.jsonl"}


class TestV1Fixture:
    """The v1 OmegaClaw archive fixture is structurally correct."""

    def test_fixture_is_valid_targz(self, v1_fixture_path):
        assert tarfile.is_tarfile(v1_fixture_path)

    def test_fixture_contains_exactly_allowlisted_members(self, v1_fixture_path):
        with tarfile.open(v1_fixture_path, "r:gz") as tar:
            names = {m.name for m in tar.getmembers()}
        # Fixture includes all four members (history + ltm + manifest)
        assert names == ALLOWLIST

    def test_fixture_all_members_are_regular_files(self, v1_fixture_path):
        with tarfile.open(v1_fixture_path, "r:gz") as tar:
            for member in tar.getmembers():
                assert member.isfile(), f"{member.name} is not a regular file"

    def test_fixture_manifest_is_valid_json(self, v1_fixture_manifest):
        assert isinstance(v1_fixture_manifest, dict)

    def test_fixture_manifest_format_version(self, v1_fixture_manifest):
        assert v1_fixture_manifest["format_version"] == 1

    def test_fixture_manifest_has_omegaclaw_version(self, v1_fixture_manifest):
        assert isinstance(v1_fixture_manifest.get("omegaclaw_version"), str)
        assert v1_fixture_manifest["omegaclaw_version"]

    def test_fixture_manifest_has_chromadb_version(self, v1_fixture_manifest):
        assert isinstance(v1_fixture_manifest.get("chromadb_version"), str)
        assert v1_fixture_manifest["chromadb_version"]

    def test_fixture_manifest_components(self, v1_fixture_manifest):
        assert set(v1_fixture_manifest["components"]) == {"history", "ltm"}

    def test_fixture_manifest_embedding_info(self, v1_fixture_manifest):
        info = v1_fixture_manifest["embedding_info"]
        assert isinstance(info["provider"], str)
        assert isinstance(info["model"], str)
        assert isinstance(info["vector_dimension"], int)
        assert info["vector_dimension"] > 0

    def test_fixture_manifest_record_count(self, v1_fixture_manifest):
        assert v1_fixture_manifest["record_count"] == 2

    def test_fixture_manifest_history_bytes(self, v1_fixture_manifest):
        assert isinstance(v1_fixture_manifest["history_bytes"], int)
        assert v1_fixture_manifest["history_bytes"] > 0

    def test_fixture_manifest_created_at_utc(self, v1_fixture_manifest):
        from datetime import datetime, timezone
        created_at = datetime.fromisoformat(
            v1_fixture_manifest["created_at"].replace("Z", "+00:00")
        )
        assert created_at.tzinfo is not None

    def test_fixture_manifest_checksums_keys_match_components(self, v1_fixture_manifest):
        expected_keys = (
            COMPONENT_FILES["history"] | COMPONENT_FILES["ltm"]
        )
        assert set(v1_fixture_manifest["checksums"]) == expected_keys

    def test_fixture_manifest_checksums_are_sha256_hex(self, v1_fixture_manifest):
        for name, digest in v1_fixture_manifest["checksums"].items():
            assert len(digest) == 64, f"Bad checksum length for {name}"
            assert all(c in "0123456789abcdef" for c in digest.lower())

    def test_fixture_records_jsonl_has_two_records(self, v1_fixture_path):
        with tarfile.open(v1_fixture_path, "r:gz") as tar:
            f = tar.extractfile("vector/records.jsonl")
            assert f is not None
            lines = [l for l in f.read().decode("utf-8").splitlines() if l.strip()]
        assert len(lines) == 2

    def test_fixture_records_have_required_fields(self, v1_fixture_path):
        with tarfile.open(v1_fixture_path, "r:gz") as tar:
            f = tar.extractfile("vector/records.jsonl")
            assert f is not None
            for line in f.read().decode("utf-8").splitlines():
                if not line.strip():
                    continue
                record = json.loads(line)
                assert isinstance(record["id"], str) and record["id"]
                assert isinstance(record["document"], str)
                assert isinstance(record["embedding"], list)
                assert isinstance(record["metadata"], dict)
