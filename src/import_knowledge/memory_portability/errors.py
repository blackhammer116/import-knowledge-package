"""
memory_portability.errors
=========================

Public exception hierarchy for the memory-portability package.

All exceptions raised by the package are subclasses of
``MemoryPortabilityError`` so callers can catch them with a single clause
while still distinguishing the specific failure category when needed.
"""

class MemoryPortabilityError(Exception):
    """Base class for all memory-portability exceptions."""

class ArchiveValidationError(MemoryPortabilityError):
    """Raised when an archive fails any structural or content validation check.

    Examples: path traversal in member names, checksum mismatch, manifest
    schema violation, record count mismatch, size limit exceeded.
    """

class ExportError(MemoryPortabilityError):
    """Raised when an export operation cannot be completed.

    Examples: transfer directory not writable, backend read failure,
    archive publication failure.
    """

class ImportError(MemoryPortabilityError):
    """Raised when an import operation cannot be completed.

    Examples: archive not found, staging failure, backend write failure,
    smoke test failure after restore.
    """

class RecoveryError(MemoryPortabilityError):
    """Raised when crash recovery cannot complete safely.

    Raised when a transaction marker exists but the rollback state is missing
    or unreadable. Operator intervention is required; the marker is preserved.
    """
