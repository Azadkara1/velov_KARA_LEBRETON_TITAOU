# velov-mlops

Projet fil rouge du cours **Industrialisation de l'IA dans le Cloud** (M2 Data Engineering / IA).

Objectif métier : prédire, pour chaque station Vélo'v, le nombre de vélos disponibles **dans une heure**,
et servir cette prédiction via une API fiable, conteneurisée, puis déployée (on-premise et cloud).

## Progression par session

Chaque étape du cours correspond à un tag git. Absent ou bloqué : repartez du tag de fin de la session précédente.

| Tag | Contenu |
|---|---|
| `s1-start` | Données simulées, features, entraînement. API à compléter (TP1) |
| `s1-end` | Modèle v0 servi par FastAPI, tests pytest |

```bash
git checkout s1-end          # récupérer l'état de fin de S1
git checkout -b mon-binome   # travailler sur sa propre branche
```

## Démarrage rapide

Prérequis : Python 3.11+ (3.12 recommandé), git. Docker sera nécessaire en S2.

```bash
python -m venv .venv
source .venv/bin/activate            # Windows : .venv\Scripts\activate
pip install -r requirements-dev.txt
pip install -e .                     # rend le package velov importable

python -m velov.data                 # génère data/velov_history.csv (simulateur, seed fixe)
python -m velov.train                # entraîne et écrit models/model.joblib + models/metadata.json
python -m velov.train --mlflow       # idem + journalisation MLflow (puis : mlflow ui)
pytest                               # tests
uvicorn velov.api.main:app --reload  # API sur http://127.0.0.1:8000/docs (--reload : en dev uniquement)
```

Exemple d'appel :

```bash
curl -X POST http://127.0.0.1:8000/v1/predict \
  -H "Content-Type: application/json" \
  -d '{"station_id": 3, "timestamp": "2026-10-06T08:00:00+02:00", "capacity": 20,
       "bikes_available": 12, "temperature": 14.5, "is_raining": false}'
```

Le `timestamp` doit porter un fuseau (`+02:00`, `Z`...) : sans fuseau, l'API répond 422.
Les instants sont renvoyés et journalisés en UTC (`"target_timestamp": "2026-10-06T07:00:00Z"`).

## Lancer avec Docker (S2)

Le modèle est embarqué dans l'image : il faut l'entraîner **avant** le build.

```bash
python -m velov.data && python -m velov.train     # crée models/model.joblib + metadata.json
cp .env.example .env

# Tags : version du package (pyproject.toml) + commit court, repris en labels OCI
VERSION=1.0.0
GIT_SHA=$(git rev-parse --short HEAD)
docker build --build-arg VERSION=$VERSION --build-arg GIT_SHA=$GIT_SHA \
  -t velov-api:$VERSION -t velov-api:$GIT_SHA .
docker run -d --name vt -p 8000:8000 --env-file .env velov-api:$VERSION

docker ps                                  # STATUS doit passer à (healthy)
curl http://localhost:8000/health          # le process répond
curl http://localhost:8000/ready           # le modèle est chargé
curl -X POST http://localhost:8000/v1/predict   -H "Content-Type: application/json"   -d '{"station_id": 3, "timestamp": "2026-10-06T08:00:00+02:00", "capacity": 20,
       "bikes_available": 12, "temperature": 14.5, "is_raining": false}'

docker logs vt                             # lire ce que dit l'application
docker stop vt && docker rm vt             # arrêter
```

Retrouver la version et le commit d'une image :

```bash
docker image ls velov-api
docker inspect -f '{{index .Config.Labels "org.opencontainers.image.revision"}}' velov-api:1.0.0
```

En cas de problème, méthode dans l'ordre : `docker ps -a`, `docker logs`, `docker exec`, `docker inspect`.

## Lancer avec Compose : API + PostgreSQL (S2)

Chaque prédiction est enregistrée dans une table `predictions` (EX-08).

```bash
python -m velov.data && python -m velov.train     # crée models/model.joblib + metadata.json
cp .env.example .env                              # puis fixer un vrai POSTGRES_PASSWORD

docker compose up --build -d
docker compose ps                                  # les deux services doivent passer healthy

curl http://localhost:8000/ready
curl -X POST http://localhost:8000/v1/predict \
  -H "Content-Type: application/json" \
  -d '{"station_id": 3, "timestamp": "2026-10-06T08:00:00+02:00", "capacity": 20,
       "bikes_available": 12, "temperature": 14.5, "is_raining": false}'

# vérifier que la prédiction est bien en base
docker compose exec db psql -U velov -c "SELECT id, station_id, predicted_bikes, model_version, created_at FROM predictions;"

docker compose logs -f api                          # lire les logs
docker compose down                                 # arrêter, les données restent (volume pgdata)
docker compose down -v                               # arrêter et effacer les données
```

Si `DATABASE_URL` n'est pas définie, ou si la base est indisponible, l'API démarre et prédit
quand même : l'échec d'écriture est seulement journalisé (`docker compose logs api`), jamais
renvoyé au client (EX-07).

## Exigences du projet

Le service doit respecter les exigences de [docs/exigences.md](docs/exigences.md), de S1 à S9.
Chaque rendu indique celles qu'il couvre et comment le vérifier.


## Structure

```
src/velov/
  data.py          simulateur de données (remplacé par l'open data en S3, même schéma)
  features.py      features partagées entraînement / API (anti training-serving skew)
  train.py         entraînement, baseline, artefact + metadata.json, option MLflow
  api/main.py      FastAPI : /health, /ready, /v1/model, /v1/predict, /v1/predict/batch
  api/schemas.py   contrat d'entrée / sortie (Pydantic)
tests/             pytest (features, API)
docs/              templates : model card, runbook, ADR
exercices/         démo pickle (S1)
```

## Usage de l'IA générative

Chaque activité indique son mode : **sans IA**, **IA déclarée** ou **IA imposée**.
En mode IA déclarée, ajoutez dans la description de vos commits ou de votre rendu :
outil utilisé, ce que vous lui avez demandé, ce que vous avez vérifié ou corrigé.
