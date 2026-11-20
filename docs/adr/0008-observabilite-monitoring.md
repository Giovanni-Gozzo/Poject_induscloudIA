# ADR-0008 — Comment assurer l'observabilité et le monitoring de l'API

**Status :** Accepté
**Date :** 20/11/2026 (séance 7)

## Contexte

L'API est en production sur un VPS Hetzner piloté par Coolify (ADR-0003, ADR-0004) et
reçoit des prédictions d'éligibilité à la livraison express. Une fois déployée, il faut
pouvoir répondre à trois questions sans se connecter au serveur :

1. **Le service est-il vivant et prêt ?** (modèle chargé, base joignable)
2. **Que fait-il ?** (nombre de requêtes, de prédictions, répartition express/standard)
3. **Est-il assez rapide ?** (latence des requêtes, erreurs)

Les sondes `/health` et `/health/ready` (séance 1) répondent à la question 1, mais ne
donnent aucune mesure d'usage ni de performance. Les logs (JSON, une ligne par requête)
permettent d'enquêter après coup, mais pas de suivre l'état du système en continu.

## Options considérées

| Option | Avantage | Inconvénient |
|---|---|---|
| A. Logs uniquement | Aucune dépendance, déjà en place | Pas de séries temporelles, pas d'alerte simple, enquête uniquement a posteriori |
| B. Sondes de santé uniquement | Très simple, suffisant pour un redémarrage automatique | Dit seulement « vivant / mort », aucune mesure d'usage |
| C. **Métriques Prometheus + logs + sondes** | Standard, léger, alerte sur seuils, fonctionne sans service payant | Un endpoint de plus à exposer et à protéger |
| D. APM SaaS (Datadog, New Relic…) | Tableaux de bord et traces clés en main | Coût, données envoyées à un tiers, dépendance externe |

## Décision

**Option C : métriques au format Prometheus, complétées par les logs et les sondes.**

### Endpoint `/metrics`

- `GET /metrics` renvoie le **format d'exposition Prometheus** (`text/plain`), pas du JSON.
  Il est **public** comme `/health` : il est destiné à un scrape par le réseau interne
  (Coolify) et n'expose aucune donnée client.
- Les métriques sont calculées **en mémoire du processus** (`app/metrics.py`), sans
  brique externe : l'API démarre même si aucun collecteur n'est joignable.

### Métriques exposées

| Métrique | Type | Labels | À quoi elle sert |
|---|---|---|---|
| `delivery_http_requests_total` | compteur | `method`, `endpoint`, `status` | volume et taux d'erreurs par route |
| `delivery_http_request_duration_seconds` | histogramme | `method`, `endpoint` | latence (p50/p95/p99 via les buckets) |
| `delivery_predictions_total` | compteur | `decision` (`oui`/`non`) | volume de prédictions express vs standard |
| `delivery_model_loaded` | jauge | — | 1 si le modèle est prêt, 0 sinon |
| `delivery_model_info` | jauge | `version` | version du modèle en service |
| `process_*`, `python_*` | — | — | CPU, mémoire, GC (collecteurs par défaut de `prometheus_client`) |

L'`endpoint` est le **gabarit de route** (`/v1/predictions/{order_id}`), pas l'URL brute,
pour éviter une explosion du nombre de séries.

### Exploitation

- **Scrape** : Prometheus (ou l'agent de l'hébergeur) interroge `http://<api>:8000/metrics`
  toutes les 15 s. En production, le port 8000 n'étant pas publié (ADR-0007), le scrape se
  fait dans le réseau Docker interne.
- **Alertes** suggérées :
  - `delivery_model_loaded == 0` pendant plus de 2 minutes → modèle non chargé ;
  - taux d'erreurs 5xx > 1 % sur 5 minutes ;
  - `histogram_quantile(0.95, …)` > 1 s sur 5 minutes ;
  - absence de scrape (`up == 0`) → l'API est tombée.
- **Logs** : une ligne par requête (méthode, route, statut, durée) et les événements métier
  (commande prédite, événement publié). Aucun secret n'y est écrit (ADR-0007).
- **Sondes** : `/health` (vivacité) et `/health/ready` (disponibilité) restent utilisées par
  Docker et Coolify pour le rolling update (ADR-0005).

## Conséquences

- Le monitoring est **testé à chaque commit** : `tests/test_api.py` vérifie le format
  Prometheus et l'incrément du compteur de prédictions.
- Les compteurs sont **par processus** : avec plusieurs instances, chaque instance expose ses
  propres séries (Prometheus les agrège grâce au label `instance`). Pour des compteurs
  partagés (quota global), il faudra un stockage externe (Redis), et cette ADR devra être
  marquée « Status : Superseded by ADR-000X ».
- Les métriques ne contiennent **aucune donnée personnelle** : uniquement des compteurs,
  des durées et la version du modèle.
- La supervision de l'infrastructure (CPU/RAM/disque du VPS) reste du ressort de l'hébergeur
  (Hetzner) ; cette ADR couvre l'observabilité **applicative**.
