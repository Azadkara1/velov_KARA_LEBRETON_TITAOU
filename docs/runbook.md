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
