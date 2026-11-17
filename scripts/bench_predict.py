"""Où part le temps d'une prédiction (S5, TP5 étape 3) : les étapes de POST /v1/predict, sans réseau.

Reproduit le code de la route predict (src/velov/api/main.py) étape par étape, avec les mêmes fonctions.
Le modèle est chargé AVANT le chronomètre ; les --warmup premières itérations ne sont pas comptées.

    python scripts/bench_predict.py --n 500
    python scripts/bench_predict.py --n 500 --batch 1 100 1000
    python scripts/bench_predict.py --n 500 --database-url postgresql://velov:...@localhost:5432/velov
    python scripts/bench_predict.py --n 500 --http http://localhost:8000

Dans les conditions de l'API (même image, un cœur) :
    docker run --rm --cpus 1 -v "$PWD/scripts:/app/scripts" <image_api> python scripts/bench_predict.py --n 500

--database-url mesure aussi l'écriture en base : les lignes portent model_version='bench' et sont supprimées à la fin.
--http envoie --n requêtes séquentielles à l'API : temps vu par le client contre X-Process-Time-Ms.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_info

from velov.api import db
from velov.api.main import load_model
from velov.api.schemas import PredictionRequest, PredictionResponse
from velov.features import FEATURES, add_features

BENCH_VERSION = "bench"
STEPS = ["0 validation", "1 dataframe", "2 features", "3 predict", "4 réponse", "5 écriture en base"]


def random_payloads(n: int, seed: int = 42) -> list[dict]:
    """Même tirage que loadtest/locustfile.py (qu'on ne peut pas importer : il importe locust)."""
    rng = random.Random(seed)
    capacity = {sid: rng.randint(15, 40) for sid in range(1, 21)}
    now = datetime.now(UTC)
    payloads = []
    for _ in range(n):
        sid = rng.randint(1, 20)
        instant = now - timedelta(minutes=rng.randint(0, 30 * 24 * 60))
        payloads.append(
            {
                "station_id": sid,
                "timestamp": instant.replace(second=0, microsecond=0).isoformat(),
                "capacity": capacity[sid],
                "bikes_available": rng.randint(0, capacity[sid]),
                "temperature": round(min(max(rng.gauss(14, 7), -30), 50), 1),
                "is_raining": rng.random() < 0.08,
            }
        )
    return payloads


def ms(samples_ns: list[int]) -> tuple[float, float]:
    arr = np.asarray(samples_ns) / 1e6
    return float(np.percentile(arr, 50)), float(np.percentile(arr, 95))


def bench_steps(model, version: str, payloads: list[dict], warmup: int, pool) -> dict[str, list[int]]:
    times: dict[str, list[int]] = {s: [] for s in STEPS if pool is not None or s != STEPS[5]}
    clock = time.perf_counter_ns
    for i, payload in enumerate(payloads):
        t0 = clock()
        request = PredictionRequest.model_validate(payload)
        t1 = clock()
        frame = pd.DataFrame([request.model_dump()])
        t2 = clock()
        features = add_features(frame)[FEATURES]
        t3 = clock()
        prediction = float(model.predict(features)[0])
        t4 = clock()
        target_timestamp = request.timestamp + timedelta(hours=1)
        predicted_bikes = min(max(prediction, 0.0), float(request.capacity))
        PredictionResponse(
            station_id=request.station_id,
            target_timestamp=target_timestamp,
            predicted_bikes=predicted_bikes,
            model_version=version,
        )
        t5 = clock()
        if pool is not None:
            db.record_prediction(
                pool,
                station_id=request.station_id,
                requested_at=datetime.now(UTC),
                target_timestamp=target_timestamp,
                capacity=request.capacity,
                bikes_available=request.bikes_available,
                temperature=request.temperature,
                is_raining=request.is_raining,
                predicted_bikes=predicted_bikes,
                model_version=BENCH_VERSION,
            )
        t6 = clock()
        if i < warmup:
            continue
        for step, (a, b) in zip(times, [(t0, t1), (t1, t2), (t2, t3), (t3, t4), (t4, t5), (t5, t6)], strict=False):
            times[step].append(b - a)
    return times


def bench_batch(
    model, payloads: list[dict], sizes: list[int], n: int, warmup: int
) -> list[tuple[int, int, float, float]]:
    requests = [PredictionRequest.model_validate(p).model_dump() for p in payloads]  # timestamps typés, comme l'API
    frame = add_features(pd.DataFrame(requests))[FEATURES]
    rows = []
    for size in sizes:
        batch = frame.sample(n=size, replace=size > len(frame), random_state=0)
        repeats = max(20, n // size)  # au moins 20 mesures, sans passer des minutes sur les gros lots
        samples = []
        for i in range(warmup + repeats):
            t0 = time.perf_counter_ns()
            model.predict(batch)
            if i >= warmup:
                samples.append(time.perf_counter_ns() - t0)
        rows.append((size, repeats, *ms(samples)))
    return rows


def bench_http(url: str, payloads: list[dict], warmup: int) -> tuple[list[int], list[int]]:
    if not url.startswith(("http://", "https://")):
        raise SystemExit(f"--http attend une URL http(s), reçu : {url}")
    client, server = [], []
    for i, payload in enumerate(payloads):
        req = urllib.request.Request(  # noqa: S310 (schéma vérifié ci-dessus)
            f"{url}/v1/predict", data=json.dumps(payload).encode(), headers={"content-type": "application/json"}
        )
        t0 = time.perf_counter_ns()
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
            resp.read()
            process_ms = float(resp.headers["X-Process-Time-Ms"])
        elapsed = time.perf_counter_ns() - t0
        if i >= warmup:
            client.append(elapsed)
            server.append(int(process_ms * 1e6))
    return client, server


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--n", type=int, default=500, help="itérations mesurées")
    parser.add_argument("--warmup", type=int, default=50, help="itérations d'échauffement, non comptées")
    parser.add_argument("--model-dir", type=Path, default=Path("models"))
    parser.add_argument("--batch", type=int, nargs="*", help="tailles de lot pour model.predict (ex. 1 100 1000)")
    parser.add_argument("--database-url", help="mesure aussi l'écriture en base (lignes model_version='bench')")
    parser.add_argument("--http", help="URL de l'API : temps client contre X-Process-Time-Ms")
    args = parser.parse_args()

    payloads = random_payloads(args.warmup + args.n)
    pools = [f"{p['internal_api']} {p['num_threads']} threads" for p in threadpool_info()]
    print(f"python {sys.version.split()[0]}, n={args.n}, échauffement={args.warmup}, pools : {', '.join(pools)}\n")

    if args.http:
        client, server = bench_http(args.http.rstrip("/"), payloads, args.warmup)
        (c50, c95), (s50, s95) = ms(client), ms(server)
        print("| mesure | p50 ms | p95 ms |\n|---|---|---|")
        print(f"| temps vu par le client | {c50:.2f} | {c95:.2f} |")
        print(f"| X-Process-Time-Ms (dans l'API) | {s50:.2f} | {s95:.2f} |")
        print(f"| écart (réseau, sérialisation, serveur) | {c50 - s50:.2f} | {c95 - s95:.2f} |")
        return 0

    model, metadata = load_model(args.model_dir)  # hors chronomètre
    pool = db.open_pool(args.database_url) if args.database_url else None
    try:
        times = bench_steps(model, metadata["model_version"], payloads, args.warmup, pool)
    finally:
        if pool is not None:
            with pool.connection() as conn, conn.cursor() as cur:
                cur.execute("DELETE FROM predictions WHERE model_version = %s", (BENCH_VERSION,))
                print(f"{cur.rowcount} lignes '{BENCH_VERSION}' supprimées de predictions\n")
            pool.close()

    total = [sum(parts) for parts in zip(*times.values(), strict=True)]
    total_p50 = ms(total)[0]
    print("| étape | p50 ms | p95 ms | part du p50 total |\n|---|---|---|---|")
    for step, samples in times.items():
        p50, p95 = ms(samples)
        print(f"| {step} | {p50:.3f} | {p95:.3f} | {p50 / total_p50:.0%} |")
    p50, p95 = ms(total)
    print(f"| **total** | **{p50:.3f}** | **{p95:.3f}** | |")

    if args.batch:
        print("\n| lignes | mesures | p50 ms | p95 ms | p50 par ligne ms |\n|---|---|---|---|---|")
        for size, repeats, b50, b95 in bench_batch(model, payloads, args.batch, args.n, warmup=5):
            print(f"| {size} | {repeats} | {b50:.3f} | {b95:.3f} | {b50 / size:.4f} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
