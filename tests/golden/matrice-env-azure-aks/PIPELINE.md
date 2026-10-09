# matrice — pipeline généré

Généré par DevOps Builder le AAAA-MM-JJ. Cible : Kubernetes managé (cloud).

## Environnements

Ordre de promotion : la même image est déployée successivement dans chaque environnement.

| Environnement | Type | Approbation | Cluster | Espace de noms / projet |
| --- | --- | --- | --- | --- |
| Développement (`dev`) | Développement | non | Azure Kubernetes Service `mon-cluster` | `mon-app-dev` |
| Préproduction (`staging`) | Préproduction | non | Azure Kubernetes Service `mon-cluster` | `mon-app-staging` |
| Production (`production`) | Production | oui | Azure Kubernetes Service `mon-cluster` | `mon-app` |

## Briques

| Étape | Brique | Licence | Fiche |
| --- | --- | --- | --- |
| Source | Azure Repos | proprietary | vérifiée |
| Build | Azure Pipelines | proprietary | vérifiée |
| Build | BuildKit (docker buildx) | Apache-2.0 | vérifiée |
| Artefacts | Azure Container Registry | proprietary | vérifiée |
| Infrastructure | Microsoft Azure | proprietary | vérifiée |
| Infrastructure | Azure Kubernetes Service | proprietary | vérifiée |
| Infrastructure | OpenTofu | MPL-2.0 | vérifiée |
| Infrastructure | Azure Blob Storage | proprietary | vérifiée |
| Déploiement | Helm | Apache-2.0 | vérifiée |

## Étapes CI

Orchestrateur : Azure Pipelines. Image publiée : `monappregistry.azurecr.io/mon-app:<commit>`.

1. Build et publication de l'image (BuildKit (docker buildx))
2. Plan OpenTofu
3. Application OpenTofu (branche principale, manuel)
4. Déploiement Helm — Développement (branche principale)
5. Déploiement Helm — Préproduction (branche principale)
6. Déploiement Helm — Production (branche principale, manuel)

## Variables CI

Les variables sans valeur sont à déclarer dans la CI ; les autres sont déjà écrites dans les fichiers.

| Variable | Secret | Valeur | Rôle |
| --- | --- | --- | --- |
| `REGISTRY_USER` | oui | à déclarer | Compte de publication sur monappregistry.azurecr.io |
| `REGISTRY_PASSWORD` | oui | à déclarer | Mot de passe ou jeton de publication sur monappregistry.azurecr.io |
| `AZURE_CLIENT_ID` | non | à déclarer | Identifiant d'application Entra ID |
| `AZURE_TENANT_ID` | non | à déclarer | Identifiant du tenant Entra ID |
| `AZURE_SUBSCRIPTION_ID` | non | à déclarer | Identifiant d'abonnement Azure |

## Diagnostics restants

- **Avertissement** (R34) — Azure Container Registry : « Nom du registre ACR » non renseigné : la valeur d'exemple « monappregistry » sera écrite dans les fichiers.
- **Avertissement** (R34) — Azure Kubernetes Service : « Nom du cluster » non renseigné : la valeur d'exemple « mon-cluster » sera écrite dans les fichiers.
- **Avertissement** (R34) — Azure Blob Storage : « Compte de stockage » non renseigné : la valeur d'exemple « monprojettfstate » sera écrite dans les fichiers.

## Notes

- Approbation (« Production ») : ajouter une vérification « Approvals » sur l'environnement Azure DevOps correspondant (Pipelines › Environments › Approvals and checks).
- `scripts/test-kind.sh` déploie le pipeline dans un cluster kind jetable (chart Helm) : utile avant la première mise en production.
- `scripts/ci-variables.sh` déclare les 5 variable(s) à renseigner avec Azure Pipelines (az), sans écrire leurs valeurs dans le dépôt.

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
- `devops-builder.yaml`
- `infra/terraform/main.tf`
- `infra/terraform/variables.tf`
- `infra/terraform/versions.tf`
- `scripts/ci-variables.sh`
- `scripts/test-kind.sh`
