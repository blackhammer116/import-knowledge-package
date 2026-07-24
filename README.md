# Import Knowledge (import-kb)

A utility package for importing distilled knowledge and curriculum files into a ChromaDB-based Long-Term Memory (LTM) system.

## Purpose
The `import-kb` package is designed to bridge the gap between static knowledge files (JSONL, MeTTa) and an active agent's memory. It processes structured knowledge, generates vector embeddings, and upserts them into a ChromaDB collection, enabling semantic search and retrieval for AI agents.

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

## Dependencies
- `openai`: For cloud-based embeddings.
- `sentence-transformers`: For local, offline embeddings.
- `chromadb`: Vector database for storage.
- `python-dotenv`: Management of environment variables.
- `tqdm`: Progress bars for batch processing.

---

## License

This project is licensed under the Apache License 2.0. See [LICENSE](LICENSE) file for details.
