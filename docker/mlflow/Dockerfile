# Image du serveur MLflow : version épinglée (la même que le client, sinon le schéma de base diverge).
FROM python:3.12-slim

RUN pip install --no-cache-dir mlflow==3.16.1 psycopg2-binary==2.9.13

RUN useradd --uid 10002 --create-home mlflow && mkdir /mlartifacts && chown mlflow /mlartifacts
USER mlflow
WORKDIR /home/mlflow
EXPOSE 5000
