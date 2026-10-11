# matrice — pipeline généré

Généré par DevOps Builder le AAAA-MM-JJ. Cible : Kubernetes managé (cloud).

## Environnements

Ordre de promotion : la même image est déployée successivement dans chaque environnement.

| Environnement | Type | Approbation | Cluster | Espace de noms / projet |
| --- | --- | --- | --- | --- |
| Production (`production`) | Production | non | Google Kubernetes Engine `mon-cluster` | `mon-app` |

## Ports

| Composant | Port publié | Port du conteneur | Usage | Exposition |
| --- | --- | --- | --- | --- |
| mon-app | — | 8000 | application | Service mon-app port 80, espace de noms mon-app |

## Briques

| Étape | Brique | Licence | Fiche |
| --- | --- | --- | --- |
| Source | GitHub | proprietary | vérifiée |
| Build | GitHub Actions | proprietary | vérifiée |
| Build | Kaniko | Apache-2.0 | vérifiée |
| Tests & qualité | Tests unitaires | MIT | vérifiée |
| Artefacts | Google Artifact Registry | proprietary | vérifiée |
| Infrastructure | Google Cloud | proprietary | vérifiée |
| Infrastructure | Google Kubernetes Engine | proprietary | vérifiée |
| Déploiement | Kustomize | Apache-2.0 | vérifiée |

## Étapes CI

Orchestrateur : GitHub Actions. Image publiée : `europe-west9-docker.pkg.dev/mon-projet/mon-app/mon-app:<commit>`.

1. Tests unitaires
2. Build et publication de l'image (Kaniko)
3. Déploiement Kustomize (branche principale)

## Variables CI

Les variables sans valeur sont à déclarer dans la CI ; les autres sont déjà écrites dans les fichiers.

| Variable | Secret | Valeur | Rôle |
| --- | --- | --- | --- |
| `GCP_SA_KEY` | oui | à déclarer | Clé JSON du compte de service (statique, déconseillé) |

## Diagnostics restants

- **Avertissement** (R14) — Kaniko : Dépôt archivé le 3 juin 2025, plus maintenu.
- **Avertissement** (R21) — La CI utilise des clés d'accès statiques alors que Google Cloud accepte la fédération d'identité OIDC.
- **Avertissement** (R34) — Google Cloud : « Identifiant du projet » non renseigné : la valeur d'exemple « mon-projet » sera écrite dans les fichiers.
- **Avertissement** (R34) — Google Kubernetes Engine : « Nom du cluster » non renseigné : la valeur d'exemple « mon-cluster » sera écrite dans les fichiers.

## Notes

- `scripts/test-kind.sh` déploie le pipeline dans un cluster kind jetable (overlay Kustomize) : utile avant la première mise en production.
- `scripts/ci-variables.sh` déclare les 1 variable(s) à renseigner avec GitHub (gh), sans écrire leurs valeurs dans le dépôt.

## Fichiers générés

- `.github/workflows/pipeline.yml`
- `PIPELINE.md`
- `deploy/kustomize/base/deployment.yaml`
- `deploy/kustomize/base/kustomization.yaml`
- `deploy/kustomize/base/service.yaml`
- `deploy/kustomize/overlays/production/kustomization.yaml`
- `devops-builder.yaml`
- `infra/terraform/.gitignore`
- `infra/terraform/main.tf`
- `infra/terraform/outputs.tf`
- `infra/terraform/variables.tf`
- `infra/terraform/versions.tf`
- `scripts/ci-variables.sh`
- `scripts/test-kind.sh`
