import hashlib
import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from memory_portability.archive import unpack
from memory_portability.backend import MemoryBackend
from memory_portability.errors import ImportError as MpImportError
from memory_portability.errors import RecoveryError
from memory_portability.extractor import iter_staged_records, read_staged_history
from memory_portability.reembedder import needs_reembedding, reembed_staged_records
from memory_portability.validator import (
    validate_checksums,
    validate_collections,
    validate_history,
    validate_manifest,
    validate_records,
)

TX_MARKER_NAME    = ".import_in_progress"
RECEIPT_DIR_NAME  = ".memory_import_receipts"
ROLLBACK_DIR_NAME = ".import_rollback"
STAGING_DIR_NAME  = ".import_staging"
_ROLLBACK_STATE   = "state.json"


def import_archive(
    backend: MemoryBackend,
    transfer_dir: Path,
    filename: str,
    mode: str = "overwrite",
    include_history: bool = True,
    include_vectors: bool = True,
) -> None:
    """Validate and restore an archive before the agent loop starts."""
    if mode not in ("overwrite", "append"):
        raise ValueError(f"Invalid mode: {mode!r}. Use 'overwrite' or 'append'.")
    if not include_history and not include_vectors:
        raise ValueError(
            "Both include_history and include_vectors are False — nothing to import."
        )
    if "/" in filename or "\\" in filename or ".." in filename:
        raise ValueError(f"filename must be a plain basename, not a path: {filename!r}")

    archive_path = transfer_dir / filename
    if not archive_path.exists():
        raise FileNotFoundError(f"Archive not found: {archive_path}")

    base    = backend.state_dir
    if not base.is_dir():
        raise MpImportError(f"backend.state_dir must be an existing directory: {base}")
    digest  = _sha256_file(archive_path)
    receipt = _receipt_path(base, digest, mode, include_history, include_vectors)

    if receipt.exists():
        return

    staging = base / STAGING_DIR_NAME
    shutil.rmtree(staging, ignore_errors=True)

    try:
        unpack(archive_path, staging)
        raw = json.loads((staging / "manifest.json").read_text(encoding="utf-8"))
        manifest = validate_manifest(raw)
        validate_checksums(staging, manifest)

        archive_components = manifest.get("components", [])

        if "history" in archive_components:
            validate_history(staging, manifest)
        missing_embeddings = False
        if "ltm" in archive_components:
            validate_collections(staging, manifest)
            missing_embeddings = validate_records(staging, manifest)

        do_history = (
            include_history
            and "history" in archive_components
            and (staging / "history" / "history.metta").is_file()
        )
        do_vectors = (
            include_vectors
            and "ltm" in archive_components
            and (staging / "vector" / "records.jsonl").is_file()
        )

        if do_vectors:
            if needs_reembedding(manifest, backend, missing_embeddings):
                reembed_staged_records(staging, backend)

        if mode == "overwrite":
            _import_overwrite(
                backend, staging, do_history, do_vectors, receipt, digest
            )
        else:
            _import_append(
                backend, staging, manifest, do_history, do_vectors, receipt, digest
            )

    finally:
        shutil.rmtree(staging, ignore_errors=True)


def recover(backend: MemoryBackend) -> None:
    """Restore or clean up an interrupted import transaction."""
    base   = backend.state_dir
    marker = base / TX_MARKER_NAME

    if not marker.exists():
        return

    if _marker_has_receipt(marker, base):
        marker.unlink(missing_ok=True)
        shutil.rmtree(base / ROLLBACK_DIR_NAME, ignore_errors=True)
        return

    try:
        transaction = json.loads(marker.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
        raise RecoveryError(
            f"Transaction marker is unreadable: {exc}. "
            "Operator intervention required."
        ) from exc

    if not isinstance(transaction, dict):
        raise RecoveryError(
            "Transaction marker has unexpected format. "
            "Operator intervention required."
        )

    append_ids = transaction.get("append_ids")
    if append_ids is not None:
        if not isinstance(append_ids, list):
            raise RecoveryError(
                "Transaction marker append_ids is not a list. "
                "Operator intervention required."
            )
        history_rollback = transaction.get("history_rollback", False)
        if type(history_rollback) is not bool:
            raise RecoveryError(
                "Transaction marker history_rollback is not a boolean. "
                "Operator intervention required."
            )
        try:
            if history_rollback:
                _restore_append_history(backend, base / ROLLBACK_DIR_NAME)
            if append_ids:
                backend.delete_records(append_ids)
        except Exception as exc:
            raise RecoveryError(
                f"Failed to delete partial append records: {exc}. "
                "Operator intervention required."
            ) from exc
        marker.unlink(missing_ok=True)
        shutil.rmtree(base / ROLLBACK_DIR_NAME, ignore_errors=True)
        return

    rollback = base / ROLLBACK_DIR_NAME
    if not rollback.exists():
        raise RecoveryError(
            "Transaction marker found but rollback directory is missing. "
            "Operator intervention required."
        )

    try:
        _restore_rollback(backend, rollback)
    except Exception as exc:
        raise RecoveryError(
            f"Rollback restoration failed: {exc}. "
            "Operator intervention required."
        ) from exc

    marker.unlink(missing_ok=True)
    shutil.rmtree(rollback, ignore_errors=True)


def _import_overwrite(
    backend: MemoryBackend,
    staging: Path,
    do_history: bool,
    do_vectors: bool,
    receipt: Path,
    digest: str,
) -> None:
    """Replace live components with rollback and crash-recovery protection."""
    base     = backend.state_dir
    rollback = base / ROLLBACK_DIR_NAME
    marker   = base / TX_MARKER_NAME

    shutil.rmtree(rollback, ignore_errors=True)
    rollback.mkdir(parents=True)

    rollback_state: dict = {}
    if do_history:
        current_history = backend.read_history()
        rollback_state["history"] = current_history is not None
        if current_history is not None:
            (rollback / "history.metta").write_text(current_history, encoding="utf-8")

    if do_vectors:
        vectors_present = backend.vector_store_exists()
        rollback_state["vectors"] = vectors_present
        if vectors_present:
            rollback_records_path = rollback / "records.jsonl"
            with rollback_records_path.open("w", encoding="utf-8") as f:
                for batch in backend.iter_records(batch_size=500):
                    for rec in batch:
                        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    _write_json_atomic(rollback / _ROLLBACK_STATE, rollback_state)

    # A missing receipt means recovery must restore this snapshot.
    _write_json_atomic(marker, {"receipt": receipt.name})

    try:
        if do_history:
            history_text = read_staged_history(staging)
            backend.write_history(history_text)

        if do_vectors:
            backend.replace_records(iter_staged_records(staging, batch_size=500))

        backend.smoke_test(do_history, do_vectors)

    except Exception as exc:
        try:
            _restore_rollback(backend, rollback)
        except Exception as rb_exc:
            raise MpImportError(
                f"Import failed and rollback also failed: {rb_exc}. "
                "Operator intervention required."
            ) from exc
        marker.unlink(missing_ok=True)
        shutil.rmtree(rollback, ignore_errors=True)
        raise MpImportError(f"Overwrite import failed (rolled back): {exc}") from exc

    _write_receipt(receipt, digest, "overwrite", do_history, do_vectors)
    marker.unlink(missing_ok=True)
    shutil.rmtree(rollback, ignore_errors=True)


def _import_append(
    backend: MemoryBackend,
    staging: Path,
    manifest: dict,
    do_history: bool,
    do_vectors: bool,
    receipt: Path,
    digest: str,
) -> None:
    """Append imported memory to existing live memory."""
    base   = backend.state_dir
    marker = base / TX_MARKER_NAME

    rollback = base / ROLLBACK_DIR_NAME

    import_uuid     = uuid.uuid4().hex
    appended_ids: list[str] = []

    shutil.rmtree(rollback, ignore_errors=True)
    if do_history:
        rollback.mkdir(parents=True)
        history = backend.read_history()
        state = {"history": history is not None}
        if history is not None:
            (rollback / "history.metta").write_text(history, encoding="utf-8")
        _write_json_atomic(rollback / _ROLLBACK_STATE, state)

    marker_state = {
        "receipt": receipt.name,
        "append_ids": appended_ids,
        "history_rollback": do_history,
    }
    _write_json_atomic(marker, marker_state)

    try:
        if do_history:
            history_text = read_staged_history(staging)
            if history_text:
                backend.append_history("\n" + history_text)

        if do_vectors:
            for batch in iter_staged_records(staging, batch_size=500):
                batch_to_upsert: list[dict] = []
                batch_ids: list[str] = []
                for rec in batch:
                    new_id = f"import-{import_uuid}-{rec['id']}"
                    batch_ids.append(new_id)
                    batch_to_upsert.append({
                        **rec,
                        "id":       new_id,
                        "metadata": {**rec.get("metadata", {}), "import_id": import_uuid},
                    })
                # Persist intended IDs before mutating live storage so recovery
                # also handles a process crash during this upsert.
                marker_state["append_ids"] = appended_ids + batch_ids
                _write_json_atomic(marker, marker_state)
                backend.upsert_records(batch_to_upsert)
                appended_ids.extend(batch_ids)

        backend.smoke_test(do_history, do_vectors)

    except Exception as exc:
        try:
            if do_history:
                _restore_append_history(backend, rollback)
            if marker_state["append_ids"]:
                backend.delete_records(marker_state["append_ids"])
        except Exception as rb_exc:
            raise MpImportError(
                f"Append import failed and cleanup also failed: {rb_exc}. "
                "Operator intervention required."
            ) from exc
        marker.unlink(missing_ok=True)
        shutil.rmtree(rollback, ignore_errors=True)
        raise MpImportError(f"Append import failed (rolled back): {exc}") from exc

    _write_receipt(receipt, digest, "append", do_history, do_vectors)
    marker.unlink(missing_ok=True)
    shutil.rmtree(rollback, ignore_errors=True)


def _restore_rollback(backend: MemoryBackend, rollback: Path) -> None:
    """Restore live memory from a rollback snapshot."""
    state_path = rollback / _ROLLBACK_STATE
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"Rollback state is unreadable: {exc}") from exc

    if not isinstance(state, dict) or not state:
        raise ValueError("Rollback state has unexpected format")
    if set(state) - {"history", "vectors"}:
        raise ValueError("Rollback state has unknown components")
    if any(type(present) is not bool for present in state.values()):
        raise ValueError("Rollback state component flags must be booleans")

    if "history" in state:
        hist_rb = rollback / "history.metta"
        if state["history"] is False:
            if hist_rb.exists():
                raise ValueError("Rollback history is present for an absent source")
            backend.write_history(None)
        elif hist_rb.is_file():
            backend.write_history(hist_rb.read_text(encoding="utf-8"))
        else:
            raise ValueError("Rollback history is missing")

    if "vectors" in state:
        records_rb = rollback / "records.jsonl"
        if state["vectors"] is True and records_rb.is_file():
            backend.replace_records(_iter_jsonl(records_rb, batch_size=500))
        elif state["vectors"] is False and not records_rb.exists():
            backend.remove_vector_store()
        else:
            raise ValueError("Rollback vector records are missing or unexpected")


def _restore_append_history(backend: MemoryBackend, rollback: Path) -> None:
    """Restore history captured before an append import."""
    state_path = rollback / _ROLLBACK_STATE
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"Append rollback state is unreadable: {exc}") from exc

    if not isinstance(state, dict) or type(state.get("history")) is not bool:
        raise ValueError("Append rollback state has invalid history flag")
    history = rollback / "history.metta"
    if state["history"] is False:
        if history.exists():
            raise ValueError("Append rollback history is unexpected")
        backend.write_history(None)
    elif history.is_file():
        backend.write_history(history.read_text(encoding="utf-8"))
    else:
        raise ValueError("Append rollback history is missing")


def _iter_jsonl(path: Path, batch_size: int = 500):
    """Yield batches of dicts from a JSONL file."""
    batch: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid rollback JSONL on line {line_no}: {exc}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"Rollback JSONL line {line_no} is not an object")
            batch.append(record)
            if len(batch) == batch_size:
                yield batch
                batch = []
    if batch:
        yield batch


def _receipt_path(
    base: Path, digest: str, mode: str,
    include_history: bool, include_vectors: bool
) -> Path:
    components = "-".join(
        c for c, included in (("history", include_history), ("ltm", include_vectors))
        if included
    )
    return base / RECEIPT_DIR_NAME / f"{digest}-{mode}-{components}.json"


def _write_receipt(
    path: Path, digest: str, mode: str,
    include_history: bool, include_vectors: bool
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    receipt = {
        "archive_sha256":  digest,
        "mode":            mode,
        "include_history": include_history,
        "include_vectors": include_vectors,
        "imported_at":     _utc_now(),
    }
    _write_json_atomic(path, receipt)


def _write_json_atomic(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def _marker_has_receipt(marker: Path, base: Path) -> bool:
    try:
        receipt_name = json.loads(marker.read_text(encoding="utf-8")).get("receipt")
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return False
    return (
        isinstance(receipt_name, str)
        and Path(receipt_name).name == receipt_name
        and (base / RECEIPT_DIR_NAME / receipt_name).is_file()
    )


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
