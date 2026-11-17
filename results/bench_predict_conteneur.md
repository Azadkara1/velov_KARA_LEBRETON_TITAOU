python 3.12.15, n=500, échauffement=50, pools : openblas 16 threads, openblas 16 threads, openmp 16 threads

550 lignes 'bench' supprimées de predictions

| étape | p50 ms | p95 ms | part du p50 total |
|---|---|---|---|
| 0 validation | 0.016 | 0.041 | 0% |
| 1 dataframe | 0.285 | 0.588 | 6% |
| 2 features | 1.078 | 1.513 | 21% |
| 3 predict | 2.270 | 2.916 | 44% |
| 4 réponse | 0.013 | 0.028 | 0% |
| 5 écriture en base | 1.481 | 1.963 | 29% |
| **total** | **5.167** | **6.908** | |

| lignes | mesures | p50 ms | p95 ms | p50 par ligne ms |
|---|---|---|---|---|
| 1 | 500 | 2.081 | 2.531 | 2.0810 |
| 100 | 20 | 2.501 | 2.584 | 0.0250 |
| 1000 | 20 | 6.436 | 6.964 | 0.0064 |
