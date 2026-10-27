# ADR-0003 — Quelle plateforme de déploiement

**Status :** Accepté
**Date :** 27/10/2026

## Contexte

L'application est une **API HTTP** (FastAPI) qui sert un modèle de Machine Learning, accompagnée d'une base PostgreSQL (ADR-0001).
Ce n'est ni une application mobile (store d'applications), ni une application de bureau, ni un plugin : elle doit tourner sur un **serveur** joignable par les systèmes clients (site e-commerce, outil logistique).

Contraintes du projet :

- l'application est déjà conteneurisée (`Dockerfile` multi-étapes, modèle intégré à l'image, ADR-0002) ;
- déploiement **automatique** à chaque push sur `main`, sans commande manuelle ;
- **budget quasi nul** (projet de cours), une seule personne pour l'exploitation ;
- il faut pouvoir **revenir en arrière** rapidement (rollback) et voir les logs ;
- HTTPS obligatoire, sans gérer les certificats à la main.

## Options considérées

| Option | Avantage | Inconvénient |
|---|---|---|
| A. PaaS managé (Render, Railway, Fly.io) | Rien à administrer, déploiement Git intégré | Offres gratuites limitées (mise en veille, RAM faible), coût qui grimpe avec la base PostgreSQL, dépendance forte au fournisseur |
| B. Service de conteneurs d'un hyperscaler (Google Cloud Run, AWS ECS Fargate, Azure Container Apps) | Auto-scaling, haute disponibilité, intégration IAM | Facturation complexe à prévoir, base managée payante en plus, beaucoup de configuration pour un seul service |
| C. Kubernetes (k3s sur un VPS, ou GKE/EKS/AKS) | Standard de l'industrie, rolling update et canary natifs | Très lourd à installer et maintenir pour une API et une base ; surdimensionné à notre échelle |
| D. VPS + Docker Compose lancé à la main en SSH | Simple à comprendre, aucun outil en plus | Pas de déploiement automatique, pas de rollback, pas de HTTPS automatique : tout est à scripter soi-même |
| E. VPS + **Coolify** (PaaS auto-hébergé, open source) | Déploiement automatique depuis GitHub, HTTPS Let's Encrypt automatique, reverse proxy Traefik, rollback vers une image précédente, bases de données et sauvegardes planifiées intégrées, logs et terminal dans l'interface | Coolify lui-même est à installer, mettre à jour et sécuriser ; il consomme de la RAM sur le VPS |

## Décision

**Option E : un VPS sur lequel tourne Coolify.**

Coolify apporte ce qu'offrent les PaaS managés (option A) : déploiement à chaque push, HTTPS, rollback et logs. Il le fait sur un serveur que l'on maîtrise et au prix d'un simple VPS.
Le `Dockerfile` reste le seul contrat entre le code et la plateforme : on peut changer de plateforme sans modifier l'application.

Kubernetes (option C) sera envisagé si l'application doit tourner sur plusieurs serveurs (auto-scaling, séance 6).

## Conséquences

- Coolify construit l'image à partir du `Dockerfile` du dépôt à chaque push sur `main` (webhook GitHub).
- Le reverse proxy **Traefik** de Coolify reçoit tout le trafic HTTPS et le redirige vers le conteneur de l'API. Le port 8000 du conteneur n'est **jamais publié** sur le serveur.
- Les variables d'environnement (`DATABASE_URL`, `API_KEYS`, `RATE_LIMIT_PER_MINUTE`) sont saisies dans Coolify, jamais dans git (ADR-0007).
- Le healthcheck de l'image (`/health/ready`) sert à Coolify pour savoir si une nouvelle version est prête (ADR-0005).
- Coolify doit être tenu à jour et son interface protégée (ADR-0006).
- Le choix du VPS et de son hébergeur est décrit dans l'ADR-0004.
