import os
import json
from pathlib import Path
import chromadb
import openai
from dotenv import load_dotenv

# Load API Key from .env
load_dotenv()

# --- Configuration ---
EMBEDDING_MODEL = "text-embedding-3-large"
COLLECTION_NAME = "memories"
KNOWLEDGE_FILES = [
    "KB/oma_distilled_knowledge.jsonl",
    "KB/max_distilled_knowledge.jsonl"
]
CURRICULUM_FILE = "KB/curriculum.metta"

# Look for the DB path
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get(
    "CHROMA_DB_PATH",
    "/PeTTa/chroma_db" if os.path.isdir("/PeTTa/chroma_db") else
    os.path.join(_PROJECT_ROOT, "..", "..", "chroma_db")
)

# --- Embedding Function  ---
def _embed_batch(texts):
    """Embed a list of texts via OpenAI. Returns list of float vectors."""
    client = openai.OpenAI()
    resp = client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
    return [item.embedding for item in resp.data]

def main():
    has_any_knowledge = any(Path(f).exists() for f in KNOWLEDGE_FILES)
    if not has_any_knowledge and not Path(CURRICULUM_FILE).exists():
        print("Error: Neither knowledge nor curriculum files were found.")
        return

    print(f"Connecting to Agent LTM at: {DB_PATH}")
    os.makedirs(DB_PATH, exist_ok=True)
    client = chromadb.PersistentClient(path=DB_PATH)
    
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=None,
    )

    ids = []
    documents = []
    metadatas = []
    seen_ids = set()

    for k_file in KNOWLEDGE_FILES:
        if Path(k_file).exists():
            print(f"Loading distilled knowledge from {k_file}...")
            with open(k_file, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    
                    record = json.loads(line)
                    record_id = record["id"]
                    
                    if record_id in seen_ids:
                        continue
                        
                    seen_ids.add(record_id)
                    ids.append(record_id)
                    documents.append(record["document"])

                    
                    meta = record.get("metadata", {})
                    clean_meta = {
                        "source": "distilled_memory",
                        "breadcrumb": f"LTM > {meta.get('domain', 'general')} > {meta.get('type', 'fact')}",
                        "type": "chunk",
                        "time": "knowledge_prior"
                    }
                    
                    for k, v in meta.items():
                        if isinstance(v, list):
                            clean_meta[k] = " | ".join(v) if v else "None"
                        else:
                            clean_meta[k] = v
                    
                    metadatas.append(clean_meta)
        else:
            print(f"Warning: {k_file} not found. Skipping...")

    if Path(CURRICULUM_FILE).exists():
        print("Loading curriculum...")
        with open(CURRICULUM_FILE, "r", encoding="utf-8") as f:
            content = f.read()
            chunks = [chunk.strip() for chunk in content.split("\n\n") if chunk.strip()]
            
            for idx, chunk in enumerate(chunks):
                curriculum_id = f"curriculum_mem_{idx}"
                
                if curriculum_id in seen_ids:
                    continue
                    
                seen_ids.add(curriculum_id)
                ids.append(curriculum_id)
                documents.append(chunk)
                metadatas.append({
                    "source": "curriculum",
                    "breadcrumb": "LTM > curriculum",
                    "type": "chunk",
                    "time": "knowledge_prior"
                })
    else:
        print(f"Warning: {CURRICULUM_FILE} not found. Skipping...")



    count = len(ids)
    if count == 0:
        print("No documents to process.")
        return

    print(f"Generating OpenAI '{EMBEDDING_MODEL}' embeddings for {count} records. Please wait...")

    batch_size = 100
    for i in range(0, count, batch_size):
        end = min(i + batch_size, count)
        
        batch_docs = documents[i:end]
        
        # Manually compute the embeddings via OpenAI API to match the agent's expected vector lengths
        try:
            batch_embeddings = _embed_batch(batch_docs)
        except Exception as e:
            print(f"Fatal error generating embeddings: {e}")
            return
        
        # Use upside instead of add to gracefully handle re-runs
        collection.upsert(
            ids=ids[i:end],
            embeddings=batch_embeddings,
            documents=batch_docs,
            metadatas=metadatas[i:end]
        )
        print(f"  -> Embedded and upserted batch {i} to {end}")

    print("\nKnowledge Transfer Complete!")
    print(f"New Agent Database now has {collection.count()} total memories.")

if __name__ == "__main__":
    main()