# Mon projet — pipeline généré

Généré par DevOps Builder le AAAA-MM-JJ. Cible : Machines virtuelles (Ansible).

## Environnements

Ordre de promotion : la même image est déployée successivement dans chaque environnement.

| Environnement | Type | Approbation | Cluster | Espace de noms / projet |
| --- | --- | --- | --- | --- |
| Production (`production`) | Production | non | — | `mon-app` |

## Ports

| Composant | Port publié | Port du conteneur | Usage | Exposition |
| --- | --- | --- | --- | --- |
| mon-app | — | 8000 | application | via Traefik, hôte mon-app.example.com |
| Traefik | 80 | 80 | HTTP | publié sur l'hôte Docker |
| Traefik | 443 | 443 | HTTPS | publié sur l'hôte Docker |
| Prometheus | 9090 | 9090 | interface et API | publié sur l'hôte Docker |
| Grafana | 3000 | 3000 | interface web | publié sur l'hôte Docker |
| MariaDB | — | 3306 | MariaDB | réseau interne Compose (hôte « mariadb »), non publié |

## Données

L'application lit l'URL de connexion complète dans la variable indiquée ; le mot de passe ne figure dans aucun fichier du dépôt.

| Base | Mode | Où | Variable de l'application | Mot de passe / URL | Sauvegarde |
| --- | --- | --- | --- | --- | --- |
| MariaDB 11.8 | autogérée | service Compose, volume nommé, réseau interne | `DATABASE_URL` | variable CI `MARIADB_PASSWORD` | `scripts/db-backup.sh` à planifier |

## Dimensionnement

Besoin estimé à partir des services Compose de l'hôte (marge de 25 %), pour chaque environnement porté, plus le système et Docker. Un ordre de grandeur pour une charge modeste, à confirmer par la supervision.

Services : mon-app (512 Mio, estimé), mariadb (512 Mio, estimé), traefik (128 Mio, estimé), prometheus (1024 Mio, estimé), grafana (512 Mio).

| Environnements | Besoin | Type retenu | Verdict |
| --- | --- | --- | --- |
| production | 2 vCPU, 3,8 Gio | hôte existant | prévoir au moins 2 vCPU et 3,8 Gio |

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
| Infrastructure | Ansible | GPL-3.0 | vérifiée |
| Données | MariaDB | GPL-2.0 | vérifiée |
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
5. Signature de l'image (Cosign) (branche principale)
6. Déploiement Ansible + Compose (branche principale)

## Variables CI

Les variables sans valeur sont à déclarer dans la CI ; les autres sont déjà écrites dans les fichiers.

| Variable | Secret | Valeur | Rôle |
| --- | --- | --- | --- |
| `MARIADB_PASSWORD` | oui | à déclarer | Mot de passe MariaDB — lettres, chiffres et . _ ~ - (il entre dans l'URL de connexion) |
| `SSH_PRIVATE_KEY` | oui | à déclarer | Clé SSH de déploiement vers les hôtes |
| `SSH_KNOWN_HOSTS` | non | à déclarer | Facultatif : clés d'hôte attendues (ssh-keyscan) ; sans elle, la clé est acceptée à la première connexion de chaque job |
| `RENOVATE_TOKEN` | oui | à déclarer | Jeton de la forge autorisé à ouvrir des merge requests (Renovate) |

## Diagnostics restants

- **Avertissement** (R34) — Ansible : « Hôtes de l'application » non renseigné : la valeur d'exemple « app1.example.com » sera écrite dans les fichiers.

## Notes

- Mise en route pas à pas, avec les commandes du projet : docs/mise-en-route.md.
- Ansible : préparer chaque hôte une fois avec `ANSIBLE_CONFIG=ansible/ansible.cfg ansible-playbook -i ansible/inventory.ini ansible/site.yml` (Docker depuis son dépôt officiel, Debian, Ubuntu, RHEL et dérivées) ; le compte SSH doit avoir sudo sans mot de passe.
- Poste de développement : `docker compose -f dev/db/compose.yaml up -d` lance les bases du projet (même version), `dev/db/app.env` donne leurs variables de connexion.
- MariaDB : service Compose non publié sur l'hôte (réseau interne), données dans un volume nommé ; `deploy/secrets.sh` écrit les mots de passe et l'URL de connexion lus par les conteneurs (env_file), à partir des variables CI.
- Sauvegardes : planifier `scripts/db-backup.sh` sur chaque hôte (cron quotidien) et copier les fichiers hors de la machine.
- Renovate : lancer l'image renovate/renovate dans un job planifié (quotidien) avec RENOVATE_TOKEN ; renovate.json règle son comportement.
- `scripts/ci-variables.sh` déclare les 4 variable(s) à renseigner avec GitLab (glab), sans écrire leurs valeurs dans le dépôt.

## Fichiers générés

- `.gitlab-ci.yml`
- `PIPELINE.md`
- `ansible/ansible.cfg`
- `ansible/deploy.yml`
- `ansible/inventory.ini`
- `ansible/requirements.yml`
- `ansible/site.yml`
- `deploy/docker-compose.yml`
- `deploy/secrets.sh`
- `dev/db/app.env`
- `dev/db/compose.yaml`
- `dev/db/init/mariadb/README.md`
- `devops-builder.yaml`
- `docs/mise-en-route.md`
- `renovate.json`
- `scripts/ci-variables.sh`
- `scripts/db-backup.sh`
- `scripts/db-restore.sh`
