"""
Real schema:
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
"""

from psycopg_pool import AsyncConnectionPool

GET_PLANT_SQL = "SELECT * FROM plants WHERE species = %s"


class PlantDatabase:
    def __init__(self, pool: AsyncConnectionPool):
        self._pool = pool

    async def get_plant(self, species: str) -> dict | None:
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(GET_PLANT_SQL, (species,))
                return await cur.fetchone()