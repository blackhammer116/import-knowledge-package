# memory-portability

`memory-portability` exports and restores OmegaClaw history and long-term
memory as checksummed `.tar.gz` archives. It uses `MEMORY_DIR` for OmegaClaw
memory and `MEMORY_TRANSFER_DIR` for archives.

## Installation

```bash
pip install "git+https://github.com/Bereket-Eshete/memory-portability-package.git@v0.2.0"
```

The package runs inside an OmegaClaw installation. It uses the existing
`src.memory_gateway` write lock while creating an export snapshot.

## Usage

```python
from memory_portability import MemoryTransfer

transfer = MemoryTransfer()
transfer.recover()
archive = transfer.export("both")
transfer.import_archive(archive["filename"], mode="overwrite")
```

Use the CLI before the agent starts:

```bash
python -m memory_portability recover
python -m memory_portability import \
  --transfer-dir /memory-transfer \
  --filename omegaclaw-memory-20260819T120000000000Z.tar.gz
```

`import` also accepts `--mode append`, `--no-history`, and `--no-vector`.
