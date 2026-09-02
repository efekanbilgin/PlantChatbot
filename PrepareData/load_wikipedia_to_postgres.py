"""
Kullanım:
    pip install "psycopg[binary]"
    export POSTGRES_URL="postgresql://user:pass@host:5432/dbname"
    python load_wikipedia_to_postgres.py
"""
import json
import os

import psycopg

POSTGRES_URL = os.environ.get(
    "POSTGRES_URL",
    "postgresql://plantbot:plantbot@localhost:5432/plantchatbot",
)

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS plants (
    species TEXT PRIMARY KEY,         
    wikipedia_url TEXT,
    summary TEXT,                      
    toxic_to_cats BOOLEAN,             
    toxic_to_dogs BOOLEAN,
    toxicity_notes TEXT,
    toxicity_source TEXT,
    pollen_season_onset TEXT,
    pollen_season_peak TEXT,
    pollen_severity TEXT,
    pollen_notes TEXT,
    pollen_source TEXT,
    updated_at TIMESTAMPTZ DEFAULT now()
);
"""

UPSERT_SQL = """
INSERT INTO plants (species, wikipedia_url, summary, updated_at)
VALUES (%s, %s, %s, now())
ON CONFLICT (species) DO UPDATE SET
    wikipedia_url = EXCLUDED.wikipedia_url,
    summary = EXCLUDED.summary,
    updated_at = now();
"""


def main():
    with open("wikipedia_fetch_results.json", "r", encoding="utf-8") as f:
        results = json.load(f)

    with psycopg.connect(POSTGRES_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(CREATE_TABLE_SQL)

            loaded, skipped = 0, 0
            for r in results:
                if r["status"] == "NOT_FOUND" or not r.get("summary"):
                    print(f"⏭  Atlandı (içerik yok): {r['label']}")
                    skipped += 1
                    continue

                cur.execute(UPSERT_SQL, (r["label"], r.get("url"), r["summary"]))
                print(f"✅ {r['label']}")
                loaded += 1

        conn.commit()

    print(f"\n{loaded} tür yüklendi, {skipped} tür atlandı.")


if __name__ == "__main__":
    main()
