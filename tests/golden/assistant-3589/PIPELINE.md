# Mon projet — pipeline généré

Généré par DevOps Builder le AAAA-MM-JJ. Cible : Hôte Docker unique.

## Environnements

Ordre de promotion : la même image est déployée successivement dans chaque environnement.

| Environnement | Type | Approbation | Cluster | Espace de noms / projet |
| --- | --- | --- | --- | --- |
| Développement (`dev`) | Développement | non | — | `mon-app-dev` |
| Préproduction (`staging`) | Préproduction | non | — | `mon-app-staging` |
| Production (`production`) | Production | oui | — | `mon-app` |

## Briques

| Étape | Brique | Licence | Fiche |
| --- | --- | --- | --- |
| Source | GitHub | proprietary | vérifiée |
| Build | GitHub Actions | proprietary | vérifiée |
| Build | BuildKit (docker buildx) | Apache-2.0 | vérifiée |
| Build | Dependabot | proprietary | vérifiée |
| Tests & qualité | Tests unitaires | MIT | vérifiée |
| Tests & qualité | SonarQube | LGPL-3.0 | vérifiée |
| Artefacts | Google Artifact Registry | proprietary | vérifiée |
| Infrastructure | Google Cloud | proprietary | vérifiée |
| Infrastructure | Terraform | BSL-1.1 | vérifiée |
| Infrastructure | Google Cloud Storage | proprietary | vérifiée |
| Déploiement | Google Cloud Run | proprietary | vérifiée |
| Observabilité | Google Cloud Monitoring et Logging | proprietary | vérifiée |

## Étapes CI

Orchestrateur : GitHub Actions. Image publiée : `europe-west9-docker.pkg.dev/mon-projet/mon-app/mon-app:<commit>`.

1. Tests unitaires
2. Qualité SonarQube
3. Build et publication de l'image (BuildKit (docker buildx))
4. Plan Terraform
5. Application Terraform (branche principale, manuel)
6. Déploiement Cloud Run — Développement (branche principale)
7. Déploiement Cloud Run — Préproduction (branche principale)
8. Déploiement Cloud Run — Production (branche principale, manuel)

## Variables CI

Les variables sans valeur sont à déclarer dans la CI ; les autres sont déjà écrites dans les fichiers.

| Variable | Secret | Valeur | Rôle |
| --- | --- | --- | --- |
| `SONAR_HOST_URL` | non | à déclarer | URL du serveur SonarQube |
| `SONAR_TOKEN` | oui | à déclarer | Jeton d'analyse SonarQube |
| `REGISTRY_USER` | oui | à déclarer | Compte de publication sur europe-west9-docker.pkg.dev |
| `REGISTRY_PASSWORD` | oui | à déclarer | Mot de passe ou jeton de publication sur europe-west9-docker.pkg.dev |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | non | à déclarer | Fournisseur Workload Identity Federation |
| `GCP_SERVICE_ACCOUNT` | non | à déclarer | Compte de service impersonné par la CI |

## Diagnostics restants

- **Avertissement** (R34) — Google Cloud : « Identifiant du projet » non renseigné : la valeur d'exemple « mon-projet » sera écrite dans les fichiers.
- **Avertissement** (R34) — Google Cloud Storage : « Bucket de l'état Terraform » non renseigné : la valeur d'exemple « mon-projet-tfstate » sera écrite dans les fichiers.
- **Info** (R24) — Terraform est sous licence BSL-1.1.
- **Info** (R31) — Aucun fichier n'est généré pour Google Cloud Monitoring et Logging dans cette configuration : à configurer à la main (listé dans PIPELINE.md).

## Notes

- Approbation (« Production ») : déclarer des relecteurs obligatoires sur l'environnement du dépôt (Settings › Environments › Required reviewers), sinon le déploiement part sans attendre.
- `scripts/ci-variables.sh` déclare les 6 variable(s) à renseigner avec GitHub (gh), sans écrire leurs valeurs dans le dépôt.

## À configurer à la main

Ces briques sont dans le pipeline mais aucun générateur ne les prend en charge :

- Google Cloud Monitoring et Logging

## Fichiers générés

- `.github/dependabot.yml`
- `.github/workflows/pipeline.yml`
- `PIPELINE.md`
- `devops-builder.yaml`
- `infra/terraform/main.tf`
- `infra/terraform/variables.tf`
- `infra/terraform/versions.tf`
- `scripts/ci-variables.sh`
