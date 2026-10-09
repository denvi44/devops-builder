# Mon projet — pipeline généré

Généré par DevOps Builder le AAAA-MM-JJ. Cible : Hôte Docker unique.

## Environnements

Ordre de promotion : la même image est déployée successivement dans chaque environnement.

| Environnement | Type | Approbation | Cluster | Espace de noms / projet |
| --- | --- | --- | --- | --- |
| Préproduction (`staging`) | Préproduction | non | — | `mon-app-staging` |
| Production (`production`) | Production | oui | — | `mon-app` |

## Briques

| Étape | Brique | Licence | Fiche |
| --- | --- | --- | --- |
| Source | Bitbucket Cloud | proprietary | vérifiée |
| Build | Woodpecker CI | Apache-2.0 | vérifiée |
| Build | BuildKit (docker buildx) | Apache-2.0 | vérifiée |
| Build | Renovate | AGPL-3.0 | vérifiée |
| Tests & qualité | Tests unitaires | MIT | vérifiée |
| Tests & qualité | SonarQube | LGPL-3.0 | vérifiée |
| Artefacts | Azure Container Registry | proprietary | vérifiée |
| Infrastructure | Microsoft Azure | proprietary | vérifiée |
| Déploiement | Azure Container Apps | proprietary | vérifiée |

## Étapes CI

Orchestrateur : Woodpecker CI. Image publiée : `monappregistry.azurecr.io/mon-app:<commit>`.

1. Tests unitaires
2. Qualité SonarQube
3. Build et publication de l'image (BuildKit (docker buildx))
4. Déploiement Azure Container Apps — Préproduction (branche principale)
5. Déploiement Azure Container Apps — Production (branche principale, manuel)

## Variables CI

Les variables sans valeur sont à déclarer dans la CI ; les autres sont déjà écrites dans les fichiers.

| Variable | Secret | Valeur | Rôle |
| --- | --- | --- | --- |
| `SONAR_HOST_URL` | non | à déclarer | URL du serveur SonarQube |
| `SONAR_TOKEN` | oui | à déclarer | Jeton d'analyse SonarQube |
| `REGISTRY_USER` | oui | à déclarer | Compte de publication sur monappregistry.azurecr.io |
| `REGISTRY_PASSWORD` | oui | à déclarer | Mot de passe ou jeton de publication sur monappregistry.azurecr.io |
| `AZURE_CLIENT_ID` | non | à déclarer | Identifiant d'application Entra ID |
| `AZURE_TENANT_ID` | non | à déclarer | Identifiant du tenant Entra ID |
| `AZURE_SUBSCRIPTION_ID` | non | à déclarer | Identifiant d'abonnement Azure |
| `RENOVATE_TOKEN` | oui | à déclarer | Jeton de la forge autorisé à ouvrir des merge requests (Renovate) |

## Diagnostics restants

- **Avertissement** (R34) — Azure Container Registry : « Nom du registre ACR » non renseigné : la valeur d'exemple « monappregistry » sera écrite dans les fichiers.

## Notes

- Approbation (« Production ») : Woodpecker n'a pas de porte d'approbation : l'étape ne s'exécute que sur un pipeline lancé manuellement depuis l'interface (événement « manual »).
- Renovate : lancer l'image renovate/renovate dans un job planifié (quotidien) avec RENOVATE_TOKEN ; renovate.json règle son comportement.

## Fichiers générés

- `.woodpecker.yml`
- `PIPELINE.md`
- `devops-builder.yaml`
- `infra/terraform/main.tf`
- `infra/terraform/variables.tf`
- `infra/terraform/versions.tf`
- `renovate.json`
