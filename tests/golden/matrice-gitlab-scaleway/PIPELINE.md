# matrice — pipeline généré

Généré par DevOps Builder le AAAA-MM-JJ. Cible : Kubernetes managé (cloud).

## Environnements

Ordre de promotion : la même image est déployée successivement dans chaque environnement.

| Environnement | Type | Approbation | Cluster | Espace de noms / projet |
| --- | --- | --- | --- | --- |
| Production (`production`) | Production | non | Scaleway Kapsule `mon-cluster` | `mon-app` |

## Ports

| Composant | Port publié | Port du conteneur | Usage | Exposition |
| --- | --- | --- | --- | --- |
| mon-app | — | 8000 | application | Service mon-app port 80, espace de noms mon-app |

## Briques

| Étape | Brique | Licence | Fiche |
| --- | --- | --- | --- |
| Source | GitLab | MIT | vérifiée |
| Build | GitLab CI | MIT | vérifiée |
| Build | BuildKit (docker buildx) | Apache-2.0 | vérifiée |
| Artefacts | Scaleway Container Registry | proprietary | vérifiée |
| Infrastructure | Scaleway | proprietary | vérifiée |
| Infrastructure | Scaleway Kapsule | proprietary | vérifiée |
| Infrastructure | OpenTofu | MPL-2.0 | vérifiée |
| Déploiement | Helm | Apache-2.0 | vérifiée |

## Étapes CI

Orchestrateur : GitLab CI. Image publiée : `rg.fr-par.scw.cloud/mon-app/mon-app:<commit>`.

1. Build et publication de l'image (BuildKit (docker buildx))
2. Plan OpenTofu
3. Application OpenTofu (branche principale, manuel)
4. Déploiement Helm (branche principale)

## Variables CI

Les variables sans valeur sont à déclarer dans la CI ; les autres sont déjà écrites dans les fichiers.

| Variable | Secret | Valeur | Rôle |
| --- | --- | --- | --- |
| `SCW_SECRET_KEY` | oui | à déclarer | Clé secrète d'API Scaleway |
| `SCW_ACCESS_KEY` | oui | à déclarer | Clé d'accès API Scaleway |
| `SCW_DEFAULT_PROJECT_ID` | oui | à déclarer | Projet Scaleway |
| `KUBECONFIG_DATA` | oui | à déclarer | Contenu du kubeconfig de Scaleway Kapsule (base64) |

## Diagnostics restants

- **Avertissement** (R34) — Scaleway Kapsule : « Nom du cluster » non renseigné : la valeur d'exemple « mon-cluster » sera écrite dans les fichiers.
- **Avertissement** (R44) — OpenTofu tourne dans la CI sans stockage d'état distant : l'état, écrit dans le job, serait perdu à la fin de chaque pipeline et l'apply suivant recréerait les ressources. Ajouter le stockage objet du fournisseur.

## Notes

- `scripts/test-kind.sh` déploie le pipeline dans un cluster kind jetable (chart Helm) : utile avant la première mise en production.
- `scripts/ci-variables.sh` déclare les 4 variable(s) à renseigner avec GitLab (glab), sans écrire leurs valeurs dans le dépôt.

## Fichiers générés

- `.gitlab-ci.yml`
- `PIPELINE.md`
- `charts/mon-app/Chart.yaml`
- `charts/mon-app/templates/deployment.yaml`
- `charts/mon-app/templates/service.yaml`
- `charts/mon-app/values.yaml`
- `devops-builder.yaml`
- `infra/terraform/.gitignore`
- `infra/terraform/main.tf`
- `infra/terraform/outputs.tf`
- `infra/terraform/variables.tf`
- `infra/terraform/versions.tf`
- `scripts/ci-variables.sh`
- `scripts/test-kind.sh`
