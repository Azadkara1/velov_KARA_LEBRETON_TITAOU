"""Traçage d'un entraînement dans MLflow (TP4, étape 2) et dépôt du modèle au registre.

Un run doit permettre de répondre, six mois plus tard, à : "avec quel code, quelles données,
quels réglages, et quel résultat ?". D'où :
- paramètres : seed, learning_rate, max_iter, test_days ;
- métriques mesurées sur le jeu de TEST (jamais sur l'entraînement) ;
- tags : commit git, arbre sale ou non, empreinte et période des données ;
- artefacts : le modèle avec sa signature, et le paquet servi par l'API (model.joblib + metadata.json).

Le modèle est ensuite enregistré dans le registre sous l'alias `challenger` : un candidat,
pas encore le modèle servi. Le passage à `champion` obéit à la règle de velov.registry.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import joblib
import pandas as pd

from velov.features import FEATURES, make_training_frame

EXPERIMENT = "velov-availability"
REGISTERED_MODEL = "velov-availability"
CHALLENGER_ALIAS = "challenger"

# MLflow 3.x sérialise sklearn en skops (sans exécution de code arbitraire) ; skops refuse les
# types qu'il ne connaît pas, on déclare donc ceux qu'on a vérifiés.
SKOPS_TRUSTED_TYPES = ["sklearn.ensemble._hist_gradient_boosting.predictor.TreePredictor"]


def _git(*args: str) -> str:
    out = subprocess.run(["git", *args], capture_output=True, text=True, check=False)  # noqa: S603, S607
    return out.stdout.strip() if out.returncode == 0 else ""


def git_info() -> dict[str, str]:
    """Commit courant et état de l'arbre de travail. `git_dirty=true` : le run n'est pas reproductible."""
    return {
        "git_commit": _git("rev-parse", "HEAD") or "unknown",
        "git_dirty": str(bool(_git("status", "--porcelain"))).lower(),
    }


def require_tracking_uri() -> str:
    uri = os.environ.get("MLFLOW_TRACKING_URI")
    if not uri:
        raise SystemExit(
            "MLFLOW_TRACKING_URI n'est pas défini.\n"
            "  serveur local : export MLFLOW_TRACKING_URI=http://127.0.0.1:5000\n"
            "  sans serveur  : export MLFLOW_TRACKING_URI=sqlite:///mlflow.db"
        )
    return uri


def _signature_sample() -> pd.DataFrame:
    return make_training_frame(
        pd.DataFrame(
            {
                "station_id": [1, 1],
                "timestamp": pd.to_datetime(["2026-06-01T06:00Z", "2026-06-01T07:00Z"]),
                "capacity": [20, 20],
                "bikes_available": [8, 5],
                "temperature": [21.0, 22.0],
                "is_raining": [False, False],
            }
        )
    )[FEATURES]


def log_run(metadata: dict, out_dir: Path) -> tuple[str, str]:
    """Trace le run, enregistre le modèle, pose l'alias `challenger`. Retourne (run_id, version)."""
    import mlflow  # import local : MLflow n'est pas requis pour servir le modèle
    from mlflow import MlflowClient
    from mlflow.models import infer_signature

    # MLflow affiche un emoji en fin de run : sur une console Windows (cp1252) cela fait planter
    # le script APRÈS l'entraînement. Même famille de piège que l'encodage de metadata.json (TP2).
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    mlflow.set_tracking_uri(require_tracking_uri())
    pipeline = joblib.load(out_dir / metadata["artifact"]["file"])
    sample = _signature_sample()

    mlflow.set_experiment(EXPERIMENT)
    with mlflow.start_run(run_name=f"v{metadata['model_version']}-seed{metadata['params']['seed']}") as run:
        mlflow.log_params({"model": "HistGradientBoostingRegressor", **metadata["params"]})
        # Seules les métriques de test (MAE) : n_train / n_test sont des tailles, pas des scores.
        mlflow.log_metrics({k: v for k, v in metadata["metrics"].items() if k.startswith("mae")})
        mlflow.set_tags(
            {
                **git_info(),
                "data_source": metadata["data_source"],
                "data_sha256": metadata["data_sha256"],
                "data_start": metadata["data_period"]["start"],
                "data_end": metadata["data_period"]["end"],
            }
        )
        info = mlflow.sklearn.log_model(
            pipeline,
            name="model",
            signature=infer_signature(sample, pipeline.predict(sample)),
            input_example=sample,
            serialization_format="skops",
            skops_trusted_types=SKOPS_TRUSTED_TYPES,
            registered_model_name=REGISTERED_MODEL,
        )
        # Le paquet exactement tel que l'API le sert : modèle + métadonnées (empreinte, versions de libs).
        mlflow.log_artifact(str(out_dir / metadata["artifact"]["file"]), artifact_path="package")
        mlflow.log_artifact(str(out_dir / "metadata.json"), artifact_path="package")

    version = str(info.registered_model_version)
    MlflowClient().set_registered_model_alias(REGISTERED_MODEL, CHALLENGER_ALIAS, version)
    return run.info.run_id, version
