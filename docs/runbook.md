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
| Le process répond | `curl -s --cacert certs/velov.crt https://<hôte>/health` | `{"status":"ok"}` |
| Le modèle est chargé | `curl -s --cacert certs/velov.crt https://<hôte>/ready` | HTTP 200 + version |

### Le proxy HTTPS (S6)
Depuis S6, l'API n'est joignable que par le proxy Nginx (ports 80 et 443). Le port 8000 n'est plus publié.
Le client a besoin de `certs/velov.crt` (certificat public, à récupérer sur la VM). La clé `certs/velov.key`
ne quitte pas la VM. `certs/` est dans `.gitignore`. Sous Windows PowerShell, utiliser `curl.exe`.

| # | Vérification | Commande (depuis le poste, `VM=192.168.1.231`) | Attendu |
|---|---|---|---|
| 1 | HTTP redirigé vers HTTPS | `curl -s -o /dev/null -w "%{http_code}" http://$VM/ready` | `301` |
| 2 | Certificat inconnu refusé | `curl -s https://$VM/ready; echo $?` | code de sortie `60` |
| 3 | HTTPS avec le certificat | `curl -s --cacert certs/velov.crt https://$VM/ready` | `200` + `{"status":"ready",...}` |
| 4 | Métriques non exposées | `curl -s -o /dev/null -w "%{http_code}" --cacert certs/velov.crt https://$VM/metrics` | `404` |
| 5 | API arrêtée (`docker compose stop api`) | appel 3 | `502` |
| - | Port 8000 fermé | `curl -s -m 5 http://$VM:8000/ready; echo $?` | code de sortie `7` (connexion refusée) |

Pour l'appel 5, attendre une dizaine de secondes après l'arrêt : Nginx garde l'adresse de l'API 10 s en cache DNS
(`resolver ... valid=10s`). Pendant ce délai, il peut répondre `504` au lieu de `502`. Relancer ensuite avec
`docker compose start api` et attendre que `/ready` revienne à 200 (quelques secondes : 502 tant que l'API démarre).

Certificat : `./scripts/make_cert.sh <ip-de-la-vm>` sur la VM, valable 90 jours. Le régénérer avant expiration
(`openssl x509 -in certs/velov.crt -noout -enddate`), puis `docker compose restart proxy`.

## 4. Incidents connus
| Symptôme | Cause probable | Diagnostic | Action |
|---|---|---|---|
| `/ready` renvoie 503 | | | |
| Le conteneur redémarre en boucle | | | |
| Latence élevée | trafic proche ou au-delà de la capacité (section 8) | `docker stats --no-stream` : API proche de 100 % d'un cœur ; débit du moment comparé à la capacité | appliquer la section 8, « Près du plafond » |

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

## 8. SLO et capacité (S5, EX-16)

### Le SLO
**p95 de `POST /v1/predict` sous 200 ms**, mesuré côté client. Une requête en erreur (>= 400) compte comme
hors SLO.

### La capacité mesurée
Configuration servie : **1 worker uvicorn, 1 cœur**, base PostgreSQL active (chaque prédiction est journalisée).

| Configuration | Capacité sous le SLO | Plafond de débit | Mémoire de l'API |
|---|---|---|---|
| 1 worker, 1 cœur (**en service**) | **35 req/s** (p95 130 ms) | 50 req/s | 150 Mo |
| 2 workers, 2 cœurs | 30 req/s (p95 100 ms) | 39 req/s | 360 Mo |

Ces chiffres viennent d'une mesure locale du 2026-11-17 (Locust, paliers de 2 min) ; le protocole, les tableaux et
les courbes sont dans le README, section Performance. À remesurer sur la VM, et après tout changement du modèle,
de l'image ou de la configuration.

Le SLO casse **avant** que le CPU soit plein : à 45 usagers (38 req/s), le p95 passe à 220 ms alors que le CPU
moyen n'est qu'à 60 % environ. Les rafales remplissent la file d'attente. Il ne faut donc pas attendre 100 % de CPU
pour réagir.

### Seuils de surveillance
| Signal | Normal | Alerte | Critique |
|---|---|---|---|
| Débit de `/v1/predict` | < 25 req/s | **25 req/s** (70 % de la capacité) | **35 req/s** (capacité sous le SLO) |
| p95 de `/v1/predict` | < 100 ms | 150 ms | 200 ms (SLO violé) |
| CPU de l'API (`docker stats`) | < 40 % | 50 % | 80 % |

### Près du plafond : que faire
1. **Confirmer** que c'est la charge et pas une panne : `/ready` en 200, CPU de l'API élevé, débit proche de 35
   req/s. Si `/ready` est en 503 ou si le CPU est bas, ce n'est pas un problème de capacité (section 4).
2. **Ne pas ajouter de workers sur la même machine.** Passer à 2 workers sur 2 cœurs a fait *baisser* la capacité
   de 13 % (mesure du 2026-11-17).
3. **Répartir sur plusieurs instances** : plusieurs conteneurs à 1 worker et 1 cœur derrière un répartiteur de
   charge, environ 35 req/s chacun. Mesurer la nouvelle capacité avant de s'y fier.
4. **En dernier recours, protéger le SLO pour les requêtes servies** : limiter le débit en amont (réponse 429) plutôt
   que de laisser la latence de tout le monde dépasser la seconde. Au-delà du plafond, le p95 dépasse 1 s.
5. **Après l'incident**, consigner le pic de trafic et remesurer la capacité si la configuration a changé.

Pistes mesurées pour relever la capacité (README, section Performance) : `model.predict` coûte environ 2 ms par
appel quelle que soit la taille du lot, donc regrouper les requêtes ; l'écriture synchrone en base pèse 29 % de la
route, donc la sortir du chemin de la requête ; et tester `OMP_NUM_THREADS=1`. Chaque piste se mesure seule, avec
les mêmes paliers.
