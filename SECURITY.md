# Politique de sécurité

## Versions maintenues

| Version | Corrections de sécurité |
|---|---|
| 1.x (dernière version mineure) | ✅ |
| < 1.0 | ❌ |

Seule la **dernière version mineure** reçoit des correctifs : mettez à jour vers la plus récente.
Le projet suit aussi la fin de vie de ses dépendances (voir [endoflife.date](https://endoflife.date)) :
Python 3.13, PostgreSQL et les bibliothèques figées dans `requirements.lock.txt` sont mis à jour
avant leur fin de support.

## Signaler une vulnérabilité

**N'ouvrez pas d'Issue publique.** Utilisez le signalement privé de GitHub :
onglet **Security** du dépôt → **Report a vulnerability**.

Indiquez si possible :

- la route ou le composant concerné et la version (`GET /health`) ;
- les étapes pour reproduire, et l'impact estimé ;
- une proposition de correction, si vous en avez une.

## Délais de traitement

| Étape | Délai |
|---|---|
| Accusé de réception | 72 heures |
| Évaluation de la gravité (CVSS) | 7 jours |
| Correctif — gravité critique | 7 jours |
| Correctif — gravité élevée | 30 jours |
| Correctif — gravité moyenne ou faible | prochaine version mineure |

Le correctif est publié via une branche `hotfix/X.Y.Z` (voir [CONTRIBUTING.md](CONTRIBUTING.md)),
puis annoncé dans le [CHANGELOG](CHANGELOG.md).

## Numérotation (CVE)

Les vulnérabilités confirmées font l'objet d'un **GitHub Security Advisory**, avec demande
d'identifiant **CVE** (Common Vulnerabilities and Exposures) lorsque c'est pertinent.
La personne qui a signalé la faille est créditée, si elle le souhaite.

## Mesures en place

Résumé des décisions [ADR-0006](docs/adr/0006-securiser-les-entrees-et-sorties.md) et
[ADR-0007](docs/adr/0007-securiser-l-acces-a-la-donnee.md) : clés d'API hachées par client
avec rôle et expiration, limitation de débit, validation stricte des entrées, HTTPS,
pare-feu, base non exposée, conteneur non root, aucun secret dans git ni dans l'image.
