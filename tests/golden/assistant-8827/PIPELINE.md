# Mon projet — pipeline généré

Généré par DevOps Builder le AAAA-MM-JJ. Cible : Kubernetes managé (cloud) ; exigence SecNumCloud.

## Environnements

Ordre de promotion : la même image est déployée successivement dans chaque environnement.

| Environnement | Type | Approbation | Cluster | Espace de noms / projet |
| --- | --- | --- | --- | --- |
| Développement (`dev`) | Développement | non | Outscale Kubernetes as a Service (OKS) `mon-cluster` | `mon-app-dev` |
| Préproduction (`staging`) | Préproduction | non | Outscale Kubernetes as a Service (OKS) `mon-cluster` | `mon-app-staging` |
| Production (`production`) | Production | oui | Outscale Kubernetes as a Service (OKS) `mon-cluster` | `mon-app` |

## Ports

| Environnement | Composant | Port publié | Port du conteneur | Usage | Exposition |
| --- | --- | --- | --- | --- | --- |
| Développement | mon-app | — | 8000 | application | Service mon-app port 80, espace de noms mon-app-dev |
| Développement | SonarQube | — | 9000 | interface web | Service Kubernetes, espace de noms sonarqube |
| Développement | Harbor | — | 80 | HTTP | Service Kubernetes, espace de noms harbor |
| Développement | Harbor | — | 443 | HTTPS (portail et registre) | Service Kubernetes, espace de noms harbor |
| Développement | Argo CD | — | 8080 | API et interface (service 80/443) | Service Kubernetes, espace de noms argocd |
| Développement | Prometheus | — | 9090 | interface et API | Service Kubernetes, espace de noms monitoring |
| Développement | Grafana | — | 3000 | interface web | Service Kubernetes, espace de noms monitoring |
| Préproduction | mon-app | — | 8000 | application | Service mon-app port 80, espace de noms mon-app-staging |
| Préproduction | SonarQube | — | 9000 | interface web | Service Kubernetes, espace de noms sonarqube |
| Préproduction | Harbor | — | 80 | HTTP | Service Kubernetes, espace de noms harbor |
| Préproduction | Harbor | — | 443 | HTTPS (portail et registre) | Service Kubernetes, espace de noms harbor |
| Préproduction | Argo CD | — | 8080 | API et interface (service 80/443) | Service Kubernetes, espace de noms argocd |
| Préproduction | Prometheus | — | 9090 | interface et API | Service Kubernetes, espace de noms monitoring |
| Préproduction | Grafana | — | 3000 | interface web | Service Kubernetes, espace de noms monitoring |
| Production | mon-app | — | 8000 | application | Service mon-app port 80, espace de noms mon-app |
| Production | SonarQube | — | 9000 | interface web | Service Kubernetes, espace de noms sonarqube |
| Production | Harbor | — | 80 | HTTP | Service Kubernetes, espace de noms harbor |
| Production | Harbor | — | 443 | HTTPS (portail et registre) | Service Kubernetes, espace de noms harbor |
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
| Sécurité | Gitleaks | MIT | vérifiée |
| Sécurité | Trivy | Apache-2.0 | vérifiée |
| Sécurité | Cosign | Apache-2.0 | vérifiée |
| Artefacts | Harbor | Apache-2.0 | vérifiée |
| Infrastructure | Outscale | proprietary | vérifiée |
| Infrastructure | Outscale Kubernetes as a Service (OKS) | proprietary | vérifiée |
| Infrastructure | Terraform | BSL-1.1 | vérifiée |
| Déploiement | Helm | Apache-2.0 | vérifiée |
| Déploiement | Argo CD | Apache-2.0 | vérifiée |
| Plateforme | cert-manager | Apache-2.0 | vérifiée |
| Observabilité | Prometheus | Apache-2.0 | vérifiée |
| Observabilité | Grafana | AGPL-3.0 | vérifiée |

## Étapes CI

Orchestrateur : Azure Pipelines. Image publiée : `registry.example.com/mon-app/mon-app:<commit>`.

1. Tests unitaires
2. Qualité SonarQube
3. Recherche de secrets
4. Build et publication de l'image (BuildKit (docker buildx))
5. Scan de vulnérabilités Trivy
6. Signature de l'image (Cosign) (branche principale)
7. Plan Terraform
8. Application Terraform (branche principale, manuel)
9. Mise à jour GitOps (Argo CD) — Développement (branche principale)
10. Mise à jour GitOps (Argo CD) — Préproduction (branche principale)
11. Mise à jour GitOps (Argo CD) — Production (branche principale, manuel)

## Variables CI

Les variables sans valeur sont à déclarer dans la CI ; les autres sont déjà écrites dans les fichiers.

| Variable | Secret | Valeur | Rôle |
| --- | --- | --- | --- |
| `SONAR_HOST_URL` | non | à déclarer | URL du serveur SonarQube |
| `SONAR_TOKEN` | oui | à déclarer | Jeton d'analyse SonarQube |
| `REGISTRY_USER` | oui | à déclarer | Compte de publication sur registry.example.com |
| `REGISTRY_PASSWORD` | oui | à déclarer | Mot de passe ou jeton de publication sur registry.example.com |
| `OSC_ACCESS_KEY` | oui | à déclarer | Clé d'accès Outscale |
| `OSC_SECRET_KEY` | oui | à déclarer | Clé secrète Outscale |
| `GITOPS_TOKEN` | oui | à déclarer | Jeton autorisé à pousser sur le dépôt GitOps |
| `GITOPS_REPO` | non | à déclarer | Dépôt GitOps surveillé, sans schéma (hôte/groupe/depot.git) |
| `RENOVATE_TOKEN` | oui | à déclarer | Jeton de la forge autorisé à ouvrir des merge requests (Renovate) |

## Diagnostics restants

- **Avertissement** (R34) — Harbor : « Adresse du registre » non renseigné : la valeur d'exemple « registry.example.com » sera écrite dans les fichiers.
- **Avertissement** (R34) — Outscale Kubernetes as a Service (OKS) : « Nom du cluster » non renseigné : la valeur d'exemple « mon-cluster » sera écrite dans les fichiers.
- **Info** (R23) — Harbor embarque déjà Trivy comme scanner ; l'étape Trivy en CI reste utile pour bloquer avant la publication.
- **Info** (R24) — Terraform est sous licence BSL-1.1.
- **Info** (R31) — Aucun fichier n'est généré pour Outscale Kubernetes as a Service (OKS) dans cette configuration : à configurer à la main (listé dans PIPELINE.md).

## Notes

- Approbation (« Production ») : ajouter une vérification « Approvals » sur l'environnement Azure DevOps correspondant (Pipelines › Environments › Approvals and checks).
- Renovate : lancer l'image renovate/renovate dans un job planifié (quotidien) avec RENOVATE_TOKEN ; renovate.json règle son comportement.
- `scripts/test-kind.sh` déploie le pipeline dans un cluster kind jetable (chart Helm) : utile avant la première mise en production.
- `scripts/ci-variables.sh` déclare les 9 variable(s) à renseigner avec Azure Pipelines (az), sans écrire leurs valeurs dans le dépôt.

## À configurer à la main

Ces briques sont dans le pipeline mais aucun générateur ne les prend en charge :

- Outscale Kubernetes as a Service (OKS)

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
- `infra/terraform/main.tf`
- `infra/terraform/variables.tf`
- `infra/terraform/versions.tf`
- `platform/install.sh`
- `renovate.json`
- `scripts/ci-variables.sh`
- `scripts/test-kind.sh`
