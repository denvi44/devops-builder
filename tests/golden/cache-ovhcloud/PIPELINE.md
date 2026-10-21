# Mon projet — pipeline généré

Généré par DevOps Builder le AAAA-MM-JJ. Cible : Machines virtuelles (Ansible).

## Environnements

Ordre de promotion : la même image est déployée successivement dans chaque environnement.

| Environnement | Type | Approbation | Cluster | Espace de noms / projet |
| --- | --- | --- | --- | --- |
| Préproduction (`staging`) | Préproduction | non | — | `mon-app-staging` |
| Production (`production`) | Production | oui | — | `mon-app` |

## Ports

| Environnement | Composant | Port publié | Port du conteneur | Usage | Exposition |
| --- | --- | --- | --- | --- | --- |
| Préproduction | mon-app | — | 8000 | application | via Traefik, hôte staging.mon-app.example.com |
| Préproduction | Traefik | 80 | 80 | HTTP | publié sur l'hôte Docker |
| Préproduction | Traefik | 443 | 443 | HTTPS | publié sur l'hôte Docker |
| Préproduction | Prometheus | — | 9090 | interface et API | réseau interne Compose, non publié |
| Préproduction | Grafana | — | 3000 | interface web | via Traefik, hôte grafana.example.com |
| Préproduction | OVHcloud Public Cloud Databases for Valkey | — | 6379 | Valkey | service managé, une instance par environnement |
| Production | mon-app | — | 8000 | application | via Traefik, hôte mon-app.example.com |
| Production | Traefik | 80 | 80 | HTTP | publié sur l'hôte Docker |
| Production | Traefik | 443 | 443 | HTTPS | publié sur l'hôte Docker |
| Production | Prometheus | — | 9090 | interface et API | réseau interne Compose, non publié |
| Production | Grafana | — | 3000 | interface web | via Traefik, hôte grafana.example.com |
| Production | OVHcloud Public Cloud Databases for Valkey | — | 6379 | Valkey | service managé, une instance par environnement |

## Données

L'application lit l'URL de connexion complète dans la variable indiquée ; le mot de passe ne figure dans aucun fichier du dépôt.

| Base | Mode | Où | Variable de l'application | Mot de passe / URL | Sauvegarde |
| --- | --- | --- | --- | --- | --- |
| OVHcloud Public Cloud Databases for Valkey | service managé | OVHcloud Public Cloud Databases for Valkey, une instance par environnement (Terraform) | `REDIS_URL` | variable CI `REDIS_URL_<ENV>` | cache : données reconstructibles, pas de sauvegarde planifiée |

## Dimensionnement

Besoin estimé à partir des services Compose de l'hôte (marge de 25 %), pour chaque environnement porté, plus le système et Docker. Un ordre de grandeur pour une charge modeste, à confirmer par la supervision.

Services : mon-app (512 Mio, estimé), traefik (128 Mio, estimé), prometheus (1024 Mio, estimé), grafana (512 Mio).

| Machines | Environnements | Besoin | Type retenu | Verdict |
| --- | --- | --- | --- | --- |
| `hors-production` | staging | 1 vCPU, 3,2 Gio | `b3-8` (2 vCPU, 8 Gio) | suffisant |
| `production` | production | 1 vCPU, 3,2 Gio | `b3-8` (2 vCPU, 8 Gio) | suffisant |

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
| Infrastructure | OVHcloud | proprietary | vérifiée |
| Infrastructure | Ansible | GPL-3.0 | vérifiée |
| Infrastructure | OVHcloud Public Cloud Instances | proprietary | vérifiée |
| Infrastructure | OpenTofu | MPL-2.0 | vérifiée |
| Infrastructure | OVHcloud Object Storage | proprietary | vérifiée |
| Données | OVHcloud Public Cloud Databases for Valkey | proprietary | vérifiée |
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
6. Plan OpenTofu
7. Application OpenTofu (branche principale, manuel)
8. Déploiement Ansible + Compose — Préproduction (branche principale)
9. Déploiement Ansible + Compose — Production (branche principale, manuel)

## Variables CI

Les variables sans valeur sont à déclarer dans la CI ; les autres sont déjà écrites dans les fichiers.

| Variable | Secret | Valeur | Rôle |
| --- | --- | --- | --- |
| `OVH_APPLICATION_KEY` | oui | à déclarer | Clé d'application OVHcloud |
| `OVH_APPLICATION_SECRET` | oui | à déclarer | Secret d'application OVHcloud |
| `OVH_CONSUMER_KEY` | oui | à déclarer | Clé consommateur OVHcloud |
| `TF_VAR_ssh_public_key` | non | à déclarer | Clé SSH publique du compte de déploiement (moitié publique de SSH_PRIVATE_KEY) (variable Terraform ssh_public_key, ex. "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA… deploy@ci") |
| `OVH_S3_ACCESS_KEY` | oui | à déclarer | Clé d'accès S3 OVHcloud (utilisateur Public Cloud), pour l'état Terraform |
| `OVH_S3_SECRET_KEY` | oui | à déclarer | Clé secrète S3 OVHcloud, pour l'état Terraform |
| `REDIS_URL_STAGING` | oui | à déclarer | URL de connexion à OVHcloud Public Cloud Databases for Valkey (Préproduction), lue par l'application dans REDIS_URL ; à composer après création de l'instance (sorties Terraform) |
| `SSH_PRIVATE_KEY` | oui | à déclarer | Clé SSH de déploiement vers les hôtes |
| `SSH_KNOWN_HOSTS` | non | à déclarer | Facultatif : clés d'hôte attendues (ssh-keyscan) ; sans elle, la clé est acceptée à la première connexion de chaque job |
| `REDIS_URL_PRODUCTION` | oui | à déclarer | URL de connexion à OVHcloud Public Cloud Databases for Valkey (Production), lue par l'application dans REDIS_URL ; à composer après création de l'instance (sorties Terraform) |
| `RENOVATE_TOKEN` | oui | à déclarer | Jeton de la forge autorisé à ouvrir des merge requests (Renovate) |

## Diagnostics restants

- **Avertissement** (R34) — OVHcloud : « Projet Public Cloud » non renseigné : la valeur d'exemple « <id-projet-public-cloud> » sera écrite dans les fichiers.
- **Avertissement** (R34) — OVHcloud Object Storage : « Bucket de l'état Terraform » non renseigné : la valeur d'exemple « mon-projet-tfstate » sera écrite dans les fichiers.
- **Avertissement** (R34) — Traefik : « Adresse publique de l'application » non renseigné : la valeur d'exemple « mon-app.example.com » sera écrite dans les fichiers.
- **Info** (R50) — OVHcloud Public Cloud Databases for Valkey est expérimental : instance et utilisateur créés ; droits de l'utilisateur et liste d'adresses autorisées à régler ensuite. Non essayé sur un compte OVHcloud.

## Notes

- Mise en route pas à pas, avec les commandes du projet : docs/mise-en-route.md.
- Approbation (« Production ») : le job attend un déclenchement manuel dans GitLab ; protéger l'environnement (Settings › CI/CD › Protected environments) pour restreindre qui peut le lancer.
- Ansible : préparer chaque hôte une fois avec `ANSIBLE_CONFIG=ansible/ansible.cfg ansible-playbook -i ansible/inventories/staging.ini ansible/site.yml` (Docker depuis son dépôt officiel, Debian, Ubuntu, RHEL et dérivées) ; le compte SSH doit avoir sudo sans mot de passe.
- Machines créées par OpenTofu (OVHcloud Public Cloud Instances) : la clé publique de SSH_PRIVATE_KEY va dans TF_VAR_ssh_public_key ; au déploiement, `scripts/tf-inventory.sh` lit la sortie « hosts » de la pile et écrit l'inventaire de l'environnement. Lancer l'apply de la pile avant le premier déploiement.
- SSH des machines ouvert à tout Internet (clé seulement) : restreindre « Accès SSH autorisé » aux adresses de l'équipe et des runners quand c'est possible.
- Poste de développement : `docker compose -f dev/db/compose.yaml up -d` lance les bases du projet (même version), `dev/db/app.env` donne leurs variables de connexion.
- Bases managées : une instance par environnement ; après `apply`, composer l'URL de connexion à partir des sorties Terraform (outputs.tf) et la déclarer en variable CI.
- Renovate : job « renovate » de .gitlab-ci.yml, lancé par une planification de pipeline portant la variable RENOVATE=1 (docs/mise-en-route.md) ; les autres jobs ne tournent pas dans ces pipelines.
- `scripts/ci-variables.sh` déclare les 11 variable(s) à renseigner avec GitLab (glab), sans écrire leurs valeurs dans le dépôt.

## Fichiers générés

- `.gitlab-ci.yml`
- `PIPELINE.md`
- `ansible/ansible.cfg`
- `ansible/deploy.yml`
- `ansible/inventories/production.ini`
- `ansible/inventories/staging.ini`
- `ansible/requirements.yml`
- `ansible/site.yml`
- `deploy/docker-compose.yml`
- `deploy/secrets.sh`
- `dev/db/app.env`
- `dev/db/compose.yaml`
- `devops-builder.yaml`
- `docs/mise-en-route.md`
- `infra/terraform/.gitignore`
- `infra/terraform/main.tf`
- `infra/terraform/outputs.tf`
- `infra/terraform/terraform.tfvars.example`
- `infra/terraform/variables.tf`
- `infra/terraform/versions.tf`
- `renovate.json`
- `scripts/ci-variables.sh`
- `scripts/tf-inventory.sh`
