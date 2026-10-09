# matrice — pipeline généré

Généré par DevOps Builder le AAAA-MM-JJ. Cible : Kubernetes autogéré.

## Environnements

Ordre de promotion : la même image est déployée successivement dans chaque environnement.

| Environnement | Type | Approbation | Cluster | Espace de noms / projet |
| --- | --- | --- | --- | --- |
| Production (`production`) | Production | non | kubeadm | `mon-app` |

## Briques

| Étape | Brique | Licence | Fiche |
| --- | --- | --- | --- |
| Source | GitLab | MIT | vérifiée |
| Build | GitLab CI | MIT | vérifiée |
| Build | BuildKit (docker buildx) | Apache-2.0 | vérifiée |
| Infrastructure | kubeadm | Apache-2.0 | vérifiée |
| Déploiement | Kustomize | Apache-2.0 | vérifiée |
| Plateforme | Calico | Apache-2.0 | vérifiée |

## Étapes CI

Orchestrateur : GitLab CI. Image publiée : `$CI_REGISTRY_IMAGE:<commit>`.

1. Build et publication de l'image (BuildKit (docker buildx))
2. Déploiement Kustomize (branche principale)

## Variables CI

Les variables sans valeur sont à déclarer dans la CI ; les autres sont déjà écrites dans les fichiers.

| Variable | Secret | Valeur | Rôle |
| --- | --- | --- | --- |
| `KUBECONFIG_DATA` | oui | à déclarer | Contenu du kubeconfig de kubeadm (base64) |

## Diagnostics restants

Aucun.

## Notes

- `scripts/test-kind.sh` déploie le pipeline dans un cluster kind jetable (overlay Kustomize) : utile avant la première mise en production.
- `scripts/ci-variables.sh` déclare les 1 variable(s) à renseigner avec GitLab (glab), sans écrire leurs valeurs dans le dépôt.

## Fichiers générés

- `.gitlab-ci.yml`
- `PIPELINE.md`
- `deploy/kustomize/base/deployment.yaml`
- `deploy/kustomize/base/kustomization.yaml`
- `deploy/kustomize/base/service.yaml`
- `deploy/kustomize/overlays/production/kustomization.yaml`
- `devops-builder.yaml`
- `infra/cluster/install-kubeadm.sh`
- `platform/install.sh`
- `scripts/ci-variables.sh`
- `scripts/test-kind.sh`
