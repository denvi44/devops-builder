# Mon projet — pipeline généré

Généré par DevOps Builder le AAAA-MM-JJ. Cible : Kubernetes managé (cloud).

## Environnements

Ordre de promotion : la même image est déployée successivement dans chaque environnement.

| Environnement | Type | Approbation | Cluster | Espace de noms / projet |
| --- | --- | --- | --- | --- |
| Développement (`dev`) | Développement | non | Scaleway Kapsule `mon-cluster` | `mon-app-dev` |
| Préproduction (`staging`) | Préproduction | non | Scaleway Kapsule `mon-cluster` | `mon-app-staging` |
| Production (`production`) | Production | oui | Scaleway Kapsule `mon-cluster` | `mon-app` |

## Ports

| Environnement | Composant | Port publié | Port du conteneur | Usage | Exposition |
| --- | --- | --- | --- | --- | --- |
| Développement | mon-app | — | 8000 | application | Service mon-app port 80, espace de noms mon-app-dev |
| Développement | SonarQube | — | 9000 | interface web | Service Kubernetes, espace de noms sonarqube |
| Développement | Argo CD | — | 8080 | API et interface (service 80/443) | Service Kubernetes, espace de noms argocd |
| Développement | Prometheus | — | 9090 | interface et API | Service Kubernetes, espace de noms monitoring |
| Développement | Grafana | — | 3000 | interface web | Service Kubernetes, espace de noms monitoring |
| Préproduction | mon-app | — | 8000 | application | Service mon-app port 80, espace de noms mon-app-staging |
| Préproduction | SonarQube | — | 9000 | interface web | Service Kubernetes, espace de noms sonarqube |
| Préproduction | Argo CD | — | 8080 | API et interface (service 80/443) | Service Kubernetes, espace de noms argocd |
| Préproduction | Prometheus | — | 9090 | interface et API | Service Kubernetes, espace de noms monitoring |
| Préproduction | Grafana | — | 3000 | interface web | Service Kubernetes, espace de noms monitoring |
| Production | mon-app | — | 8000 | application | Service mon-app port 80, espace de noms mon-app |
| Production | SonarQube | — | 9000 | interface web | Service Kubernetes, espace de noms sonarqube |
| Production | Argo CD | — | 8080 | API et interface (service 80/443) | Service Kubernetes, espace de noms argocd |
| Production | Prometheus | — | 9090 | interface et API | Service Kubernetes, espace de noms monitoring |
| Production | Grafana | — | 3000 | interface web | Service Kubernetes, espace de noms monitoring |

## Briques

| Étape | Brique | Licence | Fiche |
| --- | --- | --- | --- |
| Source | Azure Repos | proprietary | vérifiée |
| Build | Azure Pipelines | proprietary | vérifiée |
| Build | BuildKit (docker buildx) | Apache-2.0 | vérifiée |
| Build | Renovate | AGPL-3.0 | vérifiée |
| Tests & qualité | Tests unitaires | MIT | vérifiée |
| Tests & qualité | SonarQube | LGPL-3.0 | vérifiée |
| Artefacts | Scaleway Container Registry | proprietary | vérifiée |
| Infrastructure | Scaleway | proprietary | vérifiée |
| Infrastructure | Scaleway Kapsule | proprietary | vérifiée |
| Infrastructure | OpenTofu | MPL-2.0 | vérifiée |
| Infrastructure | Scaleway Object Storage | proprietary | vérifiée |
| Déploiement | Helm | Apache-2.0 | vérifiée |
| Déploiement | Argo CD | Apache-2.0 | vérifiée |
| Plateforme | cert-manager | Apache-2.0 | vérifiée |
| Observabilité | Prometheus | Apache-2.0 | vérifiée |
| Observabilité | Grafana | AGPL-3.0 | vérifiée |

## Étapes CI

Orchestrateur : Azure Pipelines. Image publiée : `rg.fr-par.scw.cloud/mon-app/mon-app:<commit>`.

1. Tests unitaires
2. Qualité SonarQube
3. Build et publication de l'image (BuildKit (docker buildx))
4. Plan OpenTofu
5. Application OpenTofu (branche principale, manuel)
6. Mise à jour GitOps (Argo CD) — Développement (branche principale)
7. Mise à jour GitOps (Argo CD) — Préproduction (branche principale)
8. Mise à jour GitOps (Argo CD) — Production (branche principale, manuel)

## Variables CI

Les variables sans valeur sont à déclarer dans la CI ; les autres sont déjà écrites dans les fichiers.

| Variable | Secret | Valeur | Rôle |
| --- | --- | --- | --- |
| `SONAR_HOST_URL` | non | à déclarer | URL du serveur SonarQube |
| `SONAR_TOKEN` | oui | à déclarer | Jeton d'analyse SonarQube |
| `SCW_SECRET_KEY` | oui | à déclarer | Clé secrète d'API Scaleway |
| `SCW_ACCESS_KEY` | oui | à déclarer | Clé d'accès API Scaleway |
| `SCW_DEFAULT_PROJECT_ID` | oui | à déclarer | Projet Scaleway |
| `GITOPS_TOKEN` | oui | à déclarer | Jeton autorisé à pousser sur le dépôt GitOps |
| `GITOPS_REPO` | non | à déclarer | Dépôt GitOps surveillé, sans schéma (hôte/groupe/depot.git) |
| `RENOVATE_TOKEN` | oui | à déclarer | Jeton de la forge autorisé à ouvrir des merge requests (Renovate) |

## Diagnostics restants

- **Avertissement** (R34) — Scaleway Kapsule : « Nom du cluster » non renseigné : la valeur d'exemple « mon-cluster » sera écrite dans les fichiers.
- **Avertissement** (R34) — Scaleway Object Storage : « Bucket de l'état Terraform » non renseigné : la valeur d'exemple « mon-projet-tfstate » sera écrite dans les fichiers.
- **Avertissement** (R34) — Argo CD : « Dépôt GitOps » non renseigné : la valeur d'exemple « https://git.example.com/groupe/gitops.git » sera écrite dans les fichiers.

## Notes

- Mise en route pas à pas, avec les commandes du projet : docs/mise-en-route.md.
- Approbation (« Production ») : ajouter une vérification « Approvals » sur l'environnement Azure DevOps correspondant (Pipelines › Environments › Approvals and checks).
- Renovate : lancer l'image renovate/renovate dans un job planifié (quotidien) avec RENOVATE_TOKEN ; renovate.json règle son comportement.
- `scripts/test-kind.sh` déploie le pipeline dans un cluster kind jetable (chart Helm) : utile avant la première mise en production.
- `scripts/ci-variables.sh` déclare les 8 variable(s) à renseigner avec Azure Pipelines (az), sans écrire leurs valeurs dans le dépôt.

## Fichiers générés

- `PIPELINE.md`
- `azure-pipelines.yml`
- `charts/mon-app/Chart.yaml`
- `charts/mon-app/templates/deployment.yaml`
- `charts/mon-app/templates/service.yaml`
- `charts/mon-app/values-dev.yaml`
- `charts/mon-app/values-production.yaml`
- `charts/mon-app/values-staging.yaml`
- `charts/mon-app/values.yaml`
- `deploy/argocd/application.yaml`
- `devops-builder.yaml`
- `docs/mise-en-route.md`
- `infra/terraform/.gitignore`
- `infra/terraform/main.tf`
- `infra/terraform/outputs.tf`
- `infra/terraform/variables.tf`
- `infra/terraform/versions.tf`
- `platform/install.sh`
- `renovate.json`
- `scripts/ci-variables.sh`
- `scripts/test-kind.sh`
