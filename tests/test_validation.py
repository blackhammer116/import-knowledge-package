import io
import tarfile

import pytest

from import_knowledge.memory_portability.archive import unpack
from import_knowledge.memory_portability.errors import ArchiveValidationError
from import_knowledge.memory_portability.importer import import_archive

from conftest import FakeBackend
def test_unpack_rejects_unexpected_archive_member(tmp_path):
    archive = tmp_path / "unsafe.tar.gz"
    with tarfile.open(archive, "w:gz") as output:
        info = tarfile.TarInfo("unexpected.txt")
        payload = b"not allowed"
        info.size = len(payload)
        output.addfile(info, io.BytesIO(payload))
    with pytest.raises(ArchiveValidationError, match="Unexpected archive member"):
        unpack(archive, tmp_path / "staging")
def test_invalid_archive_never_mutates_live_memory(tmp_path):
    archive = tmp_path / "broken.tar.gz"
    archive.write_bytes(b"not a tar archive")
    backend = FakeBackend(tmp_path / "backend")
    with pytest.raises(ArchiveValidationError, match="Unreadable archive"):
        import_archive(backend, tmp_path, archive.name)
    assert backend.read_history() == "history\n"
