# IaC AWS et Floci — pipeline généré

Généré par DevOps Builder le AAAA-MM-JJ. Cible : Kubernetes managé (cloud).

## Environnements

Ordre de promotion : la même image est déployée successivement dans chaque environnement.

| Environnement | Type | Approbation | Cluster | Espace de noms / projet |
| --- | --- | --- | --- | --- |
| Préproduction (`staging`) | Préproduction | non | Amazon EKS `boutique` | `boutique-staging` |
| Production (`production`) | Production | oui | Amazon EKS `boutique` | `boutique` |

## Ports

| Environnement | Composant | Port publié | Port du conteneur | Usage | Exposition |
| --- | --- | --- | --- | --- | --- |
| Préproduction | boutique | — | 8000 | application | Service boutique port 80, espace de noms boutique-staging |
| Préproduction | Amazon RDS | — | 5432 | PostgreSQL | service managé, une instance par environnement |
| Production | boutique | — | 8000 | application | Service boutique port 80, espace de noms boutique |
| Production | Amazon RDS | — | 5432 | PostgreSQL | service managé, une instance par environnement |

## Données

L'application lit l'URL de connexion complète dans la variable indiquée ; le mot de passe ne figure dans aucun fichier du dépôt.

| Base | Mode | Où | Variable de l'application | Mot de passe / URL | Sauvegarde |
| --- | --- | --- | --- | --- | --- |
| Amazon RDS | service managé | Amazon RDS, une instance par environnement (Terraform) | `DATABASE_URL` | variable CI `DATABASE_URL_<ENV>` | service du fournisseur (rétention configurée) |

## Briques

| Étape | Brique | Licence | Fiche |
| --- | --- | --- | --- |
| Source | GitHub | proprietary | vérifiée |
| Build | GitHub Actions | proprietary | vérifiée |
| Build | BuildKit (docker buildx) | Apache-2.0 | vérifiée |
| Tests & qualité | Tests unitaires | MIT | vérifiée |
| Tests & qualité | TFLint | MPL-2.0 | vérifiée |
| Tests & qualité | Infracost | Apache-2.0 | vérifiée |
| Tests & qualité | Floci | MIT | vérifiée |
| Artefacts | Amazon ECR | proprietary | vérifiée |
| Infrastructure | Amazon Web Services | proprietary | vérifiée |
| Infrastructure | Amazon EKS | proprietary | vérifiée |
| Infrastructure | OpenTofu | MPL-2.0 | vérifiée |
| Infrastructure | Amazon S3 | proprietary | vérifiée |
| Données | Amazon RDS | proprietary | vérifiée |
| Déploiement | Helm | Apache-2.0 | vérifiée |

## Étapes CI

Orchestrateur : GitHub Actions. Image publiée : `$AWS_ACCOUNT_ID.dkr.ecr.eu-west-3.amazonaws.com/boutique:<commit>`.

1. Tests unitaires
2. Build et publication de l'image (BuildKit (docker buildx))
3. Analyse TFLint
4. Estimation des coûts Infracost (non bloquant)
5. Plan OpenTofu
6. Application OpenTofu (branche principale, manuel)
7. Plan de l'IaC sur Floci (émulateur AWS) (non bloquant)
8. Déploiement Helm — Préproduction (branche principale)
9. Déploiement Helm — Production (branche principale, manuel)

## Variables CI

Les variables sans valeur sont à déclarer dans la CI ; les autres sont déjà écrites dans les fichiers.

| Variable | Secret | Valeur | Rôle |
| --- | --- | --- | --- |
| `AWS_ACCOUNT_ID` | non | à déclarer | Identifiant du compte AWS du registre ECR |
| `INFRACOST_API_KEY` | oui | à déclarer | Clé d'API Infracost (gratuite, infracost auth login) |
| `TF_VAR_vpc_id` | non | à déclarer | VPC du cluster EKS (variable Terraform vpc_id, ex. "vpc-0123456789abcdef0") |
| `TF_VAR_subnet_ids` | non | à déclarer | Sous-réseaux privés du cluster (variable Terraform subnet_ids, ex. ["subnet-0123456789abcdef0", "subnet-0fedcba9876543210"]) |
| `TF_VAR_db_subnet_group` | non | à déclarer | Groupe de sous-réseaux privés des instances RDS (variable Terraform db_subnet_group, ex. "rds-prive") |
| `TF_VAR_db_security_group_ids` | non | à déclarer | Groupes de sécurité autorisant l'application à joindre la base (variable Terraform db_security_group_ids, ex. ["sg-0123456789abcdef0"]) |
| `DATABASE_URL_STAGING` | oui | à déclarer | URL de connexion à Amazon RDS (Préproduction), lue par l'application dans DATABASE_URL ; à composer après création de l'instance (sorties Terraform) |
| `DATABASE_URL_PRODUCTION` | oui | à déclarer | URL de connexion à Amazon RDS (Production), lue par l'application dans DATABASE_URL ; à composer après création de l'instance (sorties Terraform) |
| `AWS_ROLE_ARN` | non | à déclarer | Rôle IAM assumé par la CI via OIDC |
| `AWS_REGION` | non | `eu-west-3` | Région AWS |

## Diagnostics restants

Aucun.

## Notes

- Approbation (« Production ») : déclarer des relecteurs obligatoires sur l'environnement du dépôt (Settings › Environments › Required reviewers), sinon le déploiement part sans attendre.
- Floci : `docker compose -f dev/floci/compose.yaml up -d` lance l'émulateur AWS sur le port 4566 ; `dev/floci/aws.env` y pointe les SDK et la CLI (identifiants factices test/test).
- Floci tourne à côté des tests unitaires dans la CI : AWS_ENDPOINT_URL désigne l'émulateur.
- `scripts/tf-floci.sh plan` joue la pile sur Floci, sans compte AWS (job CI non bloquant) ; `apply` crée puis détruit les ressources en local. Les services à conteneurs (EKS, RDS, Lambda) demandent le socket Docker, monté seulement par le script lancé en local.
- Bases managées : une instance par environnement ; après `apply`, composer l'URL de connexion à partir des sorties Terraform (outputs.tf) et la déclarer en variable CI.
- `scripts/test-kind.sh` déploie le pipeline dans un cluster kind jetable (chart Helm) : utile avant la première mise en production.
- `scripts/ci-variables.sh` déclare les 9 variable(s) à renseigner avec GitHub (gh), sans écrire leurs valeurs dans le dépôt.

## Fichiers générés

- `.github/workflows/pipeline.yml`
- `PIPELINE.md`
- `charts/boutique/Chart.yaml`
- `charts/boutique/templates/aws-rds-secret.yaml`
- `charts/boutique/templates/deployment.yaml`
- `charts/boutique/templates/service.yaml`
- `charts/boutique/values-production.yaml`
- `charts/boutique/values-staging.yaml`
- `charts/boutique/values.yaml`
- `dev/floci/aws.env`
- `dev/floci/compose.yaml`
- `devops-builder.yaml`
- `infra/terraform/.gitignore`
- `infra/terraform/.tflint.hcl`
- `infra/terraform/main.tf`
- `infra/terraform/outputs.tf`
- `infra/terraform/terraform.tfvars.example`
- `infra/terraform/variables.tf`
- `infra/terraform/versions.tf`
- `scripts/ci-variables.sh`
- `scripts/test-kind.sh`
- `scripts/tf-floci.sh`
