# Image du serveur MLflow : version épinglée, la même que le client (requirements-dev.txt),
# sinon le schéma de la base diverge. psycopg 3 : le pilote de l'URI postgresql+psycopg://.
FROM python:3.12-slim

RUN pip install --no-cache-dir mlflow==3.16.1 "psycopg[binary]==3.2.3"

RUN useradd --uid 10002 --create-home mlflow && mkdir /mlartifacts && chown mlflow /mlartifacts
USER mlflow
WORKDIR /home/mlflow
EXPOSE 5000
