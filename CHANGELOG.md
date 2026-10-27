# Changelog

Toutes les modifications notables de ce projet sont consignées dans ce fichier.

Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/),
et le projet respecte le [Semantic Versioning](https://semver.org/lang/fr/).

## [Unreleased]

### Added
- Authentification par clé d'API (`X-API-Key`) : une clé par client, avec rôle (`user`, `admin`)
  et date d'expiration ; seules les empreintes SHA-256 sont stockées (ADR-0007).
- Limitation de débit par clé (`RATE_LIMIT_PER_MINUTE`), réponse 429 avec `Retry-After`.
- En-têtes de sécurité sur toutes les réponses.
- Script `scripts/new_api_key.py` pour générer une clé.
- Abstraction `ModelRepository` / `FileModelRepository` pour le chargement du modèle.
- ADR 0003 à 0007 : plateforme, Cloud Hetzner, stratégie de déploiement, sécurité.
- README, CONTRIBUTING, SECURITY, CODE_OF_CONDUCT, LICENSE (MIT) et modèles d'Issues / PR.

### Changed
- `GET /v1/orders/{order_id}` est réservé au rôle `admin`.
- `/docs` et `/openapi.json` sont désactivés par défaut (`DOCS_ENABLED=true` pour le développement).
- `training/train.py` découpé en fonctions testables (métriques inchangées).

## [1.0.0] - 2026-10-06

### Added
- Script d'entraînement reproductible extrait du notebook (`python -m training.train`), suivi MLflow.
- API FastAPI conforme à `openapi.yml` : `/health`, `/health/ready`, `POST /v1/predictions`,
  `POST /v1/orders`, `GET /v1/orders/{order_id}`.
- Format d'erreur unique pour toutes les erreurs.
- Stockage des commandes et prédictions dans PostgreSQL (ADR-0001), en mémoire sans `DATABASE_URL`.
- Modèle intégré à l'image Docker (ADR-0002), Dockerfile pour Coolify.
- Tests automatiques de l'API et de conformité au contrat OpenAPI.

[Unreleased]: https://github.com/Giovanni-Gozzo/Poject_induscloudIA/compare/v1.0.0...develop
[1.0.0]: https://github.com/Giovanni-Gozzo/Poject_induscloudIA/releases/tag/v1.0.0
