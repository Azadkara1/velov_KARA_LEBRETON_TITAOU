"""Journalisation des prédictions en PostgreSQL (EX-08 : chaque prédiction est traçable).

TP2, partie Compose. Un pool de connexions est ouvert au démarrage de l'API (lifespan) et
fermé à l'arrêt. Si la base est indisponible, l'API continue de prédire : l'échec d'écriture
est seulement journalisé (EX-07), jamais renvoyé comme une erreur au client.
"""

from __future__ import annotations

import logging
from datetime import datetime

from psycopg_pool import ConnectionPool

logger = logging.getLogger("velov.api.db")

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS predictions (
    id SERIAL PRIMARY KEY,
    station_id INT NOT NULL,
    requested_at TIMESTAMPTZ NOT NULL,
    target_timestamp TIMESTAMPTZ NOT NULL,
    capacity INT NOT NULL,
    bikes_available INT NOT NULL,
    temperature DOUBLE PRECISION NOT NULL,
    is_raining BOOLEAN NOT NULL,
    predicted_bikes DOUBLE PRECISION NOT NULL,
    model_version TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

INSERT_PREDICTION = """
INSERT INTO predictions
    (station_id, requested_at, target_timestamp, capacity, bikes_available,
     temperature, is_raining, predicted_bikes, model_version)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


def open_pool(database_url: str) -> ConnectionPool:
    """Ouvre le pool et crée la table si besoin. Lève une exception si la base ne répond pas."""
    pool = ConnectionPool(database_url, min_size=1, max_size=5, open=True)
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(CREATE_TABLE)
    return pool


def record_prediction(
    pool: ConnectionPool,
    *,
    station_id: int,
    requested_at: datetime,
    target_timestamp: datetime,
    capacity: int,
    bikes_available: int,
    temperature: float,
    is_raining: bool,
    predicted_bikes: float,
    model_version: str,
) -> None:
    """Insère une ligne. N'importe quelle erreur est journalisée, jamais remontée à l'appelant."""
    try:
        with pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                INSERT_PREDICTION,
                (
                    station_id,
                    requested_at,
                    target_timestamp,
                    capacity,
                    bikes_available,
                    temperature,
                    is_raining,
                    predicted_bikes,
                    model_version,
                ),
            )
    except Exception:
        logger.exception("Échec de l'enregistrement de la prédiction en base")
