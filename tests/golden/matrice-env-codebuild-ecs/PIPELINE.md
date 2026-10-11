# matrice — pipeline généré

Généré par DevOps Builder le AAAA-MM-JJ. Cible : Hôte Docker unique.

## Environnements

Ordre de promotion : la même image est déployée successivement dans chaque environnement.

| Environnement | Type | Approbation | Cluster | Espace de noms / projet |
| --- | --- | --- | --- | --- |
| Développement (`dev`) | Développement | non | — | `mon-app-dev` |
| Préproduction (`staging`) | Préproduction | non | — | `mon-app-staging` |
| Production (`production`) | Production | oui | — | `mon-app` |

## Ports

| Environnement | Composant | Port publié | Port du conteneur | Usage | Exposition |
| --- | --- | --- | --- | --- | --- |
| Développement | mon-app | — | 8000 | application | ECS Fargate : URL HTTPS gérée par le service |
| Préproduction | mon-app | — | 8000 | application | ECS Fargate : URL HTTPS gérée par le service |
| Production | mon-app | — | 8000 | application | ECS Fargate : URL HTTPS gérée par le service |

## Briques

| Étape | Brique | Licence | Fiche |
| --- | --- | --- | --- |
| Source | AWS CodeCommit | proprietary | vérifiée |
| Build | AWS CodeBuild | proprietary | vérifiée |
| Build | BuildKit (docker buildx) | Apache-2.0 | vérifiée |
| Artefacts | Amazon ECR | proprietary | vérifiée |
| Infrastructure | Amazon Web Services | proprietary | vérifiée |
| Déploiement | Amazon ECS (Fargate) | proprietary | vérifiée |

## Étapes CI

Orchestrateur : AWS CodeBuild. Image publiée : `$AWS_ACCOUNT_ID.dkr.ecr.eu-west-3.amazonaws.com/mon-app:<commit>`.

1. Build et publication de l'image (BuildKit (docker buildx))
2. Déploiement ECS — Développement (branche principale)
3. Déploiement ECS — Préproduction (branche principale)
4. Déploiement ECS — Production (branche principale, manuel)

## Variables CI

Les variables sans valeur sont à déclarer dans la CI ; les autres sont déjà écrites dans les fichiers.

| Variable | Secret | Valeur | Rôle |
| --- | --- | --- | --- |
| `AWS_ACCOUNT_ID` | non | à déclarer | Identifiant du compte AWS du registre ECR |
| `AWS_ROLE_ARN` | non | à déclarer | Rôle IAM assumé par la CI via OIDC |
| `AWS_REGION` | non | `eu-west-3` | Région AWS |

## Diagnostics restants

- **Avertissement** (R34) — Amazon ECS (Fargate) : « Cluster ECS » non renseigné : la valeur d'exemple « mon-cluster-ecs » sera écrite dans les fichiers.

## Notes

- Approbation (« Production ») : placer une action d'approbation manuelle CodePipeline avant le projet CodeBuild qui exécute buildspec-deploy-*.yml.

## Fichiers générés

- `PIPELINE.md`
- `buildspec-deploy-production.yml`
- `buildspec.yml`
- `devops-builder.yaml`
- `infra/terraform/.gitignore`
- `infra/terraform/main.tf`
- `infra/terraform/outputs.tf`
- `infra/terraform/variables.tf`
- `infra/terraform/versions.tf`
