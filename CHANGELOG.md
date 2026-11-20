# Changelog

Toutes les modifications notables de ce projet sont consignées dans ce fichier.

Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/),
et le projet respecte le [Semantic Versioning](https://semver.org/lang/fr/).

## [Unreleased]

### Added
- ADR-0006 : choix de MongoDB (base analytique) comme source d'entraînement plutôt que la base de production PostgreSQL.
- `training/repository.py` : abstraction `OrderRepository` (`save`, `get`, `get_all`), `InMemoryOrderRepository` et `MongoOrderRepository`.
- Entraînement sur les données de `OrderRepository` (nettoyage et validation systématiques), activé par `MONGO_URI`.
- Orchestration du réentraînement, séparée de la CI/CD : `orchestration/retrain_pipeline.py`
  (garde-fous sur le volume de données et le ROC-AUC) et DAG Airflow `orchestration/dags/`.
- `docker-compose.test.yml` et `docker-compose.prod.yml` (API, PostgreSQL, MongoDB, RabbitMQ, interface logisticien, réentraînement).
- Streaming RabbitMQ (TP6) : publication de chaque prédiction au format `OrderEvent` (`openapi.yml`) sur la file quorum `delivery_orders` (`app/streaming.py`),
  consommateur et interface web du logisticien (`streaming/`), simulateur de flux (`streaming/producer_demo.py`).
- Endpoints `GET /v1/model`, `POST /v1/predictions/batch` et `GET /v1/predictions/{order_id}` conformes au contrat `openapi.yml`.
- Observabilité (séance 7) : `GET /metrics` au format Prometheus (requêtes, latence, prédictions, état du modèle), instrumentation de l'API et ADR-0008.

## [1.1.0] - 2026-10-27

### Added
- Authentification par clé d'API (`X-API-Key`) : une clé par client, avec rôle (`user`, `admin`)
  et date d'expiration ; seules les empreintes SHA-256 sont stockées (ADR-0007).
- Limitation de débit par clé (`RATE_LIMIT_PER_MINUTE`), réponse 429 avec `Retry-After`.
- En-têtes de sécurité sur toutes les réponses.
- Script `scripts/new_api_key.py` pour générer une clé.
- Abstraction `ModelRepository` / `FileModelRepository` pour le chargement du modèle.
- ADR 0003 à 0007 : plateforme, Cloud Hetzner, stratégie de déploiement, sécurité.
- README, CONTRIBUTING, SECURITY, CODE_OF_CONDUCT, LICENSE (MIT) et modèles d'Issues / PR.
- `docker-compose.yml` (API + PostgreSQL) et `.env.example`.
- GitHub Actions : `ci.yml` (pylint, pytest avec PostgreSQL, build Docker) et `release.yml`
  (image publiée sur GHCR et Release GitHub à chaque tag `vX.Y.Z`).

### Changed
- `GET /v1/orders/{order_id}` est réservé au rôle `admin`.
- `/docs` et `/openapi.json` sont désactivés par défaut (`DOCS_ENABLED=true` pour le développement).
- `training/train.py` découpé en fonctions testables (métriques inchangées).
- Image Docker en 3 étapes : environnement virtuel copié, pip supprimé, labels OCI.

## [1.0.0] - 2026-10-06

### Added
- Script d'entraînement reproductible extrait du notebook (`python -m training.train`), suivi MLflow.
- API FastAPI conforme à `openapi.yml` : `/health`, `/health/ready`, `POST /v1/predictions`,
  `POST /v1/orders`, `GET /v1/orders/{order_id}`.
- Format d'erreur unique pour toutes les erreurs.
- Stockage des commandes et prédictions dans PostgreSQL (ADR-0001), en mémoire sans `DATABASE_URL`.
- Modèle intégré à l'image Docker (ADR-0002), Dockerfile pour Coolify.
- Tests automatiques de l'API et de conformité au contrat OpenAPI.

[Unreleased]: https://github.com/Giovanni-Gozzo/Poject_induscloudIA/compare/v1.1.0...develop
[1.1.0]: https://github.com/Giovanni-Gozzo/Poject_induscloudIA/releases/tag/v1.1.0
