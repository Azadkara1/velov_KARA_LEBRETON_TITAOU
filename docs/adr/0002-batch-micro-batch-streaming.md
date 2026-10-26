# ADR-0002 : Batch, micro-batch ou streaming pour le pipeline de données

- Statut : accepté
- Date : 2026-10-26
- Auteurs : équipe velov (KARA, LEBRETON, TITAOU)

## Contexte
Le besoin : prédire le nombre de vélos disponibles **à H+1** par station. Les données arrivent
au pas horaire (une mesure par station et par heure), le modèle est réentraîné au plus
quotidiennement, et l'API de prédiction n'a pas besoin de données plus fraîches que l'heure.

## Options envisagées
| Option | Latence | Complexité | Ordre de grandeur de coût (20 stations, ~480 lignes/jour) |
|---|---|---|---|
| Batch quotidien | jusqu'à 24 h | faible : un cron + `dbt build` | ~0 € : une petite VM déjà payée (≈ 5 €/mois), quelques secondes de calcul par jour |
| Micro-batch horaire | ~1 h | faible à moyenne : un cron ou un flow Prefect toutes les heures | idem, la charge reste négligeable (~500 lignes/h) |
| Streaming (Redpanda/Kafka + consommateur) | secondes | élevée : broker, consommateurs, gestion des retards | +1 service permanent (~1 à 2 Go de RAM) : environ 20 à 50 €/mois en cloud managé, plus le temps d'exploitation |

## Décision
**Micro-batch horaire** pour la collecte et l'ingestion, **batch quotidien** pour `dbt build` et l'entraînement.
La granularité des données est l'heure : un flux continu n'apporterait aucune information que
l'ingestion horaire n'a pas déjà. Le volume (quelques centaines de lignes par heure) tient
dans une seule requête SQL ; le coût d'un broker permanent serait disproportionné.

## Conséquences
- Les ré-ingestions sont sûres (ingestion idempotente), ce qui rend le micro-batch simple à relancer.
- La fraîcheur maximale de la table gold est d'environ une heure ; acceptable pour une prédiction à H+1.
- À réévaluer si le besoin devient la prédiction à quelques minutes, ou si le volume dépasse
  plusieurs millions de lignes par heure (ex. toute la France, mesures à la minute).
