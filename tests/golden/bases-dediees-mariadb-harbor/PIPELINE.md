# Mon projet — pipeline généré

Généré par DevOps Builder le AAAA-MM-JJ. Cible : Kubernetes autogéré.

## Environnements

Ordre de promotion : la même image est déployée successivement dans chaque environnement.

| Environnement | Type | Approbation | Cluster | Espace de noms / projet |
| --- | --- | --- | --- | --- |
| Préproduction (`staging`) | Préproduction | non | k3s | `mon-app-staging` |
| Production (`production`) | Production | oui | k3s | `mon-app` |

## Ports

| Environnement | Composant | Port publié | Port du conteneur | Usage | Exposition |
| --- | --- | --- | --- | --- | --- |
| Préproduction | mon-app | — | 8000 | application | Service mon-app port 80, espace de noms mon-app-staging, exposé par Traefik, hôte staging.mon-app.example.com |
| Préproduction | Gitea | — | 3000 | interface web | Service Kubernetes, espace de noms gitea, exposé par Traefik, hôte gitea.example.com |
| Préproduction | Gitea | — | 22 | SSH Git | Service Kubernetes, espace de noms gitea |
| Préproduction | Harbor | — | 80 | HTTP | Service Kubernetes, espace de noms harbor, exposé par Traefik, hôte harbor.boutique.fr |
| Préproduction | Harbor | — | 443 | HTTPS (portail et registre) | Service Kubernetes, espace de noms harbor |
| Préproduction | Traefik | — | 80 | HTTP | Service Kubernetes, espace de noms traefik |
| Préproduction | Traefik | — | 443 | HTTPS | Service Kubernetes, espace de noms traefik |
| Préproduction | Prometheus | — | 9090 | interface et API | Service Kubernetes, espace de noms monitoring |
| Préproduction | Grafana | — | 3000 | interface web | Service Kubernetes, espace de noms monitoring, exposé par Traefik, hôte grafana.example.com |
| Production | mon-app | — | 8000 | application | Service mon-app port 80, espace de noms mon-app, exposé par Traefik, hôte mon-app.example.com |
| Production | Gitea | — | 3000 | interface web | Service Kubernetes, espace de noms gitea, exposé par Traefik, hôte gitea.example.com |
| Production | Gitea | — | 22 | SSH Git | Service Kubernetes, espace de noms gitea |
| Production | Harbor | — | 80 | HTTP | Service Kubernetes, espace de noms harbor, exposé par Traefik, hôte harbor.boutique.fr |
| Production | Harbor | — | 443 | HTTPS (portail et registre) | Service Kubernetes, espace de noms harbor |
| Production | Traefik | — | 80 | HTTP | Service Kubernetes, espace de noms traefik |
| Production | Traefik | — | 443 | HTTPS | Service Kubernetes, espace de noms traefik |
| Production | Prometheus | — | 9090 | interface et API | Service Kubernetes, espace de noms monitoring |
| Production | Grafana | — | 3000 | interface web | Service Kubernetes, espace de noms monitoring, exposé par Traefik, hôte grafana.example.com |

## Briques

| Étape | Brique | Licence | Fiche |
| --- | --- | --- | --- |
| Source | GitHub | proprietary | vérifiée |
| Source | Gitea | MIT | vérifiée |
| Build | GitHub Actions | proprietary | vérifiée |
| Build | BuildKit (docker buildx) | Apache-2.0 | vérifiée |
| Build | Dependabot | proprietary | vérifiée |
| Tests & qualité | Tests unitaires | MIT | vérifiée |
| Sécurité | Gitleaks | MIT | vérifiée |
| Sécurité | Trivy | Apache-2.0 | vérifiée |
| Sécurité | Cosign | Apache-2.0 | vérifiée |
| Artefacts | GitHub Container Registry | proprietary | vérifiée |
| Artefacts | Harbor | Apache-2.0 | vérifiée |
| Infrastructure | k3s | Apache-2.0 | vérifiée |
| Déploiement | Helm | Apache-2.0 | vérifiée |
| Plateforme | Traefik | MIT | vérifiée |
| Plateforme | cert-manager | Apache-2.0 | vérifiée |
| Observabilité | Prometheus | Apache-2.0 | vérifiée |
| Observabilité | Grafana | AGPL-3.0 | vérifiée |

## Étapes CI

Orchestrateur : GitHub Actions. Image publiée : `ghcr.io/OWNER/mon-app:<commit>`.

1. Tests unitaires
2. Recherche de secrets
3. Build et publication de l'image (BuildKit (docker buildx))
4. Scan de vulnérabilités Trivy
5. Signature de l'image (Cosign) (branche principale)
6. Déploiement Helm — Préproduction (branche principale)
7. Déploiement Helm — Production (branche principale, manuel)

## Variables CI

Les variables sans valeur sont à déclarer dans la CI ; les autres sont déjà écrites dans les fichiers.

| Variable | Secret | Valeur | Rôle |
| --- | --- | --- | --- |
| `KUBECONFIG_DATA_STAGING` | oui | à déclarer | Contenu du kubeconfig de k3s (Préproduction) (base64) |
| `KUBECONFIG_DATA_PRODUCTION` | oui | à déclarer | Contenu du kubeconfig de k3s (Production) (base64) |

## Diagnostics restants

- **Avertissement** (R34) — Traefik : « Adresse publique de l'application » non renseigné : la valeur d'exemple « mon-app.example.com » sera écrite dans les fichiers.
- **Info** (R23) — Harbor embarque déjà Trivy comme scanner ; l'étape Trivy en CI reste utile pour bloquer avant la publication.

## Notes

- Mise en route pas à pas, avec les commandes du projet : docs/mise-en-route.md.
- Approbation (« Production ») : déclarer des relecteurs obligatoires sur l'environnement du dépôt (Settings › Environments › Required reviewers), sinon le déploiement part sans attendre.
- Bases dédiées : une base par outil dans platform/db-<instance>.yaml (Cluster CloudNativePG pour PostgreSQL avec l'opérateur, sinon StatefulSet). Les réglages Helm qui branchent l'outil sur sa base (clés --set de install.sh) suivent la documentation de chaque chart : les vérifier à la première installation.
- HTTPS Kubernetes : platform/cluster-issuer.yaml (Let's Encrypt, challenge HTTP-01) ; chaque nom d'hôte doit pointer vers l'adresse publique du contrôleur d'entrée avant l'émission du certificat.
- `scripts/test-kind.sh` déploie le pipeline dans un cluster kind jetable (chart Helm) : utile avant la première mise en production.
- `scripts/ci-variables.sh` déclare les 2 variable(s) à renseigner avec GitHub (gh), sans écrire leurs valeurs dans le dépôt.

## Fichiers générés

- `.github/dependabot.yml`
- `.github/workflows/pipeline.yml`
- `PIPELINE.md`
- `charts/mon-app/Chart.yaml`
- `charts/mon-app/templates/deployment.yaml`
- `charts/mon-app/templates/ingress.yaml`
- `charts/mon-app/templates/service.yaml`
- `charts/mon-app/values-production.yaml`
- `charts/mon-app/values-staging.yaml`
- `charts/mon-app/values.yaml`
- `devops-builder.yaml`
- `docs/mise-en-route.md`
- `infra/cluster/install-k3s.sh`
- `platform/cluster-issuer.yaml`
- `platform/db-gitea.yaml`
- `platform/db-harbor.yaml`
- `platform/install.sh`
- `scripts/ci-variables.sh`
- `scripts/test-kind.sh`
