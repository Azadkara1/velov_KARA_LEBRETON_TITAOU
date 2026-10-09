"""API de serving du modèle Vélo'v.

TP1, partie 3 : exposez le modèle. Mode : IA déclarée autorisée pour cette partie.

Endpoints attendus (niveaux du TP1 : Must, Should, Stretch) :
    POST /v1/predict        [Must]    une prédiction
    GET  /health            [Should]  liveness : le process répond (ne dépend pas du modèle)
    GET  /ready             [Should]  readiness : 200 si le modèle est chargé, 503 sinon
    GET  /v1/model, POST /v1/predict/batch   [Stretch]

Lancement :
    uvicorn velov.api.main:app --reload
"""

from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException

from velov.api import db
from velov.api.schemas import PredictionRequest, PredictionResponse
from velov.features import FEATURES, add_features
from velov.train import METADATA_FILENAME, sha256_of

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("velov.api")

STATE: dict = {"model": None, "metadata": None, "db_pool": None}


def load_model(model_dir: Path) -> tuple[object, dict]:
    """Fourni : charge le modèle APRÈS avoir vérifié son empreinte SHA-256."""
    metadata_path = model_dir / METADATA_FILENAME
    if not metadata_path.exists():
        raise FileNotFoundError(f"{metadata_path} introuvable")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    model_path = model_dir / metadata["artifact"]["file"]
    if sha256_of(model_path) != metadata["artifact"]["sha256"]:
        raise RuntimeError(f"Empreinte invalide pour {model_path}")
    return joblib.load(model_path), metadata


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Fourni : exécuté une fois au démarrage (avant yield) et à l'arrêt (après yield)."""
    model_dir = Path(os.getenv("MODEL_DIR", "models"))
    try:
        STATE["model"], STATE["metadata"] = load_model(model_dir)
        logger.info("Modèle %s chargé", STATE["metadata"]["model_version"])
    except Exception:
        logger.exception("Échec du chargement du modèle depuis %s", model_dir)

    database_url = os.getenv("DATABASE_URL")
    if database_url:
        try:
            STATE["db_pool"] = db.open_pool(database_url)
            logger.info("Connexion à la base de données établie")
        except Exception:
            # EX-07 : la cause est dans les logs. L'API continue de prédire sans journaliser.
            logger.exception("Base de données indisponible, les prédictions ne seront pas enregistrées")
    else:
        logger.warning("DATABASE_URL absent : les prédictions ne seront pas enregistrées")

    yield

    STATE.update(model=None, metadata=None)
    if STATE["db_pool"] is not None:
        STATE["db_pool"].close()


app = FastAPI(title="Vélo'v availability API", version="1.0.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    """Liveness : le process répond. Ne dépend pas du modèle."""
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict:
    """Readiness : 200 uniquement si le modèle est chargé et prêt à prédire."""
    if STATE["model"] is None:
        raise HTTPException(status_code=503, detail="Modèle non chargé")
    return {"status": "ready", "model_version": STATE["metadata"]["model_version"]}


@app.get("/v1/model")
def model_info() -> dict:
    """Métadonnées du modèle servi (version, métriques, versions des librairies)."""
    if STATE["model"] is None:
        raise HTTPException(status_code=503, detail="Modèle non chargé")
    return STATE["metadata"]


@app.post("/v1/predict", response_model=PredictionResponse)
def predict(request: PredictionRequest) -> PredictionResponse:
    if STATE["model"] is None:
        raise HTTPException(status_code=503, detail="Modèle non chargé")
    # add_features est importé, pas recalculé ici : une seule implémentation des features
    # pour l'entraînement et l'API, sinon training-serving skew silencieux.
    frame = add_features(pd.DataFrame([request.model_dump()]))
    prediction = float(STATE["model"].predict(frame[FEATURES])[0])
    target_timestamp = request.timestamp + timedelta(hours=1)
    predicted_bikes = min(max(prediction, 0.0), float(request.capacity))
    model_version = STATE["metadata"]["model_version"]

    if STATE["db_pool"] is not None:
        db.record_prediction(
            STATE["db_pool"],
            station_id=request.station_id,
            requested_at=datetime.now(UTC),
            target_timestamp=target_timestamp,
            capacity=request.capacity,
            bikes_available=request.bikes_available,
            temperature=request.temperature,
            is_raining=request.is_raining,
            predicted_bikes=predicted_bikes,
            model_version=model_version,
        )

    return PredictionResponse(
        station_id=request.station_id,
        target_timestamp=target_timestamp,
        predicted_bikes=predicted_bikes,
        model_version=model_version,
    )
