# PrepareData

Fetches, enriches, and indexes plant reference data into Postgres and Qdrant.

## Prerequisites

```bash
docker compose up -d   # Postgres + Qdrant
pip install requests "psycopg[binary]" langchain-text-splitters langchain-qdrant langchain-openai
```

`chunk_and_embed_to_qdrant.py` also requires a local embedding server (LM Studio, `text-embedding-nomic-embed-text-v2-moe`) running at `http://127.0.0.1:1234/v1`.

## Run order

### 1. `fetch_wikipedia.py`
```bash
python fetch_wikipedia.py
```
Reads `class_names.json`, queries the Wikipedia API for each species, and writes:
- `wikipedia_fetch_results.json` — summary, body, url, match status per species
- `needs_review.json` — species that needed a search fallback or weren't found

Check `needs_review.json` before continuing. Add corrections to `MANUAL_OVERRIDES` in `fetch_wikipedia.py` if a match is wrong, then re-run.

### 2. `load_wikipedia_to_postgres.py`
```bash
python load_wikipedia_to_postgres.py
```
Creates the `plants` table if it doesn't exist and loads `species`, `wikipedia_url`, `summary` from `wikipedia_fetch_results.json`.

### 3. `update_pollen_data.py`
```bash
python update_pollen_data.py
```
Updates `pollen_season_onset`, `pollen_season_peak`, `pollen_severity`, `pollen_notes` for species matched at genus/family level. Species not in this list keep `NULL` values.

### 4. `chunk_and_embed_to_qdrant.py`
```bash
python chunk_and_embed_to_qdrant.py
```
Splits the Wikipedia `body` field (article text minus the lead paragraph) into chunks and embeds them into the Qdrant collection `plant_wikipedia_chunks`, tagged with `species` and `source_type: "wikipedia"` metadata.

## Notes

- `species` values must match `class_names.json` exactly — this is the join key across Postgres and Qdrant.
- Steps 2–4 can be re-run safely; step 2 upserts by `species`, step 4 appends to the existing Qdrant collection.
