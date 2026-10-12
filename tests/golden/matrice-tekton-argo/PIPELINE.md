# matrice — pipeline généré

Généré par DevOps Builder le AAAA-MM-JJ. Cible : Kubernetes autogéré.

## Environnements

Ordre de promotion : la même image est déployée successivement dans chaque environnement.

| Environnement | Type | Approbation | Cluster | Espace de noms / projet |
| --- | --- | --- | --- | --- |
| Production (`production`) | Production | non | RKE2 | `mon-app` |

## Ports

| Composant | Port publié | Port du conteneur | Usage | Exposition |
| --- | --- | --- | --- | --- |
| mon-app | — | 8000 | application | Service mon-app port 80, espace de noms mon-app |
| Harbor | — | 80 | HTTP | Service Kubernetes, espace de noms harbor |
| Harbor | — | 443 | HTTPS (portail et registre) | Service Kubernetes, espace de noms harbor |
| Argo CD | — | 8080 | API et interface (service 80/443) | Service Kubernetes, espace de noms argocd |

## Briques

| Étape | Brique | Licence | Fiche |
| --- | --- | --- | --- |
| Source | GitHub | proprietary | vérifiée |
| Build | Tekton | Apache-2.0 | vérifiée |
| Build | Buildah | Apache-2.0 | vérifiée |
| Tests & qualité | Tests unitaires | MIT | vérifiée |
| Artefacts | Harbor | Apache-2.0 | vérifiée |
| Infrastructure | RKE2 | Apache-2.0 | vérifiée |
| Déploiement | Argo CD | Apache-2.0 | vérifiée |
| Déploiement | Helm | Apache-2.0 | vérifiée |

## Étapes CI

Orchestrateur : Tekton. Image publiée : `registry.example.com/mon-app/mon-app:<commit>`.

1. Tests unitaires
2. Build et publication de l'image (Buildah)
3. Mise à jour GitOps (Argo CD) (branche principale)

## Variables CI

Les variables sans valeur sont à déclarer dans la CI ; les autres sont déjà écrites dans les fichiers.

| Variable | Secret | Valeur | Rôle |
| --- | --- | --- | --- |
| `REGISTRY_USER` | oui | à déclarer | Compte de publication sur registry.example.com |
| `REGISTRY_PASSWORD` | oui | à déclarer | Mot de passe ou jeton de publication sur registry.example.com |
| `GITOPS_TOKEN` | oui | à déclarer | Jeton autorisé à pousser sur le dépôt GitOps |
| `GITOPS_REPO` | non | à déclarer | Dépôt GitOps surveillé, sans schéma (hôte/groupe/depot.git) |

## Diagnostics restants

- **Avertissement** (R34) — Harbor : « Adresse du registre » non renseigné : la valeur d'exemple « registry.example.com » sera écrite dans les fichiers.
- **Info** (R50) — Tekton est expérimental : pas de porte d'approbation native : la production part d'un déclenchement manuel ; secrets de la CI à déclarer à la main.
- **Info** (R50) — RKE2 est expérimental : le contrôleur d'entrée embarqué dépend de la version : à désactiver à la main si un autre contrôleur est posé.

## Notes

- Mise en route pas à pas, avec les commandes du projet : docs/mise-en-route.md.
- `scripts/test-kind.sh` déploie le pipeline dans un cluster kind jetable (chart Helm) : utile avant la première mise en production.

## Fichiers générés

- `PIPELINE.md`
- `charts/mon-app/Chart.yaml`
- `charts/mon-app/templates/deployment.yaml`
- `charts/mon-app/templates/service.yaml`
- `charts/mon-app/values.yaml`
- `deploy/argocd/application.yaml`
- `devops-builder.yaml`
- `docs/mise-en-route.md`
- `infra/cluster/install-rke2.sh`
- `platform/install.sh`
- `scripts/test-kind.sh`
- `tekton/pipeline.yaml`
