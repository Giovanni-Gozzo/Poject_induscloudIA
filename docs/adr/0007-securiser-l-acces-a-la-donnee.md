# ADR-0007 — Comment sécuriser l'accès à la donnée

**Status :** Accepté
**Date :** 27/10/2026

## Contexte

Deux catégories de données sont à protéger :

1. **Les commandes clients et les prédictions**, stockées dans PostgreSQL (ADR-0001) et lisibles par `GET /v1/orders/{order_id}`.
2. **Le service de prédiction lui-même** : le modèle est une propriété intellectuelle, et chaque appel consomme des ressources du serveur.

Jusqu'ici, n'importe qui connaissant l'URL pouvait envoyer des commandes, demander des prédictions et relire **toutes** les commandes enregistrées.

Les clients de l'API sont des **systèmes** (site e-commerce, outil logistique), pas des personnes qui se connectent avec un navigateur. Il y a deux besoins d'accès distincts :

- **envoyer** des commandes et obtenir des prédictions : les systèmes clients ;
- **relire** les commandes collectées, qui sont des données clients : l'administrateur seulement.

## Options considérées

| Option | Avantage | Inconvénient |
|---|---|---|
| A. Pas d'authentification (l'URL est « secrète ») | Aucun effort | Une URL fuit toujours (logs, captures d'écran) ; aucune traçabilité |
| B. Une seule clé d'API partagée par tous | Simple | Impossible de savoir qui appelle, impossible de révoquer un seul client, pas de rôles |
| C. **Une clé d'API par client, avec rôle et date d'expiration** | On sait qui appelle, on révoque un client sans toucher aux autres, rôles distincts, rotation possible | Les clés sont à créer, transmettre et renouveler (processus décrit ci-dessous) |
| D. OAuth2 / JWT avec un serveur d'identité (Keycloak, Auth0) | Standard, adapté aux utilisateurs humains, jetons de courte durée | Un service de plus à héberger et sécuriser ; surdimensionné pour quelques systèmes clients |

## Décision

**Option C : une clé d'API par système client, avec un rôle et une date d'expiration.**

### Fonctionnement (`app/security.py`)

- Le client envoie sa clé dans l'en-tête `X-API-Key`. Elle est aléatoire (256 bits, préfixe `sk_`) et générée par `python -m scripts.new_api_key`.
- **Seule l'empreinte SHA-256** de chaque clé est stockée, dans la variable `API_KEYS`. Même si cette variable fuit, elle ne permet pas d'appeler l'API.
- Chaque clé a un **rôle** (moindre privilège) :

| Rôle | Droits | Pour qui |
|---|---|---|
| `user` | `POST /v1/orders`, `POST /v1/predictions` | Systèmes clients |
| `admin` | Tout ce que fait `user` + `GET /v1/orders/{order_id}` (données clients) | Administrateur |

- `/health` et `/health/ready` restent **publics** : Coolify et Docker en ont besoin, et ils ne renvoient aucune donnée.
- Chaque clé a une **date d'expiration** (**90 jours** par défaut). Une clé expirée reçoit 401 et l'événement est journalisé.
- Réponses : 401 si la clé est absente, inconnue ou expirée ; 403 si le rôle est insuffisant ; 429 si le client dépasse sa limite de débit (ADR-0006).
- Une variable `API_KEYS` mal formée **empêche l'API de démarrer** : on préfère une panne visible à une API ouverte par erreur. Sans aucune clé, toutes les routes `/v1` répondent 401.

### Rotation des clés (avant expiration)

1. Générer une nouvelle clé pour le client : `python -m scripts.new_api_key --name boutique-web --role user --days 90`.
2. **Ajouter** sa ligne à `API_KEYS` dans Coolify, sans retirer l'ancienne, puis redéployer. Les deux clés fonctionnent.
3. Transmettre la nouvelle clé au client par un canal sûr (gestionnaire de mots de passe partagé, jamais par e-mail en clair).
4. Une fois que le client l'utilise, **retirer** l'ancienne ligne et redéployer.

En cas de fuite d'une clé : retirer immédiatement sa ligne et redéployer. Le rolling update (ADR-0005) applique la révocation sans coupure.

### Où sont les secrets

- `API_KEYS`, `DATABASE_URL` (avec le mot de passe PostgreSQL) et les identifiants Object Storage sont des **variables d'environnement Coolify**, stockées chiffrées par Coolify.
- **Aucun secret dans git** : pas de fichier `.env` versionné (`.gitignore`), pas de secret dans le `Dockerfile` ni dans l'image.
- La clé en clair n'est affichée **qu'une fois**, à sa création. Elle n'est ni stockée ni journalisée côté serveur.

### Accès à la base PostgreSQL

- La base n'a **aucun port publié** : seule l'API y accède, par le réseau Docker interne de Coolify (ADR-0006).
- Mot de passe long et aléatoire, généré par Coolify ; un utilisateur dédié à l'application, propriétaire uniquement de ses tables.
- Toutes les requêtes SQL sont **paramétrées** (`%s`, `app/store.py`) : pas d'injection SQL possible par le contenu d'une commande.
- Les sauvegardes partent sur un bucket Hetzner Object Storage **privé** (ADR-0004).
- L'accès humain aux données passe par l'API avec une clé `admin`, ou par le terminal Coolify. Il n'y a pas de client SQL ouvert sur Internet.

## Conséquences

- Chaque appel est rattaché à un client nommé, ce qui permet de journaliser, limiter et révoquer client par client.
- Ajouter, renouveler ou révoquer une clé impose un **redéploiement** (lecture de `API_KEYS` au démarrage). C'est rapide et sans coupure grâce au rolling update. Si les clients deviennent nombreux, les clés passeront dans une table PostgreSQL, et cette ADR devra être marquée « Status : Superseded by ADR-000X ».
- Les dates d'expiration doivent être surveillées : un rappel est à planifier 7 jours avant chaque échéance.
- Une seule clé secrète suffit ici (pas de paire « clé publique + clé secrète ») : la clé ne sert qu'à authentifier un système, pas à signer des requêtes.
- L'utilisateur PostgreSQL de l'API a besoin du droit `CREATE` sur son schéma, car `app/schema.sql` est exécuté au démarrage. Quand les migrations seront outillées (Alembic), un utilisateur de migration séparé permettra de retirer ce droit à l'API.
- Les tests `tests/test_security.py` et `tests/test_api.py` vérifient les 401, 403, 429 et l'expiration à chaque commit.
