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

docker build -t velov-api:0.1.0 .
docker run -d --name vt -p 8000:8000 --env-file .env velov-api:0.1.0

docker ps                                  # STATUS doit passer à (healthy)
curl http://localhost:8000/health          # le process répond
curl http://localhost:8000/ready           # le modèle est chargé
curl -X POST http://localhost:8000/v1/predict   -H "Content-Type: application/json"   -d '{"station_id": 3, "timestamp": "2026-10-06T08:00:00+02:00", "capacity": 20,
       "bikes_available": 12, "temperature": 14.5, "is_raining": false}'

docker logs vt                             # lire ce que dit l'application
docker stop vt && docker rm vt             # arrêter
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

## Pipeline de données (S3)

```
CSV / collecte --ingest--> bronze.velov_raw --dbt--> silver.stg_observations --dbt--> gold.gold_hourly_features --> train.py
 (brut, tel que reçu)      (PK station+instant)      (propre, 1 ligne / station / heure)   (contrat enforced)       (contrat Pandera)
```

| Couche | Rôle | Garantie |
|---|---|---|
| bronze | données brutes, jamais corrigées | idempotente : clé primaire + `ON CONFLICT DO NOTHING` |
| silver | heure pleine, dédoublonnage, lignes incohérentes écartées | une ligne par (station, heure) |
| gold | table d'entraînement : colonnes du contrat + `bikes_next_hour` | schéma figé (`contract.enforced`), tests dbt |

```bash
pip install -r requirements-dev.txt && pip install -e .
cp .env.example .env                      # fixer POSTGRES_PASSWORD
set -a; . ./.env; set +a                  # PowerShell : $env:POSTGRES_PASSWORD="..."
docker compose up -d db                   # PostgreSQL, publié sur 127.0.0.1:5432 uniquement
python -m velov.data                      # génère data/velov_history.csv
python -m velov.ingest                    # 1er passage : N lignes nouvelles
python -m velov.ingest                    # 2e passage  : 0 ligne nouvelle (idempotent)
cd dbt/velov && dbt build --profiles-dir . && cd ../..   # silver + gold + tests
python -m velov.train --source gold       # lit gold, vérifie le contrat Pandera, entraîne
```

Vérifier l'idempotence de bout en bout (EX-10) : l'empreinte doit être identique avant et après un rejeu.

```bash
docker compose exec db psql -U velov -At -c "select md5(string_agg(t::text,'|' order by station_id, timestamp)) from gold.gold_hourly_features t"
```

Choix de conception : les features dérivées (heure, jour, `occupancy_rate`) ne sont **pas** calculées en SQL.
Elles restent dans `velov.features`, partagé avec l'API, pour qu'il n'y ait qu'une seule implémentation (anti training-serving skew).
Choix batch / streaming : [ADR-0002](docs/adr/0002-batch-micro-batch-streaming.md).

## Tracer, promouvoir, intégrer (S4)

### 1. Serveur MLflow (PostgreSQL + volume d'artefacts)

```bash
cp .env.example .env                       # fixer MLFLOW_DB_PASSWORD (jamais dans git)
docker compose -f compose.mlflow.yaml up -d --build
docker compose -f compose.mlflow.yaml ps   # mlflow et mlflow-db : healthy
# interface : http://127.0.0.1:5000
```

Runs, métriques et registre sont dans PostgreSQL (volume `mlflow-pgdata`), les modèles et fichiers dans le
volume `mlflow-artifacts` : un `restart` ne perd rien (vérifié : versions et alias identiques après redémarrage).
Le serveur est écouté sur `127.0.0.1` par défaut. Sur une VM : `MLFLOW_BIND=0.0.0.0` et
`MLFLOW_ALLOWED_HOSTS=<ip-vm>:*,localhost:*` dans `.env`, pour que l'équipe y accède.

### 2. Runs tracés

```bash
export MLFLOW_TRACKING_URI=http://127.0.0.1:5000     # PowerShell : $env:MLFLOW_TRACKING_URI="..."
python -m velov.data
python -m velov.train --mlflow --seed 42
```

Chaque run porte : paramètres (`seed`, `learning_rate`, `max_iter`, `test_days`), métriques de **test**
(`mae_model`, `mae_baseline_persistence`, `mae_model_peak_hours`), tags (`git_commit`, `git_dirty`, `data_sha256`,
`data_start`, `data_end`), le modèle avec sa signature, et le paquet `package/model.joblib` + `metadata.json`.
`git_dirty=true` signale un run lancé avec des modifications non commitées : il n'est pas reproductible à l'identique.

**Écart entre seeds** (mêmes données, 90 jours, 20 stations, test sur les 14 derniers jours) :

| seed | MAE modèle | MAE heures de pointe |
|---|---|---|
| 0 | 1,360 | 1,467 |
| 1 | 1,341 | 1,395 |
| 2 | 1,340 | 1,407 |
| 3 | 1,345 | 1,408 |
| 4 | 1,342 | 1,412 |
| 5 | 1,349 | 1,424 |
| 7 | 1,345 | 1,427 |
| 42 | 1,339 | 1,415 |

Deux runs avec la **même** seed donnent exactement les mêmes métriques (reproductible). Entre seeds, la MAE varie
de **0,021** (1,339 à 1,360) et la MAE de pointe de **0,072**. Seed 42 contre seed 7 : 1,339 contre 1,345 (écart 0,006).
Cet écart est du bruit, pas une amélioration : il fixe les seuils de la règle de promotion.

### 3. Registre et règle de promotion

Le modèle `velov-availability` est enregistré à chaque run avec l'alias `challenger` (candidat). L'alias `champion`
désigne le modèle autorisé à être servi. Le passage de l'un à l'autre n'est pas manuel :

```bash
python -m velov.registry promote            # applique la règle ; code retour 1 si refusé
python -m velov.registry promote --dry-run  # verdict seul
```

Le challenger est promu si les **trois** conditions sont vraies :

| # | Condition | Pourquoi |
|---|---|---|
| 1 | MAE du modèle < MAE de la baseline de persistance | le modèle justifie sa complexité (EX-05) |
| 2 | MAE inférieure d'au moins **0,03** à celle du champion | 0,03 > 0,021, l'étendue du bruit entre seeds : on ne promeut pas du hasard |
| 3 | MAE aux heures de pointe pas pire que celle du champion de plus de **0,08** | 0,08 > 0,072, étendue du bruit de pointe : une meilleure moyenne ne doit pas cacher une pire pointe |

Sans champion, seule la condition 1 s'applique. Exemple réel : le premier challenger devient champion ; un nouvel
entraînement seed 42 (gain de 0,006) est **refusé** : `2. gain +0.006 vélo(s) < marge exigée 0.030 (bruit possible)`.
La règle est une fonction pure (`velov.registry.decide`), testée dans `tests/test_registry.py`.

### 4. Intégration continue

`.github/workflows/ci.yml`, sur chaque push et pull request : `lint` (ruff), `test` (pytest, dont
`tests/test_model.py` : le modèle bat la baseline, prédictions plausibles, métriques reproductibles) et `gitleaks`
(historique complet). Les actions sont épinglées sur un SHA de commit, les droits du workflow sont limités à la lecture.
`.gitleaksignore` écarte un seul faux positif connu, par empreinte exacte : la clé factice de l'exercice d'audit S2.

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
  ingest.py        ingestion bronze idempotente (CSV -> PostgreSQL)
  contract.py      contrat de la table gold (Pandera), vérifié avant l'entraînement
  tracking.py      trace un run dans MLflow, enregistre le modèle (alias challenger)
  registry.py      règle de promotion challenger -> champion
compose.mlflow.yaml + docker/mlflow/   serveur MLflow (PostgreSQL + volume d'artefacts)
.github/workflows/ci.yml               lint, tests, gitleaks
dbt/velov/         modèles dbt silver et gold, tests, contrat enforced
tests/             pytest (features, API)
docs/              templates : model card, runbook, ADR
exercices/         démo pickle (S1)
```

## Usage de l'IA générative

Chaque activité indique son mode : **sans IA**, **IA déclarée** ou **IA imposée**.
En mode IA déclarée, ajoutez dans la description de vos commits ou de votre rendu :
outil utilisé, ce que vous lui avez demandé, ce que vous avez vérifié ou corrigé.
