# Mon projet — pipeline généré

Généré par DevOps Builder le AAAA-MM-JJ. Cible : Kubernetes managé (cloud) ; exigence SecNumCloud.

## Environnements

Ordre de promotion : la même image est déployée successivement dans chaque environnement.

| Environnement | Type | Approbation | Cluster | Espace de noms / projet |
| --- | --- | --- | --- | --- |
| Développement (`dev`) | Développement | non | OVHcloud Managed Kubernetes `mon-cluster` | `mon-app-dev` |
| Préproduction (`staging`) | Préproduction | non | OVHcloud Managed Kubernetes `mon-cluster` | `mon-app-staging` |
| Production (`production`) | Production | oui | OVHcloud Managed Kubernetes `mon-cluster` | `mon-app` |

## Ports

| Environnement | Composant | Port publié | Port du conteneur | Usage | Exposition |
| --- | --- | --- | --- | --- | --- |
| Développement | mon-app | — | 8000 | application | Service mon-app port 80, espace de noms mon-app-dev |
| Développement | SonarQube | — | 9000 | interface web | Service Kubernetes, espace de noms sonarqube |
| Préproduction | mon-app | — | 8000 | application | Service mon-app port 80, espace de noms mon-app-staging |
| Préproduction | SonarQube | — | 9000 | interface web | Service Kubernetes, espace de noms sonarqube |
| Production | mon-app | — | 8000 | application | Service mon-app port 80, espace de noms mon-app |
| Production | SonarQube | — | 9000 | interface web | Service Kubernetes, espace de noms sonarqube |

## Briques

| Étape | Brique | Licence | Fiche |
| --- | --- | --- | --- |
| Source | GitHub | proprietary | vérifiée |
| Build | GitHub Actions | proprietary | vérifiée |
| Build | BuildKit (docker buildx) | Apache-2.0 | vérifiée |
| Build | Dependabot | proprietary | vérifiée |
| Tests & qualité | Tests unitaires | MIT | vérifiée |
| Tests & qualité | SonarQube | LGPL-3.0 | vérifiée |
| Sécurité | Gitleaks | MIT | vérifiée |
| Sécurité | Trivy | Apache-2.0 | vérifiée |
| Sécurité | Cosign | Apache-2.0 | vérifiée |
| Artefacts | OVHcloud Managed Private Registry | proprietary | vérifiée |
| Infrastructure | OVHcloud | proprietary | vérifiée |
| Infrastructure | OVHcloud Managed Kubernetes | proprietary | vérifiée |
| Déploiement | Helm | Apache-2.0 | vérifiée |
| Plateforme | cert-manager | Apache-2.0 | vérifiée |

## Étapes CI

Orchestrateur : GitHub Actions. Image publiée : `registry.example.com/mon-app/mon-app:<commit>`.

1. Tests unitaires
2. Qualité SonarQube
3. Recherche de secrets
4. Build et publication de l'image (BuildKit (docker buildx))
5. Scan de vulnérabilités Trivy
6. Signature de l'image (Cosign) (branche principale)
7. Déploiement Helm — Développement (branche principale)
8. Déploiement Helm — Préproduction (branche principale)
9. Déploiement Helm — Production (branche principale, manuel)

## Variables CI

Les variables sans valeur sont à déclarer dans la CI ; les autres sont déjà écrites dans les fichiers.

| Variable | Secret | Valeur | Rôle |
| --- | --- | --- | --- |
| `SONAR_HOST_URL` | non | à déclarer | URL du serveur SonarQube |
| `SONAR_TOKEN` | oui | à déclarer | Jeton d'analyse SonarQube |
| `REGISTRY_USER` | oui | à déclarer | Compte de publication sur registry.example.com |
| `REGISTRY_PASSWORD` | oui | à déclarer | Mot de passe ou jeton de publication sur registry.example.com |
| `KUBECONFIG_DATA_DEV` | oui | à déclarer | Contenu du kubeconfig de OVHcloud Managed Kubernetes (Développement) (base64) |
| `KUBECONFIG_DATA_STAGING` | oui | à déclarer | Contenu du kubeconfig de OVHcloud Managed Kubernetes (Préproduction) (base64) |
| `KUBECONFIG_DATA_PRODUCTION` | oui | à déclarer | Contenu du kubeconfig de OVHcloud Managed Kubernetes (Production) (base64) |

## Diagnostics restants

- **Avertissement** (R34) — OVHcloud : « Projet Public Cloud » non renseigné : la valeur d'exemple « <id-projet-public-cloud> » sera écrite dans les fichiers.
- **Avertissement** (R34) — OVHcloud Managed Kubernetes : « Nom du cluster » non renseigné : la valeur d'exemple « mon-cluster » sera écrite dans les fichiers.

## Notes

- Approbation (« Production ») : déclarer des relecteurs obligatoires sur l'environnement du dépôt (Settings › Environments › Required reviewers), sinon le déploiement part sans attendre.
- `scripts/test-kind.sh` déploie le pipeline dans un cluster kind jetable (chart Helm) : utile avant la première mise en production.
- `scripts/ci-variables.sh` déclare les 7 variable(s) à renseigner avec GitHub (gh), sans écrire leurs valeurs dans le dépôt.

## Fichiers générés

- `.github/dependabot.yml`
- `.github/workflows/pipeline.yml`
- `PIPELINE.md`
- `charts/mon-app/Chart.yaml`
- `charts/mon-app/templates/deployment.yaml`
- `charts/mon-app/templates/service.yaml`
- `charts/mon-app/values-dev.yaml`
- `charts/mon-app/values-production.yaml`
- `charts/mon-app/values-staging.yaml`
- `charts/mon-app/values.yaml`
- `devops-builder.yaml`
- `infra/terraform/.gitignore`
- `infra/terraform/main.tf`
- `infra/terraform/outputs.tf`
- `infra/terraform/variables.tf`
- `infra/terraform/versions.tf`
- `platform/install.sh`
- `scripts/ci-variables.sh`
- `scripts/test-kind.sh`
