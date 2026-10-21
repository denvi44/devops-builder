# Mon projet — pipeline généré

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
| Préproduction | mon-app | — | 8000 | application | Azure Container Apps : URL HTTPS gérée par le service |
| Production | mon-app | — | 8000 | application | Azure Container Apps : URL HTTPS gérée par le service |

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
| Artefacts | Azure Container Registry | proprietary | vérifiée |
| Infrastructure | Microsoft Azure | proprietary | vérifiée |
| Infrastructure | OpenTofu | MPL-2.0 | vérifiée |
| Infrastructure | Azure Blob Storage | proprietary | vérifiée |
| Déploiement | Azure Container Apps | proprietary | vérifiée |
| Déploiement | Azure Functions | proprietary | vérifiée |

## Étapes CI

Orchestrateur : GitLab CI. Image publiée : `monappregistry.azurecr.io/mon-app:<commit>`.

1. Tests unitaires
2. Recherche de secrets
3. Build et publication de l'image (BuildKit (docker buildx))
4. Scan de vulnérabilités Trivy
5. Signature de l'image (Cosign) (branche principale)
6. Plan OpenTofu
7. Application OpenTofu (branche principale, manuel)
8. Déploiement Azure Container Apps — Préproduction (branche principale)
9. Déploiement Azure Container Apps — Production (branche principale, manuel)

## Variables CI

Les variables sans valeur sont à déclarer dans la CI ; les autres sont déjà écrites dans les fichiers.

| Variable | Secret | Valeur | Rôle |
| --- | --- | --- | --- |
| `REGISTRY_USER` | oui | à déclarer | Compte de publication sur monappregistry.azurecr.io |
| `REGISTRY_PASSWORD` | oui | à déclarer | Mot de passe ou jeton de publication sur monappregistry.azurecr.io |
| `AZURE_CLIENT_ID` | non | à déclarer | Identifiant d'application Entra ID |
| `AZURE_TENANT_ID` | non | à déclarer | Identifiant du tenant Entra ID |
| `AZURE_SUBSCRIPTION_ID` | non | à déclarer | Identifiant d'abonnement Azure |
| `AZURE_INFRA_CLIENT_ID` | non | à déclarer | Application Entra ID des jobs d'infrastructure (plan, apply) |
| `RENOVATE_TOKEN` | oui | à déclarer | Jeton de la forge autorisé à ouvrir des merge requests (Renovate) |

## Diagnostics restants

- **Avertissement** (R34) — Azure Container Registry : « Nom du registre ACR » non renseigné : la valeur d'exemple « monappregistry » sera écrite dans les fichiers.
- **Avertissement** (R34) — Azure Blob Storage : « Compte de stockage » non renseigné : la valeur d'exemple « monprojettfstate » sera écrite dans les fichiers.
- **Info** (R50) — Azure Container Apps est expérimental : aucune ressource Terraform générée : l'application Container Apps se crée à la main, la CI la met ensuite à jour.

## Notes

- Mise en route pas à pas, avec les commandes du projet : docs/mise-en-route.md.
- Approbation (« Production ») : le job attend un déclenchement manuel dans GitLab ; protéger l'environnement (Settings › CI/CD › Protected environments) pour restreindre qui peut le lancer.
- Azure Functions : une fonction par environnement (mon-app-staging, mon-app) avec une adresse HTTPS publique en sortie (fn_<environnement>_url).
- Azure Functions : la pile crée la fonction et ne réécrit plus son code ; la CI déploie le code de l'application (étape « Déploiement de la fonction »).
- Azure Functions : le nom de l'application de fonctions et celui du compte de stockage doivent être uniques dans tout Azure.
- Renovate : job « renovate » de .gitlab-ci.yml, lancé par une planification de pipeline portant la variable RENOVATE=1 (docs/mise-en-route.md) ; les autres jobs ne tournent pas dans ces pipelines.
- `scripts/ci-variables.sh` déclare les 7 variable(s) à renseigner avec GitLab (glab), sans écrire leurs valeurs dans le dépôt.

## Fichiers générés

- `.gitlab-ci.yml`
- `PIPELINE.md`
- `devops-builder.yaml`
- `docs/mise-en-route.md`
- `infra/terraform/.gitignore`
- `infra/terraform/main.tf`
- `infra/terraform/outputs.tf`
- `infra/terraform/variables.tf`
- `infra/terraform/versions.tf`
- `renovate.json`
- `scripts/ci-variables.sh`
