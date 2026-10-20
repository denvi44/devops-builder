# Mon projet — pipeline généré

Généré par DevOps Builder le AAAA-MM-JJ. Cible : Machines virtuelles (Ansible).

## Environnements

Ordre de promotion : la même image est déployée successivement dans chaque environnement.

| Environnement | Type | Approbation | Cluster | Espace de noms / projet |
| --- | --- | --- | --- | --- |
| Développement (`dev`) | Développement | non | — | `mon-app-dev` |
| Recette (`recette`) | Recette | non | — | `mon-app-recette` |
| Production (`production`) | Production | oui | — | `mon-app` |

## Ports

Hôte partagé `hors-production` : Développement (+0), Recette (+10000). Les ports publiés de chaque environnement sont dans `deploy/env/<environnement>.env`.

| Environnement | Composant | Port publié | Port du conteneur | Usage | Exposition |
| --- | --- | --- | --- | --- | --- |
| Développement | mon-app | — | 8000 | application | via Traefik, hôte dev.mon-app.example.com |
| Développement | Traefik | 80 | 80 | HTTP | publié sur l'hôte Docker |
| Développement | Traefik | 443 | 443 | HTTPS | publié sur l'hôte Docker |
| Développement | Prometheus | — | 9090 | interface et API | réseau interne Compose, non publié |
| Développement | Grafana | — | 3000 | interface web | via Traefik, hôte grafana.example.com |
| Recette | mon-app | — | 8000 | application | via Traefik, hôte recette.mon-app.example.com |
| Recette | Traefik | 10080 | 80 | HTTP | publié sur l'hôte Docker |
| Recette | Traefik | 10443 | 443 | HTTPS | publié sur l'hôte Docker |
| Recette | Prometheus | — | 9090 | interface et API | réseau interne Compose, non publié |
| Recette | Grafana | — | 3000 | interface web | via Traefik, hôte grafana.example.com |
| Production | mon-app | — | 8000 | application | via Traefik, hôte mon-app.example.com |
| Production | Traefik | 80 | 80 | HTTP | publié sur l'hôte Docker |
| Production | Traefik | 443 | 443 | HTTPS | publié sur l'hôte Docker |
| Production | Prometheus | — | 9090 | interface et API | réseau interne Compose, non publié |
| Production | Grafana | — | 3000 | interface web | via Traefik, hôte grafana.example.com |

## Dimensionnement

Besoin estimé à partir des services Compose de l'hôte (marge de 25 %), pour chaque environnement porté, plus le système et Docker. Un ordre de grandeur pour une charge modeste, à confirmer par la supervision.

Services : mon-app (512 Mio, estimé), traefik (128 Mio, estimé), prometheus (1024 Mio, estimé), grafana (512 Mio).

| Machines | Environnements | Besoin | Type retenu | Verdict |
| --- | --- | --- | --- | --- |
| `hors-production` | dev, recette | 2 vCPU, 5,8 Gio | `b3-8` (2 vCPU, 8 Gio) | suffisant |
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
| Infrastructure | OVHcloud Private Network | proprietary | vérifiée |
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
8. Déploiement Ansible + Compose — Développement (branche principale)
9. Déploiement Ansible + Compose — Recette (branche principale)
10. Déploiement Ansible + Compose — Production (branche principale, manuel)

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
| `SSH_PRIVATE_KEY` | oui | à déclarer | Clé SSH de déploiement vers les hôtes |
| `SSH_KNOWN_HOSTS` | non | à déclarer | Facultatif : clés d'hôte attendues (ssh-keyscan) ; sans elle, la clé est acceptée à la première connexion de chaque job |
| `RENOVATE_TOKEN` | oui | à déclarer | Jeton de la forge autorisé à ouvrir des merge requests (Renovate) |

## Diagnostics restants

- **Avertissement** (R34) — OVHcloud : « Projet Public Cloud » non renseigné : la valeur d'exemple « <id-projet-public-cloud> » sera écrite dans les fichiers.
- **Avertissement** (R34) — OVHcloud Object Storage : « Bucket de l'état Terraform » non renseigné : la valeur d'exemple « mon-projet-tfstate » sera écrite dans les fichiers.
- **Avertissement** (R34) — Traefik : « Adresse publique de l'application » non renseigné : la valeur d'exemple « mon-app.example.com » sera écrite dans les fichiers.
- **Info** (R50) — OVHcloud Private Network est expérimental : rattaché au cluster Managed Kubernetes seulement : les instances et les bases restent sur le réseau public (à rattacher à la main). Non essayé sur un compte OVHcloud.

## Notes

- Mise en route pas à pas, avec les commandes du projet : docs/mise-en-route.md.
- Approbation (« Production ») : le job attend un déclenchement manuel dans GitLab ; protéger l'environnement (Settings › CI/CD › Protected environments) pour restreindre qui peut le lancer.
- Plusieurs environnements partagent un hôte Docker : leurs ports publiés sont décalés (deploy/env/<environnement>.env, copié en .env à côté du fichier Compose).
- Ansible : préparer chaque hôte une fois avec `ANSIBLE_CONFIG=ansible/ansible.cfg ansible-playbook -i ansible/inventories/dev.ini ansible/site.yml` (Docker depuis son dépôt officiel, Debian, Ubuntu, RHEL et dérivées) ; le compte SSH doit avoir sudo sans mot de passe.
- OVHcloud Private Network : les instances restent sur le réseau public ; rattacher le réseau privé aux machines à la main (bloc network de ovh_cloud_project_instance).
- Machines créées par OpenTofu (OVHcloud Public Cloud Instances) : la clé publique de SSH_PRIVATE_KEY va dans TF_VAR_ssh_public_key ; au déploiement, `scripts/tf-inventory.sh` lit la sortie « hosts » de la pile et écrit l'inventaire de l'environnement. Lancer l'apply de la pile avant le premier déploiement.
- SSH des machines ouvert à tout Internet (clé seulement) : restreindre « Accès SSH autorisé » aux adresses de l'équipe et des runners quand c'est possible.
- Renovate : job « renovate » de .gitlab-ci.yml, lancé par une planification de pipeline portant la variable RENOVATE=1 (docs/mise-en-route.md) ; les autres jobs ne tournent pas dans ces pipelines.
- `scripts/ci-variables.sh` déclare les 9 variable(s) à renseigner avec GitLab (glab), sans écrire leurs valeurs dans le dépôt.

## Fichiers générés

- `.gitlab-ci.yml`
- `PIPELINE.md`
- `ansible/ansible.cfg`
- `ansible/deploy.yml`
- `ansible/inventories/dev.ini`
- `ansible/inventories/production.ini`
- `ansible/inventories/recette.ini`
- `ansible/requirements.yml`
- `ansible/site.yml`
- `deploy/docker-compose.yml`
- `deploy/env/dev.env`
- `deploy/env/production.env`
- `deploy/env/recette.env`
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
