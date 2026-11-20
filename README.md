# eligibilite-livraison-express

API de production qui prédit si une commande peut être **livrée en express dans la journée**.
Elle industrialise le notebook `project_test_v1_final_final2.ipynb` (régression logistique scikit-learn).

## Structure

```text
app/                    API FastAPI (servie en production)
├── main.py             routes, branchement des dépendances
├── schemas.py          contrat d'entrée/sortie (traduction de openapi.yml)
├── model.py            ModelService : garde-fous + prédiction
├── model_repository.py ModelRepository (abstraction) → FileModelRepository   (ADR-0002)
├── store.py            OrderStore (abstraction) → InMemory / Postgres        (ADR-0001)
├── security.py         clés d'API, rôles, expiration, limitation de débit    (ADR-0007)
├── metrics.py          métriques Prometheus : requêtes, latence, prédictions (ADR-0008)
├── errors.py           format d'erreur unique
└── config.py           réglages par variables d'environnement
training/               entraînement reproductible (extrait du notebook)
├── data.py             génération, nettoyage, validation des données
├── repository.py       OrderRepository → InMemory / Mongo (source d'entraînement, ADR-0006)
└── train.py            pipeline scikit-learn, évaluation, MLflow, model card
orchestration/          réentraînement (séparé de la CI/CD) : pipeline + DAG Airflow
streaming/              RabbitMQ : consommateur, interface logisticien, simulateur de flux
scripts/                new_api_key.py (clé d'API), seed_mongo.py (données de test MongoDB)
tests/                  tests automatiques (pytest)
docs/adr/               décisions d'architecture
openapi.yml             contrat de l'API (fourni)
Dockerfile              image de production : entraînement + API
docker-compose.yml      API + PostgreSQL en local
docker-compose.test.yml environnement de test : API, PostgreSQL, MongoDB, RabbitMQ, interface logisticien
docker-compose.prod.yml environnement de prod (durci, secrets dans .env)
.github/                workflows CI/CD, modèles d'Issues et de PR
```

## Démarrage (dans le devcontainer)

```bash
python -m training.train                     # produit artifacts/ (modèle + model card)
python -m pytest                             # tests
python -m pytest --cov=app --cov=training    # couverture (pytest-cov)

# Créer une clé pour soi, puis lancer l'API avec la documentation activée
python -m scripts.new_api_key --name dev --role admin --days 7
export API_KEYS='[<entrée JSON affichée par la commande ci-dessus>]'
DOCS_ENABLED=true uvicorn app.main:app --reload     # http://localhost:8000/docs
```

Appel :

```bash
curl -X POST http://localhost:8000/v1/predictions \
  -H "X-API-Key: sk_…" -H "Content-Type: application/json" \
  -d '{"hour":14,"day_of_week":2,"weekend":0,"distance_km":3.5,"order_value_eur":89.9,
       "weight_kg":2.4,"stock_available":1,"preparation_time_min":18,"carrier_capacity":0.85,
       "weather":"normal","delivery_zone":"centre","customer_type":"premium"}'
```

## Docker

```bash
cp .env.example .env          # renseigner POSTGRES_PASSWORD et API_KEYS (.env n'est jamais commité)
docker compose up --build     # API sur http://127.0.0.1:8000 + PostgreSQL (non exposé)
```

L'image (`Dockerfile`) est construite en 3 étapes : dépendances → entraînement → image finale,
sans pip, sans MLflow, avec un utilisateur non root. Le conteneur tourne en lecture seule et sans privilèges Linux.

### Environnements de test et de production

```bash
# Test : tout tourne en local, avec des identifiants de test (aucun secret)
docker compose -f docker-compose.test.yml up --build -d
docker compose -f docker-compose.test.yml run --rm seed-mongo   # remplit MongoDB
docker compose -f docker-compose.test.yml run --rm trainer      # réentraîne depuis MongoDB

# Prod : secrets dans .env (POSTGRES_PASSWORD, API_KEYS, MONGO_*, RABBITMQ_*)
docker compose -f docker-compose.prod.yml up --build -d
```

| Service | URL (test) |
|---|---|
| API | http://127.0.0.1:8000 (`/docs` activé en test) |
| Interface logisticien | http://127.0.0.1:8080 |
| Console RabbitMQ | http://127.0.0.1:15672 (`livraison` / `livraison`, test uniquement) |

## Réentraînement (séance 4)

L'entraînement est un processus d'**exécution**, pas de construction : il ne passe pas par la CI/CD.

```bash
MONGO_URI=mongodb://localhost:27017 python -m orchestration.retrain_pipeline --min-orders 200 --min-roc-auc 0.70
```

L'orchestrateur lit les commandes dans MongoDB (`OrderRepository`, ADR-0006), les nettoie et les valide,
entraîne et enregistre le run dans MLflow, puis **n'écrit les artefacts que si** le volume de données et
le ROC-AUC sont suffisants. Le DAG Airflow `orchestration/dags/retrain_model_dag.py` le planifie chaque jour.
Le nouveau modèle part en production par une nouvelle release de l'image (ADR-0002).

## Streaming (séance 6)

Chaque prédiction est publiée, après la réponse HTTP, sur la file RabbitMQ `delivery_orders`
(file *quorum*, durable). L'interface du logisticien la consomme en continu et affiche les
livraisons du jour (express ou standard), qu'il marque comme préparées.

```bash
python -m streaming.consumer                              # consommateur seul, en terminal
uvicorn streaming.logistician_ui:app --port 8080          # interface web (consomme dans un thread)
python -m streaming.producer_demo --count 20 --interval 1 # simule un flux de commandes
```

## Supervision (séance 7)

`GET /metrics` expose les métriques au **format Prometheus** (`text/plain`), calculées en
mémoire du processus (`app/metrics.py`, [ADR-0008](docs/adr/0008-observabilite-monitoring.md)) :

| Métrique | Type | Contenu |
|---|---|---|
| `delivery_http_requests_total` | compteur | requêtes par méthode, route et statut |
| `delivery_http_request_duration_seconds` | histogramme | latence des requêtes |
| `delivery_predictions_total` | compteur | prédictions par décision (`oui` / `non`) |
| `delivery_model_loaded` | jauge | 1 si le modèle est prêt, 0 sinon |
| `delivery_model_info` | jauge | version du modèle en service |

```bash
curl http://127.0.0.1:8000/metrics            # format texte Prometheus
curl http://127.0.0.1:8000/metrics | grep delivery_predictions_total
```

Prometheus (ou l'agent de l'hébergeur) scrape cet endpoint toutes les 15 s. Les sondes
`/health` et `/health/ready` restent utilisées par Docker et Coolify.

## CI/CD (GitHub Actions)

| Workflow | Déclencheur | Ce qu'il fait |
|---|---|---|
| `ci.yml` | push sur `main`, `develop`, `feature/**`, `release/**`, `hotfix/**`, et Pull Requests | pylint (≥ 9/10), pytest avec PostgreSQL (couverture ≥ 80 %), construction de l'image |
| `release.yml` | tag `vX.Y.Z` | CI, puis image publiée sur `ghcr.io/giovanni-gozzo/poject_induscloudia`, puis Release GitHub |

Publier une version (GitFlow) : `release/X.Y.Z` depuis `develop` → mise à jour de `APP_VERSION`
et du `CHANGELOG` → merge dans `main` et `develop` → `git tag vX.Y.Z && git push origin vX.Y.Z`.

## Variables d'environnement

| Variable | Défaut | Rôle |
|---|---|---|
| `API_KEYS` | `[]` (toutes les routes `/v1` en 401) | Empreintes des clés autorisées, avec rôle et expiration (ADR-0007) |
| `RATE_LIMIT_PER_MINUTE` | `60` | Appels autorisés par clé et par minute (ADR-0007) |
| `DATABASE_URL` | absent → stockage en mémoire | Connexion PostgreSQL (ADR-0001) |
| `DOCS_ENABLED` | `false` | Active `/docs` et `/openapi.json` (développement uniquement) |
| `ARTIFACTS_DIR` | `artifacts` | Dossier du modèle et de la model card |
| `RABBITMQ_URL` | absent → aucune publication | Broker RabbitMQ pour le streaming des prédictions |
| `RABBITMQ_QUEUE` | `delivery_orders` | File RabbitMQ lue par l'interface logisticien |
| `MONGO_URI`, `MONGO_DB`, `MONGO_COLLECTION` | absent → données synthétiques | Source d'entraînement MongoDB (ADR-0006) |

En production, ces variables sont saisies dans Coolify. **Aucun secret dans git.**

## Routes

| Route | Accès | Rôle |
|---|---|---|
| `GET /health`, `GET /health/ready` | public | sondes de vie et de disponibilité |
| `POST /v1/predictions` | clé `user` ou `admin` | prédiction immédiate |
| `POST /v1/predictions/batch` | clé `user` ou `admin` | prédiction par lot (jusqu'à 1000 commandes) |
| `GET /v1/predictions/{order_id}` | clé `user` ou `admin` | relecture d'une prédiction déjà calculée |
| `POST /v1/orders` | clé `user` ou `admin` | collecte d'une commande (prédite en arrière-plan) |
| `GET /v1/orders/{order_id}` | clé `admin` | relecture d'une commande (données clients) |
| `GET /v1/model` | clé `user` ou `admin` | métadonnées et métriques du modèle en service |
| `GET /metrics` | public | métriques au format Prometheus (scrape) |

## Décisions d'architecture (ADR)

| ADR | Question | Décision |
|---|---|---|
| [0001](docs/adr/0001-stockage-commandes-clients.md) | Où stocker les commandes ? | PostgreSQL dans Coolify |
| [0002](docs/adr/0002-stockage-artefacts-modele.md) | Où stocker le modèle ? | Dans l'image Docker |
| [0003](docs/adr/0003-plateforme-de-deploiement.md) | Quelle plateforme de déploiement ? | Coolify sur un VPS |
| [0004](docs/adr/0004-cloud-on-premise-ou-local.md) | Cloud, on-premise ou local ? Quels services ? | Cloud Hetzner (UE) : Server, Firewall, Backups, Object Storage |
| [0005](docs/adr/0005-strategie-de-deploiement.md) | Quelle stratégie de déploiement ? | Rolling update sur healthcheck + Rollback + Hotfix |
| [0006](docs/adr/0006-postgresql-ou-mongodb.md) | PostgreSQL, MongoDB, autre ? | MongoDB (base analytique, alimentée par ETL), via `OrderRepository` |
| [0007](docs/adr/0007-securiser-entrees-sorties-et-acces-donnee.md) | Sécuriser les entrées, les sorties et l'accès à la donnée ? | Pare-feu → Traefik → application ; clés d'API hachées par client, avec rôle et expiration |

## Éléments à industrialiser (tableau du notebook)

| Élément | Séance | Solution technique |
|---|---|---|
| Collecte de données | 1 | `POST /v1/orders` + `OrderStore` |
| Exposition d'une fonction de prédiction | 1 | API FastAPI conforme à `openapi.yml` |
| Entraînement du modèle | 1 | `python -m training.train` (reproductible, MLflow) |
| Prédiction à l'aide du modèle | 1 | `POST /v1/predictions`, `ModelService` |
| Environnement (dev → test → prod) | 1 & 3 | devcontainer → pytest → Docker / Coolify, réglages par variables d'environnement |
| Déploiement | 2 | Coolify sur Hetzner, rolling update (ADR-0003 à 0005) |
| Sécurisation de la chaîne de déploiement | 2 | Défense en profondeur et clés d'API (ADR-0007) |
| Sauvegarde du modèle | 3 | Artefacts dans l'image Docker (ADR-0002) |
| CI/CD | 3 | GitHub Actions : `ci.yml` (qualité, tests, build) et `release.yml` (image sur GHCR) |
| Nettoyage / validation des données | 4 | `training/data.py` + `OrderRepository` (`MongoOrderRepository`) |
| Orchestration du réentraînement | 4 | `orchestration/retrain_pipeline.py` + DAG Airflow (`orchestration/dags/`) |
| Environnements Test / Prod | 4 | `docker-compose.test.yml` et `docker-compose.prod.yml` (API + Postgres + MongoDB) |
| MLflow | 4 | suivi des runs dans `training/train.py`, Model Registry à venir |
| Pipeline batch / flux temps réel | 5 & 6 | `POST /v1/predictions/batch` + RabbitMQ (`OrderEvent`, file quorum `delivery_orders`) + interface logisticien |
| Supervision | 7 | `GET /metrics` (format Prometheus) + logs + sondes (ADR-0008) |
| Mise à l'échelle | 7 | à venir (facultatif) |
