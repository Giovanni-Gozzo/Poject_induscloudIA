# ADR-0001 — Où stocker les commandes clients

**Status :** Accepté
**Date :** 06/10/2026

## Contexte

L'API reçoit les commandes clients (`POST /v1/orders`), calcule leur éligibilité à la livraison express en tâche de fond, puis permet de les relire (`GET /v1/orders/{order_id}`).
Les commandes et leurs prédictions doivent donc être conservées.

Aujourd'hui, elles sont stockées en mémoire (`InMemoryOrderStore` dans `app/store.py`) :

- tout est **perdu à chaque redéploiement** ou redémarrage du conteneur ;
- une seule instance de l'API peut tourner, car chaque instance aurait sa propre mémoire.

Le volume est faible (projet de cours), mais les données doivent survivre aux déploiements, qui ont lieu à chaque push sur `main` via Coolify.

## Options considérées

| Option | Avantage | Inconvénient |
|---|---|---|
| A. Mémoire (`InMemoryOrderStore`, existant) | Aucun service à installer, très rapide | Données perdues à chaque redémarrage, une seule instance possible |
| B. SQLite sur un volume persistant | Simple, un seul fichier, données conservées | Un seul processus peut écrire à la fois, pas adapté à plusieurs instances |
| C. PostgreSQL sur le VPS (créé dans Coolify) | Accès concurrents, transactions, sauvegardes planifiées intégrées à Coolify, gratuit sur le VPS existant | Un service supplémentaire à maintenir, consomme de la RAM sur le VPS |
| D. PostgreSQL managé (Neon, Supabase, cloud) | Rien à maintenir, haute disponibilité | Coût récurrent ou limites de l'offre gratuite, données hors de notre serveur, latence réseau |

## Décision

**Option C : PostgreSQL, déployé comme ressource Coolify sur le même VPS que l'API.**

C'est la seule option qui conserve les données **et** permet de faire tourner plusieurs instances de l'API, sans coût supplémentaire.
L'option D sera envisagée si la disponibilité devient critique (un seul VPS = un seul point de panne).

## Conséquences

- Une classe `PostgresOrderStore(OrderStore)` est ajoutée. Grâce à l'abstraction `OrderStore`, l'API ne change pas : seule la ligne qui instancie le store dans `app/main.py` est modifiée.
- `InMemoryOrderStore` est conservé pour les tests et le développement local.
- La connexion est fournie par une variable d'environnement `DATABASE_URL`, renseignée dans Coolify. Aucun identifiant n'est écrit dans le code ni dans git.
- La base n'est **pas exposée sur Internet** : l'API y accède par le réseau Docker interne de Coolify.
- Le schéma des tables doit être créé et versionné (script SQL ou outil de migration).
- Des **sauvegardes planifiées** de la base sont activées dans Coolify.
- `GET /health/ready` vérifie la connexion à la base via `OrderStore.ping()` : si la base est indisponible, l'API se déclare non prête.
- Le jour où la disponibilité devient critique, cette ADR devra être marquée « Status : Superseded by ADR-000X », avec une nouvelle décision écrite.
