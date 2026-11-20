# ADR-0007 — Comment sécuriser les entrées, les sorties et l'accès à la donnée

**Status :** Accepté
**Date :** 27/10/2026 (mise à jour le 20/11/2026 : composants des séances 4 et 6)

> Cette ADR regroupe les anciennes ADR « sécuriser les entrées et sorties » et « sécuriser
> l'accès à la donnée », pour suivre la numérotation du barème du projet.

## Partie 1 — Entrées et sorties

### Contexte

L'API est exposée sur Internet depuis un serveur Hetzner géré par Coolify (ADR-0003, ADR-0004).
Tout ce qui **entre** dans l'infrastructure (connexions réseau, requêtes HTTP, contenu JSON) et tout ce qui en **sort** (réponses, messages d'erreur, logs) doit être contrôlé.

Menaces principales :

- accès direct aux services internes : base PostgreSQL, interface d'administration Coolify, SSH ;
- interception du trafic (HTTP en clair) ;
- saturation de l'API par un trop grand nombre de requêtes ou par des requêtes énormes ;
- données invalides ou malveillantes envoyées au modèle ;
- fuite d'informations internes dans les réponses (traces d'erreur Python, structure de l'API).

### Options considérées

| Option | Avantage | Inconvénient |
|---|---|---|
| A. Sécurité uniquement dans l'application | Tout est dans le code, donc testé | Le serveur reste ouvert : un service oublié (base, Coolify) est attaquable directement |
| B. Sécurité uniquement réseau (pare-feu, proxy) | Bloque les attaques avant le serveur | Le pare-feu ne voit pas le contenu des requêtes : il ne peut pas refuser une commande invalide |
| C. **Défense en profondeur** : pare-feu, puis reverse proxy, puis application | Chaque couche arrête ce que la précédente laisse passer | Plus de configuration à documenter et maintenir |

### Décision

**Option C : trois couches de défense successives.**

#### Couche 1 — Pare-feu (Hetzner Cloud Firewall, avant le serveur)

Tout est **refusé par défaut** en entrée. Seules ces règles sont ouvertes :

| Port | Protocole | Source | Usage |
|---|---|---|---|
| 22 | TCP | IP de l'administrateur uniquement | SSH, **par clé uniquement** (mot de passe désactivé) |
| 80 | TCP | Tout Internet | Redirigé vers 443 par Traefik |
| 443 | TCP | Tout Internet | HTTPS : seule porte d'entrée de l'API |
| 8000, 6001, 6002 | TCP | IP de l'administrateur uniquement | Interface et temps réel de Coolify (à fermer dès que l'interface a un nom de domaine en HTTPS) |

PostgreSQL (5432) et le port interne de l'API (8000 du conteneur) ne sont **jamais publiés** : ils ne sont joignables que par le réseau Docker interne de Coolify.

#### Couche 2 — Reverse proxy (Traefik, géré par Coolify)

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

#### Couche 3 — Application (code de ce dépôt, testé automatiquement)

Entrées :

- **Authentification avant tout traitement** : une requête sans clé valide reçoit 401 **avant** la validation du contenu, pour ne rien révéler du format attendu (partie 2, `app/security.py`).
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

### Conséquences

- Les règles du pare-feu Hetzner et les labels Traefik sont de la **configuration hors du dépôt** : elles sont documentées ici et doivent être vérifiées après toute reconstruction du serveur.
- L'IP de l'administrateur doit être mise à jour dans le pare-feu si elle change. En cas d'urgence, la console web de Hetzner permet de se connecter sans SSH.
- `--forwarded-allow-ips='*'` (Dockerfile) n'est acceptable **que** parce que le conteneur n'est joignable que par Traefik. Il ne faut jamais publier le port 8000 de l'API.
- La limitation de débit de l'application est **en mémoire, par conteneur** : avec plusieurs instances, la limite réelle serait multipliée. Il faudra alors la déplacer dans Redis ou ne garder que celle de Traefik.
- Les tests `tests/test_api.py` et `tests/test_security.py` vérifient la couche 3 à chaque commit.

## Partie 2 — Accès à la donnée

### Contexte

Deux catégories de données sont à protéger :

1. **Les commandes clients et les prédictions**, stockées dans PostgreSQL (ADR-0001) et lisibles par `GET /v1/orders/{order_id}`.
2. **Le service de prédiction lui-même** : le modèle est une propriété intellectuelle, et chaque appel consomme des ressources du serveur.

Jusqu'ici, n'importe qui connaissant l'URL pouvait envoyer des commandes, demander des prédictions et relire **toutes** les commandes enregistrées.

Les clients de l'API sont des **systèmes** (site e-commerce, outil logistique), pas des personnes qui se connectent avec un navigateur. Il y a deux besoins d'accès distincts :

- **envoyer** des commandes et obtenir des prédictions : les systèmes clients ;
- **relire** les commandes collectées, qui sont des données clients : l'administrateur seulement.

### Options considérées

| Option | Avantage | Inconvénient |
|---|---|---|
| A. Pas d'authentification (l'URL est « secrète ») | Aucun effort | Une URL fuit toujours (logs, captures d'écran) ; aucune traçabilité |
| B. Une seule clé d'API partagée par tous | Simple | Impossible de savoir qui appelle, impossible de révoquer un seul client, pas de rôles |
| C. **Une clé d'API par client, avec rôle et date d'expiration** | On sait qui appelle, on révoque un client sans toucher aux autres, rôles distincts, rotation possible | Les clés sont à créer, transmettre et renouveler (processus décrit ci-dessous) |
| D. OAuth2 / JWT avec un serveur d'identité (Keycloak, Auth0) | Standard, adapté aux utilisateurs humains, jetons de courte durée | Un service de plus à héberger et sécuriser ; surdimensionné pour quelques systèmes clients |

### Décision

**Option C : une clé d'API par système client, avec un rôle et une date d'expiration.**

#### Fonctionnement (`app/security.py`)

- Le client envoie sa clé dans l'en-tête `X-API-Key`. Elle est aléatoire (256 bits, préfixe `sk_`) et générée par `python -m scripts.new_api_key`.
- **Seule l'empreinte SHA-256** de chaque clé est stockée, dans la variable `API_KEYS`. Même si cette variable fuit, elle ne permet pas d'appeler l'API.
- Chaque clé a un **rôle** (moindre privilège) :

| Rôle | Droits | Pour qui |
|---|---|---|
| `user` | `POST /v1/orders`, `POST /v1/predictions` | Systèmes clients |
| `admin` | Tout ce que fait `user` + `GET /v1/orders/{order_id}` (données clients) | Administrateur |

- `/health` et `/health/ready` restent **publics** : Coolify et Docker en ont besoin, et ils ne renvoient aucune donnée.
- Chaque clé a une **date d'expiration** (**90 jours** par défaut). Une clé expirée reçoit 401 et l'événement est journalisé.
- Réponses : 401 si la clé est absente, inconnue ou expirée ; 403 si le rôle est insuffisant ; 429 si le client dépasse sa limite de débit (partie 1).
- Une variable `API_KEYS` mal formée **empêche l'API de démarrer** : on préfère une panne visible à une API ouverte par erreur. Sans aucune clé, toutes les routes `/v1` répondent 401.

#### Rotation des clés (avant expiration)

1. Générer une nouvelle clé pour le client : `python -m scripts.new_api_key --name boutique-web --role user --days 90`.
2. **Ajouter** sa ligne à `API_KEYS` dans Coolify, sans retirer l'ancienne, puis redéployer. Les deux clés fonctionnent.
3. Transmettre la nouvelle clé au client par un canal sûr (gestionnaire de mots de passe partagé, jamais par e-mail en clair).
4. Une fois que le client l'utilise, **retirer** l'ancienne ligne et redéployer.

En cas de fuite d'une clé : retirer immédiatement sa ligne et redéployer. Le rolling update (ADR-0005) applique la révocation sans coupure.

#### Où sont les secrets

- `API_KEYS`, `DATABASE_URL` (avec le mot de passe PostgreSQL) et les identifiants Object Storage sont des **variables d'environnement Coolify**, stockées chiffrées par Coolify.
- **Aucun secret dans git** : pas de fichier `.env` versionné (`.gitignore`), pas de secret dans le `Dockerfile` ni dans l'image.
- La clé en clair n'est affichée **qu'une fois**, à sa création. Elle n'est ni stockée ni journalisée côté serveur.

#### Accès à la base PostgreSQL

- La base n'a **aucun port publié** : seule l'API y accède, par le réseau Docker interne de Coolify (partie 1).
- Mot de passe long et aléatoire, généré par Coolify ; un utilisateur dédié à l'application, propriétaire uniquement de ses tables.
- Toutes les requêtes SQL sont **paramétrées** (`%s`, `app/store.py`) : pas d'injection SQL possible par le contenu d'une commande.
- Les sauvegardes partent sur un bucket Hetzner Object Storage **privé** (ADR-0004).
- L'accès humain aux données passe par l'API avec une clé `admin`, ou par le terminal Coolify. Il n'y a pas de client SQL ouvert sur Internet.

### Conséquences

- Chaque appel est rattaché à un client nommé, ce qui permet de journaliser, limiter et révoquer client par client.
- Ajouter, renouveler ou révoquer une clé impose un **redéploiement** (lecture de `API_KEYS` au démarrage). C'est rapide et sans coupure grâce au rolling update. Si les clients deviennent nombreux, les clés passeront dans une table PostgreSQL, et cette ADR devra être marquée « Status : Superseded by ADR-000X ».
- Les dates d'expiration doivent être surveillées : un rappel est à planifier 7 jours avant chaque échéance.
- Une seule clé secrète suffit ici (pas de paire « clé publique + clé secrète ») : la clé ne sert qu'à authentifier un système, pas à signer des requêtes.
- L'utilisateur PostgreSQL de l'API a besoin du droit `CREATE` sur son schéma, car `app/schema.sql` est exécuté au démarrage. Quand les migrations seront outillées (Alembic), un utilisateur de migration séparé permettra de retirer ce droit à l'API.
- Les tests `tests/test_security.py` et `tests/test_api.py` vérifient les 401, 403, 429 et l'expiration à chaque commit.

## Partie 3 — Composants ajoutés aux séances 4 et 6

| Composant | Risque | Mesure |
|---|---|---|
| MongoDB analytique (ADR-0006) | Lecture/écriture des données clients sans contrôle | Authentification activée en production (`MONGO_INITDB_ROOT_*`), aucun port publié, identifiants uniquement dans `.env` / Coolify |
| RabbitMQ (streaming) | Injection de faux messages dans la file, lecture des commandes | Utilisateur dédié (l'utilisateur `guest` est refusé hors localhost), aucun port AMQP ni console publiés en production, identifiants dans `.env` |
| Interface logisticien | Affichage de messages venant du réseau (XSS) ; accès aux commandes du jour | Échappement HTML de toutes les valeurs, accessible uniquement sur `127.0.0.1` (ou derrière Traefik + authentification si elle est exposée) |
| Publication des événements | Un broker lent ou absent ralentit l'API | Publication en tâche de fond, après la réponse ; une erreur RabbitMQ est journalisée sans faire échouer la prédiction |
| Réentraînement | Un modèle de mauvaise qualité est publié | Garde-fous de l'orchestrateur : volume minimal de données et ROC-AUC minimal avant d'écrire les artefacts |
