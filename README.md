# import-knowledge-package/import-knowledge-package/README.md

# Import Knowledge Package

This project provides a Python package for importing and processing knowledge from specified JSONL and curriculum files. It utilizes OpenAI's embedding model to generate embeddings for the knowledge data, which can then be stored in a Chroma database for later retrieval and use.

## Project Structure

```
import-knowledge-package
├── KB
│   ├── curriculum.metta
│   ├── max_distilled_knowledge.jsonl
│   └── oma_distilled_knowledge.jsonl
├── src
│   └── import_knowledge
│       ├── __init__.py
│       └── import_knowledge.py
├── pyproject.toml
├── setup.py
├── MANIFEST.in
└── README.md
```

### KB Directory

- **curriculum.metta**: Contains the curriculum data used for knowledge transfer.
- **max_distilled_knowledge.jsonl**: Contains distilled knowledge data related to "max".
- **oma_distilled_knowledge.jsonl**: Contains distilled knowledge data related to "oma".

### Source Directory

- **import_knowledge/__init__.py**: Marks the directory as a Python package.
- **import_knowledge.py**: Contains the main logic for importing knowledge, including functions for embedding text and processing knowledge files.

## Installation

To install the package, clone the repository and run:

```bash
pip install .
```

## Usage

After installation, you can use the package to import knowledge by running the `import_knowledge.py` script. Ensure that your environment is set up with the necessary API keys and dependencies.

## Dependencies

- OpenAI API
- sentence-transformers
- ChromaDB
- dotenv

Make sure to install the required dependencies listed in `setup.py` or `pyproject.toml`.

## License

This project is licensed under the MIT License. See the LICENSE file for more details.