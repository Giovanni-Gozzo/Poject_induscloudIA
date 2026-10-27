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
├── errors.py           format d'erreur unique
└── config.py           réglages par variables d'environnement
training/               entraînement reproductible (extrait du notebook)
scripts/new_api_key.py  génération d'une clé d'API
tests/                  tests automatiques (pytest)
docs/adr/               décisions d'architecture
openapi.yml             contrat de l'API (fourni)
Dockerfile              image de production : entraînement + API
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

## Variables d'environnement

| Variable | Défaut | Rôle |
|---|---|---|
| `API_KEYS` | `[]` (toutes les routes `/v1` en 401) | Empreintes des clés autorisées, avec rôle et expiration (ADR-0007) |
| `RATE_LIMIT_PER_MINUTE` | `60` | Appels autorisés par clé et par minute (ADR-0006) |
| `DATABASE_URL` | absent → stockage en mémoire | Connexion PostgreSQL (ADR-0001) |
| `DOCS_ENABLED` | `false` | Active `/docs` et `/openapi.json` (développement uniquement) |
| `ARTIFACTS_DIR` | `artifacts` | Dossier du modèle et de la model card |

En production, ces variables sont saisies dans Coolify. **Aucun secret dans git.**

## Routes

| Route | Accès | Rôle |
|---|---|---|
| `GET /health`, `GET /health/ready` | public | sondes de vie et de disponibilité |
| `POST /v1/predictions` | clé `user` ou `admin` | prédiction immédiate |
| `POST /v1/orders` | clé `user` ou `admin` | collecte d'une commande (prédite en arrière-plan) |
| `GET /v1/orders/{order_id}` | clé `admin` | relecture d'une commande (données clients) |

## Décisions d'architecture (ADR)

| ADR | Question | Décision |
|---|---|---|
| [0001](docs/adr/0001-stockage-commandes-clients.md) | Où stocker les commandes ? | PostgreSQL dans Coolify |
| [0002](docs/adr/0002-stockage-artefacts-modele.md) | Où stocker le modèle ? | Dans l'image Docker |
| [0003](docs/adr/0003-plateforme-de-deploiement.md) | Quelle plateforme de déploiement ? | Coolify sur un VPS |
| [0004](docs/adr/0004-cloud-on-premise-ou-local.md) | Cloud, on-premise ou local ? Quels services ? | Cloud Hetzner (UE) : Server, Firewall, Backups, Object Storage |
| [0005](docs/adr/0005-strategie-de-deploiement.md) | Quelle stratégie de déploiement ? | Rolling update sur healthcheck + Rollback + Hotfix |
| [0006](docs/adr/0006-securiser-les-entrees-et-sorties.md) | Sécuriser les entrées et sorties ? | Pare-feu → Traefik (HTTPS, débit, taille) → application |
| [0007](docs/adr/0007-securiser-l-acces-a-la-donnee.md) | Sécuriser l'accès à la donnée ? | Clés d'API hachées, par client, avec rôle et expiration |

## Éléments à industrialiser (tableau du notebook)

| Élément | Séance | Solution technique |
|---|---|---|
| Collecte de données | 1 | `POST /v1/orders` + `OrderStore` |
| Exposition d'une fonction de prédiction | 1 | API FastAPI conforme à `openapi.yml` |
| Entraînement du modèle | 1 | `python -m training.train` (reproductible, MLflow) |
| Prédiction à l'aide du modèle | 1 | `POST /v1/predictions`, `ModelService` |
| Environnement (dev → test → prod) | 1 & 3 | devcontainer → pytest → Docker / Coolify, réglages par variables d'environnement |
| Déploiement | 2 | Coolify sur Hetzner, rolling update (ADR-0003 à 0005) |
| Sécurisation de la chaîne de déploiement | 2 | Défense en profondeur et clés d'API (ADR-0006, ADR-0007) |
| Sauvegarde du modèle | 3 | Artefacts dans l'image Docker (ADR-0002) |
| CI/CD | 3 | à venir |
| Nettoyage / validation des données | 4 | `training/data.py` (déjà extrait), à brancher sur les données réelles |
| MLflow | 4 | suivi des runs dans `training/train.py`, Model Registry à venir |
| Pipeline batch / flux temps réel | 5 | à venir (`/v1/predictions/batch` prévu par le contrat) |
| Supervision / mise à l'échelle | 6 | à venir (`/metrics` prévu par le contrat) |
