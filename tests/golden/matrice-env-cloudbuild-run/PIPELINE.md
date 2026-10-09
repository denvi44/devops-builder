# matrice — pipeline généré

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
| Préproduction | mon-app | — | 8000 | application | Cloud Run : URL HTTPS gérée par le service |
| Production | mon-app | — | 8000 | application | Cloud Run : URL HTTPS gérée par le service |

## Briques

| Étape | Brique | Licence | Fiche |
| --- | --- | --- | --- |
| Source | GitHub | proprietary | vérifiée |
| Build | Google Cloud Build | proprietary | vérifiée |
| Build | Cloud Native Buildpacks | Apache-2.0 | vérifiée |
| Artefacts | Google Artifact Registry | proprietary | vérifiée |
| Infrastructure | Google Cloud | proprietary | vérifiée |
| Déploiement | Google Cloud Run | proprietary | vérifiée |

## Étapes CI

Orchestrateur : Google Cloud Build. Image publiée : `europe-west9-docker.pkg.dev/mon-projet/mon-app/mon-app:<commit>`.

1. Build et publication de l'image (Cloud Native Buildpacks)
2. Déploiement Cloud Run — Préproduction (branche principale)
3. Déploiement Cloud Run — Production (branche principale, manuel)

## Variables CI

Les variables sans valeur sont à déclarer dans la CI ; les autres sont déjà écrites dans les fichiers.

| Variable | Secret | Valeur | Rôle |
| --- | --- | --- | --- |
| `REGISTRY_USER` | oui | à déclarer | Compte de publication sur europe-west9-docker.pkg.dev |
| `REGISTRY_PASSWORD` | oui | à déclarer | Mot de passe ou jeton de publication sur europe-west9-docker.pkg.dev |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | non | à déclarer | Fournisseur Workload Identity Federation |
| `GCP_SERVICE_ACCOUNT` | non | à déclarer | Compte de service impersonné par la CI |

## Diagnostics restants

- **Avertissement** (R34) — Google Cloud : « Identifiant du projet » non renseigné : la valeur d'exemple « mon-projet » sera écrite dans les fichiers.

## Notes

- Approbation (« Production ») : créer pour cloudbuild-deploy-*.yaml un déclencheur Cloud Build avec l'option « Approbation requise ».

## Fichiers générés

- `PIPELINE.md`
- `cloudbuild-deploy-production.yaml`
- `cloudbuild.yaml`
- `devops-builder.yaml`
- `infra/terraform/main.tf`
- `infra/terraform/variables.tf`
- `infra/terraform/versions.tf`
