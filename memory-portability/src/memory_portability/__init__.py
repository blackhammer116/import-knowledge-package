"""
memory_portability
==================

Agent-agnostic memory backup and restore package.

Public API
----------
MemoryBackend   -- abstract storage adapter interface agents must implement.
MemoryTransfer  -- main entry point for export, import, and recovery.

Import errors and result types are also exported from this namespace so
callers never need to import from internal submodules.
"""

from memory_portability.backend import MemoryBackend
from memory_portability.transfer import MemoryTransfer
from memory_portability.errors import (
    MemoryPortabilityError,
    ArchiveValidationError,
    ImportError,
    ExportError,
    RecoveryError,
)

__all__ = [
    "MemoryBackend",
    "MemoryTransfer",
    "MemoryPortabilityError",
    "ArchiveValidationError",
    "ImportError",
    "ExportError",
    "RecoveryError",
]
