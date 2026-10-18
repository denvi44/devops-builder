# Modèle Azure VM — pipeline généré

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
| Préproduction | Prometheus | 9090 | 9090 | interface et API | publié sur l'hôte Docker |
| Préproduction | Grafana | 3000 | 3000 | interface web | publié sur l'hôte Docker |
| Préproduction | PostgreSQL | — | 5432 | PostgreSQL | réseau interne Compose (hôte « postgresql »), non publié |
| Production | mon-app | — | 8000 | application | via Traefik, hôte mon-app.example.com |
| Production | Traefik | 80 | 80 | HTTP | publié sur l'hôte Docker |
| Production | Traefik | 443 | 443 | HTTPS | publié sur l'hôte Docker |
| Production | Prometheus | 9090 | 9090 | interface et API | publié sur l'hôte Docker |
| Production | Grafana | 3000 | 3000 | interface web | publié sur l'hôte Docker |
| Production | PostgreSQL | — | 5432 | PostgreSQL | réseau interne Compose (hôte « postgresql »), non publié |

## Données

L'application lit l'URL de connexion complète dans la variable indiquée ; le mot de passe ne figure dans aucun fichier du dépôt.

| Base | Mode | Où | Variable de l'application | Mot de passe / URL | Sauvegarde |
| --- | --- | --- | --- | --- | --- |
| PostgreSQL 18 | autogérée | service Compose, volume nommé, réseau interne | `DATABASE_URL` | `deploy/secrets/<env>.enc.env` (SOPS) | `scripts/db-backup.sh` à planifier |

## Dimensionnement

Besoin estimé à partir des services Compose de l'hôte (marge de 25 %), pour chaque environnement porté, plus le système et Docker. Un ordre de grandeur pour une charge modeste, à confirmer par la supervision.

Services : mon-app (512 Mio, estimé), postgresql (512 Mio, estimé), traefik (128 Mio, estimé), prometheus (1024 Mio, estimé), grafana (512 Mio).

| Machines | Environnements | Besoin | Type retenu | Verdict |
| --- | --- | --- | --- | --- |
| `staging` | staging | 2 vCPU, 3,8 Gio | `Standard_B2s` (2 vCPU, 4 Gio) | suffisant |
| `production` | production | 2 vCPU, 3,8 Gio | `Standard_B2s` (2 vCPU, 4 Gio) | suffisant |

## Briques

| Étape | Brique | Licence | Fiche |
| --- | --- | --- | --- |
| Source | GitHub | proprietary | vérifiée |
| Build | GitHub Actions | proprietary | vérifiée |
| Build | BuildKit (docker buildx) | Apache-2.0 | vérifiée |
| Build | Dependabot | proprietary | vérifiée |
| Tests & qualité | Tests unitaires | MIT | vérifiée |
| Sécurité | Gitleaks | MIT | vérifiée |
| Sécurité | Trivy | Apache-2.0 | vérifiée |
| Sécurité | Cosign | Apache-2.0 | vérifiée |
| Artefacts | GitHub Container Registry | proprietary | vérifiée |
| Infrastructure | Microsoft Azure | proprietary | vérifiée |
| Infrastructure | Ansible | GPL-3.0 | vérifiée |
| Infrastructure | Azure Virtual Machines | proprietary | vérifiée |
| Infrastructure | OpenTofu | MPL-2.0 | vérifiée |
| Infrastructure | Azure Blob Storage | proprietary | vérifiée |
| Données | PostgreSQL | PostgreSQL | vérifiée |
| Déploiement | Docker Compose | Apache-2.0 | vérifiée |
| Plateforme | Traefik | MIT | vérifiée |
| Plateforme | SOPS | MPL-2.0 | vérifiée |
| Observabilité | Prometheus | Apache-2.0 | vérifiée |
| Observabilité | Grafana | AGPL-3.0 | vérifiée |

## Étapes CI

Orchestrateur : GitHub Actions. Image publiée : `ghcr.io/OWNER/mon-app:<commit>`.

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
| `TF_VAR_ssh_public_key` | non | à déclarer | Clé SSH publique du compte de déploiement (moitié publique de SSH_PRIVATE_KEY) (variable Terraform ssh_public_key, ex. "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA… deploy@ci") |
| `SOPS_AGE_KEY` | oui | à déclarer | Clé privée age qui déchiffre deploy/secrets/*.enc.env (age-keygen) |
| `SSH_PRIVATE_KEY` | oui | à déclarer | Clé SSH de déploiement vers les hôtes |
| `SSH_KNOWN_HOSTS` | non | à déclarer | Facultatif : clés d'hôte attendues (ssh-keyscan) ; sans elle, la clé est acceptée à la première connexion de chaque job |
| `AZURE_CLIENT_ID` | non | à déclarer | Identifiant d'application Entra ID |
| `AZURE_TENANT_ID` | non | à déclarer | Identifiant du tenant Entra ID |
| `AZURE_SUBSCRIPTION_ID` | non | à déclarer | Identifiant d'abonnement Azure |
| `AZURE_INFRA_CLIENT_ID` | non | à déclarer | Application Entra ID des jobs d'infrastructure (plan, apply) |

## Diagnostics restants

- **Avertissement** (R34) — Azure Blob Storage : « Compte de stockage » non renseigné : la valeur d'exemple « monprojettfstate » sera écrite dans les fichiers.
- **Avertissement** (R34) — Traefik : « Adresse publique de l'application » non renseigné : la valeur d'exemple « mon-app.example.com » sera écrite dans les fichiers.
- **Avertissement** (R34) — SOPS : « Destinataires age » non renseigné : la valeur d'exemple « age1ql3z7hjy54pw3hyww5ayyfg7zqgvc7w3j2elw8zmrj2kg5sfn9aqmcac8p » sera écrite dans les fichiers.

## Notes

- Mise en route pas à pas, avec les commandes du projet : docs/mise-en-route.md.
- Approbation (« Production ») : déclarer des relecteurs obligatoires sur l'environnement du dépôt (Settings › Environments › Required reviewers), sinon le déploiement part sans attendre.
- Ansible : préparer chaque hôte une fois avec `ANSIBLE_CONFIG=ansible/ansible.cfg ansible-playbook -i ansible/inventories/staging.ini ansible/site.yml` (Docker depuis son dépôt officiel, Debian, Ubuntu, RHEL et dérivées) ; le compte SSH doit avoir sudo sans mot de passe.
- Machines créées par OpenTofu (Azure Virtual Machines) : la clé publique de SSH_PRIVATE_KEY va dans TF_VAR_ssh_public_key ; au déploiement, `scripts/tf-inventory.sh` lit la sortie « hosts » de la pile et écrit l'inventaire de l'environnement. Lancer l'apply de la pile avant le premier déploiement.
- SSH des machines ouvert à tout Internet (clé seulement) : restreindre « Accès SSH autorisé » aux adresses de l'équipe et des runners quand c'est possible.
- Secrets par SOPS : renseigner la clé publique age dans la brique SOPS (.sops.yaml), puis `scripts/secrets-seed.sh <environnement>` chiffre les valeurs dans deploy/secrets/<environnement>.enc.env, à committer. La CI les déchiffre avec SOPS_AGE_KEY.
- Poste de développement : `docker compose -f dev/db/compose.yaml up -d` lance les bases du projet (même version), `dev/db/app.env` donne leurs variables de connexion.
- PostgreSQL : service Compose non publié sur l'hôte (réseau interne), données dans un volume nommé ; `deploy/secrets.sh` écrit les mots de passe et l'URL de connexion lus par les conteneurs (env_file), à partir des fichiers SOPS déchiffrés par la CI.
- Sauvegardes : planifier `scripts/db-backup.sh` sur chaque hôte (cron quotidien) et copier les fichiers hors de la machine.
- `scripts/ci-variables.sh` déclare les 8 variable(s) à renseigner avec GitHub (gh), sans écrire leurs valeurs dans le dépôt.

## Fichiers générés

- `.github/dependabot.yml`
- `.github/workflows/pipeline.yml`
- `.sops.yaml`
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
- `dev/db/init/postgresql/README.md`
- `devops-builder.yaml`
- `docs/mise-en-route.md`
- `infra/terraform/.gitignore`
- `infra/terraform/main.tf`
- `infra/terraform/outputs.tf`
- `infra/terraform/terraform.tfvars.example`
- `infra/terraform/variables.tf`
- `infra/terraform/versions.tf`
- `scripts/ci-variables.sh`
- `scripts/db-backup.sh`
- `scripts/db-restore.sh`
- `scripts/secrets-fetch.sh`
- `scripts/secrets-seed.sh`
- `scripts/tf-inventory.sh`
