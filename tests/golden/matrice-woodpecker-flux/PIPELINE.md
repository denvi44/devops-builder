# matrice — pipeline généré

Généré par DevOps Builder le AAAA-MM-JJ. Cible : Kubernetes autogéré.

## Environnements

Ordre de promotion : la même image est déployée successivement dans chaque environnement.

| Environnement | Type | Approbation | Cluster | Espace de noms / projet |
| --- | --- | --- | --- | --- |
| Production (`production`) | Production | non | k3s | `mon-app` |

## Briques

| Étape | Brique | Licence | Fiche |
| --- | --- | --- | --- |
| Source | Gitea | MIT | vérifiée |
| Build | Woodpecker CI | Apache-2.0 | vérifiée |
| Build | Buildah | Apache-2.0 | vérifiée |
| Tests & qualité | Tests unitaires | MIT | vérifiée |
| Artefacts | zot | Apache-2.0 | vérifiée |
| Infrastructure | k3s | Apache-2.0 | vérifiée |
| Déploiement | Flux | Apache-2.0 | vérifiée |
| Déploiement | Kustomize | Apache-2.0 | vérifiée |

## Étapes CI

Orchestrateur : Woodpecker CI. Image publiée : `registry.example.com/mon-app/mon-app:<commit>`.

1. Tests unitaires
2. Build et publication de l'image (Buildah)
3. Mise à jour GitOps (Flux) (branche principale)

## Variables CI

Les variables sans valeur sont à déclarer dans la CI ; les autres sont déjà écrites dans les fichiers.

| Variable | Secret | Valeur | Rôle |
| --- | --- | --- | --- |
| `REGISTRY_USER` | oui | à déclarer | Compte de publication sur registry.example.com |
| `REGISTRY_PASSWORD` | oui | à déclarer | Mot de passe ou jeton de publication sur registry.example.com |
| `GITOPS_TOKEN` | oui | à déclarer | Jeton autorisé à pousser sur le dépôt GitOps |
| `GITOPS_REPO` | non | à déclarer | Dépôt GitOps surveillé, sans schéma (hôte/groupe/depot.git) |

## Diagnostics restants

- **Avertissement** (R34) — zot : « Adresse du registre » non renseigné : la valeur d'exemple « registry.example.com » sera écrite dans les fichiers.

## Notes

- `scripts/test-kind.sh` déploie le pipeline dans un cluster kind jetable (overlay Kustomize) : utile avant la première mise en production.

## Fichiers générés

- `.woodpecker.yml`
- `PIPELINE.md`
- `deploy/flux/gitops.yaml`
- `deploy/kustomize/base/deployment.yaml`
- `deploy/kustomize/base/kustomization.yaml`
- `deploy/kustomize/base/service.yaml`
- `deploy/kustomize/overlays/production/kustomization.yaml`
- `devops-builder.yaml`
- `infra/cluster/install-k3s.sh`
- `platform/install.sh`
- `scripts/test-kind.sh`
