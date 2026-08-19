"""
Step 4 tests: extractor.py and reembedder.py.

extractor.py
- iter_staged_records yields correct batches from a valid records.jsonl.
- iter_staged_records respects batch_size.
- iter_staged_records raises ArchiveValidationError on invalid JSON.
- iter_staged_records raises ArchiveValidationError on missing id.
- iter_staged_records raises ArchiveValidationError on non-string document.
- iter_staged_records raises ArchiveValidationError on invalid embedding values.
- iter_staged_records skips blank lines.
- iter_staged_records yields nothing when file is empty.
- iter_staged_records normalises metadata (None→"null", list→JSON, dict→JSON).
- iter_staged_records coerces int embeddings to float.
- read_staged_history returns content when file exists.
- read_staged_history returns None when file is absent.
- normalise_metadata passes through scalar values unchanged.
- normalise_metadata converts None to "null".
- normalise_metadata JSON-encodes lists and dicts.
- normalise_metadata converts unknown types via str().
- normalise_metadata raises on non-dict input.
- normalise_metadata raises on non-string or empty key.
- v1 fixture: iter_staged_records yields all records correctly.
- v1 fixture: read_staged_history returns non-empty string.

reembedder.py
- needs_reembedding returns False when profiles match.
- needs_reembedding returns True when provider differs.
- needs_reembedding returns True when model differs.
- needs_reembedding returns True when vector_dimension differs.
- needs_reembedding returns True when vector_dimension is zero.
- reembed_staged_records rewrites embeddings from backend.embed().
- reembed_staged_records uses correct batch_size when calling embed().
- reembed_staged_records overwrites file atomically (tmp gone after success).
- reembed_staged_records raises ExportError when embed() returns wrong length.
- reembed_staged_records raises ExportError when embed() returns wrong dimension.
- reembed_staged_records removes tmp file on error.
- reembed_staged_records result is readable by iter_staged_records.
- reembed_staged_records preserves record IDs and documents.
"""

import json
from pathlib import Path

import pytest

from memory_portability.errors import ArchiveValidationError, ImportError
from memory_portability.extractor import (
    iter_staged_records,
    normalise_metadata,
    read_staged_history,
)
from memory_portability.reembedder import needs_reembedding, reembed_staged_records
from tests.test_backend import FakeBackend

from memory_portability.archive import unpack


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_records(staging: Path, records: list[dict]) -> None:
    """Write records as JSONL into staging/vector/records.jsonl."""
    (staging / "vector").mkdir(parents=True, exist_ok=True)
    lines = "\n".join(json.dumps(r) for r in records) + "\n"
    (staging / "vector" / "records.jsonl").write_text(lines, encoding="utf-8")


def _write_history(staging: Path, content: str) -> None:
    (staging / "history").mkdir(parents=True, exist_ok=True)
    (staging / "history" / "history.metta").write_text(content, encoding="utf-8")


def _make_record(record_id: str, doc: str = "doc", dim: int = 4) -> dict:
    return {
        "id":        record_id,
        "document":  doc,
        "embedding": [0.1 * i for i in range(dim)],
        "metadata":  {"record_kind": "user_memory"},
    }


# ---------------------------------------------------------------------------
# extractor — iter_staged_records
# ---------------------------------------------------------------------------

class TestIterStagedRecords:

    def test_yields_all_records(self, tmp_path):
        records = [_make_record(f"r{i}") for i in range(3)]
        _write_records(tmp_path, records)
        result = [r for batch in iter_staged_records(tmp_path) for r in batch]
        assert len(result) == 3
        assert {r["id"] for r in result} == {"r0", "r1", "r2"}

    def test_respects_batch_size(self, tmp_path):
        records = [_make_record(f"r{i}") for i in range(5)]
        _write_records(tmp_path, records)
        batches = list(iter_staged_records(tmp_path, batch_size=2))
        assert all(len(b) <= 2 for b in batches)
        assert sum(len(b) for b in batches) == 5

    def test_last_batch_smaller_than_batch_size(self, tmp_path):
        records = [_make_record(f"r{i}") for i in range(3)]
        _write_records(tmp_path, records)
        batches = list(iter_staged_records(tmp_path, batch_size=2))
        assert len(batches[-1]) == 1

    def test_skips_blank_lines(self, tmp_path):
        (tmp_path / "vector").mkdir()
        content = (
            json.dumps(_make_record("r1")) + "\n"
            "\n"
            "   \n"
            + json.dumps(_make_record("r2")) + "\n"
        )
        (tmp_path / "vector" / "records.jsonl").write_text(content)
        result = [r for b in iter_staged_records(tmp_path) for r in b]
        assert len(result) == 2

    def test_yields_nothing_for_empty_file(self, tmp_path):
        (tmp_path / "vector").mkdir()
        (tmp_path / "vector" / "records.jsonl").write_text("")
        assert list(iter_staged_records(tmp_path)) == []

    def test_raises_on_invalid_json(self, tmp_path):
        (tmp_path / "vector").mkdir()
        (tmp_path / "vector" / "records.jsonl").write_text("not json\n")
        with pytest.raises(ArchiveValidationError, match="Invalid JSONL"):
            list(iter_staged_records(tmp_path))

    def test_raises_on_missing_id(self, tmp_path):
        records = [{"document": "doc", "embedding": [0.1]*4, "metadata": {}}]
        _write_records(tmp_path, records)
        with pytest.raises(ArchiveValidationError, match="invalid or missing id"):
            list(iter_staged_records(tmp_path))

    def test_raises_on_empty_id(self, tmp_path):
        records = [{"id": "", "document": "doc", "embedding": [0.1]*4, "metadata": {}}]
        _write_records(tmp_path, records)
        with pytest.raises(ArchiveValidationError, match="invalid or missing id"):
            list(iter_staged_records(tmp_path))

    def test_raises_on_non_string_document(self, tmp_path):
        records = [{"id": "r1", "document": 42, "embedding": [0.1]*4, "metadata": {}}]
        _write_records(tmp_path, records)
        with pytest.raises(ArchiveValidationError, match="non-string document"):
            list(iter_staged_records(tmp_path))

    def test_raises_on_invalid_embedding_value(self, tmp_path):
        records = [{"id": "r1", "document": "doc", "embedding": ["bad"], "metadata": {}}]
        _write_records(tmp_path, records)
        with pytest.raises(ArchiveValidationError, match="invalid embedding"):
            list(iter_staged_records(tmp_path))

    def test_coerces_int_embeddings_to_float(self, tmp_path):
        records = [{"id": "r1", "document": "doc", "embedding": [1, 2, 3, 4], "metadata": {}}]
        _write_records(tmp_path, records)
        result = [r for b in iter_staged_records(tmp_path) for r in b]
        for v in result[0]["embedding"]:
            assert isinstance(v, float)

    def test_normalises_none_metadata_value(self, tmp_path):
        records = [{"id": "r1", "document": "doc", "embedding": [],
                    "metadata": {"key": None}}]
        _write_records(tmp_path, records)
        result = [r for b in iter_staged_records(tmp_path) for r in b]
        assert result[0]["metadata"]["key"] == "null"

    def test_normalises_list_metadata_value(self, tmp_path):
        records = [{"id": "r1", "document": "doc", "embedding": [],
                    "metadata": {"tags": ["a", "b"]}}]
        _write_records(tmp_path, records)
        result = [r for b in iter_staged_records(tmp_path) for r in b]
        assert json.loads(result[0]["metadata"]["tags"]) == ["a", "b"]

    def test_normalises_dict_metadata_value(self, tmp_path):
        records = [{"id": "r1", "document": "doc", "embedding": [],
                    "metadata": {"nested": {"x": 1}}}]
        _write_records(tmp_path, records)
        result = [r for b in iter_staged_records(tmp_path) for r in b]
        assert json.loads(result[0]["metadata"]["nested"]) == {"x": 1}

    def test_v1_fixture_yields_two_records(self, tmp_path, v1_fixture_path):
        dest = tmp_path / "extracted"
        unpack(v1_fixture_path, dest)
        result = [r for b in iter_staged_records(dest) for r in b]
        assert len(result) == 2

    def test_v1_fixture_records_have_required_fields(self, tmp_path, v1_fixture_path):
        dest = tmp_path / "extracted"
        unpack(v1_fixture_path, dest)
        for rec in (r for b in iter_staged_records(dest) for r in b):
            assert isinstance(rec["id"], str) and rec["id"]
            assert isinstance(rec["document"], str)
            assert isinstance(rec["embedding"], list)
            assert isinstance(rec["metadata"], dict)


# ---------------------------------------------------------------------------
# extractor — read_staged_history
# ---------------------------------------------------------------------------

class TestReadStagedHistory:

    def test_returns_content_when_file_exists(self, tmp_path):
        _write_history(tmp_path, "some history content\n")
        assert read_staged_history(tmp_path) == "some history content\n"

    def test_returns_none_when_file_absent(self, tmp_path):
        assert read_staged_history(tmp_path) is None

    def test_v1_fixture_returns_non_empty_string(self, tmp_path, v1_fixture_path):
        dest = tmp_path / "extracted"
        unpack(v1_fixture_path, dest)
        history = read_staged_history(dest)
        assert isinstance(history, str) and len(history) > 0


# ---------------------------------------------------------------------------
# extractor — normalise_metadata
# ---------------------------------------------------------------------------

class TestNormaliseMetadata:

    def test_passes_through_string(self):
        assert normalise_metadata({"k": "v"}) == {"k": "v"}

    def test_passes_through_int(self):
        assert normalise_metadata({"k": 1}) == {"k": 1}

    def test_passes_through_float(self):
        assert normalise_metadata({"k": 1.5}) == {"k": 1.5}

    def test_passes_through_bool(self):
        assert normalise_metadata({"k": True}) == {"k": True}

    def test_converts_none_to_null_string(self):
        assert normalise_metadata({"k": None}) == {"k": "null"}

    def test_json_encodes_list(self):
        result = normalise_metadata({"k": [1, 2]})
        assert json.loads(result["k"]) == [1, 2]

    def test_json_encodes_dict(self):
        result = normalise_metadata({"k": {"a": 1}})
        assert json.loads(result["k"]) == {"a": 1}

    def test_converts_unknown_type_via_str(self):
        result = normalise_metadata({"k": object.__new__(object)})
        assert isinstance(result["k"], str)

    def test_raises_on_non_dict_input(self):
        with pytest.raises(ArchiveValidationError, match="JSON object"):
            normalise_metadata(["not", "a", "dict"])

    def test_raises_on_empty_string_key(self):
        with pytest.raises(ArchiveValidationError, match="non-empty strings"):
            normalise_metadata({"": "value"})

    def test_dict_json_encoding_is_deterministic(self):
        meta = {"k": {"b": 2, "a": 1}}
        r1 = normalise_metadata(meta)
        r2 = normalise_metadata(meta)
        assert r1 == r2


# ---------------------------------------------------------------------------
# reembedder — needs_reembedding
# ---------------------------------------------------------------------------

class TestNeedsReembedding:

    def _manifest(self, provider="Local", model="intfloat/e5-large-v2", dim=4) -> dict:
        return {
            "embedding_info": {
                "provider":         provider,
                "model":            model,
                "vector_dimension": dim,
            }
        }

    def test_returns_false_when_profiles_match(self, tmp_path):
        backend = FakeBackend(tmp_path)
        profile = backend.get_embedding_profile()
        manifest = self._manifest(
            provider=profile["provider"],
            model=profile["model"],
            dim=profile["vector_dimension"],
        )
        assert needs_reembedding(manifest, backend) is False

    def test_returns_true_when_provider_differs(self, tmp_path):
        backend = FakeBackend(tmp_path)
        manifest = self._manifest(provider="OpenAI")
        assert needs_reembedding(manifest, backend) is True

    def test_returns_true_when_model_differs(self, tmp_path):
        backend = FakeBackend(tmp_path)
        manifest = self._manifest(model="all-MiniLM-L6-v2")
        assert needs_reembedding(manifest, backend) is True

    def test_returns_true_when_dimension_differs(self, tmp_path):
        backend = FakeBackend(tmp_path)
        manifest = self._manifest(dim=1536)
        assert needs_reembedding(manifest, backend) is True

    def test_returns_true_when_dimension_is_zero(self, tmp_path):
        backend = FakeBackend(tmp_path)
        manifest = self._manifest(dim=0)
        assert needs_reembedding(manifest, backend) is True

    def test_returns_true_when_archive_has_missing_embeddings(self, tmp_path):
        backend = FakeBackend(tmp_path)
        assert needs_reembedding(self._manifest(), backend, embeddings_missing=True) is True

    def test_returns_true_when_runtime_dimension_is_unknown(self, tmp_path):
        backend = FakeBackend(tmp_path)
        profile = backend.get_embedding_profile()
        backend.get_embedding_profile = lambda: {**profile, "vector_dimension": None}
        manifest = self._manifest(
            provider=profile["provider"], model=profile["model"], dim=4
        )
        assert needs_reembedding(manifest, backend) is True


# ---------------------------------------------------------------------------
# reembedder — reembed_staged_records
# ---------------------------------------------------------------------------

class TestReembedStagedRecords:

    def _staging_with_records(self, tmp_path: Path, records: list[dict]) -> Path:
        staging = tmp_path / "staging"
        staging.mkdir()
        (staging / "vector").mkdir()
        lines = "\n".join(json.dumps(r) for r in records) + "\n"
        (staging / "vector" / "records.jsonl").write_text(lines)
        return staging

    def test_rewrites_embeddings(self, tmp_path):
        backend = FakeBackend(tmp_path)
        records = [
            {"id": "r1", "document": "hello", "embedding": [], "metadata": {}},
            {"id": "r2", "document": "world", "embedding": [], "metadata": {}},
        ]
        staging = self._staging_with_records(tmp_path, records)
        reembed_staged_records(staging, backend)

        result = [r for b in iter_staged_records(staging) for r in b]
        dim = backend.get_embedding_profile()["vector_dimension"]
        for rec in result:
            assert len(rec["embedding"]) == dim
            assert all(isinstance(v, float) for v in rec["embedding"])

    def test_uses_batch_size(self, tmp_path):
        backend = FakeBackend(tmp_path)
        records = [{"id": f"r{i}", "document": f"doc {i}", "embedding": [], "metadata": {}}
                   for i in range(5)]
        staging = self._staging_with_records(tmp_path, records)
        reembed_staged_records(staging, backend, batch_size=2)
        # 5 records / batch_size 2 → 3 embed() calls
        assert len(backend._embed_calls) == 3
        assert len(backend._embed_calls[0]) == 2
        assert len(backend._embed_calls[1]) == 2
        assert len(backend._embed_calls[2]) == 1

    def test_tmp_file_removed_after_success(self, tmp_path):
        backend = FakeBackend(tmp_path)
        records = [{"id": "r1", "document": "doc", "embedding": [], "metadata": {}}]
        staging = self._staging_with_records(tmp_path, records)
        reembed_staged_records(staging, backend)
        tmp = staging / "vector" / "records.jsonl.tmp"
        assert not tmp.exists()

    def test_tmp_file_removed_on_error(self, tmp_path):
        """If embed() raises, the tmp file must be cleaned up."""
        backend = FakeBackend(tmp_path)

        def bad_embed(texts):
            raise RuntimeError("embed failed")

        backend.embed = bad_embed
        records = [{"id": "r1", "document": "doc", "embedding": [], "metadata": {}}]
        staging = self._staging_with_records(tmp_path, records)
        with pytest.raises(RuntimeError):
            reembed_staged_records(staging, backend)
        tmp = staging / "vector" / "records.jsonl.tmp"
        assert not tmp.exists()

    def test_raises_when_embed_returns_wrong_length(self, tmp_path):
        backend = FakeBackend(tmp_path)

        def short_embed(texts):
            return []  # returns nothing regardless of input

        backend.embed = short_embed
        records = [{"id": "r1", "document": "doc", "embedding": [], "metadata": {}}]
        staging = self._staging_with_records(tmp_path, records)
        with pytest.raises(ImportError, match="returned 0 embeddings"):
            reembed_staged_records(staging, backend)

    def test_raises_when_embed_returns_wrong_dimension(self, tmp_path):
        backend = FakeBackend(tmp_path)
        expected_dim = backend.get_embedding_profile()["vector_dimension"]

        def wrong_dim_embed(texts):
            return [[0.1] * (expected_dim + 10)] * len(texts)

        backend.embed = wrong_dim_embed
        records = [{"id": "r1", "document": "doc", "embedding": [], "metadata": {}}]
        staging = self._staging_with_records(tmp_path, records)
        with pytest.raises(ImportError, match="dimension"):
            reembed_staged_records(staging, backend)

    def test_preserves_record_ids_and_documents(self, tmp_path):
        backend = FakeBackend(tmp_path)
        records = [
            {"id": "keep-id-1", "document": "keep this text", "embedding": [], "metadata": {}},
            {"id": "keep-id-2", "document": "also keep",      "embedding": [], "metadata": {}},
        ]
        staging = self._staging_with_records(tmp_path, records)
        reembed_staged_records(staging, backend)
        result = [r for b in iter_staged_records(staging) for r in b]
        assert result[0]["id"]       == "keep-id-1"
        assert result[0]["document"] == "keep this text"
        assert result[1]["id"]       == "keep-id-2"
        assert result[1]["document"] == "also keep"

    def test_result_readable_by_iter_staged_records(self, tmp_path):
        backend = FakeBackend(tmp_path)
        records = [{"id": f"r{i}", "document": f"doc {i}", "embedding": [], "metadata": {}}
                   for i in range(3)]
        staging = self._staging_with_records(tmp_path, records)
        reembed_staged_records(staging, backend)
        result = [r for b in iter_staged_records(staging) for r in b]
        assert len(result) == 3

    def test_embeddings_are_floats_after_reembed(self, tmp_path):
        backend = FakeBackend(tmp_path)
        records = [{"id": "r1", "document": "doc", "embedding": [], "metadata": {}}]
        staging = self._staging_with_records(tmp_path, records)
        reembed_staged_records(staging, backend)
        result = [r for b in iter_staged_records(staging) for r in b]
        for v in result[0]["embedding"]:
            assert isinstance(v, float)

    def test_infers_dimension_when_runtime_store_is_empty(self, tmp_path):
        backend = FakeBackend(tmp_path)
        profile = backend.get_embedding_profile()
        backend.get_embedding_profile = lambda: {**profile, "vector_dimension": None}
        backend.embed = lambda texts: [[0.1] * 4 for _ in texts]
        records = [{"id": "r1", "document": "doc", "embedding": [], "metadata": {}}]
        staging = self._staging_with_records(tmp_path, records)

        reembed_staged_records(staging, backend)

        result = [r for b in iter_staged_records(staging) for r in b]
        assert len(result[0]["embedding"]) == 4
