# Modèle AWS ECS — pipeline généré

Généré par DevOps Builder le AAAA-MM-JJ. Cible : Hôte Docker unique.

## Environnements

Ordre de promotion : la même image est déployée successivement dans chaque environnement.

| Environnement | Type | Approbation | Cluster | Espace de noms / projet |
| --- | --- | --- | --- | --- |
| Préproduction (`staging`) | Préproduction | non | — | `mon-app-staging` |
| Production (`production`) | Production | oui | — | `mon-app` |

## Ports

| Environnement | Composant | Port publié | Port du conteneur | Usage | Exposition |
| --- | --- | --- | --- | --- | --- |
| Préproduction | mon-app | — | 8000 | application | ECS Fargate : URL HTTPS gérée par le service |
| Préproduction | Amazon RDS | — | 5432 | PostgreSQL | service managé, une instance par environnement |
| Production | mon-app | — | 8000 | application | ECS Fargate : URL HTTPS gérée par le service |
| Production | Amazon RDS | — | 5432 | PostgreSQL | service managé, une instance par environnement |

## Données

L'application lit l'URL de connexion complète dans la variable indiquée ; le mot de passe ne figure dans aucun fichier du dépôt.

| Base | Mode | Où | Variable de l'application | Mot de passe / URL | Sauvegarde |
| --- | --- | --- | --- | --- | --- |
| Amazon RDS | service managé | Amazon RDS, une instance par environnement (Terraform) | `DATABASE_URL` | AWS Secrets Manager, clé `<espace de noms>/aws-rds` (écrit par Terraform) | service du fournisseur (rétention configurée) |

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
| Artefacts | Amazon ECR | proprietary | vérifiée |
| Infrastructure | Amazon Web Services | proprietary | vérifiée |
| Infrastructure | OpenTofu | MPL-2.0 | vérifiée |
| Infrastructure | Amazon S3 | proprietary | vérifiée |
| Données | Amazon RDS | proprietary | vérifiée |
| Déploiement | Amazon ECS (Fargate) | proprietary | vérifiée |
| Plateforme | AWS Secrets Manager | proprietary | vérifiée |

## Étapes CI

Orchestrateur : GitHub Actions. Image publiée : `$AWS_ACCOUNT_ID.dkr.ecr.eu-west-3.amazonaws.com/mon-app:<commit>`.

1. Tests unitaires
2. Recherche de secrets
3. Build et publication de l'image (BuildKit (docker buildx))
4. Scan de vulnérabilités Trivy
5. Signature de l'image (Cosign) (branche principale)
6. Plan OpenTofu
7. Application OpenTofu (branche principale, manuel)
8. Déploiement ECS — Préproduction (branche principale)
9. Déploiement ECS — Production (branche principale, manuel)

## Variables CI

Les variables sans valeur sont à déclarer dans la CI ; les autres sont déjà écrites dans les fichiers.

| Variable | Secret | Valeur | Rôle |
| --- | --- | --- | --- |
| `AWS_ACCOUNT_ID` | non | à déclarer | Identifiant du compte AWS du registre ECR |
| `TF_VAR_db_subnet_group` | non | à déclarer | Groupe de sous-réseaux privés des instances RDS (variable Terraform db_subnet_group, ex. "rds-prive") |
| `TF_VAR_db_security_group_ids` | non | à déclarer | Groupes de sécurité autorisant l'application à joindre la base (variable Terraform db_security_group_ids, ex. ["sg-0123456789abcdef0"]) |
| `AWS_ROLE_ARN` | non | à déclarer | Rôle IAM assumé par la CI via OIDC |
| `AWS_REGION` | non | `eu-west-3` | Région AWS |
| `AWS_INFRA_ROLE_ARN` | non | à déclarer | Rôle IAM des jobs d'infrastructure (plan, apply), assumé via OIDC |

## Diagnostics restants

- **Avertissement** (R34) — Amazon S3 : « Bucket de l'état Terraform » non renseigné : la valeur d'exemple « mon-projet-tfstate » sera écrite dans les fichiers.
- **Avertissement** (R34) — Amazon ECS (Fargate) : « Cluster ECS » non renseigné : la valeur d'exemple « mon-cluster-ecs » sera écrite dans les fichiers.

## Notes

- Mise en route pas à pas, avec les commandes du projet : docs/mise-en-route.md.
- Approbation (« Production ») : déclarer des relecteurs obligatoires sur l'environnement du dépôt (Settings › Environments › Required reviewers), sinon le déploiement part sans attendre.
- AWS Secrets Manager : la pile Terraform y écrit les secrets de connexion (Amazon RDS ; clé <espace de noms>/<brique>, l'URL de connexion seule, à monter dans le service) ; les valeurs passent par l'état, à garder dans un backend chiffré à accès restreint. L'URL d'Amazon RDS reprend le mot de passe principal géré par RDS : après une rotation, relancer `apply` pour la réécrire.
- Poste de développement : `docker compose -f dev/db/compose.yaml up -d` lance les bases du projet (même version), `dev/db/app.env` donne leurs variables de connexion.
- Connexion de l'application à la base sur un service serverless — ECS : bloc `secrets` de la définition de tâche (Secrets Manager ou Parameter Store).
- `scripts/ci-variables.sh` déclare les 5 variable(s) à renseigner avec GitHub (gh), sans écrire leurs valeurs dans le dépôt.

## Fichiers générés

- `.github/dependabot.yml`
- `.github/workflows/pipeline.yml`
- `PIPELINE.md`
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
