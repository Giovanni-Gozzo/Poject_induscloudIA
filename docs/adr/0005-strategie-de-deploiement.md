# ADR-0005 — Quelle stratégie de déploiement

**Status :** Accepté
**Date :** 27/10/2026

## Contexte

Chaque push sur `main` produit une nouvelle image Docker (code **et** modèle, ADR-0002), que Coolify déploie sur l'unique serveur Hetzner (ADR-0003, ADR-0004).

Besoins :

- **aucune interruption** visible pour les clients pendant un déploiement ;
- une nouvelle version qui ne démarre pas correctement (modèle non chargé, base injoignable) ne doit **jamais** recevoir de trafic ;
- retour à la version précédente en quelques minutes si un problème apparaît après coup ;
- corriger vite un bug en production sans attendre une « release ».

Le trafic est faible et les clients ne sont pas segmentés : il n'y a pas de groupe d'utilisateurs « pilote » identifiable.

## Options considérées

| Stratégie | Avantage | Inconvénient dans notre contexte |
|---|---|---|
| Big Bang Release (arrêt puis redémarrage à une date planifiée) | Très simple | Coupure de service à chaque déploiement ; un problème touche 100 % des clients |
| Déploiement par service | Limite l'impact à un service | Nous n'avons qu'un service applicatif |
| Déploiement pilote / Canary Release | On expose d'abord 10 % du trafic, puis plus | Demande plusieurs instances en parallèle et un routage pondéré du trafic ; avec peu de requêtes, 10 % du trafic ne permet de rien conclure |
| Shadow (miroir) | Compare deux modèles sur le vrai trafic, sans risque pour l'utilisateur | Double la charge, demande de dupliquer les requêtes et de comparer les réponses : utile plus tard pour valider un **nouveau modèle**, pas pour chaque déploiement |
| Blue / Green | Bascule instantanée, retour arrière instantané | Garder deux environnements complets en permanence double les ressources du seul serveur |
| **Rolling update** + **Rollback** + **Hotfix** | Fourni nativement par Coolify : le nouveau conteneur démarre **à côté** de l'ancien ; Traefik ne bascule le trafic qu'une fois le healthcheck vert ; l'ancien est ensuite arrêté | Pendant quelques secondes, deux versions tournent en même temps sur la même base |

## Décision

**Rolling update par Coolify, conditionné au healthcheck `/health/ready`, complété par le Rollback et un processus de Hotfix.**

Avec un seul conteneur, le rolling update de Coolify fonctionne comme un **Blue / Green éphémère** :

1. Coolify construit l'image (entraînement compris) et démarre le nouveau conteneur (« green ») pendant que l'ancien (« blue ») sert toujours le trafic.
2. Le `HEALTHCHECK` de l'image appelle `/health/ready`, qui ne répond 200 que si **le modèle est chargé et la base joignable**.
3. Si la nouvelle version est saine, Traefik lui envoie le trafic et l'ancien conteneur est arrêté. **Sinon, le déploiement échoue et l'ancienne version continue de servir** : aucun client n'est touché.

En cas de problème découvert après la bascule :

- **Rollback** : l'onglet *Rollback* de Coolify redéploie une image précédente conservée (*Image retention*), **sans réentraîner** (ADR-0002).
- **Hotfix** : branche `hotfix/…` créée depuis `main`, tests automatiques, merge dans `main`, qui déclenche le même rolling update.

Le **Shadow** est retenu pour plus tard : c'est la bonne stratégie pour comparer un nouveau modèle à l'ancien sur du trafic réel (séance 5, prédictions conservées en base).

## Conséquences

- Le healthcheck doit rester **fiable** : `/health/ready` vérifie le modèle et la base, `/health` reste un simple test de vie.
- Pour que Coolify puisse faire tourner deux conteneurs à la fois, l'application ne doit **ni publier de port sur l'hôte, ni avoir de nom de conteneur fixe** dans Coolify. Sinon, il revient à un arrêt puis redémarrage (coupure).
- Les deux versions partagent la même base pendant la bascule : tout changement de `app/schema.sql` doit rester **rétrocompatible** (ajouter une colonne ou une table, jamais renommer ni supprimer dans le même déploiement).
- `uvicorn` reçoit `SIGTERM` à l'arrêt (`exec` dans le `CMD` du Dockerfile) et termine proprement les requêtes en cours.
- Le nombre d'images conservées par Coolify détermine jusqu'où l'on peut revenir en arrière.
- Le jour où plusieurs serveurs seront nécessaires, une vraie Canary Release (routage pondéré) deviendra possible : cette ADR devra alors être marquée « Status : Superseded by ADR-000X ».
