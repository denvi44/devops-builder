# Mon projet — pipeline généré

Généré par DevOps Builder le AAAA-MM-JJ. Cible : Kubernetes managé (cloud).

## Environnements

Ordre de promotion : la même image est déployée successivement dans chaque environnement.

| Environnement | Type | Approbation | Cluster | Espace de noms / projet |
| --- | --- | --- | --- | --- |
| Préproduction (`staging`) | Préproduction | non | Amazon EKS `mon-cluster` | `mon-app-staging` |
| Production (`production`) | Production | oui | Amazon EKS `mon-cluster` | `mon-app` |

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
| Artefacts | Amazon ECR | proprietary | vérifiée |
| Infrastructure | Amazon Web Services | proprietary | vérifiée |
| Infrastructure | Amazon EKS | proprietary | vérifiée |
| Déploiement | Helm | Apache-2.0 | vérifiée |
| Déploiement | Argo CD | Apache-2.0 | vérifiée |
| Plateforme | cert-manager | Apache-2.0 | vérifiée |

## Étapes CI

Orchestrateur : GitHub Actions. Image publiée : `$AWS_ACCOUNT_ID.dkr.ecr.eu-west-3.amazonaws.com/mon-app:<commit>`.

1. Tests unitaires
2. Qualité SonarQube
3. Recherche de secrets
4. Build et publication de l'image (BuildKit (docker buildx))
5. Scan de vulnérabilités Trivy
6. Signature de l'image (Cosign) (branche principale)
7. Mise à jour GitOps (Argo CD) — Préproduction (branche principale)
8. Mise à jour GitOps (Argo CD) — Production (branche principale, manuel)

## Variables CI

Les variables sans valeur sont à déclarer dans la CI ; les autres sont déjà écrites dans les fichiers.

| Variable | Secret | Valeur | Rôle |
| --- | --- | --- | --- |
| `SONAR_HOST_URL` | non | à déclarer | URL du serveur SonarQube |
| `SONAR_TOKEN` | oui | à déclarer | Jeton d'analyse SonarQube |
| `AWS_ACCOUNT_ID` | non | à déclarer | Identifiant du compte AWS du registre ECR |
| `GITOPS_TOKEN` | oui | à déclarer | Jeton autorisé à pousser sur le dépôt GitOps |
| `GITOPS_REPO` | non | à déclarer | Dépôt GitOps surveillé, sans schéma (hôte/groupe/depot.git) |
| `AWS_ROLE_ARN` | non | à déclarer | Rôle IAM assumé par la CI via OIDC |
| `AWS_REGION` | non | `eu-west-3` | Région AWS |

## Diagnostics restants

- **Avertissement** (R34) — Amazon EKS : « Nom du cluster » non renseigné : la valeur d'exemple « mon-cluster » sera écrite dans les fichiers.

## Notes

- Approbation (« Production ») : déclarer des relecteurs obligatoires sur l'environnement du dépôt (Settings › Environments › Required reviewers), sinon le déploiement part sans attendre.
- `scripts/test-kind.sh` déploie le pipeline dans un cluster kind jetable (chart Helm) : utile avant la première mise en production.
- `scripts/ci-variables.sh` déclare les 6 variable(s) à renseigner avec GitHub (gh), sans écrire leurs valeurs dans le dépôt.

## Fichiers générés

- `.github/dependabot.yml`
- `.github/workflows/pipeline.yml`
- `PIPELINE.md`
- `charts/mon-app/Chart.yaml`
- `charts/mon-app/templates/deployment.yaml`
- `charts/mon-app/templates/service.yaml`
- `charts/mon-app/values-production.yaml`
- `charts/mon-app/values-staging.yaml`
- `charts/mon-app/values.yaml`
- `deploy/argocd/application.yaml`
- `devops-builder.yaml`
- `infra/terraform/main.tf`
- `infra/terraform/variables.tf`
- `infra/terraform/versions.tf`
- `platform/install.sh`
- `scripts/ci-variables.sh`
- `scripts/test-kind.sh`
