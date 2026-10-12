# matrice — pipeline généré

Généré par DevOps Builder le AAAA-MM-JJ. Cible : Hôte Docker unique.

## Environnements

Ordre de promotion : la même image est déployée successivement dans chaque environnement.

| Environnement | Type | Approbation | Cluster | Espace de noms / projet |
| --- | --- | --- | --- | --- |
| Production (`production`) | Production | non | — | `mon-app` |

## Ports

| Composant | Port publié | Port du conteneur | Usage | Exposition |
| --- | --- | --- | --- | --- |
| mon-app | — | 8000 | application | Cloud Run : URL HTTPS gérée par le service |

## Briques

| Étape | Brique | Licence | Fiche |
| --- | --- | --- | --- |
| Source | GitHub | proprietary | vérifiée |
| Build | Google Cloud Build | proprietary | vérifiée |
| Build | Cloud Native Buildpacks | Apache-2.0 | vérifiée |
| Tests & qualité | Tests unitaires | MIT | vérifiée |
| Artefacts | Google Artifact Registry | proprietary | vérifiée |
| Infrastructure | Google Cloud | proprietary | vérifiée |
| Infrastructure | Google Cloud Storage | proprietary | vérifiée |
| Infrastructure | OpenTofu | MPL-2.0 | vérifiée |
| Déploiement | Google Cloud Run | proprietary | vérifiée |

## Étapes CI

Orchestrateur : Google Cloud Build. Image publiée : `europe-west9-docker.pkg.dev/mon-projet/mon-app/mon-app:<commit>`.

1. Tests unitaires
2. Build et publication de l'image (Cloud Native Buildpacks)
3. Plan OpenTofu
4. Application OpenTofu (branche principale, manuel)
5. Déploiement Cloud Run (branche principale)

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
- **Avertissement** (R34) — Google Cloud Storage : « Bucket de l'état Terraform » non renseigné : la valeur d'exemple « mon-projet-tfstate » sera écrite dans les fichiers.
- **Info** (R50) — Google Cloud Build est expérimental : pas de porte d'approbation native : la production part d'un déclenchement manuel ; secrets de la CI à déclarer à la main.

## Notes

- Mise en route pas à pas, avec les commandes du projet : docs/mise-en-route.md.

## Fichiers générés

- `PIPELINE.md`
- `cloudbuild.yaml`
- `devops-builder.yaml`
- `docs/mise-en-route.md`
- `infra/terraform/.gitignore`
- `infra/terraform/main.tf`
- `infra/terraform/outputs.tf`
- `infra/terraform/variables.tf`
- `infra/terraform/versions.tf`
