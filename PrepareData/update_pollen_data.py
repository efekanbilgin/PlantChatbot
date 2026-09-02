import os
import psycopg

POSTGRES_URL = os.environ.get(
    "POSTGRES_URL",
    "postgresql://plantbot:plantbot@localhost:5432/plantchatbot",
)

POLLEN_DATA = [
    {"species": "Juniperus chinensis Kaizuca", "onset": "February", "peak": "February-March",
     "severity": "very high", "notes": "Family-level data (Cupressaceae)."},
    {"species": "Platycladus orientalis", "onset": "February", "peak": "February-March",
     "severity": "very high", "notes": "Family-level data (Cupressaceae)."},
    {"species": "Metasequoia glyptostroboides", "onset": "February", "peak": "February-March",
     "severity": "very high", "notes": "Family-level data (Cupressaceae)."},
    {"species": "Taxodium ascendens Brongn", "onset": "February", "peak": "February-March",
     "severity": "very high", "notes": "Family-level data (Cupressaceae)."},
    {"species": "Cedrus deodara", "onset": "May", "peak": "June",
     "severity": "very high", "notes": "Family-level data (Pinaceae)."},
    {"species": "Pinus massoniana Lamb", "onset": "May", "peak": "June",
     "severity": "very high", "notes": "Family-level data (Pinaceae)."},
    {"species": "Pinus parviflora", "onset": "May", "peak": "June",
     "severity": "very high", "notes": "Family-level data (Pinaceae)."},
    {"species": "Acer palmatum", "onset": "March", "peak": "April",
     "severity": "medium", "notes": "Genus-level data (Acer)."},
    {"species": "Platanus", "onset": "March", "peak": "April",
     "severity": "medium", "notes": "Genus-level data (Platanus)."},
    {"species": "Populus deltoides", "onset": "March", "peak": "April",
     "severity": "high", "notes": "Genus-level data (Populus)."},
]

UPDATE_SQL = """
UPDATE plants SET
    pollen_season_onset = %s,
    pollen_season_peak = %s,
    pollen_severity = %s,
    pollen_notes = %s,
    updated_at = now()
WHERE species = %s;
"""


def main():
    with psycopg.connect(POSTGRES_URL) as conn:
        with conn.cursor() as cur:
            updated, missing = 0, []

            for row in POLLEN_DATA:
                cur.execute(UPDATE_SQL, (
                    row["onset"], row["peak"], row["severity"], row["notes"],
                    row["species"],
                ))
                if cur.rowcount == 0:
                    missing.append(row["species"])
                    print(f"⚠️  No match: {row['species']}")
                else:
                    updated += 1
                    print(f"✅ {row['species']}")

        conn.commit()

    print(f"\n{updated}/{len(POLLEN_DATA)} species updated.")
    if missing:
        for m in missing:
            print(f"  - {m!r}")


if __name__ == "__main__":
    main()
