"""
wikipedia_fetch_results.json'daki 'body' alanını (lead paragraf HARİÇ tüm
makale -- SQL'deki summary ile duplikasyon olmasın diye) chunk'layıp,
her chunk'ı species metadata'sıyla Qdrant'a yükler.

Bu metadata sayesinde ileride agent, PlantLangGraph'ta classify sonrası
sadece o türe ait chunk'lar içinde arama yapabilecek:
    vectorstore.similarity_search(query, filter={"species": predicted_species})

Kullanım:
    python chunk_and_embed_to_qdrant.py
"""
import json

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_qdrant import QdrantVectorStore

COLLECTION = "plant_wikipedia_chunks"
QDRANT_URL = "http://localhost:6333"

embeddings = OpenAIEmbeddings(
    model="text-embedding-nomic-embed-text-v2-moe@f32",
    base_url="http://127.0.0.1:1234/v1",
    api_key="key",
    check_embedding_ctx_length=False,
)

text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=800,
    chunk_overlap=100,
)


def main():
    with open("wikipedia_fetch_results.json", "r", encoding="utf-8") as f:
        results = json.load(f)

    documents = []
    for r in results:
        if r["status"] == "NOT_FOUND" or not r.get("body"):
            print(f"⏭  Atlandı (chunk'lanacak içerik yok): {r['label']}")
            continue

        chunks = text_splitter.split_text(r["body"])
        for chunk in chunks:
            documents.append(
                Document(
                    page_content=chunk,
                    # "species" -> Postgres'teki `species` kolonuyla BİREBİR aynı
                    # ham etiket. Bu iki tablo/koleksiyonun birbirine bağlandığı
                    # tek anahtar burası.
                    metadata={"species": r["label"], "source_url": r.get("url")},
                )
            )
        print(f"✅ {r['label']}: {len(chunks)} chunk")

    if not documents:
        print("Yüklenecek chunk bulunamadı, çıkılıyor.")
        return

    print(f"\nToplam {len(documents)} chunk Qdrant'a yükleniyor...")
    QdrantVectorStore.from_documents(
        documents,
        embedding=embeddings,
        collection_name=COLLECTION,
        url=QDRANT_URL,
    )
    print("Tamamlandı.")


if __name__ == "__main__":
    main()
