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
| Gitea | — | 3000 | interface web | Service Kubernetes, espace de noms gitea |
| Gitea | — | 22 | SSH Git | Service Kubernetes, espace de noms gitea |
| zot | — | 5000 | registre OCI | Service Kubernetes, espace de noms zot |

## Briques

| Étape | Brique | Licence | Fiche |
| --- | --- | --- | --- |
| Source | Gitea | MIT | vérifiée |
| Build | Woodpecker CI | Apache-2.0 | vérifiée |
| Build | Buildah | Apache-2.0 | vérifiée |
| Artefacts | zot | Apache-2.0 | vérifiée |
| Infrastructure | RKE2 | Apache-2.0 | vérifiée |
| Déploiement | Helm | Apache-2.0 | vérifiée |
| Plateforme | Cilium | Apache-2.0 | vérifiée |

## Étapes CI

Orchestrateur : Woodpecker CI. Image publiée : `registry.example.com/mon-app/mon-app:<commit>`.

1. Build et publication de l'image (Buildah)
2. Déploiement Helm (branche principale)

## Variables CI

Les variables sans valeur sont à déclarer dans la CI ; les autres sont déjà écrites dans les fichiers.

| Variable | Secret | Valeur | Rôle |
| --- | --- | --- | --- |
| `REGISTRY_USER` | oui | à déclarer | Compte de publication sur registry.example.com |
| `REGISTRY_PASSWORD` | oui | à déclarer | Mot de passe ou jeton de publication sur registry.example.com |
| `KUBECONFIG_DATA` | oui | à déclarer | Contenu du kubeconfig de RKE2 (base64) |

## Diagnostics restants

- **Avertissement** (R34) — zot : « Adresse du registre » non renseigné : la valeur d'exemple « registry.example.com » sera écrite dans les fichiers.
- **Info** (R50) — Woodpecker CI est expérimental : pas de porte d'approbation native : la production part d'un déclenchement manuel ; secrets de la CI à déclarer à la main.
- **Info** (R50) — RKE2 est expérimental : le contrôleur d'entrée embarqué dépend de la version : à désactiver à la main si un autre contrôleur est posé.

## Notes

- Mise en route pas à pas, avec les commandes du projet : docs/mise-en-route.md.
- RKE2 installe lui-même Cilium (clé « cni » de /etc/rancher/rke2/config.yaml).
- `scripts/test-kind.sh` déploie le pipeline dans un cluster kind jetable (chart Helm) : utile avant la première mise en production.

## Fichiers générés

- `.woodpecker.yml`
- `PIPELINE.md`
- `charts/mon-app/Chart.yaml`
- `charts/mon-app/templates/deployment.yaml`
- `charts/mon-app/templates/service.yaml`
- `charts/mon-app/values.yaml`
- `devops-builder.yaml`
- `docs/mise-en-route.md`
- `infra/cluster/install-rke2.sh`
- `platform/install.sh`
- `scripts/test-kind.sh`
