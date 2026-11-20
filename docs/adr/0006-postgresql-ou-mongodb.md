# ADR-0006 — Choix de la source de données d'entraînement (PostgreSQL vs MongoDB)

**Status :** Accepté
**Date :** 29/10/2026

## Contexte

Pour réentraîner le modèle d'éligibilité à la livraison express sur des données réelles, deux bases existantes peuvent être connectées :

1. **PostgreSQL** (`localhost:5432`, table `public.orders`) :
   - Base historique (2015, schéma modifié en 2017 et 2023).
   - Base de **production** utilisée en échange bilatéral temps réel par `ERP Pro 2015` et une autre application critique.
   - Non mise à jour depuis 2023 (départ de l'administrateur de base de données, non remplacé).
2. **MongoDB** (`localhost:27017`, base `livraison_express`, collection `orders`) :
   - Base **analytique** créée en 2023 pour isoler les usages Data/Analytics de la production PostgreSQL.
   - Alimentée en temps réel par un flux ETL **unilatéral** depuis PostgreSQL (toute écriture dans MongoDB n'affecte pas la production).
   - Historique limité à 2023+, sans authentification configurée sur l'instance actuelle, et maintenue par un alternant en fin de contrat.

Par ailleurs, l'API elle-même persiste ses propres commandes collectées et prédictions dans sa base PostgreSQL dédiée (voir [ADR-0001](0001-stockage-commandes-clients.md)).

## Options considérées

| Option | Avantages | Inconvénients |
|---|---|---|
| **A. PostgreSQL (prod ERP)** | Historique complet depuis 2015 ; schéma relationnel typé ; déjà connu via `psycopg`. | Risque direct sur la production (charge, verrous, erreur humaine) partagée avec deux applications critiques ; aucun DBA pour intervenir en cas d'incident. |
| **B. MongoDB (base analytique)** | Isolation totale de la production (flux ETL unilatéral) ; conçue pour les équipes Data ; schéma souple. | Données uniquement depuis 2023 ; qualité et schéma non garantis au niveau base ; authentification absente et passation à prévoir avant le départ de l'alternant. |

## Décision

**Option B : MongoDB (base analytique)** via l'abstraction `OrderRepository` (`MongoOrderRepository`).

La règle prioritaire en industrialisation est de **ne jamais coupler directement l'entraînement ML à la base de production critique** d'un ERP, surtout en l'absence d'administrateur dédié. La base analytique MongoDB existe précisément pour cet usage.

## Conséquences

1. **Nettoyage et validation obligatoires** : la souplesse NoSQL empêchant de garantir le schéma à l'écriture, `clean_orders_data()` et `validate_dataset()` (`training/data.py`) sont systématiquement exécutés après extraction avant tout entraînement.
2. **Découplage par abstraction** : `training/repository.py` définit `OrderRepository` (`save`, `get`, `get_all`) avec `InMemoryOrderRepository` (tests) et `MongoOrderRepository` (ETL/analytique). Si une réplique PostgreSQL (streaming replication) est mise en place plus tard, une implémentation `PostgresOrderRepository` pourra être ajoutée sans modifier le pipeline d'entraînement.
3. **Plan d'action sécurité & reprise** : avant toute exposition hors réseau local, activer l'authentification SCRAM-SHA-256, TLS et la gestion des secrets (voir [ADR-0007](0007-securiser-entrees-sorties-et-acces-donnee.md)), et organiser le transfert de compétences de l'ETL avant le départ de l'alternant.
4. **Fenêtre temporelle** : l'entraînement s'appuie sur les données 2023+, ce qui correspond au fonctionnement logistique actuel ; si l'historique 2015–2022 devenait nécessaire, un export ponctuel à froid serait réalisé hors heures ouvrées.
