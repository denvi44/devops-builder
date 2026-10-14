# Mon projet — pipeline généré

Généré par DevOps Builder le AAAA-MM-JJ. Cible : Hôte Docker unique.

## Environnements

Ordre de promotion : la même image est déployée successivement dans chaque environnement.

| Environnement | Type | Approbation | Cluster | Espace de noms / projet |
| --- | --- | --- | --- | --- |
| Préproduction (`staging`) | Préproduction | non | — | `mon-app-staging` |
| Production (`production`) | Production | oui | — | `mon-app` |

## Ports

| Environnement | Composant | Port publié | Port du conteneur | Usage | Exposition |
| --- | --- | --- | --- | --- | --- |
| Préproduction | mon-app | — | 8000 | application | via Traefik, hôte mon-app.example.com |
| Préproduction | Traefik | 80 | 80 | HTTP | publié sur l'hôte Docker |
| Préproduction | Traefik | 443 | 443 | HTTPS | publié sur l'hôte Docker |
| Préproduction | Zabbix | — | 8080 | interface web | via Traefik, hôte zabbix.boutique.fr |
| Préproduction | PostgreSQL | — | 5432 | PostgreSQL | réseau interne Compose (hôte « postgresql »), non publié |
| Production | mon-app | — | 8000 | application | via Traefik, hôte mon-app.example.com |
| Production | Traefik | 80 | 80 | HTTP | publié sur l'hôte Docker |
| Production | Traefik | 443 | 443 | HTTPS | publié sur l'hôte Docker |
| Production | Zabbix | — | 8080 | interface web | via Traefik, hôte zabbix.boutique.fr |
| Production | PostgreSQL | — | 5432 | PostgreSQL | réseau interne Compose (hôte « postgresql »), non publié |

## Données

L'application lit l'URL de connexion complète dans la variable indiquée ; le mot de passe ne figure dans aucun fichier du dépôt.

| Base | Mode | Où | Variable de l'application | Mot de passe / URL | Sauvegarde |
| --- | --- | --- | --- | --- | --- |
| PostgreSQL 18 | autogérée | service Compose, volume nommé, réseau interne | `DATABASE_URL` | variable CI `POSTGRESQL_PASSWORD_<ENV>` | `scripts/db-backup.sh` à planifier |

## Dimensionnement

Besoin estimé à partir des services Compose de l'hôte (marge de 25 %), pour chaque environnement porté, plus le système et Docker. Un ordre de grandeur pour une charge modeste, à confirmer par la supervision.

Services : mon-app (512 Mio, estimé), postgresql (512 Mio, estimé), traefik (128 Mio, estimé), zabbix-server (512 Mio, estimé), zabbix-web (256 Mio, estimé), zabbix-agent (64 Mio, estimé), zabbix-db (512 Mio, estimé).

| Machines | Environnements | Besoin | Type retenu | Verdict |
| --- | --- | --- | --- | --- |
| `staging` | staging | 2 vCPU, 3,5 Gio | hôte existant | prévoir au moins 2 vCPU et 3,5 Gio |
| `production` | production | 2 vCPU, 3,5 Gio | hôte existant | prévoir au moins 2 vCPU et 3,5 Gio |

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
| Sécurité | Cosign | Apache-2.0 | vérifiée |
| Données | PostgreSQL | PostgreSQL | vérifiée |
| Déploiement | Docker Compose | Apache-2.0 | vérifiée |
| Plateforme | Traefik | MIT | vérifiée |
| Observabilité | Zabbix | AGPL-3.0 | vérifiée |

## Étapes CI

Orchestrateur : GitLab CI. Image publiée : `$CI_REGISTRY_IMAGE:<commit>`.

1. Tests unitaires
2. Recherche de secrets
3. Build et publication de l'image (BuildKit (docker buildx))
4. Scan de vulnérabilités Trivy
5. Signature de l'image (Cosign) (branche principale)
6. Déploiement Docker Compose (SSH) — Préproduction (branche principale)
7. Déploiement Docker Compose (SSH) — Production (branche principale, manuel)

## Variables CI

Les variables sans valeur sont à déclarer dans la CI ; les autres sont déjà écrites dans les fichiers.

| Variable | Secret | Valeur | Rôle |
| --- | --- | --- | --- |
| `POSTGRESQL_PASSWORD_STAGING` | oui | à déclarer | Mot de passe PostgreSQL (Préproduction) — lettres, chiffres et . _ ~ - (il entre dans l'URL de connexion) |
| `ZABBIX_DB_PASSWORD_STAGING` | oui | à déclarer | Mot de passe de la base de Zabbix (serveur, interface web et base le partagent) (Préproduction) |
| `SSH_PRIVATE_KEY` | oui | à déclarer | Clé SSH de déploiement vers l'hôte Docker |
| `SSH_KNOWN_HOSTS` | non | à déclarer | Facultatif : clés d'hôte attendues (ssh-keyscan) ; sans elle, la clé est acceptée à la première connexion de chaque job |
| `DEPLOY_HOST_STAGING` | non | à déclarer | Hôte Docker cible (Préproduction) (utilisateur@hôte) |
| `POSTGRESQL_PASSWORD_PRODUCTION` | oui | à déclarer | Mot de passe PostgreSQL (Production) — lettres, chiffres et . _ ~ - (il entre dans l'URL de connexion) |
| `ZABBIX_DB_PASSWORD_PRODUCTION` | oui | à déclarer | Mot de passe de la base de Zabbix (serveur, interface web et base le partagent) (Production) |
| `DEPLOY_HOST_PRODUCTION` | non | à déclarer | Hôte Docker cible (Production) (utilisateur@hôte) |
| `RENOVATE_TOKEN` | oui | à déclarer | Jeton de la forge autorisé à ouvrir des merge requests (Renovate) |

## Diagnostics restants

Aucun.

## Notes

- Mise en route pas à pas, avec les commandes du projet : docs/mise-en-route.md.
- Approbation (« Production ») : le job attend un déclenchement manuel dans GitLab ; protéger l'environnement (Settings › CI/CD › Protected environments) pour restreindre qui peut le lancer.
- Poste de développement : `docker compose -f dev/db/compose.yaml up -d` lance les bases du projet (même version), `dev/db/app.env` donne leurs variables de connexion.
- PostgreSQL : service Compose non publié sur l'hôte (réseau interne), données dans un volume nommé ; `deploy/secrets.sh` écrit les mots de passe et l'URL de connexion lus par les conteneurs (env_file), à partir des variables CI.
- Sauvegardes : planifier `scripts/db-backup.sh` sur chaque hôte (cron quotidien) et copier les fichiers hors de la machine.
- Zabbix : interface sur https://zabbix.boutique.fr ; compte Admin / zabbix au premier accès, à changer aussitôt (docs/mise-en-route.md). L'agent fourni supervise le serveur Zabbix lui-même ; les autres hôtes reçoivent chacun un agent.
- Renovate : lancer l'image renovate/renovate dans un job planifié (quotidien) avec RENOVATE_TOKEN ; renovate.json règle son comportement.
- `scripts/ci-variables.sh` déclare les 9 variable(s) à renseigner avec GitLab (glab), sans écrire leurs valeurs dans le dépôt.

## Fichiers générés

- `.gitlab-ci.yml`
- `PIPELINE.md`
- `deploy/docker-compose.yml`
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
