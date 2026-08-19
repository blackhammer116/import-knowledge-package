# memory-portability

`memory-portability` is an agent-agnostic library for exporting and restoring
persistent agent memory. It produces versioned, checksummed `.tar.gz` archives
containing conversation history and logical vector records.

The package owns archive validation, transactions, crash recovery, and
re-embedding. The host agent supplies a `MemoryBackend` adapter for its live
history, vector store, and embedding provider. This keeps the package free of
runtime `chromadb`, `torch`, and embedding-provider dependencies.

## Installation

```bash
pip install "git+https://github.com/blackhammer116/import-knowledge-package.git@v0.1.0#subdirectory=memory-portability"
```

After the package is published to a package index, installation can instead
use `pip install memory-portability==0.1.0`.

## Usage

Implement `MemoryBackend` for the host agent, then construct a
`MemoryTransfer` with that backend and a host-owned transfer directory:

```python
from pathlib import Path

from memory_portability import MemoryTransfer

backend = MyAgentMemoryBackend(...)
transfer = MemoryTransfer(
    backend=backend,
    transfer_dir=Path("/secure/memory-transfer"),
)

transfer.recover()
archive = transfer.export("both")
transfer.import_archive(archive["filename"], mode="overwrite")
```

Call `recover()` before the agent starts accepting memory writes. Import is
also a host-agent operation: the package deliberately provides no generic CLI,
because only the host adapter knows how to safely restore its live vector
store. A host may expose its own CLI or authenticated operator command.

See the `MemoryBackend` docstrings for the adapter contract and
`MEMORY_PORTABILITY_PROPOSAL.md` in the repository root for the archive format
and OmegaClaw integration design.
