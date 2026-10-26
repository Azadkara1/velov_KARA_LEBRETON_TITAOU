# Runbook : API velov-availability

> Template à compléter au fil des sessions. Public cible : une personne d'astreinte
> qui ne connaît pas le projet et doit rétablir le service à 3 h du matin.

## 1. Vue d'ensemble
- Ce que fait le service, en deux phrases :
- Schéma d'architecture (lien) :
- Dépendances (base de données, stockage du modèle...) :

## 2. Démarrer / arrêter
```bash
# démarrer
# arrêter
# redémarrer un seul service
```

## 3. Vérifier que tout va bien
| Vérification | Commande | Résultat attendu |
|---|---|---|
| Le process répond | `curl -s http://<hôte>:8000/health` | `{"status":"ok"}` |
| Le modèle est chargé | `curl -s http://<hôte>:8000/ready` | HTTP 200 + version |
| | | |

## 4. Incidents connus
| Symptôme | Cause probable | Diagnostic | Action |
|---|---|---|---|
| `/ready` renvoie 503 | | | |
| Le conteneur redémarre en boucle | | | |
| Latence élevée | | | |

## 5. Déployer une nouvelle version du modèle
1.
2.
3. Retour arrière (rollback) :

## 6. Contacts et escalade
-

## 7. Pipeline de données (S3)

### La collecte s'arrête : que faire ?
1. Vérifier la fraîcheur : `docker compose exec db psql -U velov -At -c "select max(observed_at), now() - max(observed_at) from bronze.velov_raw"`.
   Plus de 2 h de retard = collecte arrêtée.
2. Causes probables : conteneur ou VM arrêtés (`docker compose ps`), disque saturé (`docker system df`), source indisponible (logs du collecteur).
3. Relancer la collecte, puis ré-ingérer les heures manquantes si la source les conserve (voir ci-dessous).
4. Une heure non collectée n'a pas de ligne : gold n'invente rien, la cible de l'heure précédente est simplement absente.

### Rejouer une journée
```bash
python -m velov.ingest --csv <fichier_du_jour.csv>     # sans risque : les doublons sont ignorés
cd dbt/velov && dbt build --profiles-dir .             # recalcule silver et gold en entier
```
Rejouer est sûr (EX-10) : bronze ignore les lignes déjà connues, gold est recalculée de façon déterministe.
Limite : `DO NOTHING` garde la **première** valeur reçue. Si la source corrige une valeur après coup, il faut
la corriger explicitement en bronze (UPDATE ciblé), puis relancer `dbt build`.

### `dbt build` échoue
| Symptôme | Cause | Action |
|---|---|---|
| `assert_bronze_capacity_plausible` en ERROR (> 50 lignes) | la collecte produit des capacités ou des vélos absurdes | corriger la source, supprimer les lignes fautives de bronze, rejouer |
| Erreur de contrat sur `gold_hourly_features` | colonne ou type différent du contrat | corriger le modèle SQL ; ne jamais assouplir le contrat pour « faire passer » |
| `bikes_within_capacity` en échec | silver laisse passer une ligne incohérente | vérifier les filtres de `stg_observations` |
| `env_var 'POSTGRES_PASSWORD' not found` | `.env` non chargé dans le shell | `set -a; . ./.env; set +a` |

Un échec bloque l'aval : gold n'est pas reconstruite et ne contient jamais de données invalides (EX-12).
