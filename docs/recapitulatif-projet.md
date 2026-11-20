# Récapitulatif du projet — Industrialisation de l'IA dans le cloud

**Sujet :** déterminer si une commande peut être livrée en express dans la journée.
**Objectif global :** transformer un notebook expérimental en application de production.
**Dépôt :** https://github.com/Giovanni-Gozzo/Poject_induscloudIA
**Production :** https://api.giovannigozzo.fr (version 1.1.0)
**Mis à jour le :** 20/11/2026

---

## Séance 1 — Transformer le notebook en application

### Ce qui était demandé

- Transformer le notebook (génération, nettoyage, sélection de variables, entraînement de la
  régression logistique, test, évaluation, prédiction) en **application**.
- Respecter les principes de **Clean Code** : SOLID, DRY, YAGNI, design patterns.
- Rédiger des **ADR** et respecter le **contrat OpenAPI** fourni.

### Ce qui a été fait

| Élément | Réalisation |
|---|---|
| Données | `training/data.py` : génération, contrôles qualité, nettoyage (cellules 8, 14, 18 du notebook) |
| Entraînement | `training/train.py` : pipeline scikit-learn, évaluation, suivi MLflow, model card — reproductible (`RANDOM_STATE = 42`, versions figées) |
| API | `app/` (FastAPI) : `/health`, `/health/ready`, `POST /v1/predictions`, `POST /v1/orders`, `GET /v1/orders/{order_id}` |
| Contrat | `app/schemas.py` traduit `openapi.yml` (types stricts, bornes, champs inconnus refusés) ; test automatique de conformité |
| Erreurs | Format d'erreur unique (`app/errors.py`) |
| Stockage | Abstraction `OrderStore` → `InMemoryOrderStore` (dev/tests) et `PostgresOrderStore` (prod) |
| Modèle | Abstraction `ModelRepository` → `FileModelRepository` (exemple du cours) ; garde-fous au chargement |
| ADR | [0001](adr/0001-stockage-commandes-clients.md) stockage des commandes (PostgreSQL), [0002](adr/0002-stockage-artefacts-modele.md) artefacts du modèle (image Docker) |
| Environnement | Devcontainer, dépendances figées (`requirements.lock.txt`) |

Principes appliqués : **SOLID** (abstractions `OrderStore` et `ModelRepository`, injection dans
`ModelService` et `Authenticator`), **DRY** (constantes et listes de features centralisées),
**YAGNI** (pas de Load Balancer, de Kubernetes ni de Model Registry tant qu'ils ne sont pas nécessaires).

---

## Séance 2 — Déploiement et sécurisation

### Ce qui était demandé

1. Finir de développer l'application (en se basant sur le notebook).
2. Rédiger des ADR :
   a. Quelle plateforme de déploiement ?
   b. Cloud, on-premise ou local ? Si Cloud, quels services ?
   c. Quelle stratégie de déploiement ?
   d. Comment sécuriser les entrées et sorties, et l'accès à la donnée ?
3. Pour les plus rapides : créer une image Docker.

### Ce qui a été fait

**Application terminée et sécurisée** (`app/security.py`) :

- une clé d'API par client (`X-API-Key`), seule son **empreinte SHA-256** est stockée ;
- **rôles** `user` (prédire, envoyer des commandes) et `admin` (relire les commandes) ;
- **expiration** des clés (90 jours par défaut), génération par `python -m scripts.new_api_key` ;
- **limitation de débit** par clé (429 avec `Retry-After`) ;
- en-têtes de sécurité, `/docs` désactivé en production ;
- refactorisation : `ModelRepository`, `train.py` découpé en fonctions testables (métriques inchangées).

**ADR rédigées :**

| Question | ADR | Décision |
|---|---|---|
| a. Plateforme | [0003](adr/0003-plateforme-de-deploiement.md) | **Coolify** (PaaS auto-hébergé) sur un VPS |
| b. Cloud / on-premise / local | [0004](adr/0004-cloud-on-premise-ou-local.md) | **Cloud Hetzner** (Allemagne, UE) : Cloud Server, Cloud Firewall, Backups, Object Storage |
| c. Stratégie | [0005](adr/0005-strategie-de-deploiement.md) | **Rolling update** conditionné à `/health/ready` + **Rollback** + **Hotfix** (Shadow retenu pour valider un futur modèle) |
| d.i & d.ii Sécurité | [0007](adr/0007-securiser-entrees-sorties-et-acces-donnee.md) | Défense en profondeur (Hetzner → Traefik → API) + clés hachées, rôles, expiration, secrets hors git |

**Image Docker :** `Dockerfile` multi-étapes (entraînement pendant le build, utilisateur non root, healthcheck).

---

## Séance 3 — CI/CD, GitHub et Docker

### Ce qui était demandé

| # | Tâche | Obligatoire |
|---|---|---|
| 1 | Corriger les séances 1 et 2 si besoin | — |
| 2 | Ajouter le projet sur GitHub | oui |
| 3 | Système de branches GitFlow | facultatif (malus si absent) |
| 4 | README, CONTRIBUTING, LICENSE, SECURITY | oui |
| 4 | CODE_OF_CONDUCT | facultatif (malus si absent) |
| 5 | Dockerfile, docker-compose.yml | oui |
| 5 | Optimisation, compression et sécurisation de l'image | facultatif (malus si absent) |
| 6 | GitHub Actions : finir l'application, image Docker automatique à chaque release | oui |
| 6 | GitHub Actions : tester l'application (pytest + pylint) | facultatif (malus si absent) |

### Ce qui a été fait

| Tâche | Réalisation |
|---|---|
| Corrections | Séances 1 et 2 terminées (voir plus haut) |
| GitHub | Dépôt `Giovanni-Gozzo/Poject_induscloudIA` |
| GitFlow | `main` (production), `develop` (intégration, branche par défaut), `feature/*`, `release/*`, `hotfix/*` ; fusions `--no-ff` ; **`main` et `develop` protégées** (PR obligatoire, CI verte requise) |
| Collaboration | [README](../README.md), [CONTRIBUTING](../CONTRIBUTING.md), [LICENSE](../LICENSE) (MIT), [SECURITY](../SECURITY.md) (signalement privé activé sur GitHub), [CODE_OF_CONDUCT](../CODE_OF_CONDUCT.md), [CHANGELOG](../CHANGELOG.md) (Keep a Changelog), modèles d'Issues et de PR |
| Versions | Semantic Versioning : release **v1.1.0** |
| Dockerfile | 3 étapes (dépendances → entraînement → image finale) ; image finale **sans pip, sans MLflow, sans code d'entraînement** ; non root ; labels OCI ; aucun `.env` dans l'image |
| docker-compose.yml | API + PostgreSQL ; conteneur en **lecture seule**, **sans privilèges Linux** (`cap_drop: ALL`, `no-new-privileges`) ; base sans port publié ; API accessible seulement en local ; secrets via `.env` (non commité, modèle `.env.example`) |
| CI (`ci.yml`) | À chaque push et PR : **pylint** (≥ 9/10), **pytest** avec une vraie base PostgreSQL (couverture ≥ 80 %), construction de l'image |
| CD (`release.yml`) | À chaque tag `vX.Y.Z` : CI, puis **image publiée sur GHCR** (`ghcr.io/giovanni-gozzo/poject_induscloudia`), puis **Release GitHub** |

---

## Séance 7 — Observabilité et monitoring

### Ce qui était demandé

- Mesurer l'état de santé d'un système en production (observabilité, monitoring).
- Rédiger un **ADR** sur la supervision.

### Ce qui a été fait

| Élément | Réalisation |
|---|---|
| Endpoint | `GET /metrics` au format d'exposition **Prometheus** (`text/plain`), public pour le scrape interne |
| Code | `app/metrics.py` : compteurs et histogrammes en mémoire, sans brique externe |
| Métriques | requêtes HTTP (méthode, route, statut), latence, prédictions (`oui`/`non`), modèle chargé, version du modèle |
| Instrumentation | middleware de mesure de chaque requête + incrément à chaque prédiction (unitaire, lot, arrière-plan) |
| ADR | [0008](adr/0008-observabilite-monitoring.md) : métriques Prometheus + logs + sondes, alertes suggérées |
| Tests | format Prometheus exposé, endpoint public, incrément du compteur de prédictions |

Les sondes `/health` et `/health/ready` (séance 1) restent utilisées par Docker et Coolify
pour le rolling update. La mise à l'échelle (facultative) n'est pas traitée.

## Résultats vérifiés

**Qualité (dernière CI) :**

| Indicateur | Résultat |
|---|---|
| Tests | **85 réussis**, 6 ignorés en local (tests PostgreSQL, exécutés en CI) |
| Couverture | **85 %** (minimum demandé : 80 %) |
| Pylint | **9,97 / 10** |
| Image Docker | construite et publiée (`1.1.0`, `1.1`) |

**Production (`https://api.giovannigozzo.fr`, après la release 1.1.0) :**

| Test | Résultat |
|---|---|
| `GET /health/ready` | `ready`, version **1.1.0**, modèle chargé, base joignable |
| `GET /health` | 200 |
| `GET /docs` | **404** (documentation masquée) |
| `POST /v1/predictions` sans clé | **401** (clé exigée) |

---

## Tableau « Éléments à industrialiser » du notebook

| Élément | Séance | Solution technique | État |
|---|---|---|---|
| Collecte de données | 1 | `POST /v1/orders` + `OrderStore` (PostgreSQL) | ✅ |
| Exposition d'une fonction de prédiction | 1 | API FastAPI conforme à `openapi.yml` | ✅ |
| Entraînement du modèle | 1 | `python -m training.train` (reproductible) | ✅ |
| Prédiction à l'aide du modèle | 1 | `POST /v1/predictions`, `ModelService` | ✅ |
| Environnement (dev → test → prod) | 1 & 3 | devcontainer → CI GitHub Actions → Coolify | ✅ |
| Déploiement | 2 | Coolify sur Hetzner, rolling update | ✅ |
| Sécurisation de la chaîne de déploiement | 2 | Défense en profondeur, clés d'API, branches protégées | ✅ |
| Sauvegarde du modèle | 3 | Artefacts intégrés à l'image Docker (ADR-0002) | ✅ |
| CI/CD | 3 | GitHub Actions (`ci.yml`, `release.yml`) | ✅ |
| Nettoyage des données | 4 | `training/data.py` + `OrderRepository` (`MongoOrderRepository`, ADR-0006) | ✅ |
| Validation des données | 4 | `validate_dataset()` systématique avant entraînement | ✅ |
| MLflow | 4 | Suivi des runs dans `training/train.py` et `orchestration/retrain_pipeline.py` | ✅ |
| Pipeline batch | 5 | `POST /v1/predictions/batch` et `GET /v1/predictions/{order_id}` | ✅ |
| Flux temps réel | 6 | `OrderEvent` via RabbitMQ (`app/streaming.py`) + interface logisticien (`streaming/`) | ✅ |
| Supervision | 7 | `GET /metrics` (Prometheus) + logs + sondes (ADR-0008) | ✅ |
| Mise à l'échelle | 7 | Facultatif, non traité | ⏳ |

---

## Reste à faire

**Par toi :**

- [ ] Tester la prédiction en production avec la clé `user` (réponse attendue : `"decision":"oui"`, probabilité ≈ 0,93).
- [ ] Appliquer les règles du pare-feu Hetzner et les labels Traefik décrits dans l'[ADR-0007](adr/0007-securiser-entrees-sorties-et-acces-donnee.md).
- [ ] Activer l'authentification à deux facteurs sur Coolify.
- [ ] Vérifier `docker compose up` en local (Docker n'était pas installé pendant le développement).
- [ ] Planifier un rappel avant l'expiration des clés d'API (90 jours).

**Améliorations possibles :**

- Mettre à jour les actions GitHub vers des versions basées sur Node 24 (avertissement de dépréciation de Node 20).
- Analyse de vulnérabilités de l'image Docker dans la CI.
