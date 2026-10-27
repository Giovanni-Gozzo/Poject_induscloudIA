# ADR-0004 — Cloud, on-premise ou local, et quels services Cloud

**Status :** Accepté
**Date :** 27/10/2026

## Contexte

La plateforme retenue est Coolify sur un serveur Linux (ADR-0003). Il reste à décider **où** se trouve ce serveur.

Besoins :

- l'API doit être joignable **24 h/24 depuis Internet** par les systèmes clients ;
- les données de commandes doivent rester dans l'**Union européenne** (RGPD) ;
- un seul serveur suffit aujourd'hui (quelques requêtes par seconde au plus), avec 2 vCPU et 4 Go de RAM au minimum pour Coolify, l'API et PostgreSQL ;
- budget de quelques euros par mois, sans engagement ;
- aucune exigence de type « secret défense » ou de calcul intensif (GPU) qui imposerait du matériel dédié.

## Options considérées

| Option | Avantage | Inconvénient |
|---|---|---|
| A. Local (le PC du développeur) | Gratuit, immédiat | Pas joignable de façon fiable depuis Internet, s'arrête quand le PC s'éteint : ce n'est pas de la production |
| B. On-premise (serveur physique dans nos locaux) | Contrôle total du matériel et des données | Achat du matériel, électricité, connexion Internet professionnelle, IP fixe, remplacement des pannes : coût et charge disproportionnés |
| C. Cloud hyperscaler (AWS, Google Cloud, Azure) | Catalogue de services immense, régions UE disponibles | Tarification complexe, trafic sortant facturé, VM équivalente nettement plus chère |
| D. Cloud **Hetzner** (IaaS européen) | Serveurs en Allemagne et en Finlande (UE), prix bas et prévisibles, pare-feu cloud gratuit, stockage objet compatible S3 | Catalogue limité (pas de base PostgreSQL managée), support moins étendu qu'un hyperscaler |

## Décision

**Option D : Cloud public, chez Hetzner, région Allemagne (Falkenstein ou Nuremberg).**

Le Cloud supprime la gestion du matériel (option B) tout en donnant un serveur joignable en permanence (contrairement à l'option A). Hetzner offre le meilleur rapport prix/besoin, avec des données hébergées dans l'UE.

### Services Hetzner utilisés

| Service | Rôle dans l'architecture |
|---|---|
| **Cloud Server** (Ubuntu LTS, 2 vCPU / 4 Go RAM minimum) | Héberge Coolify, Traefik, le conteneur de l'API et PostgreSQL |
| **Cloud Firewall** | Filtre les connexions entrantes avant même qu'elles atteignent le serveur (règles dans l'ADR-0006) |
| **Backups** du serveur | Image complète du serveur chaque jour, pour le reconstruire après un incident grave |
| **Object Storage** (compatible S3) | Destination des sauvegardes planifiées de PostgreSQL configurées dans Coolify (ADR-0001), stockées hors du serveur |

Services **non** utilisés, volontairement (YAGNI) :

- **Load Balancer** : un seul serveur, Traefik suffit à répartir vers le conteneur ;
- **base de données managée** : Hetzner Cloud n'en propose pas, et PostgreSQL dans Coolify convient (ADR-0001) ;
- **Volumes** supplémentaires : le disque du serveur suffit au volume de données actuel.

## Conséquences

- Coût mensuel prévisible : un serveur, ses backups et un peu de stockage objet.
- **Un seul serveur = un seul point de panne.** Les backups quotidiens et les sauvegardes de la base sur Object Storage limitent la perte de données, mais pas l'indisponibilité. Si la disponibilité devient critique, cette ADR devra être marquée « Status : Superseded by ADR-000X » (deuxième serveur, Load Balancer Hetzner).
- Le système d'exploitation du serveur est à notre charge : mises à jour de sécurité automatiques (`unattended-upgrades`) à activer.
- Le développement reste **local** (devcontainer) et les tests tournent en local et en CI : seule la production est dans le Cloud.
