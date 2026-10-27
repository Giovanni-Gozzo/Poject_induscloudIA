# ADR-0006 — Comment sécuriser les entrées et les sorties

**Status :** Accepté
**Date :** 27/10/2026

## Contexte

L'API est exposée sur Internet depuis un serveur Hetzner géré par Coolify (ADR-0003, ADR-0004).
Tout ce qui **entre** dans l'infrastructure (connexions réseau, requêtes HTTP, contenu JSON) et tout ce qui en **sort** (réponses, messages d'erreur, logs) doit être contrôlé.

Menaces principales :

- accès direct aux services internes : base PostgreSQL, interface d'administration Coolify, SSH ;
- interception du trafic (HTTP en clair) ;
- saturation de l'API par un trop grand nombre de requêtes ou par des requêtes énormes ;
- données invalides ou malveillantes envoyées au modèle ;
- fuite d'informations internes dans les réponses (traces d'erreur Python, structure de l'API).

## Options considérées

| Option | Avantage | Inconvénient |
|---|---|---|
| A. Sécurité uniquement dans l'application | Tout est dans le code, donc testé | Le serveur reste ouvert : un service oublié (base, Coolify) est attaquable directement |
| B. Sécurité uniquement réseau (pare-feu, proxy) | Bloque les attaques avant le serveur | Le pare-feu ne voit pas le contenu des requêtes : il ne peut pas refuser une commande invalide |
| C. **Défense en profondeur** : pare-feu, puis reverse proxy, puis application | Chaque couche arrête ce que la précédente laisse passer | Plus de configuration à documenter et maintenir |

## Décision

**Option C : trois couches de défense successives.**

### Couche 1 — Pare-feu (Hetzner Cloud Firewall, avant le serveur)

Tout est **refusé par défaut** en entrée. Seules ces règles sont ouvertes :

| Port | Protocole | Source | Usage |
|---|---|---|---|
| 22 | TCP | IP de l'administrateur uniquement | SSH, **par clé uniquement** (mot de passe désactivé) |
| 80 | TCP | Tout Internet | Redirigé vers 443 par Traefik |
| 443 | TCP | Tout Internet | HTTPS : seule porte d'entrée de l'API |
| 8000, 6001, 6002 | TCP | IP de l'administrateur uniquement | Interface et temps réel de Coolify (à fermer dès que l'interface a un nom de domaine en HTTPS) |

PostgreSQL (5432) et le port interne de l'API (8000 du conteneur) ne sont **jamais publiés** : ils ne sont joignables que par le réseau Docker interne de Coolify.

### Couche 2 — Reverse proxy (Traefik, géré par Coolify)

- **HTTPS obligatoire** : certificat Let's Encrypt automatique, redirection de HTTP vers HTTPS, en-tête HSTS.
- **Limitation de débit par adresse IP**, avant que la requête n'atteigne Python.
- **Taille maximale de requête** : une commande fait moins de 1 Ko, on refuse au-delà de 1 Mo.

Labels à ajouter à l'application dans Coolify (*Container Labels*), en ajoutant `api-security` à la liste des middlewares du routeur HTTPS existant :

```text
traefik.http.middlewares.api-security-ratelimit.ratelimit.average=20
traefik.http.middlewares.api-security-ratelimit.ratelimit.burst=40
traefik.http.middlewares.api-security-body.buffering.maxRequestBodyBytes=1048576
traefik.http.middlewares.api-security-hsts.headers.stsSeconds=31536000
traefik.http.middlewares.api-security-hsts.headers.stsIncludeSubdomains=true
traefik.http.middlewares.api-security.chain.middlewares=api-security-ratelimit,api-security-body,api-security-hsts
```

### Couche 3 — Application (code de ce dépôt, testé automatiquement)

Entrées :

- **Authentification avant tout traitement** : une requête sans clé valide reçoit 401 **avant** la validation du contenu, pour ne rien révéler du format attendu (ADR-0007, `app/security.py`).
- **Limitation de débit par clé d'API** (`RATE_LIMIT_PER_MINUTE`, 60 par défaut) : réponse 429 avec `Retry-After`. Elle complète celle de Traefik, faite par IP.
- **Validation stricte du contrat** (`app/schemas.py`) : champ inconnu refusé (`extra="forbid"`), types stricts (`"14"` n'est pas converti en `14`), bornes (`hour` entre 0 et 23, `carrier_capacity` entre 0 et 1…), listes fermées pour `weather`, `delivery_zone` et `customer_type`. Toute violation produit une 422.
- **Le modèle n'est chargé que depuis l'image** construite par notre CI, jamais depuis un fichier envoyé par un client, car `joblib` exécute du code au chargement (`app/model_repository.py`).

Sorties :

- **Format d'erreur unique** (`app/errors.py`) : une erreur imprévue renvoie `{"error": "internal_error"}`, et la trace Python ne part que dans les logs.
- **Documentation désactivée en production** : `/docs` et `/openapi.json` répondent 404, sauf si `DOCS_ENABLED=true` (développement).
- **En-têtes de sécurité** sur chaque réponse : `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Cache-Control: no-store`, `Referrer-Policy: no-referrer`.
- **Pas de CORS** : l'API est appelée de serveur à serveur. Aucun site web tiers ne peut l'appeler depuis un navigateur.
- **Logs sans secrets** : on journalise le nom de la clé utilisée, jamais la clé elle-même.

Conteneur :

- L'API tourne avec un utilisateur **non root** (`appuser`), dans une image `slim` sans outils d'entraînement ni MLflow.
- Les versions de toutes les bibliothèques sont **figées** (`requirements.lock.txt`) : une mise à jour est une décision explicite, testée avant d'aller en production.

## Conséquences

- Les règles du pare-feu Hetzner et les labels Traefik sont de la **configuration hors du dépôt** : elles sont documentées ici et doivent être vérifiées après toute reconstruction du serveur.
- L'IP de l'administrateur doit être mise à jour dans le pare-feu si elle change. En cas d'urgence, la console web de Hetzner permet de se connecter sans SSH.
- `--forwarded-allow-ips='*'` (Dockerfile) n'est acceptable **que** parce que le conteneur n'est joignable que par Traefik. Il ne faut jamais publier le port 8000 de l'API.
- La limitation de débit de l'application est **en mémoire, par conteneur** : avec plusieurs instances, la limite réelle serait multipliée. Il faudra alors la déplacer dans Redis ou ne garder que celle de Traefik.
- Les tests `tests/test_api.py` et `tests/test_security.py` vérifient la couche 3 à chaque commit.
