import logging
import os

os.environ["PYMUPDF_MESSAGE"] = "logging:"
logging.getLogger("pymupdf").setLevel(logging.CRITICAL)

import re
from pathlib import Path

from langchain_pymupdf4llm import PyMuPDF4LLMLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

PDF_ROOT = Path("PDFS")
COLLECTION = "plant_article_chunks"
QDRANT_URL = "http://localhost:6333"

REFERENCES_PATTERN = re.compile(r"\n\s*(references|bibliography)\s*\n", re.IGNORECASE)

embeddings = OpenAIEmbeddings(
    model="text-embedding-qwen3-embedding-4b@q4_k_m",
    base_url="http://127.0.0.1:4213/v1",
    api_key="key",
    check_embedding_ctx_length=False,
)

text_splitter = RecursiveCharacterTextSplitter(chunk_size=1200, chunk_overlap=200)


def strip_references(text: str) -> str:
    match = REFERENCES_PATTERN.search(text)
    return text[:match.start()] if match else text


def load_pdf_text(pdf_path: Path) -> str:
    pages = PyMuPDF4LLMLoader(str(pdf_path), mode="page", use_ocr=False).load()
    return "\n".join(p.page_content for p in pages)


def main():
    if not PDF_ROOT.exists():
        print(f"'{PDF_ROOT}/' not found.")
        return

    species_folders = sorted(p for p in PDF_ROOT.iterdir() if p.is_dir())
    if not species_folders:
        print(f"No species folders under '{PDF_ROOT}/'.")
        return

    documents = []

    for species_folder in species_folders:
        species = species_folder.name
        pdf_files = sorted(species_folder.glob("*.pdf"))

        if not pdf_files:
            print(f"⏭  {species}: no PDFs")
            continue

        species_chunks = 0
        for pdf_path in pdf_files:
            try:
                full_text = load_pdf_text(pdf_path)
            except Exception as e:
                print(f"❌ {species}/{pdf_path.name}: {e}")
                continue

            full_text = strip_references(full_text)
            chunks = text_splitter.split_text(full_text)

            for chunk in chunks:
                documents.append(
                    Document(
                        page_content=chunk,
                        metadata={
                            "species": species,
                            "source_type": "pdf",
                            "source_file": pdf_path.name,
                        },
                    )
                )
            species_chunks += len(chunks)

        print(f"✅ {species}: {len(pdf_files)} PDFs, {species_chunks} chunks")

    if not documents:
        print("No chunks to upload.")
        return

    print(f"\nUploading {len(documents)} chunks to Qdrant...")

    client = QdrantClient(url=QDRANT_URL)
    existing = [c.name for c in client.get_collections().collections]

    if COLLECTION not in existing:
        vector_size = len(embeddings.embed_query("test"))
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )

    vectorstore = QdrantVectorStore(client=client, collection_name=COLLECTION, embedding=embeddings)
    vectorstore.add_documents(documents)
    print("Done.")


if __name__ == "__main__":
    main()

#  8715 chunks total.