"""
Shared pytest fixtures for the memory-portability test suite.
"""

import tarfile
from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture()
def v1_fixture_path() -> Path:
    """Return the path to the checked-in v1 OmegaClaw archive fixture."""
    path = FIXTURE_DIR / "omegaclaw_v1_fixture.tar.gz"
    assert path.exists(), f"Fixture not found: {path}. Run build_fixture.py to regenerate."
    return path


@pytest.fixture()
def v1_fixture_manifest(v1_fixture_path: Path) -> dict:
    """Return the parsed manifest.json from the v1 fixture archive."""
    import json
    with tarfile.open(v1_fixture_path, "r:gz") as tar:
        f = tar.extractfile("manifest.json")
        assert f is not None
        return json.loads(f.read())
