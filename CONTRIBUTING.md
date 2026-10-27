# Contribuer au projet

Merci de vouloir contribuer ! Ce guide explique comment proposer une correction ou une
fonctionnalité. En participant, vous acceptez de respecter le [code de conduite](CODE_OF_CONDUCT.md).

## Signaler un bug ou proposer une idée

Ouvrez une **Issue** avec le modèle adapté (*Bug* ou *Fonctionnalité*) et précisez :

- un titre court et précis ;
- comment reproduire le problème (requête envoyée, réponse obtenue, réponse attendue) ;
- la version concernée (champ `version` de `GET /health`).

⚠️ Une **faille de sécurité** ne se signale pas dans une Issue publique : voir [SECURITY.md](SECURITY.md).

## Organisation des branches (GitFlow)

| Branche | Rôle | Créée depuis | Fusionnée dans |
|---|---|---|---|
| `main` | Versions publiées, **déployées en production** par Coolify | — | — |
| `develop` | Intégration des fonctionnalités terminées | `main` | `release/*` |
| `feature/<sujet>` | Une fonctionnalité ou correction | `develop` | `develop` |
| `release/<X.Y.Z>` | Préparation d'une version (CHANGELOG, numéro de version) | `develop` | `main` **et** `develop` |
| `hotfix/<X.Y.Z>` | Correction urgente de la production | `main` | `main` **et** `develop` |

On ne pousse **jamais** directement sur `main` ni sur `develop` : tout passe par une Pull Request.

## Proposer une modification (Pull Request)

1. Créez votre branche : `git switch develop && git switch -c feature/mon-sujet`
   (contributeur externe : *fork* du dépôt, puis même principe).
2. Préparez l'environnement : ouvrez le projet dans le **devcontainer**, ou bien
   `python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt`.
3. Codez **avec des tests**, puis vérifiez en local :
   ```bash
   python -m training.train      # une fois, pour produire artifacts/
   python -m pytest --cov=app --cov=training
   ```
4. Ajoutez une ligne dans la section `[Unreleased]` du [CHANGELOG](CHANGELOG.md).
5. Ouvrez la Pull Request **vers `develop`** et remplissez le modèle. La CI (tests) doit être verte.

## Conventions

- **Commits** : [Conventional Commits](https://www.conventionalcommits.org/fr/) —
  `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`, `perf:`, `ci:`.
- **Code** : PEP 8, annotations de type sur les fonctions, commentaires et messages en français,
  fonctions courtes. Pas de secret dans le code (voir ADR-0007).
- **Contrat** : toute route doit respecter `openapi.yml` (vérifié par `tests/test_api.py`).
- **Architecture** : une décision structurante (stockage, déploiement, sécurité…) s'accompagne
  d'une **ADR** dans `docs/adr/` (numéro suivant, mêmes sections : Contexte, Options, Décision,
  Conséquences).
- **Versions** : [Semantic Versioning](https://semver.org/lang/fr/) `X.Y.Z` — X : changement
  incompatible du contrat, Y : ajout compatible, Z : correction.

## Fonctionnement du projet en bref

`training/` entraîne le modèle → les artefacts sont intégrés à l'image Docker (ADR-0002) →
`app/` les charge au démarrage et sert les prédictions. Les dépendances (stockage, modèle,
sécurité) sont derrière des abstractions (`OrderStore`, `ModelRepository`) : voir le [README](README.md).
