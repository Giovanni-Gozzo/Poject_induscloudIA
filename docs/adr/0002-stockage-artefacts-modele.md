# ADR-0002 — Où stocker les artefacts du modèle de Machine Learning

**Status :** Accepté
**Date :** 06/10/2026

## Contexte

L'API doit pouvoir charger un modèle au démarrage sans réentraîner à chaque redéploiement.
Les artefacts sont `express_delivery_model.joblib` (la pipeline scikit-learn, quelques Mo) et `model_card.json` (version, features, seuil, métriques, version de scikit-learn).
Ils sont écrits rarement (à chaque nouvelle version du modèle) et lus très souvent (à chaque démarrage de l'API).

Contraintes du projet :

- un seul VPS, sans budget supplémentaire ;
- déploiement automatique par Coolify à chaque push sur `main` ;
- le modèle doit être exactement compatible avec la version de scikit-learn de l'API (contrôlé au chargement dans `app/model.py`) ;
- il faut pouvoir revenir rapidement à une version précédente en cas de problème.

## Options considérées

| Option | Avantage | Inconvénient |
|---|---|---|
| A. Répertoire local sur le serveur | Aucun service à installer | Pas de versionnage fiable, fichier modifiable à la main, perdu si le serveur est reconstruit |
| B. Volume persistant partagé (Coolify) | Le modèle survit aux redéploiements, partage simple entre conteneurs | Le modèle et le code peuvent se désynchroniser, pas d'historique des versions |
| C. Model Registry (MLflow) | Versionnage natif, métriques et lignée de chaque modèle, promotion staging → production | Un service supplémentaire à héberger, sécuriser et sauvegarder, ce qui ajoute de la RAM et des points de panne |
| D. Stockage objet (S3, Hetzner Object Storage) | Durable, versionnable, indépendant du serveur | Coût mensuel, gestion des identifiants d'accès |
| E. Artefacts intégrés à l'image Docker | L'image est immuable : code + modèle + dépendances forment une seule version cohérente ; retour arrière immédiat ; aucun service ni coût supplémentaire | Image plus lourde, et une nouvelle version du modèle impose un nouveau build |

## Décision

**Option E : les artefacts sont produits pendant le build Docker et intégrés à l'image de l'API.**

Le `Dockerfile` contient une étape `train` qui exécute `python -m training.train`. L'image finale ne contient que l'API et les deux artefacts.

Pourquoi c'est compatible avec le contexte (« ne pas réentraîner à chaque redéploiement ») :

- un **redémarrage**, une mise à l'échelle ou un **rollback** dans Coolify réutilisent une image déjà construite : **aucun réentraînement** ;
- seul un **nouveau build**, c'est-à-dire un changement de code poussé sur `main`, produit un nouveau modèle ;
- l'entraînement est **reproductible** : données générées avec une graine fixe (`RANDOM_STATE = 42`) et versions des bibliothèques figées par `requirements.lock.txt`. Le même commit produit donc le même modèle.

C'est aussi ce qui garantit que le modèle est toujours entraîné avec **exactement la même version de scikit-learn** que celle qui le sert.

Évolution probable vers l'option C (MLflow Model Registry) dès que le modèle sera entraîné sur des données réelles, ou qu'il faudra comparer et promouvoir plusieurs modèles.

## Conséquences

- Chaque image Docker correspond à une version précise du code **et** du modèle. Le `model_card.json` qu'elle contient indique `model_version`, `sklearn_version`, `trained_at` et les métriques.
- Une nouvelle version du modèle doit être identifiée explicitement, en incrémentant `MODEL_VERSION` dans `training/train.py`.
- Le retour arrière se fait avec la fonction **Rollback** de Coolify, qui redéploie une image précédente conservée (réglage *Image retention*).
- Chaque build dure plus longtemps, d'environ 25 secondes pour l'entraînement actuel.
- Le suivi MLflow fait pendant le build n'est pas conservé. Les métriques restent disponibles dans `model_card.json`.
- Si l'entraînement devient long ou dépend de données réelles, cette ADR devra être marquée « Status : Superseded by ADR-000X », avec une nouvelle décision écrite.
