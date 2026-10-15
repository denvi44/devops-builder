# Mon projet — pipeline généré

Généré par DevOps Builder le AAAA-MM-JJ. Cible : Kubernetes autogéré ; exigence SecNumCloud.

## Environnements

Ordre de promotion : la même image est déployée successivement dans chaque environnement.

| Environnement | Type | Approbation | Cluster | Espace de noms / projet |
| --- | --- | --- | --- | --- |
| Préproduction (`staging`) | Préproduction | non | k3s | `mon-app-staging` |
| Production (`production`) | Production | oui | k3s | `mon-app` |

## Ports

| Environnement | Composant | Port publié | Port du conteneur | Usage | Exposition |
| --- | --- | --- | --- | --- | --- |
| Préproduction | mon-app | — | 8000 | application | Service mon-app port 80, espace de noms mon-app-staging, exposé par Traefik |
| Préproduction | Gitea | — | 3000 | interface web | Service Kubernetes, espace de noms gitea |
| Préproduction | Gitea | — | 22 | SSH Git | Service Kubernetes, espace de noms gitea |
| Préproduction | SonarQube | — | 9000 | interface web | Service Kubernetes, espace de noms sonarqube |
| Préproduction | Harbor | — | 80 | HTTP | Service Kubernetes, espace de noms harbor |
| Préproduction | Harbor | — | 443 | HTTPS (portail et registre) | Service Kubernetes, espace de noms harbor |
| Préproduction | Argo CD | — | 8080 | API et interface (service 80/443) | Service Kubernetes, espace de noms argocd |
| Préproduction | Traefik | — | 80 | HTTP | Service Kubernetes, espace de noms traefik |
| Préproduction | Traefik | — | 443 | HTTPS | Service Kubernetes, espace de noms traefik |
| Préproduction | Prometheus | — | 9090 | interface et API | Service Kubernetes, espace de noms monitoring |
| Préproduction | Grafana | — | 3000 | interface web | Service Kubernetes, espace de noms monitoring |
| Production | mon-app | — | 8000 | application | Service mon-app port 80, espace de noms mon-app, exposé par Traefik |
| Production | Gitea | — | 3000 | interface web | Service Kubernetes, espace de noms gitea |
| Production | Gitea | — | 22 | SSH Git | Service Kubernetes, espace de noms gitea |
| Production | SonarQube | — | 9000 | interface web | Service Kubernetes, espace de noms sonarqube |
| Production | Harbor | — | 80 | HTTP | Service Kubernetes, espace de noms harbor |
| Production | Harbor | — | 443 | HTTPS (portail et registre) | Service Kubernetes, espace de noms harbor |
| Production | Argo CD | — | 8080 | API et interface (service 80/443) | Service Kubernetes, espace de noms argocd |
| Production | Traefik | — | 80 | HTTP | Service Kubernetes, espace de noms traefik |
| Production | Traefik | — | 443 | HTTPS | Service Kubernetes, espace de noms traefik |
| Production | Prometheus | — | 9090 | interface et API | Service Kubernetes, espace de noms monitoring |
| Production | Grafana | — | 3000 | interface web | Service Kubernetes, espace de noms monitoring |

## Briques

| Étape | Brique | Licence | Fiche |
| --- | --- | --- | --- |
| Source | Gitea | MIT | vérifiée |
| Build | Gitea Actions | MIT | vérifiée |
| Build | BuildKit (docker buildx) | Apache-2.0 | vérifiée |
| Build | Renovate | AGPL-3.0 | vérifiée |
| Tests & qualité | Tests unitaires | MIT | vérifiée |
| Tests & qualité | SonarQube | LGPL-3.0 | vérifiée |
| Artefacts | Harbor | Apache-2.0 | vérifiée |
| Infrastructure | k3s | Apache-2.0 | vérifiée |
| Déploiement | Helm | Apache-2.0 | vérifiée |
| Déploiement | Argo CD | Apache-2.0 | vérifiée |
| Plateforme | Traefik | MIT | vérifiée |
| Plateforme | cert-manager | Apache-2.0 | vérifiée |
| Observabilité | Prometheus | Apache-2.0 | vérifiée |
| Observabilité | Grafana | AGPL-3.0 | vérifiée |

## Étapes CI

Orchestrateur : Gitea Actions. Image publiée : `registry.example.com/mon-app/mon-app:<commit>`.

1. Tests unitaires
2. Qualité SonarQube
3. Build et publication de l'image (BuildKit (docker buildx))
4. Mise à jour GitOps (Argo CD) — Préproduction (branche principale)
5. Mise à jour GitOps (Argo CD) — Production (branche principale, manuel)

## Variables CI

Les variables sans valeur sont à déclarer dans la CI ; les autres sont déjà écrites dans les fichiers.

| Variable | Secret | Valeur | Rôle |
| --- | --- | --- | --- |
| `SONAR_HOST_URL` | non | à déclarer | URL du serveur SonarQube |
| `SONAR_TOKEN` | oui | à déclarer | Jeton d'analyse SonarQube |
| `REGISTRY_USER` | oui | à déclarer | Compte de publication sur registry.example.com |
| `REGISTRY_PASSWORD` | oui | à déclarer | Mot de passe ou jeton de publication sur registry.example.com |
| `GITOPS_TOKEN` | oui | à déclarer | Jeton autorisé à pousser sur le dépôt GitOps |
| `GITOPS_REPO` | non | à déclarer | Dépôt GitOps surveillé, sans schéma (hôte/groupe/depot.git) |
| `RENOVATE_TOKEN` | oui | à déclarer | Jeton de la forge autorisé à ouvrir des merge requests (Renovate) |

## Diagnostics restants

- **Avertissement** (R34) — Harbor : « Adresse du registre » non renseigné : la valeur d'exemple « registry.example.com » sera écrite dans les fichiers.
- **Avertissement** (R34) — Argo CD : « Dépôt GitOps » non renseigné : la valeur d'exemple « https://git.example.com/groupe/gitops.git » sera écrite dans les fichiers.

## Notes

- Mise en route pas à pas, avec les commandes du projet : docs/mise-en-route.md.
- Approbation (« Production ») : déclarer des relecteurs obligatoires sur l'environnement du dépôt (Settings › Environments › Required reviewers), sinon le déploiement part sans attendre.
- Renovate : lancer l'image renovate/renovate dans un job planifié (quotidien) avec RENOVATE_TOKEN ; renovate.json règle son comportement.
- `scripts/test-kind.sh` déploie le pipeline dans un cluster kind jetable (chart Helm) : utile avant la première mise en production.
- `scripts/ci-variables.sh` déclare les 7 variable(s) à renseigner avec Gitea (API), sans écrire leurs valeurs dans le dépôt.

## Fichiers générés

- `.gitea/workflows/pipeline.yml`
- `PIPELINE.md`
- `charts/mon-app/Chart.yaml`
- `charts/mon-app/templates/deployment.yaml`
- `charts/mon-app/templates/service.yaml`
- `charts/mon-app/values-production.yaml`
- `charts/mon-app/values-staging.yaml`
- `charts/mon-app/values.yaml`
- `deploy/argocd/application.yaml`
- `devops-builder.yaml`
- `docs/mise-en-route.md`
- `infra/cluster/install-k3s.sh`
- `platform/install.sh`
- `renovate.json`
- `scripts/ci-variables.sh`
- `scripts/test-kind.sh`
