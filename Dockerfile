# Image de serving de l'API velov (checklist S2)
ARG PYTHON_IMAGE=python:3.12-slim

# ---------- Étape 1 : builder (outils de build et caches, jetée à la fin) ----------
FROM ${PYTHON_IMAGE} AS builder
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Dépendances épinglées avant le code : elles restent en cache tant que requirements.txt ne bouge pas
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-deps .

# ---------- Étape 2 : runtime (l'image qui part en production) ----------
FROM ${PYTHON_IMAGE} AS runtime
ENV PATH="/opt/venv/bin:$PATH" \
    MODEL_DIR=/app/models \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
RUN useradd --create-home --uid 10001 appuser
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
# Le modèle doit être entraîné AVANT le build (python -m velov.train)
COPY models/ models/
USER appuser

EXPOSE 8000

# Sain = prêt à prédire : on interroge /ready (pas de curl dans une image slim)
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 \
  CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=2).status == 200 else 1)"]

# Forme JSON : uvicorn est le PID 1 et reçoit SIGTERM (arrêt propre)
CMD ["uvicorn", "velov.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
