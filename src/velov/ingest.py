"""Ingestion bronze idempotente : CSV (ou collecte) -> table bronze.velov_raw en PostgreSQL.

Idempotent = rejouer la même ingestion ne change pas la table. La garantie ne repose pas sur
"on ne le lancera qu'une fois" mais sur la base : clé primaire (station_id, observed_at) et
INSERT ... ON CONFLICT DO NOTHING. Un doublon est ignoré par PostgreSQL, quoi qu'il arrive
(relance après un crash, deux passages, chevauchement entre deux fichiers de collecte).

La couche bronze garde les données telles que reçues : aucune règle métier ici
(les lignes incohérentes sont écartées en silver, pas supprimées à la source).

Usage :
    python -m velov.ingest --csv data/velov_history.csv
    # deux passages -> le second affiche "0 ligne(s) nouvelle(s)"
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import psycopg

CREATE_BRONZE = """
CREATE SCHEMA IF NOT EXISTS bronze;
CREATE TABLE IF NOT EXISTS bronze.velov_raw (
    station_id      INT              NOT NULL,
    observed_at     TIMESTAMPTZ      NOT NULL,
    capacity        INT,
    bikes_available INT,
    temperature     DOUBLE PRECISION,
    is_raining      BOOLEAN,
    ingested_at     TIMESTAMPTZ      NOT NULL DEFAULT now(),
    PRIMARY KEY (station_id, observed_at)
);
"""

CREATE_STAGING = """
CREATE TEMP TABLE staging (
    station_id INT, observed_at TIMESTAMPTZ, capacity INT,
    bikes_available INT, temperature DOUBLE PRECISION, is_raining BOOLEAN
) ON COMMIT DROP;
"""

COPY_STAGING = (
    "COPY staging (station_id, observed_at, capacity, bikes_available, temperature, is_raining) "
    "FROM STDIN WITH (FORMAT csv, HEADER true)"
)

MERGE = """
INSERT INTO bronze.velov_raw
    (station_id, observed_at, capacity, bikes_available, temperature, is_raining)
SELECT station_id, observed_at, capacity, bikes_available, temperature, is_raining FROM staging
ON CONFLICT (station_id, observed_at) DO NOTHING
"""


def default_database_url() -> str:
    """URL de la base, depuis l'environnement (jamais de mot de passe écrit dans le code)."""
    if url := os.environ.get("PIPELINE_DATABASE_URL"):
        return url
    password = os.environ.get("POSTGRES_PASSWORD")
    if not password:
        raise SystemExit("POSTGRES_PASSWORD (ou PIPELINE_DATABASE_URL) doit être défini")
    host, port = os.environ.get("POSTGRES_HOST", "localhost"), os.environ.get("POSTGRES_PORT", "5432")
    return f"postgresql://velov:{password}@{host}:{port}/velov"


def ingest_csv(csv_path: Path, database_url: str) -> dict[str, int]:
    """Charge le CSV dans bronze.velov_raw. Retourne le nombre de lignes lues / nouvelles / total."""
    with psycopg.connect(database_url) as conn, conn.cursor() as cur:
        cur.execute("SET TIME ZONE 'UTC'")
        cur.execute(CREATE_BRONZE)
        cur.execute(CREATE_STAGING)
        with csv_path.open("rb") as f, cur.copy(COPY_STAGING) as copy:
            while chunk := f.read(1 << 20):
                copy.write(chunk)
        cur.execute("SELECT count(*) FROM staging")
        read = cur.fetchone()[0]
        cur.execute(MERGE)
        inserted = cur.rowcount
        cur.execute("SELECT count(*) FROM bronze.velov_raw")
        total = cur.fetchone()[0]
    return {"read": read, "inserted": inserted, "total": total}


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingestion bronze idempotente.")
    parser.add_argument("--csv", type=Path, default=Path("data/velov_history.csv"))
    args = parser.parse_args()
    if not args.csv.exists():
        raise SystemExit(f"{args.csv} introuvable : lancer d'abord `python -m velov.data`")

    r = ingest_csv(args.csv, default_database_url())
    print(
        f"{r['read']:,} lignes lues, {r['inserted']:,} ligne(s) nouvelle(s), bronze.velov_raw : {r['total']:,} lignes"
    )


if __name__ == "__main__":
    main()
