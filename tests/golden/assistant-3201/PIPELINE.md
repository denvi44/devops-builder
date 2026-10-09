# Mon projet — pipeline généré

Généré par DevOps Builder le AAAA-MM-JJ. Cible : Kubernetes managé (cloud) ; exigence SecNumCloud.

## Environnements

Ordre de promotion : la même image est déployée successivement dans chaque environnement.

| Environnement | Type | Approbation | Cluster | Espace de noms / projet |
| --- | --- | --- | --- | --- |
| Production (`production`) | Production | non | Outscale Kubernetes as a Service (OKS) `mon-cluster` | `mon-app` |

## Briques

| Étape | Brique | Licence | Fiche |
| --- | --- | --- | --- |
| Source | GitHub | proprietary | vérifiée |
| Build | GitHub Actions | proprietary | vérifiée |
| Build | BuildKit (docker buildx) | Apache-2.0 | vérifiée |
| Build | Dependabot | proprietary | vérifiée |
| Tests & qualité | Tests unitaires | MIT | vérifiée |
| Tests & qualité | SonarQube | LGPL-3.0 | vérifiée |
| Artefacts | GitHub Container Registry | proprietary | vérifiée |
| Infrastructure | Outscale | proprietary | vérifiée |
| Infrastructure | Outscale Kubernetes as a Service (OKS) | proprietary | vérifiée |
| Déploiement | Helm | Apache-2.0 | vérifiée |
| Déploiement | Argo CD | Apache-2.0 | vérifiée |
| Plateforme | cert-manager | Apache-2.0 | vérifiée |

## Étapes CI

Orchestrateur : GitHub Actions. Image publiée : `ghcr.io/OWNER/mon-app:<commit>`.

1. Tests unitaires
2. Qualité SonarQube
3. Build et publication de l'image (BuildKit (docker buildx))
4. Mise à jour GitOps (Argo CD) (branche principale)

## Variables CI

Les variables sans valeur sont à déclarer dans la CI ; les autres sont déjà écrites dans les fichiers.

| Variable | Secret | Valeur | Rôle |
| --- | --- | --- | --- |
| `SONAR_HOST_URL` | non | à déclarer | URL du serveur SonarQube |
| `SONAR_TOKEN` | oui | à déclarer | Jeton d'analyse SonarQube |
| `GITOPS_TOKEN` | oui | à déclarer | Jeton autorisé à pousser sur le dépôt GitOps |
| `GITOPS_REPO` | non | à déclarer | Dépôt GitOps surveillé, sans schéma (hôte/groupe/depot.git) |

## Diagnostics restants

- **Avertissement** (R34) — Outscale Kubernetes as a Service (OKS) : « Nom du cluster » non renseigné : la valeur d'exemple « mon-cluster » sera écrite dans les fichiers.
- **Info** (R31) — Aucun fichier n'est généré pour Outscale Kubernetes as a Service (OKS) dans cette configuration : à configurer à la main (listé dans PIPELINE.md).

## Notes

- `scripts/test-kind.sh` déploie le pipeline dans un cluster kind jetable (chart Helm) : utile avant la première mise en production.
- `scripts/ci-variables.sh` déclare les 4 variable(s) à renseigner avec GitHub (gh), sans écrire leurs valeurs dans le dépôt.

## À configurer à la main

Ces briques sont dans le pipeline mais aucun générateur ne les prend en charge :

- Outscale Kubernetes as a Service (OKS)

## Fichiers générés

- `.github/dependabot.yml`
- `.github/workflows/pipeline.yml`
- `PIPELINE.md`
- `charts/mon-app/Chart.yaml`
- `charts/mon-app/templates/deployment.yaml`
- `charts/mon-app/templates/service.yaml`
- `charts/mon-app/values.yaml`
- `deploy/argocd/application.yaml`
- `devops-builder.yaml`
- `infra/terraform/main.tf`
- `infra/terraform/variables.tf`
- `infra/terraform/versions.tf`
- `platform/install.sh`
- `scripts/ci-variables.sh`
- `scripts/test-kind.sh`
