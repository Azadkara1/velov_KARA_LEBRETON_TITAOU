# Récapitulatif — TP Docker (S2) — Industrialisation de l'IA dans le Cloud

> Document écrit pour servir de support de révision (à coller dans Claude ou à relire soi-même)
> et de passation pour un collègue qui reprend le projet. Il couvre deux choses distinctes :
> **(A)** un exercice d'audit, fait dans un dossier séparé, hors de ce repo ;
> **(B)** le TP2 du projet fil rouge "velov", fait dans CE repo (`velov_KARA_LEBRETON_TITAOU`).
> Ce fichier lui-même se trouve dans (B) : `velov_KARA_LEBRETON_TITAOU/CLAUDE.md`.

## Contexte du cours (S2 · Docker)

But de la session : faire tourner l'API de prédiction Vélo'v à l'identique sur n'importe quelle
machine, avec Docker. Trois parties : conteneurs (concepts), Dockerfile de production, puis
Compose + sécurité. Checklist de production à 8 règles (slide 16 du support de cours) :

| # | Règle | Ce qu'elle évite |
|---|---|---|
| 1 | Image de base slim, version explicite | Une base qui change sans prévenir |
| 2 | Dépendances épinglées, installées avant le code | Builds lents et non reproductibles |
| 3 | Plusieurs étapes (multi-stage) | Les outils de build en production |
| 4 | Un `.dockerignore` | Envoyer `.git`, `.env` ou des données au build |
| 5 | Un utilisateur non-root | Une faille qui donne tous les droits |
| 6 | Aucun secret dans l'image | Des identifiants lisibles par quiconque récupère l'image |
| 7 | `CMD` en forme JSON | Un arrêt brutal (SIGKILL) à chaque déploiement |
| 8 | Un healthcheck sur `/ready` | Un conteneur "sain" qui ne sait pas prédire |

---

## (A) Exercice d'audit — dossier `docker_exo` (séparé, pas sur GitHub)

Fichier source : `exercice.pptx`. Consigne : une IA a généré un Dockerfile pour une API
FastAPI qui sert un modèle scikit-learn. L'image se construit, l'API répond. **Faut-il
l'accepter en production ?**

Dockerfile audité (fourni par l'exercice) :
```dockerfile
FROM python:latest
WORKDIR /app
COPY . .
RUN pip install fastapi uvicorn scikit-learn pandas joblib
ENV PYTHONPATH=/app/src
ENV MODEL_DIR=/app/models
ENV API_KEY=sk-prod-7f3a9c2e41b8
EXPOSE 8000
HEALTHCHECK CMD curl -f http://localhost:8000/health || exit 1
CMD uvicorn velov.api.main:app --host 0.0.0.0 --port 8000 --reload
```

12 problèmes trouvés, du plus grave au moins grave (détail complet dans
`docker_exo/AUDIT.md`) :

1. **Secret en clair** (`ENV API_KEY=...`) — lisible par `docker history`, jamais effaçable
   d'une couche antérieure. → le secret doit arriver au démarrage via `--env-file`.
2. **Pas de `.dockerignore`** — `COPY . .` envoie `.git`, `.env`, `data/` dans l'image.
3. **Pas de `USER`** — le process tourne en root.
4. **Dépendances non épinglées** — un modèle scikit-learn sérialisé n'est pas garanti
   d'une version à l'autre : builds non reproductibles.
5. **`python:latest`** — base qui change sans prévenir, image énorme (~1 Go).
6. **`--reload` en production** — mode développement, pas fait pour un déploiement.
7. **`CMD` en forme shell** — le PID 1 est `/bin/sh`, qui ne transmet pas SIGTERM à uvicorn :
   `docker stop` attend 10 s puis tue (SIGKILL), coupant les requêtes en cours.
8. **Healthcheck sur `/health` avec `curl`** — `/health` dit seulement "le process répond",
   pas "le modèle est chargé" ; et `curl` disparaît dans une image `slim`.
9. **Une seule étape** — les outils de build restent dans l'image finale.
10. **Dépendances installées après le code** — invalide le cache à chaque changement.
11. **`PYTHONPATH` au lieu d'un vrai paquet installé** — bricolage.
12. Pas de `PYTHONUNBUFFERED`, cache pip conservé.

**Ce qu'une IA trouve en général** : le secret, `latest`, root, `--reload`.
**Ce qu'elle rate souvent** : la forme shell du `CMD` et SIGTERM, `/health` ≠ `/ready`,
le lien version-scikit-learn/modèle sérialisé, `curl` absent d'une image slim.
**Leçon** : l'IA a fait exactement ce qu'on lui a demandé ; les exigences de production
n'étaient pas dans la question initiale.

Un Dockerfile corrigé (multi-stage, non-root, healthcheck sur `/ready`, CMD JSON) est dans
`docker_exo/Dockerfile`, avec un commentaire `[Rn]` par ligne qui renvoie à la règle corrigée.
Ce dossier **n'est pas** sur GitHub : c'est un exercice local, séparé du projet fil rouge.

---

## (B) Projet fil rouge "velov" — ce repo

Repo : `https://github.com/Azadkara1/velov_KARA_LEBRETON_TITAOU`, branche `main`.

### Historique des commits

| Commit | Contenu |
|---|---|
| `f687c9e` | Point de départ fourni par le prof (S1, TODO à compléter) |
| `e461fa8` | **TP1** : schémas Pydantic, endpoints `/health`, `/ready`, `/v1/model`, `/v1/predict`, tests |
| `c83e044` | **TP2 début** : Dockerfile multi-stage non-root, `.dockerignore`, section Docker du README |
| `bc6a4ed` | Un aller-retour sur une erreur volontaire (voir encadré ci-dessous) |
| `3fbc179` | **TP2 Compose** : `compose.yaml`, module `db.py`, journalisation des prédictions, correction d'un bug d'encodage réel |

> **Encadré — erreur volontaire envoyée à un autre groupe.** Une consigne de TP demandait
> d'introduire une erreur dans le repo avant de le partager à un autre binôme, pour qu'il la
> diagnostique avec `docker ps`, `docker logs`, `docker exec`. Deux erreurs ont été essayées
> successivement : une route API mal nommée (`/v1/prediction` au lieu de `/v1/predict`,
> → 404), puis une faute de frappe dans le `CMD` du Dockerfile (`velov.api.app` au lieu de
> `velov.api.main`, → le conteneur boucle en `Restarting`, cause visible dans `docker logs`).
> **Au commit `3fbc179`, cette erreur a été corrigée** pour pouvoir développer la suite du
> TP (Compose). Le repo est donc actuellement dans un état propre, sans erreur volontaire.
> Si l'exercice de debug croisé n'est pas terminé, il faut réintroduire l'erreur avant de
> renvoyer le lien à l'autre groupe.

### TP1 — l'API (complétée)

Fichiers : `src/velov/api/schemas.py`, `src/velov/api/main.py`.

- **`schemas.py`** (`PredictionRequest`) : 6 champs (`station_id`, `timestamp`, `capacity`,
  `bikes_available`, `temperature`, `is_raining`), avec bornes (`Field(ge=..., le=...)`),
  `extra="forbid"` (refuse un champ inconnu → 422), un validateur qui refuse
  `bikes_available > capacity`, et `timestamp` normalisé en UTC via `AwareDatetime` + un
  `field_validator` (un timestamp sans fuseau est ambigu, donc refusé → 422).
- **`main.py`** :
  - `/health` : 200 toujours (liveness, ne dépend pas du modèle).
  - `/ready` : 200 + version du modèle si chargé, 503 sinon (readiness).
  - `/v1/model` : métadonnées du modèle (version, métriques, versions des libs).
  - `/v1/predict` : construit un DataFrame d'une ligne, appelle `add_features` (**importé**
    de `velov.features`, jamais recalculé dans l'API — règle d'or anti
    *training-serving skew* : une seule implémentation des features, entraînement et
    serving utilisent exactement le même code), prédit, borne le résultat entre 0 et
    `capacity`, renvoie `target_timestamp = timestamp + 1h`.
- **Tests ajoutés** (`tests/test_api.py`) : `/health` 200 + `/ready` 503 sans modèle,
  version du modèle dans `/ready`, champ inconnu → 422, timestamp sans fuseau → 422,
  prédiction bornée dans `[0, capacity]`. **13 tests passent, `ruff check`/`format` propres.**

### TP2 — Dockerfile (multi-stage, checklist S2 appliquée)

Fichier : `Dockerfile`, deux étapes :

```dockerfile
# Étape 1 : builder — jetée à la fin
FROM ${PYTHON_IMAGE} AS builder
RUN python -m venv /opt/venv          # tout dans un seul dossier, facile à copier
COPY requirements.txt .  &&  RUN pip install -r requirements.txt   # avant le code : cache
COPY pyproject.toml . && COPY src/ src/ && RUN pip install --no-deps .

# Étape 2 : runtime — ce qui part en production
FROM ${PYTHON_IMAGE} AS runtime
RUN useradd --uid 10001 appuser       # règle 5 : non-root
COPY --from=builder /opt/venv /opt/venv   # seul le venv est récupéré, pas les outils de build
COPY models/ models/
USER appuser
HEALTHCHECK CMD ["python", "-c", "...urlopen('http://127.0.0.1:8000/ready')..."]  # règle 8
CMD ["uvicorn", "velov.api.main:app", "--host", "0.0.0.0", "--port", "8000"]      # règle 7 (JSON)
```

Le modèle (`models/model.joblib`, `models/metadata.json`) n'est **pas** dans git
(`.gitignore` l'exclut) : il faut l'entraîner avant chaque build (`python -m velov.train`).
`.dockerignore` exclut `.git`, `.env`, `data/`, `tests/`, etc.

**Bug réel trouvé et corrigé en testant** (pas un exercice, un vrai bug) : `train.py`
écrivait `metadata.json` avec `Path.write_text(...)` **sans préciser l'encodage**. Sous
Windows, Python utilise par défaut l'encodage de la locale (`cp1252`), pas l'UTF-8. Le
caractère accentué dans `"task": "Prédire..."` devenait un octet invalide en UTF-8. Ça
fonctionnait en local sous Windows (même encodage à la lecture), mais le conteneur Linux
(UTF-8 par défaut) plantait au démarrage avec `UnicodeDecodeError`. **C'est exactement le
piège "ça marche sur ma machine" du slide 2 du cours** — bon exemple à citer à l'oral.
Correction : `encoding="utf-8"` explicite à l'écriture (`train.py`) et à la lecture
(`main.py`, fonction `load_model`).

### TP2 — Compose : API + PostgreSQL (dernier commit, `3fbc179`)

**But (exigence EX-08)** : chaque prédiction est enregistrée en base, avec les entrées,
la sortie, la version du modèle et un horodatage UTC.

Fichiers ajoutés :
- **`compose.yaml`** :
  ```yaml
  services:
    api:
      build: .
      ports: ["8000:8000"]
      environment:
        DATABASE_URL: postgresql://velov:${POSTGRES_PASSWORD:?}@db:5432/velov
      depends_on:
        db: {condition: service_healthy}
    db:
      image: postgres:17-alpine
      environment: {POSTGRES_USER: velov, POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?}, POSTGRES_DB: velov}
      volumes: ["pgdata:/var/lib/postgresql/data"]
      healthcheck: {test: ["CMD-SHELL", "pg_isready -U velov"]}
  volumes:
    pgdata:
  ```
  Points à retenir : `${POSTGRES_PASSWORD:?}` fait échouer le démarrage si la variable
  manque (pas de valeur par défaut silencieuse) ; `db` n'a **pas** de section `ports` →
  invisible depuis l'extérieur, seule l'API peut la joindre, par son nom (`db`), sur le
  réseau privé que Compose crée automatiquement ; `depends_on: service_healthy` fait
  attendre que Postgres accepte vraiment des connexions (pas juste que son process démarre).
- **`src/velov/api/db.py`** : pool de connexions `psycopg_pool.ConnectionPool`, table
  `predictions` créée au démarrage si absente (`CREATE TABLE IF NOT EXISTS`),
  `record_prediction()` insère une ligne. **Toute erreur d'écriture est seulement
  journalisée (`logger.exception`), jamais renvoyée au client** (exigence EX-07) : si
  Postgres tombe, l'API continue de prédire, elle ne casse pas pour un problème de
  journalisation.
- **`main.py`** : dans `lifespan`, ouverture du pool si `DATABASE_URL` est définie (sinon
  warning dans les logs, l'API démarre quand même sans journaliser) ; dans
  `/v1/predict`, appel à `db.record_prediction(...)` après le calcul, avant de répondre.
- **`requirements.txt`** : ajout de `psycopg[binary,pool]==3.2.3`.
- **`.env.example`** : ajout de `POSTGRES_PASSWORD=change-me`.

**Vérifié en conditions réelles** (Docker Desktop actif) :
```
docker compose up --build -d
docker compose ps          → api (healthy), db (healthy), en quelques secondes
POST /v1/predict ×2        → 200, predicted_bikes renvoyé
SELECT * FROM predictions  → 2 lignes, avec station_id, predicted_bikes, model_version, created_at
```

---

## Instructions pour un collègue qui reprend le projet

### 0. Récupérer le projet

```bash
git clone https://github.com/Azadkara1/velov_KARA_LEBRETON_TITAOU.git
cd velov_KARA_LEBRETON_TITAOU
```

### 1. Construire et lancer l'image seule (sans base de données)

```bash
# Entraîner le modèle AVANT de construire l'image : l'image embarque models/
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux : source .venv/bin/activate
pip install -r requirements-dev.txt
pip install -e .
python -m velov.data            # génère data/velov_history.csv
python -m velov.train           # écrit models/model.joblib + models/metadata.json

cp .env.example .env            # Windows : copy .env.example .env

docker build -t velov-api:0.1.0 .
docker run -d --name vt -p 8000:8000 --env-file .env velov-api:0.1.0

docker ps                       # attendre que STATUS affiche (healthy), ~15-20 s
curl http://localhost:8000/health
curl http://localhost:8000/ready
curl -X POST http://localhost:8000/v1/predict -H "Content-Type: application/json" -d "{\"station_id\": 3, \"timestamp\": \"2026-10-06T08:00:00+02:00\", \"capacity\": 20, \"bikes_available\": 12, \"temperature\": 14.5, \"is_raining\": false}"

docker logs vt                  # si quelque chose ne va pas
docker stop vt && docker rm vt  # nettoyer avant de passer à Compose (sinon conflit de port 8000)
```

### 2. Lancer la stack complète avec Compose (API + PostgreSQL)

```bash
# modèle déjà entraîné à l'étape 1 ; sinon le faire maintenant (python -m velov.train)
# .env déjà créé à l'étape 1 ; ouvrir .env et mettre un vrai mot de passe dans POSTGRES_PASSWORD

docker compose up --build -d
docker compose ps                # les DEUX services doivent passer à (healthy)

curl http://localhost:8000/ready
curl -X POST http://localhost:8000/v1/predict -H "Content-Type: application/json" -d "{\"station_id\": 3, \"timestamp\": \"2026-10-06T08:00:00+02:00\", \"capacity\": 20, \"bikes_available\": 12, \"temperature\": 14.5, \"is_raining\": false}"

docker compose exec db psql -U velov -c "SELECT id, station_id, predicted_bikes, model_version, created_at FROM predictions;"

docker compose logs -f api       # Ctrl+C pour sortir
docker compose down              # arrête, garde les données (volume pgdata)
docker compose down -v           # arrête et efface les données
```

### 3. Pièges les plus probables (rencontrés en testant ce projet)

| Symptôme | Cause | Solution |
|---|---|---|
| `port is already allocated` au démarrage | Un conteneur précédent (ex. `docker run ... -p 8000:8000`) occupe déjà le port 8000 | `docker ps` pour le repérer, `docker stop <nom>`, relancer |
| Le conteneur `api` boucle en `Restarting` | Le `Dockerfile` ou le code a une faute de frappe (ex. mauvais nom de module dans `CMD`) | `docker compose logs api` donne l'erreur exacte en clair |
| `UnicodeDecodeError` au chargement du modèle | `metadata.json` réécrit sur Windows sans `encoding="utf-8"` explicite | Doit être corrigé dans ce repo (commit `3fbc179`) ; si ça revient, vérifier `train.py` |
| `/ready` reste à 503 | Le dossier `models/` est vide : le modèle n'a pas été entraîné avant le build | `python -m velov.train` puis **rebuild** l'image (`docker compose up --build`) |
| Compose refuse de démarrer, erreur sur `POSTGRES_PASSWORD` | `.env` absent ou variable non définie (`${POSTGRES_PASSWORD:?}` est volontairement strict) | `cp .env.example .env` et y mettre une valeur |
| `relation "predictions" does not exist` | La table se crée au démarrage de l'API (`db.open_pool`) ; elle n'existe pas si l'API n'a jamais démarré avec succès | Vérifier `docker compose logs api`, corriger la cause, relancer |
| Aucune ligne dans `predictions` après un `POST /v1/predict` qui répond pourtant 200 | `DATABASE_URL` absente de l'environnement de l'API (ex. lancé avec `docker run` au lieu de `docker compose up`) | Les écritures en base sont volontairement silencieuses en cas d'échec (EX-07) : regarder `docker compose logs api` pour le détail |

### 4. Exigences couvertes à ce stade (voir `docs/exigences.md`)

EX-01 (erreurs 4xx), EX-02 (`/ready` fiable), EX-03 (`model_version` dans chaque réponse),
EX-04 (démarrage documenté, Python et Docker), EX-06 (aucun secret dans l'image ni le
repo), EX-07 (erreurs observables dans les logs), EX-08 (prédictions journalisées en base).
Reste à faire : tagging image avec version + SHA court du commit (Should), publication
GHCR + scan Trivy (Stretch), mise à jour du runbook (`docs/runbook.md`) et de l'ADR sur le
modèle dans l'image ou chargé au démarrage.
