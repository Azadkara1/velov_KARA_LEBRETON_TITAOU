"""Test de MODÈLE (CI) : un entraînement rapide sur données simulées doit rester sain.

Ces tests ne vérifient pas du code mais le comportement du modèle entraîné : si une modification
des features ou des hyperparamètres le dégrade, la CI le voit avant le registre.
"""

import numpy as np
import pandas as pd

from velov.features import FEATURES, add_features
from velov.train import train


def test_model_beats_persistence_baseline(model_dir):
    """EX-05 : le modèle justifie sa complexité face à la baseline de persistance."""
    import json

    m = json.loads((model_dir / "metadata.json").read_text(encoding="utf-8"))["metrics"]
    assert m["mae_model"] < m["mae_baseline_persistence"]


def test_metadata_traces_params_and_data(model_dir):
    import json

    meta = json.loads((model_dir / "metadata.json").read_text(encoding="utf-8"))
    assert set(meta["params"]) == {"seed", "learning_rate", "max_iter", "test_days"}
    assert len(meta["data_sha256"]) == 64
    assert meta["data_period"]["start"] < meta["data_period"]["end"]
    assert "mae_model_peak_hours" in meta["metrics"]


def test_predictions_are_finite_and_plausible(model_dir):
    import joblib

    model = joblib.load(model_dir / "model.joblib")
    raw = pd.DataFrame(
        {
            "station_id": [1, 2, 3],
            "timestamp": pd.to_datetime(["2026-06-02T06:00Z", "2026-06-02T16:00Z", "2026-06-06T12:00Z"]),
            "capacity": [20, 30, 15],
            "bikes_available": [10, 3, 15],
            "temperature": [18.0, 25.0, 9.0],
            "is_raining": [False, True, False],
        }
    )
    pred = model.predict(add_features(raw)[FEATURES])
    assert np.isfinite(pred).all()
    assert (pred > -5).all() and (pred < 50).all()


def test_same_seed_gives_same_metrics(tmp_path):
    """Reproductibilité : mêmes données + même seed = mêmes métriques (sinon un run n'est pas traçable)."""
    from velov.data import simulate

    data = tmp_path / "h.csv"
    simulate(days=20, n_stations=3, seed=0).to_csv(data, index=False)
    a = train(data, tmp_path / "a", test_days=3, seed=5)
    b = train(data, tmp_path / "b", test_days=3, seed=5)
    assert a["metrics"] == b["metrics"]
    assert a["data_sha256"] == b["data_sha256"]
