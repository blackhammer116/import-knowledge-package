# Import Knowledge and Memory Portability (`import-kb`)

A utility package for importing distilled knowledge into a ChromaDB-based Long-Term Memory (LTM) system and backing up or restoring OmegaClaw user memory.

## Purpose
The `import-kb` package is designed to bridge the gap between static knowledge files (JSONL, MeTTa) and an active agent's memory. It processes structured knowledge, generates vector embeddings, and upserts them into a ChromaDB collection, enabling semantic search and retrieval for AI agents.

The package also provides `memory_portability`, a programmatic interface for exporting and restoring OmegaClaw conversation history and user LTM records. OmegaClaw Core remains responsible for its CLI, container lifecycle, transfer-directory mount, and user-facing decisions.

## Supported Embedding Models
This package supports two primary embedding modes:

- **OpenAI (Cloud)**:
  - Default model: `text-embedding-3-large`
  - High accuracy but requires an internet connection and an API key.
- **SentenceTransformers (Local)**:
  - Default model: `intfloat/e5-large-v2`
  - Runs fully offline on your local machine.
  - Can be configured to use any model compatible with the `sentence-transformers` library (e.g., `all-MiniLM-L6-v2`).

## Installation

You can install the package directly from PyPI:

```bash
pip install import-kb
```

Or install it locally in editable mode:

```bash
git clone <repository-url>
cd import-knowledge-package
pip install -e .
```

## Setup
Create a `.env` file in your project root or set the following environment variables:

- `OPENAI_API_KEY`: Required if using OpenAI embeddings.
- `CHROMA_DB_PATH`: (Optional) Custom path to your Chroma database. Defaults to looking for `/PeTTa/chroma_db` or a local `chroma_db` folder.

## How to Run

### Command Line Interface (CLI)
After installation, you can run the import via the provided entry point:

```bash
# Use OpenAI embeddings (default)
import-knowledge

# Use Local embeddings
import-knowledge --local

# Use a specific local model
import-knowledge --local --model "all-MiniLM-L6-v2"

# Override OpenAI model
import-knowledge --model "text-embedding-3-small"
```

Alternatively, run it as a module:
```bash
python3 -m import_knowledge.import_knowledge --local
```

### Programmatic Usage
You can initialize the embedding system and trigger the import programmatically from your Python scripts:

```python
from import_knowledge import initLocalEmbedding, main

# Initialize for local use
initLocalEmbedding(model_name="intfloat/e5-large-v2")

# Run the import process
main()
```

## Memory Portability

`MemoryTransfer` exports selected user-memory components to one portable archive and imports them using either overwrite or append behavior.

### Configuration

The implementation uses environment variables and can also accept paths directly:

- `MEMORY_DIR`: OmegaClaw memory directory containing `history.metta` and import transaction state.
- `CHROMA_DB_PATH`: ChromaDB persistence directory.
- `OMEGACLAW_DIR`: OmegaClaw-Core project root used when component paths are not set. Defaults to `/PeTTa/repos/OmegaClaw-Core`.
- `MEMORY_TRANSFER_DIR`: Directory containing exported and imported archives. Defaults to `/memory-transfer`.
- `EMBEDDING_PROVIDER`: `Local` or `OpenAI`.
- `SENTENCE_TRANSFORMERS_MODEL`: Active local embedding model. Defaults to `intfloat/e5-large-v2`.
- `OPENAI_EMBEDDING_MODEL`: Active OpenAI embedding model. Defaults to `text-embedding-3-large`.
- `EMBEDDING_DIMENSION`: Optional vector dimension for a custom embedding model.
- `OMEGACLAW_VERSION`: Optional source version recorded in the archive manifest.

OpenAI re-embedding also requires `OPENAI_API_KEY`.

### Export

```python
from memory_portability import MemoryTransfer

transfer = MemoryTransfer()

# component may be "history", "ltm", or "both".
result = transfer.export(component="both")
print(result["filename"])
```

The export is synchronous. If the host application permits concurrent memory writes, it should hold its memory-write lock while exporting when a cross-component point-in-time snapshot is required.

The archive contains only the selected files:

```text
manifest.json
history/history.metta
vector/collections.json
vector/records.jsonl
```

ChromaDB is exported as logical user-memory records rather than raw database files. Knowledge priors and operational records are excluded.

### Import

The filename must be a plain `.tar.gz` filename located inside the configured transfer directory:

```python
result = transfer.import_archive(
    "omegaclaw-memory-20260822T120000Z.tar.gz",
    mode="overwrite",
    include_history=True,
    include_vectors=True,
)
```

Import modes:

- `overwrite` replaces the selected user-memory components and restores their previous state if the operation fails.
- `append` keeps existing history and LTM records, appending history and assigning namespaced IDs to imported vectors.

Archives are validated before live memory is modified. Validation covers the manifest, allowed archive members, paths, sizes, checksums, record counts, and embedding dimensions. Missing or incompatible embeddings are regenerated with the active embedding provider.

### Interrupted Import Recovery

Call recovery before starting a new import or before the host agent begins using memory:

```python
recovery = transfer.recover()
print(recovery["status"])
```

Recovery completes an already committed transaction or rolls back an interrupted one. Import receipts prevent the same archive and import selection from being applied more than once.

## Dependencies
- `openai`: For cloud-based embeddings.
- `sentence-transformers`: For local, offline embeddings.
- `chromadb`: Vector database for storage.
- `python-dotenv`: Management of environment variables.
- `tqdm`: Progress bars for batch processing.

---

## License

This project is licensed under the Apache License 2.0. See [LICENSE](LICENSE) file for details.
