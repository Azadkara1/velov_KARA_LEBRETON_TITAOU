"""Entraînement du modèle v0 et production de l'artefact distribuable.

Ce qu'on distribue (S1) n'est pas "un modèle" mais un paquet :
- le pipeline sklearn complet (prétraitement + modèle) -> models/model.joblib
- ses métadonnées (version, features, métriques, empreinte SHA-256, versions des
  librairies, hash des données) -> models/metadata.json

Usage :
    python -m velov.train --data data/velov_history.csv --out models/
    python -m velov.train --data data/velov_history.csv --out models/ --mlflow
    python -m velov.train --source gold --out models/     # lit gold.gold_hourly_features (TP3)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import psycopg
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from velov.features import (
    CATEGORICAL_FEATURES,
    FEATURES,
    NUMERIC_FEATURES,
    RAW_COLUMNS,
    TARGET,
    add_features,
    make_training_frame,
)
from velov.ingest import default_database_url

PEAK_HOURS = (7, 8, 9, 17, 18, 19)  # heures locales de départ / retour du travail
MODEL_FILENAME = "model.joblib"
METADATA_FILENAME = "metadata.json"


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_pipeline(seed: int = 42, learning_rate: float = 0.1, max_iter: int = 200) -> Pipeline:
    preprocess = ColumnTransformer(
        [
            ("station", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_FEATURES),
            ("num", "passthrough", NUMERIC_FEATURES),
        ]
    )
    model = HistGradientBoostingRegressor(max_iter=max_iter, learning_rate=learning_rate, random_state=seed)
    return Pipeline([("preprocess", preprocess), ("model", model)])


def temporal_split(df: pd.DataFrame, test_days: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Découpage temporel : on teste sur le futur, jamais sur un échantillon aléatoire."""
    cutoff = pd.to_datetime(df["timestamp"]).max() - pd.Timedelta(days=test_days)
    ts = pd.to_datetime(df["timestamp"])
    train, test = df[ts <= cutoff], df[ts > cutoff]
    if train.empty or test.empty:
        raise ValueError("Split vide : augmenter l'historique ou réduire test_days")
    return train, test


def read_gold(database_url: str) -> pd.DataFrame:
    """Lit la table gold, puis vérifie le contrat Pandera AVANT tout entraînement (EX-12)."""
    # Import local : l'API importe ce module (sha256_of) mais Pandera n'est pas une dépendance de serving.
    from velov.contract import validate_gold

    with psycopg.connect(database_url) as conn, conn.cursor() as cur:
        cur.execute("SET TIME ZONE 'UTC'")
        cur.execute("SELECT * FROM gold.gold_hourly_features ORDER BY station_id, timestamp")
        columns = [c.name for c in cur.description]
        df = pd.DataFrame(cur.fetchall(), columns=columns)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return validate_gold(df)


def train(
    data_path: Path | None,
    out_dir: Path,
    version: str = "0.1.0",
    test_days: int = 14,
    seed: int = 42,
    source: str = "csv",
    learning_rate: float = 0.1,
    max_iter: int = 200,
) -> dict:
    """Entraîne, évalue contre une baseline, écrit l'artefact. Retourne les métadonnées.

    source="csv"  : lit `data_path` et calcule la cible (chemin S1/S2).
    source="gold" : lit la table gold (cible déjà calculée par dbt), contrat vérifié avant.
    """
    if source == "gold":
        gold = read_gold(default_database_url())
        frame = add_features(gold)  # mêmes features que l'API : une seule implémentation
        data_hash = hashlib.sha256(pd.util.hash_pandas_object(gold, index=False).values.tobytes()).hexdigest()
    else:
        if not data_path.exists():
            raise FileNotFoundError(f"{data_path} introuvable : lancer d'abord `python -m velov.data`")
        raw = pd.read_csv(data_path, parse_dates=["timestamp"])
        frame = make_training_frame(raw)
        data_hash = sha256_of(data_path)
    train_df, test_df = temporal_split(frame, test_days)

    pipeline = build_pipeline(seed, learning_rate, max_iter)
    pipeline.fit(train_df[FEATURES], train_df[TARGET])

    y_test = test_df[TARGET]
    pred = np.clip(pipeline.predict(test_df[FEATURES]), 0, test_df["capacity"])
    mae_model = float(mean_absolute_error(y_test, pred))
    # Baseline "persistance" : dans 1 h, il y aura autant de vélos que maintenant.
    # Le modèle doit justifier sa complexité face à cette baseline (exigence EX-05).
    mae_baseline = float(mean_absolute_error(y_test, test_df["bikes_available"]))
    # Heures de pointe (heure locale de l'instant de prédiction) : là où le service se joue.
    # Une moyenne globale peut cacher une dégradation sur ces heures.
    peak = test_df["hour"].isin(PEAK_HOURS).to_numpy()
    mae_peak = float(mean_absolute_error(y_test[peak], pred[peak])) if peak.any() else mae_model

    out_dir.mkdir(parents=True, exist_ok=True)
    model_path = out_dir / MODEL_FILENAME
    joblib.dump(pipeline, model_path)

    metadata = {
        "model_name": "velov-availability",
        "model_version": version,
        "trained_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "task": "Prédire le nombre de vélos disponibles à H+1 par station",
        "input_columns": RAW_COLUMNS,
        "features": FEATURES,
        "target": TARGET,
        "params": {"seed": seed, "learning_rate": learning_rate, "max_iter": max_iter, "test_days": test_days},
        "metrics": {
            "mae_model": round(mae_model, 3),
            "mae_baseline_persistence": round(mae_baseline, 3),
            "mae_model_peak_hours": round(mae_peak, 3),
            "test_days": test_days,
            "n_train": int(len(train_df)),
            "n_test": int(len(test_df)),
        },
        "artifact": {"file": MODEL_FILENAME, "sha256": sha256_of(model_path)},
        "data_source": source,
        "data_sha256": data_hash,
        "data_period": {
            "start": frame["timestamp"].min().isoformat(),
            "end": frame["timestamp"].max().isoformat(),
        },
        "runtime": {
            "python": platform.python_version(),
            "scikit-learn": sklearn.__version__,
            "pandas": pd.__version__,
            "numpy": np.__version__,
        },
    }
    (out_dir / METADATA_FILENAME).write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description="Entraîne le modèle Vélo'v v0.")
    parser.add_argument("--source", choices=["csv", "gold"], default="csv", help="origine des données")
    parser.add_argument("--data", type=Path, default=Path("data/velov_history.csv"))
    parser.add_argument("--out", type=Path, default=Path("models"))
    parser.add_argument("--version", default="0.1.0")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--learning-rate", type=float, default=0.1)
    parser.add_argument("--max-iter", type=int, default=200)
    parser.add_argument("--test-days", type=int, default=14)
    parser.add_argument("--mlflow", action="store_true", help="tracer le run dans MLflow (URL : MLFLOW_TRACKING_URI)")
    args = parser.parse_args()

    metadata = train(
        args.data,
        args.out,
        version=args.version,
        test_days=args.test_days,
        seed=args.seed,
        source=args.source,
        learning_rate=args.learning_rate,
        max_iter=args.max_iter,
    )
    m = metadata["metrics"]
    print(f"MAE modèle   : {m['mae_model']:.3f} vélos")
    print(f"MAE baseline : {m['mae_baseline_persistence']:.3f} vélos (persistance)")
    print(f"MAE pointe   : {m['mae_model_peak_hours']:.3f} vélos (heures de pointe)")
    print(f"Artefact     : {args.out / MODEL_FILENAME} (sha256 {metadata['artifact']['sha256'][:12]}...)")
    if args.mlflow:
        from velov.tracking import log_run  # import local : MLflow n'est pas requis pour servir le modèle

        run_id, model_version = log_run(metadata, args.out)
        print(f"Run {run_id} tracé ; modèle enregistré en version {model_version}, alias challenger")


if __name__ == "__main__":
    main()
