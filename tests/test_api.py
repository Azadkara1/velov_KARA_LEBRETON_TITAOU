"""Tests de l'API. Les fixtures (client, valid_payload, model_dir) sont dans conftest.py.

TODO 8 [Must] : faire passer les deux tests ci-dessous (une prédiction valide, une entrée invalide).
TODO 9 [Should] : en ajouter d'autres, par exemple :
  - /health renvoie 200 et /ready 503 quand MODEL_DIR pointe vers un dossier vide
  - un champ inconnu renvoie 422
  - un timestamp sans fuseau ("2026-10-06T08:00:00") renvoie 422
  - la prédiction est comprise entre 0 et capacity
  - (Stretch) une station jamais vue à l'entraînement ne fait pas planter l'API
"""

from datetime import UTC, datetime


def test_predict_valid(client, valid_payload):
    r = client.post("/v1/predict", json=valid_payload)
    assert r.status_code == 200
    # 8 h à Lyon (+02:00) + 1 h = 7 h UTC, quel que soit le fuseau dans lequel l'API répond
    target = datetime.fromisoformat(r.json()["target_timestamp"])
    assert target == datetime(2026, 10, 6, 7, tzinfo=UTC)


def test_predict_rejects_bikes_above_capacity(client, valid_payload):
    r = client.post("/v1/predict", json={**valid_payload, "bikes_available": 25})
    assert r.status_code == 422


def test_health_ok_and_ready_503_without_model(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from velov.api.main import app

    monkeypatch.setenv("MODEL_DIR", str(tmp_path))  # dossier vide : pas de modèle
    with TestClient(app) as c:
        assert c.get("/health").status_code == 200
        assert c.get("/ready").status_code == 503


def test_ready_returns_model_version(client):
    r = client.get("/ready")
    assert r.status_code == 200
    assert r.json()["model_version"] == "0.0.0-test"


def test_unknown_field_rejected(client, valid_payload):
    assert client.post("/v1/predict", json={**valid_payload, "foo": 1}).status_code == 422


def test_timestamp_without_timezone_rejected(client, valid_payload):
    r = client.post("/v1/predict", json={**valid_payload, "timestamp": "2026-10-06T08:00:00"})
    assert r.status_code == 422


def test_prediction_within_capacity(client, valid_payload):
    r = client.post("/v1/predict", json=valid_payload)
    assert 0 <= r.json()["predicted_bikes"] <= valid_payload["capacity"]
