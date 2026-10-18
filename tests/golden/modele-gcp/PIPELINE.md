# Modèle Google Cloud — pipeline généré

Généré par DevOps Builder le AAAA-MM-JJ. Cible : Kubernetes managé (cloud).

## Environnements

Ordre de promotion : la même image est déployée successivement dans chaque environnement.

| Environnement | Type | Approbation | Cluster | Espace de noms / projet |
| --- | --- | --- | --- | --- |
| Préproduction (`staging`) | Préproduction | non | Google Kubernetes Engine `mon-cluster` | `mon-app-staging` |
| Production (`production`) | Production | oui | Google Kubernetes Engine `mon-cluster` | `mon-app` |

## Ports

| Environnement | Composant | Port publié | Port du conteneur | Usage | Exposition |
| --- | --- | --- | --- | --- | --- |
| Préproduction | mon-app | — | 8000 | application | Service mon-app port 80, espace de noms mon-app-staging |
| Préproduction | Google Cloud SQL | — | 5432 | PostgreSQL | service managé, une instance par environnement |
| Production | mon-app | — | 8000 | application | Service mon-app port 80, espace de noms mon-app |
| Production | Google Cloud SQL | — | 5432 | PostgreSQL | service managé, une instance par environnement |

## Données

L'application lit l'URL de connexion complète dans la variable indiquée ; le mot de passe ne figure dans aucun fichier du dépôt.

| Base | Mode | Où | Variable de l'application | Mot de passe / URL | Sauvegarde |
| --- | --- | --- | --- | --- | --- |
| Google Cloud SQL | service managé | Google Cloud SQL, une instance par environnement (Terraform) | `DATABASE_URL` | Google Secret Manager, clé `<espace de noms>-cloud-sql` (External Secrets, écrit par Terraform) | service du fournisseur (rétention configurée) |

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
| Artefacts | Google Artifact Registry | proprietary | vérifiée |
| Infrastructure | Google Cloud | proprietary | vérifiée |
| Infrastructure | Google Kubernetes Engine | proprietary | vérifiée |
| Infrastructure | OpenTofu | MPL-2.0 | vérifiée |
| Infrastructure | Google Cloud Storage | proprietary | vérifiée |
| Données | Google Cloud SQL | proprietary | vérifiée |
| Déploiement | Helm | Apache-2.0 | vérifiée |
| Plateforme | cert-manager | Apache-2.0 | vérifiée |
| Plateforme | Google Secret Manager | proprietary | vérifiée |
| Plateforme | External Secrets Operator | Apache-2.0 | vérifiée |
| Observabilité | Google Cloud Monitoring et Logging | proprietary | vérifiée |

## Étapes CI

Orchestrateur : GitLab CI. Image publiée : `europe-west9-docker.pkg.dev/mon-projet/mon-app/mon-app:<commit>`.

1. Tests unitaires
2. Recherche de secrets
3. Build et publication de l'image (BuildKit (docker buildx))
4. Scan de vulnérabilités Trivy
5. Signature de l'image (Cosign) (branche principale)
6. Plan OpenTofu
7. Application OpenTofu (branche principale, manuel)
8. Déploiement Helm — Préproduction (branche principale)
9. Déploiement Helm — Production (branche principale, manuel)

## Variables CI

Les variables sans valeur sont à déclarer dans la CI ; les autres sont déjà écrites dans les fichiers.

| Variable | Secret | Valeur | Rôle |
| --- | --- | --- | --- |
| `REGISTRY_USER` | oui | à déclarer | Compte de publication sur europe-west9-docker.pkg.dev |
| `REGISTRY_PASSWORD` | oui | à déclarer | Mot de passe ou jeton de publication sur europe-west9-docker.pkg.dev |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | non | à déclarer | Fournisseur Workload Identity Federation |
| `GCP_SERVICE_ACCOUNT` | non | à déclarer | Compte de service impersonné par la CI |
| `GCP_INFRA_SERVICE_ACCOUNT` | non | à déclarer | Compte de service des jobs d'infrastructure (plan, apply) |
| `RENOVATE_TOKEN` | oui | à déclarer | Jeton de la forge autorisé à ouvrir des merge requests (Renovate) |

## Diagnostics restants

- **Avertissement** (R34) — Google Cloud : « Identifiant du projet » non renseigné : la valeur d'exemple « mon-projet » sera écrite dans les fichiers.
- **Avertissement** (R34) — Google Kubernetes Engine : « Nom du cluster » non renseigné : la valeur d'exemple « mon-cluster » sera écrite dans les fichiers.
- **Avertissement** (R34) — Google Cloud Storage : « Bucket de l'état Terraform » non renseigné : la valeur d'exemple « mon-projet-tfstate » sera écrite dans les fichiers.

## Notes

- Mise en route pas à pas, avec les commandes du projet : docs/mise-en-route.md.
- Approbation (« Production ») : le job attend un déclenchement manuel dans GitLab ; protéger l'environnement (Settings › CI/CD › Protected environments) pour restreindre qui peut le lancer.
- Cloud Monitoring et Cloud Logging sont actifs par défaut sur GKE Autopilot : rien à installer.
- External Secrets : le ClusterSecretStore « mon-app » (platform/external-secrets/cluster-secret-store.yaml, appliqué par platform/install.sh) lit Google Secret Manager et chaque ExternalSecret recrée le Secret de base de données attendu par l'application ; la pile Terraform donne au contrôleur la lecture du coffre (identité de charge de travail).
- Google Secret Manager : la pile Terraform y écrit les secrets de connexion (Google Cloud SQL ; clé <espace de noms>-<brique>, JSON, lu par External Secrets) ; les valeurs passent par l'état, à garder dans un backend chiffré à accès restreint.
- Poste de développement : `docker compose -f dev/db/compose.yaml up -d` lance les bases du projet (même version), `dev/db/app.env` donne leurs variables de connexion.
- Renovate : job « renovate » de .gitlab-ci.yml, lancé par une planification de pipeline portant la variable RENOVATE=1 (docs/mise-en-route.md) ; les autres jobs ne tournent pas dans ces pipelines.
- `scripts/test-kind.sh` déploie le pipeline dans un cluster kind jetable (chart Helm) : utile avant la première mise en production.
- `scripts/ci-variables.sh` déclare les 6 variable(s) à renseigner avec GitLab (glab), sans écrire leurs valeurs dans le dépôt.

## Fichiers générés

- `.gitlab-ci.yml`
- `PIPELINE.md`
- `charts/mon-app/Chart.yaml`
- `charts/mon-app/templates/cloud-sql-secret.yaml`
- `charts/mon-app/templates/deployment.yaml`
- `charts/mon-app/templates/externalsecrets.yaml`
- `charts/mon-app/templates/service.yaml`
- `charts/mon-app/values-production.yaml`
- `charts/mon-app/values-staging.yaml`
- `charts/mon-app/values.yaml`
- `dev/db/app.env`
- `dev/db/compose.yaml`
- `dev/db/init/postgresql/README.md`
- `devops-builder.yaml`
- `docs/mise-en-route.md`
- `infra/terraform/.gitignore`
- `infra/terraform/main.tf`
- `infra/terraform/outputs.tf`
- `infra/terraform/variables.tf`
- `infra/terraform/versions.tf`
- `platform/external-secrets/cluster-secret-store.yaml`
- `platform/install.sh`
- `renovate.json`
- `scripts/ci-variables.sh`
- `scripts/test-kind.sh`
