# Boutique avec base de données — pipeline généré

Généré par DevOps Builder le AAAA-MM-JJ. Cible : Hôte Docker unique.

## Environnements

Ordre de promotion : la même image est déployée successivement dans chaque environnement.

| Environnement | Type | Approbation | Cluster | Espace de noms / projet |
| --- | --- | --- | --- | --- |
| Développement (`dev`) | Développement | non | — | `boutique-dev` |
| Recette (`recette`) | Recette | non | — | `boutique-recette` |
| Production (`production`) | Production | oui | — | `boutique` |

## Ports

Hôte partagé `vm-hors-prod` : Développement (+0), Recette (+10000). Les ports publiés de chaque environnement sont dans `deploy/env/<environnement>.env`.

| Environnement | Composant | Port publié | Port du conteneur | Usage | Exposition |
| --- | --- | --- | --- | --- | --- |
| Développement | boutique | — | 8000 | application | via Traefik, hôte boutique-dev.example.com |
| Développement | Traefik | 80 | 80 | HTTP | publié sur l'hôte Docker |
| Développement | Traefik | 443 | 443 | HTTPS | publié sur l'hôte Docker |
| Développement | Prometheus | 9090 | 9090 | interface et API | publié sur l'hôte Docker |
| Développement | Grafana | 3000 | 3000 | interface web | publié sur l'hôte Docker |
| Développement | PostgreSQL | — | 5432 | PostgreSQL | réseau interne Compose (hôte « postgresql »), non publié |
| Développement | Valkey | — | 6379 | Valkey | réseau interne Compose (hôte « valkey »), non publié |
| Recette | boutique | — | 8000 | application | via Traefik, hôte boutique-recette.example.com |
| Recette | Traefik | 10080 | 80 | HTTP | publié sur l'hôte Docker |
| Recette | Traefik | 10443 | 443 | HTTPS | publié sur l'hôte Docker |
| Recette | Prometheus | 19090 | 9090 | interface et API | publié sur l'hôte Docker |
| Recette | Grafana | 13000 | 3000 | interface web | publié sur l'hôte Docker |
| Recette | PostgreSQL | — | 5432 | PostgreSQL | réseau interne Compose (hôte « postgresql »), non publié |
| Recette | Valkey | — | 6379 | Valkey | réseau interne Compose (hôte « valkey »), non publié |
| Production | boutique | — | 8000 | application | via Traefik, hôte boutique.example.com |
| Production | Traefik | 80 | 80 | HTTP | publié sur l'hôte Docker |
| Production | Traefik | 443 | 443 | HTTPS | publié sur l'hôte Docker |
| Production | Prometheus | 9090 | 9090 | interface et API | publié sur l'hôte Docker |
| Production | Grafana | 3000 | 3000 | interface web | publié sur l'hôte Docker |
| Production | PostgreSQL | — | 5432 | PostgreSQL | réseau interne Compose (hôte « postgresql »), non publié |
| Production | Valkey | — | 6379 | Valkey | réseau interne Compose (hôte « valkey »), non publié |

## Données

L'application lit l'URL de connexion complète dans la variable indiquée ; le mot de passe ne figure dans aucun fichier du dépôt.

| Base | Mode | Où | Variable de l'application | Mot de passe / URL | Sauvegarde |
| --- | --- | --- | --- | --- | --- |
| PostgreSQL 18 | autogérée | service Compose, volume nommé, réseau interne | `DATABASE_URL` | variable CI `POSTGRESQL_PASSWORD_<ENV>` | `scripts/db-backup.sh` à planifier |
| Valkey 8 | autogérée | service Compose, volume nommé, réseau interne | `REDIS_URL` | variable CI `VALKEY_PASSWORD_<ENV>` | persistance AOF du volume |

Migrations : `alembic upgrade head`, exécutée avec l'image de l'application avant chaque démarrage (service Compose « migrate » ou initContainer).

## Dimensionnement

Besoin estimé à partir des services Compose de l'hôte (marge de 25 %), pour chaque environnement porté, plus le système et Docker. Un ordre de grandeur pour une charge modeste, à confirmer par la supervision.

Services : boutique (512 Mio, estimé), postgresql (512 Mio, estimé), valkey (256 Mio, estimé), traefik (128 Mio, estimé), prometheus (1024 Mio, estimé), grafana (512 Mio).

| Machines | Environnements | Besoin | Type retenu | Verdict |
| --- | --- | --- | --- | --- |
| `vm-hors-prod` | dev, recette | 2 vCPU, 7,7 Gio | hôte existant | prévoir au moins 2 vCPU et 7,7 Gio |
| `production` | production | 2 vCPU, 4,1 Gio | hôte existant | prévoir au moins 2 vCPU et 4,1 Gio |

## Briques

| Étape | Brique | Licence | Fiche |
| --- | --- | --- | --- |
| Source | GitLab | MIT | vérifiée |
| Build | GitLab CI | MIT | vérifiée |
| Build | BuildKit (docker buildx) | Apache-2.0 | vérifiée |
| Build | Renovate | AGPL-3.0 | vérifiée |
| Tests & qualité | Tests unitaires | MIT | vérifiée |
| Sécurité | Gitleaks | MIT | vérifiée |
| Sécurité | Trivy | Apache-2.0 | vérifiée |
| Données | PostgreSQL | PostgreSQL | vérifiée |
| Données | Valkey | BSD-3-Clause | vérifiée |
| Données | Migrations de schéma | MIT | vérifiée |
| Déploiement | Docker Compose | Apache-2.0 | vérifiée |
| Plateforme | Traefik | MIT | vérifiée |
| Observabilité | Prometheus | Apache-2.0 | vérifiée |
| Observabilité | Grafana | AGPL-3.0 | vérifiée |

## Étapes CI

Orchestrateur : GitLab CI. Image publiée : `$CI_REGISTRY_IMAGE:<commit>`.

1. Tests unitaires
2. Recherche de secrets
3. Build et publication de l'image (BuildKit (docker buildx))
4. Scan de vulnérabilités Trivy
5. Déploiement Docker Compose (SSH) — Développement (branche principale)
6. Déploiement Docker Compose (SSH) — Recette (branche principale)
7. Déploiement Docker Compose (SSH) — Production (branche principale, manuel)

## Variables CI

Les variables sans valeur sont à déclarer dans la CI ; les autres sont déjà écrites dans les fichiers.

| Variable | Secret | Valeur | Rôle |
| --- | --- | --- | --- |
| `POSTGRESQL_PASSWORD_DEV` | oui | à déclarer | Mot de passe PostgreSQL (Développement) — lettres, chiffres et . _ ~ - (il entre dans l'URL de connexion) |
| `VALKEY_PASSWORD_DEV` | oui | à déclarer | Mot de passe Valkey (Développement) — lettres, chiffres et . _ ~ - (il entre dans l'URL de connexion) |
| `SSH_PRIVATE_KEY` | oui | à déclarer | Clé SSH de déploiement vers l'hôte Docker |
| `SSH_KNOWN_HOSTS` | non | à déclarer | Facultatif : clés d'hôte attendues (ssh-keyscan) ; sans elle, la clé est acceptée à la première connexion de chaque job |
| `DEPLOY_HOST_DEV` | non | à déclarer | Hôte Docker cible (Développement) (utilisateur@hôte) |
| `POSTGRESQL_PASSWORD_RECETTE` | oui | à déclarer | Mot de passe PostgreSQL (Recette) — lettres, chiffres et . _ ~ - (il entre dans l'URL de connexion) |
| `VALKEY_PASSWORD_RECETTE` | oui | à déclarer | Mot de passe Valkey (Recette) — lettres, chiffres et . _ ~ - (il entre dans l'URL de connexion) |
| `DEPLOY_HOST_RECETTE` | non | à déclarer | Hôte Docker cible (Recette) (utilisateur@hôte) |
| `POSTGRESQL_PASSWORD_PRODUCTION` | oui | à déclarer | Mot de passe PostgreSQL (Production) — lettres, chiffres et . _ ~ - (il entre dans l'URL de connexion) |
| `VALKEY_PASSWORD_PRODUCTION` | oui | à déclarer | Mot de passe Valkey (Production) — lettres, chiffres et . _ ~ - (il entre dans l'URL de connexion) |
| `DEPLOY_HOST_PRODUCTION` | non | à déclarer | Hôte Docker cible (Production) (utilisateur@hôte) |
| `RENOVATE_TOKEN` | oui | à déclarer | Jeton de la forge autorisé à ouvrir des merge requests (Renovate) |

## Diagnostics restants

Aucun.

## Notes

- Mise en route pas à pas, avec les commandes du projet : docs/mise-en-route.md.
- Approbation (« Production ») : le job attend un déclenchement manuel dans GitLab ; protéger l'environnement (Settings › CI/CD › Protected environments) pour restreindre qui peut le lancer.
- Plusieurs environnements partagent un hôte Docker : leurs ports publiés sont décalés (deploy/env/<environnement>.env, copié en .env à côté du fichier Compose).
- Poste de développement : `docker compose -f dev/db/compose.yaml up -d` lance les bases du projet (même version), `dev/db/app.env` donne leurs variables de connexion.
- PostgreSQL, Valkey : service Compose non publié sur l'hôte (réseau interne), données dans un volume nommé ; `deploy/secrets.sh` écrit les mots de passe et l'URL de connexion lus par les conteneurs (env_file), à partir des variables CI.
- Sauvegardes : planifier `scripts/db-backup.sh` sur chaque hôte (cron quotidien) et copier les fichiers hors de la machine.
- Renovate : lancer l'image renovate/renovate dans un job planifié (quotidien) avec RENOVATE_TOKEN ; renovate.json règle son comportement.
- `scripts/ci-variables.sh` déclare les 12 variable(s) à renseigner avec GitLab (glab), sans écrire leurs valeurs dans le dépôt.

## Fichiers générés

- `.gitlab-ci.yml`
- `PIPELINE.md`
- `deploy/docker-compose.yml`
- `deploy/env/dev.env`
- `deploy/env/production.env`
- `deploy/env/recette.env`
- `deploy/secrets.sh`
- `dev/db/app.env`
- `dev/db/compose.yaml`
- `dev/db/init/postgresql/README.md`
- `devops-builder.yaml`
- `docs/mise-en-route.md`
- `renovate.json`
- `scripts/ci-variables.sh`
- `scripts/db-backup.sh`
- `scripts/db-restore.sh`
