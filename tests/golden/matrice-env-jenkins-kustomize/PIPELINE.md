# matrice — pipeline généré

Généré par DevOps Builder le AAAA-MM-JJ. Cible : Kubernetes autogéré.

## Environnements

Ordre de promotion : la même image est déployée successivement dans chaque environnement.

| Environnement | Type | Approbation | Cluster | Espace de noms / projet |
| --- | --- | --- | --- | --- |
| Développement (`dev`) | Développement | non | k3s | `mon-app-dev` |
| Préproduction (`staging`) | Préproduction | non | k3s | `mon-app-staging` |
| Production (`production`) | Production | oui | k3s | `mon-app` |

## Ports

| Environnement | Composant | Port publié | Port du conteneur | Usage | Exposition |
| --- | --- | --- | --- | --- | --- |
| Développement | mon-app | — | 8000 | application | Service mon-app port 80, espace de noms mon-app-dev |
| Développement | Jenkins | — | 8080 | interface web | Service Kubernetes, espace de noms jenkins |
| Développement | Jenkins | — | 50000 | agents | Service Kubernetes, espace de noms jenkins |
| Développement | Harbor | — | 80 | HTTP | Service Kubernetes, espace de noms harbor |
| Développement | Harbor | — | 443 | HTTPS (portail et registre) | Service Kubernetes, espace de noms harbor |
| Préproduction | mon-app | — | 8000 | application | Service mon-app port 80, espace de noms mon-app-staging |
| Préproduction | Jenkins | — | 8080 | interface web | Service Kubernetes, espace de noms jenkins |
| Préproduction | Jenkins | — | 50000 | agents | Service Kubernetes, espace de noms jenkins |
| Préproduction | Harbor | — | 80 | HTTP | Service Kubernetes, espace de noms harbor |
| Préproduction | Harbor | — | 443 | HTTPS (portail et registre) | Service Kubernetes, espace de noms harbor |
| Production | mon-app | — | 8000 | application | Service mon-app port 80, espace de noms mon-app |
| Production | Jenkins | — | 8080 | interface web | Service Kubernetes, espace de noms jenkins |
| Production | Jenkins | — | 50000 | agents | Service Kubernetes, espace de noms jenkins |
| Production | Harbor | — | 80 | HTTP | Service Kubernetes, espace de noms harbor |
| Production | Harbor | — | 443 | HTTPS (portail et registre) | Service Kubernetes, espace de noms harbor |

## Briques

| Étape | Brique | Licence | Fiche |
| --- | --- | --- | --- |
| Source | GitLab | MIT | vérifiée |
| Build | Jenkins | MIT | vérifiée |
| Build | BuildKit (docker buildx) | Apache-2.0 | vérifiée |
| Artefacts | Harbor | Apache-2.0 | vérifiée |
| Infrastructure | k3s | Apache-2.0 | vérifiée |
| Déploiement | Kustomize | Apache-2.0 | vérifiée |

## Étapes CI

Orchestrateur : Jenkins. Image publiée : `registry.example.com/mon-app/mon-app:<commit>`.

1. Build et publication de l'image (BuildKit (docker buildx))
2. Déploiement Kustomize — Développement (branche principale)
3. Déploiement Kustomize — Préproduction (branche principale)
4. Déploiement Kustomize — Production (branche principale, manuel)

## Variables CI

Les variables sans valeur sont à déclarer dans la CI ; les autres sont déjà écrites dans les fichiers.

| Variable | Secret | Valeur | Rôle |
| --- | --- | --- | --- |
| `REGISTRY_USER` | oui | à déclarer | Compte de publication sur registry.example.com |
| `REGISTRY_PASSWORD` | oui | à déclarer | Mot de passe ou jeton de publication sur registry.example.com |
| `KUBECONFIG_DATA_DEV` | oui | à déclarer | Contenu du kubeconfig de k3s (Développement) (base64) |
| `KUBECONFIG_DATA_STAGING` | oui | à déclarer | Contenu du kubeconfig de k3s (Préproduction) (base64) |
| `KUBECONFIG_DATA_PRODUCTION` | oui | à déclarer | Contenu du kubeconfig de k3s (Production) (base64) |

## Diagnostics restants

- **Avertissement** (R34) — Harbor : « Adresse du registre » non renseigné : la valeur d'exemple « registry.example.com » sera écrite dans les fichiers.

## Notes

- Mise en route pas à pas, avec les commandes du projet : docs/mise-en-route.md.
- `scripts/test-kind.sh` déploie le pipeline dans un cluster kind jetable (overlay Kustomize) : utile avant la première mise en production.

## Fichiers générés

- `Jenkinsfile`
- `PIPELINE.md`
- `deploy/kustomize/base/deployment.yaml`
- `deploy/kustomize/base/kustomization.yaml`
- `deploy/kustomize/base/service.yaml`
- `deploy/kustomize/overlays/dev/kustomization.yaml`
- `deploy/kustomize/overlays/production/kustomization.yaml`
- `deploy/kustomize/overlays/staging/kustomization.yaml`
- `devops-builder.yaml`
- `docs/mise-en-route.md`
- `infra/cluster/install-k3s.sh`
- `platform/install.sh`
- `scripts/test-kind.sh`
