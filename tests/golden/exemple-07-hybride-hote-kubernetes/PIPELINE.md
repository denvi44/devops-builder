# Hybride : hôte Docker puis Kubernetes — pipeline généré

Généré par DevOps Builder le AAAA-MM-JJ. Cible : Kubernetes autogéré.

## Environnements

Ordre de promotion : la même image est déployée successivement dans chaque environnement.

| Environnement | Type | Hébergement | Approbation | Cluster | Espace de noms / projet |
| --- | --- | --- | --- | --- | --- |
| Développement (`dev`) | Développement | Hôte Docker unique | non | k3s | `boutique-dev` |
| Préproduction (`staging`) | Préproduction | Kubernetes autogéré | non | k3s | `boutique-staging` |
| Production (`production`) | Production | Kubernetes autogéré | oui | k3s | `boutique` |

## Ports

| Environnement | Composant | Port publié | Port du conteneur | Usage | Exposition |
| --- | --- | --- | --- | --- | --- |
| Développement | boutique | 8000 | 8000 | application | publié sur l'hôte Docker |
| Préproduction | boutique | — | 8000 | application | Service boutique port 80, espace de noms boutique-staging |
| Production | boutique | — | 8000 | application | Service boutique port 80, espace de noms boutique |

## Briques

| Étape | Brique | Licence | Fiche |
| --- | --- | --- | --- |
| Source | GitHub | proprietary | vérifiée |
| Build | GitHub Actions | proprietary | vérifiée |
| Build | BuildKit (docker buildx) | Apache-2.0 | vérifiée |
| Artefacts | GitHub Container Registry | proprietary | vérifiée |
| Infrastructure | k3s | Apache-2.0 | vérifiée |
| Déploiement | Docker Compose | Apache-2.0 | vérifiée |
| Déploiement | Helm | Apache-2.0 | vérifiée |

## Étapes CI

Orchestrateur : GitHub Actions. Image publiée : `ghcr.io/OWNER/boutique:<commit>`.

1. Build et publication de l'image (BuildKit (docker buildx))
2. Déploiement Docker Compose (SSH) — Développement (branche principale)
3. Déploiement Helm — Préproduction (branche principale)
4. Déploiement Helm — Production (branche principale, manuel)

## Variables CI

Les variables sans valeur sont à déclarer dans la CI ; les autres sont déjà écrites dans les fichiers.

| Variable | Secret | Valeur | Rôle |
| --- | --- | --- | --- |
| `SSH_PRIVATE_KEY` | oui | à déclarer | Clé SSH de déploiement vers l'hôte Docker |
| `SSH_KNOWN_HOSTS` | non | à déclarer | Facultatif : clés d'hôte attendues (ssh-keyscan) ; sans elle, la clé est acceptée à la première connexion de chaque job |
| `DEPLOY_HOST_DEV` | non | à déclarer | Hôte Docker cible (Développement) (utilisateur@hôte) |
| `KUBECONFIG_DATA_STAGING` | oui | à déclarer | Contenu du kubeconfig de k3s (Préproduction) (base64) |
| `KUBECONFIG_DATA_PRODUCTION` | oui | à déclarer | Contenu du kubeconfig de k3s (Production) (base64) |

## Diagnostics restants

Aucun.

## Notes

- Mise en route pas à pas, avec les commandes du projet : docs/mise-en-route.md.
- Approbation (« Production ») : déclarer des relecteurs obligatoires sur l'environnement du dépôt (Settings › Environments › Required reviewers), sinon le déploiement part sans attendre.
- `scripts/test-kind.sh` déploie le pipeline dans un cluster kind jetable (chart Helm) : utile avant la première mise en production.
- `scripts/ci-variables.sh` déclare les 5 variable(s) à renseigner avec GitHub (gh), sans écrire leurs valeurs dans le dépôt.

## Fichiers générés

- `.github/workflows/pipeline.yml`
- `PIPELINE.md`
- `charts/boutique/Chart.yaml`
- `charts/boutique/templates/deployment.yaml`
- `charts/boutique/templates/ingress.yaml`
- `charts/boutique/templates/service.yaml`
- `charts/boutique/values-dev.yaml`
- `charts/boutique/values-production.yaml`
- `charts/boutique/values-staging.yaml`
- `charts/boutique/values.yaml`
- `deploy/docker-compose.yml`
- `devops-builder.yaml`
- `docs/mise-en-route.md`
- `infra/cluster/install-k3s.sh`
- `scripts/ci-variables.sh`
- `scripts/test-kind.sh`
