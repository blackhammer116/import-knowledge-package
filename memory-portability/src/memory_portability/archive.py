import shutil
import tarfile
from pathlib import Path

from memory_portability.errors import ArchiveValidationError

ARCHIVE_FORMAT_VERSION: int = 1

ALLOWLIST: frozenset[str] = frozenset([
    "manifest.json",
    "history/history.metta",
    "vector/collections.json",
    "vector/records.jsonl",
])

COMPONENT_FILES: dict[str, set[str]] = {
    "history": {"history/history.metta"},
    "ltm":     {"vector/collections.json", "vector/records.jsonl"},
}

MAX_COMPRESSED_BYTES: int = 500 * 1024 * 1024         # 500 MB
MAX_EXTRACTED_BYTES:  int = 2   * 1024 * 1024 * 1024  # 2 GB


def pack(staging: Path, dest: Path) -> None:
    """Pack allowlisted files from ``staging`` into a ``.tar.gz`` at ``dest``.

    Only files whose archive path is in ``ALLOWLIST`` and that exist inside
    ``staging`` are included. Members are added in sorted order for
    reproducibility. ``dest`` must not already exist.

    Parameters
    ----------
    staging:
        Directory containing the files to pack, laid out with paths matching
        ``ALLOWLIST`` (e.g. ``staging/manifest.json``,
        ``staging/history/history.metta``).
    dest:
        Output ``.tar.gz`` path. Parent directory must exist.

    Raises
    ------
    FileExistsError
        If ``dest`` already exists.
    """
    if dest.exists():
        raise FileExistsError(f"Archive destination already exists: {dest}")

    with tarfile.open(dest, "w:gz") as tar:
        for member in sorted(ALLOWLIST):
            p = staging / member
            if p.exists():
                tar.add(p, arcname=member)


def unpack(archive: Path, dest: Path) -> None:
    """Extract allowlisted regular files from ``archive`` into ``dest``.

    Validates every member before extraction:
    - Must be in ``ALLOWLIST``.
    - Must be a regular file (no symlinks, hardlinks, or device files).
    - Must not contain path traversal (``..`` components or absolute paths).
    - Must not be a duplicate of an already-seen member name.
    - Total extracted size must not exceed ``MAX_EXTRACTED_BYTES``.

    ``dest`` is created if it does not exist.

    Parameters
    ----------
    archive:
        Path to the ``.tar.gz`` to extract.
    dest:
        Directory into which members are extracted, preserving their paths
        relative to the archive root.

    Raises
    ------
    ArchiveValidationError
        If any member fails a safety check or the size limit is exceeded.
    """
    if archive.stat().st_size > MAX_COMPRESSED_BYTES:
        raise ArchiveValidationError(
            f"Archive too large: {archive.stat().st_size} bytes "
            f"(limit {MAX_COMPRESSED_BYTES})"
        )

    dest.mkdir(parents=True, exist_ok=True)
    base = dest.resolve()

    seen:            set[str] = set()
    total_extracted: int      = 0

    try:
        with tarfile.open(archive, "r:gz") as tar:
            for member in tar.getmembers():
                name = member.name

                if name not in ALLOWLIST:
                    raise ArchiveValidationError(
                        f"Unexpected archive member: {name!r}"
                    )
                if name in seen:
                    raise ArchiveValidationError(
                        f"Duplicate archive member: {name!r}"
                    )
                if not member.isfile():
                    raise ArchiveValidationError(
                        f"Non-regular archive member: {name!r}"
                    )
                member_path = Path(name)
                if member_path.is_absolute() or ".." in member_path.parts:
                    raise ArchiveValidationError(
                        f"Path traversal in archive member: {name!r}"
                    )
                total_extracted += member.size
                if total_extracted > MAX_EXTRACTED_BYTES:
                    raise ArchiveValidationError(
                        f"Archive extracted size exceeds limit of {MAX_EXTRACTED_BYTES} bytes"
                    )
                seen.add(name)

            _safe_extract(tar, base)
    except tarfile.TarError as exc:
        raise ArchiveValidationError(f"Unreadable archive: {exc}") from exc


def _safe_extract(tar: tarfile.TarFile, base: Path) -> None:
    """Extract only regular allowlisted members without relying on tarfile filters.

    Python 3.11 does not support ``TarFile.extractall(filter=...)``, so
    extraction is performed member-by-member after the caller has already
    validated each one.
    """
    for member in tar.getmembers():
        name = member.name
        if name not in ALLOWLIST or not member.isfile():
            raise ArchiveValidationError(f"Unsafe archive member during extraction: {name!r}")

        target = (base / name).resolve()
        if base not in target.parents:
            raise ArchiveValidationError(f"Path traversal in member: {name!r}")

        target.parent.mkdir(parents=True, exist_ok=True)
        source = tar.extractfile(member)
        if source is None:
            raise ArchiveValidationError(f"Could not read archive member: {name!r}")
        with source, target.open("wb") as out:
            shutil.copyfileobj(source, out)
