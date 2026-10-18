# API sur k3s en GitOps — pipeline généré

Généré par DevOps Builder le AAAA-MM-JJ. Cible : Kubernetes autogéré.

## Environnements

Ordre de promotion : la même image est déployée successivement dans chaque environnement.

| Environnement | Type | Approbation | Cluster | Espace de noms / projet |
| --- | --- | --- | --- | --- |
| Développement (`dev`) | Développement | non | k3s | `api-dev` |
| Préproduction (`staging`) | Préproduction | non | k3s | `api-staging` |
| Production (`production`) | Production | oui | k3s | `api` |

## Ports

| Environnement | Composant | Port publié | Port du conteneur | Usage | Exposition |
| --- | --- | --- | --- | --- | --- |
| Développement | api | — | 3000 | application | Service api port 80, espace de noms api-dev, exposé par Envoy Gateway, hôte dev.api.example.com |
| Développement | Argo CD | — | 8080 | API et interface (service 80/443) | Service Kubernetes, espace de noms argocd |
| Développement | Envoy Gateway | — | 80 | HTTP | Service Kubernetes, espace de noms envoy-gateway-system |
| Développement | Envoy Gateway | — | 443 | HTTPS | Service Kubernetes, espace de noms envoy-gateway-system |
| Développement | OpenBao | — | 8200 | API et interface | Service Kubernetes, espace de noms openbao |
| Développement | Prometheus | — | 9090 | interface et API | Service Kubernetes, espace de noms monitoring |
| Développement | Grafana | — | 3000 | interface web | Service Kubernetes, espace de noms monitoring, exposé par Envoy Gateway, hôte grafana.example.com |
| Développement | OpenTelemetry Collector | — | 4317 | OTLP gRPC | Service Kubernetes, espace de noms observability |
| Développement | OpenTelemetry Collector | — | 4318 | OTLP HTTP | Service Kubernetes, espace de noms observability |
| Développement | Grafana Tempo | — | 3200 | API HTTP | Service Kubernetes, espace de noms monitoring |
| Préproduction | api | — | 3000 | application | Service api port 80, espace de noms api-staging, exposé par Envoy Gateway, hôte staging.api.example.com |
| Préproduction | Argo CD | — | 8080 | API et interface (service 80/443) | Service Kubernetes, espace de noms argocd |
| Préproduction | Envoy Gateway | — | 80 | HTTP | Service Kubernetes, espace de noms envoy-gateway-system |
| Préproduction | Envoy Gateway | — | 443 | HTTPS | Service Kubernetes, espace de noms envoy-gateway-system |
| Préproduction | OpenBao | — | 8200 | API et interface | Service Kubernetes, espace de noms openbao |
| Préproduction | Prometheus | — | 9090 | interface et API | Service Kubernetes, espace de noms monitoring |
| Préproduction | Grafana | — | 3000 | interface web | Service Kubernetes, espace de noms monitoring, exposé par Envoy Gateway, hôte grafana.example.com |
| Préproduction | OpenTelemetry Collector | — | 4317 | OTLP gRPC | Service Kubernetes, espace de noms observability |
| Préproduction | OpenTelemetry Collector | — | 4318 | OTLP HTTP | Service Kubernetes, espace de noms observability |
| Préproduction | Grafana Tempo | — | 3200 | API HTTP | Service Kubernetes, espace de noms monitoring |
| Production | api | — | 3000 | application | Service api port 80, espace de noms api, exposé par Envoy Gateway, hôte api.example.com |
| Production | Argo CD | — | 8080 | API et interface (service 80/443) | Service Kubernetes, espace de noms argocd |
| Production | Envoy Gateway | — | 80 | HTTP | Service Kubernetes, espace de noms envoy-gateway-system |
| Production | Envoy Gateway | — | 443 | HTTPS | Service Kubernetes, espace de noms envoy-gateway-system |
| Production | OpenBao | — | 8200 | API et interface | Service Kubernetes, espace de noms openbao |
| Production | Prometheus | — | 9090 | interface et API | Service Kubernetes, espace de noms monitoring |
| Production | Grafana | — | 3000 | interface web | Service Kubernetes, espace de noms monitoring, exposé par Envoy Gateway, hôte grafana.example.com |
| Production | OpenTelemetry Collector | — | 4317 | OTLP gRPC | Service Kubernetes, espace de noms observability |
| Production | OpenTelemetry Collector | — | 4318 | OTLP HTTP | Service Kubernetes, espace de noms observability |
| Production | Grafana Tempo | — | 3200 | API HTTP | Service Kubernetes, espace de noms monitoring |

## Briques

| Étape | Brique | Licence | Fiche |
| --- | --- | --- | --- |
| Source | GitHub | proprietary | vérifiée |
| Build | GitHub Actions | proprietary | vérifiée |
| Build | BuildKit (docker buildx) | Apache-2.0 | vérifiée |
| Build | Dependabot | proprietary | vérifiée |
| Tests & qualité | Tests unitaires | MIT | vérifiée |
| Tests & qualité | Semgrep CE | LGPL-2.1 | vérifiée |
| Sécurité | Trivy | Apache-2.0 | vérifiée |
| Sécurité | Syft | Apache-2.0 | vérifiée |
| Sécurité | Cosign | Apache-2.0 | vérifiée |
| Artefacts | GitHub Container Registry | proprietary | vérifiée |
| Infrastructure | k3s | Apache-2.0 | vérifiée |
| Déploiement | Helm | Apache-2.0 | vérifiée |
| Déploiement | Argo CD | Apache-2.0 | vérifiée |
| Plateforme | Cilium | Apache-2.0 | vérifiée |
| Plateforme | Envoy Gateway | Apache-2.0 | vérifiée |
| Plateforme | cert-manager | Apache-2.0 | vérifiée |
| Plateforme | Kyverno | Apache-2.0 | vérifiée |
| Plateforme | External Secrets Operator | Apache-2.0 | vérifiée |
| Plateforme | OpenBao | MPL-2.0 | vérifiée |
| Observabilité | Prometheus | Apache-2.0 | vérifiée |
| Observabilité | Grafana | AGPL-3.0 | vérifiée |
| Observabilité | OpenTelemetry Collector | Apache-2.0 | vérifiée |
| Observabilité | Grafana Tempo | AGPL-3.0 | vérifiée |

## Étapes CI

Orchestrateur : GitHub Actions. Image publiée : `ghcr.io/OWNER/api:<commit>`.

1. Tests unitaires
2. Analyse statique Semgrep
3. Build et publication de l'image (BuildKit (docker buildx))
4. Scan de vulnérabilités Trivy
5. SBOM Syft
6. Signature de l'image (Cosign) (branche principale)
7. Mise à jour GitOps (Argo CD) — Développement (branche principale)
8. Mise à jour GitOps (Argo CD) — Préproduction (branche principale)
9. Mise à jour GitOps (Argo CD) — Production (branche principale, manuel)

## Variables CI

Les variables sans valeur sont à déclarer dans la CI ; les autres sont déjà écrites dans les fichiers.

| Variable | Secret | Valeur | Rôle |
| --- | --- | --- | --- |
| `GITOPS_TOKEN` | oui | à déclarer | Jeton autorisé à pousser sur le dépôt GitOps |
| `GITOPS_REPO` | non | à déclarer | Dépôt GitOps surveillé, sans schéma (hôte/groupe/depot.git) |

## Diagnostics restants

- **Avertissement** (R34) — Argo CD : « Dépôt GitOps » non renseigné : la valeur d'exemple « https://git.example.com/groupe/gitops.git » sera écrite dans les fichiers.
- **Avertissement** (R34) — Envoy Gateway : « Adresse publique de l'application » non renseigné : la valeur d'exemple « api.example.com » sera écrite dans les fichiers.

## Notes

- Mise en route pas à pas, avec les commandes du projet : docs/mise-en-route.md.
- Approbation (« Production ») : déclarer des relecteurs obligatoires sur l'environnement du dépôt (Settings › Environments › Required reviewers), sinon le déploiement part sans attendre.
- Envoy Gateway : platform/gateway.yaml déclare la GatewayClass, la Gateway (HTTP, port 80) et une route par interface web ; ajouter un listener HTTPS avec un certificat (cert-manager) pour le TLS, et vérifier le nom des Services (kubectl -n <espace> get svc).
- External Secrets : le ClusterSecretStore « api » (platform/external-secrets/cluster-secret-store.yaml, appliqué par platform/install.sh) lit OpenBao et les ExternalSecret de l'application s'y réfèrent ; scripts/vault-setup.sh configure la connexion Kubernetes et le rôle « external-secrets ».
- `scripts/test-kind.sh` déploie le pipeline dans un cluster kind jetable (chart Helm) : utile avant la première mise en production.
- `scripts/ci-variables.sh` déclare les 2 variable(s) à renseigner avec GitHub (gh), sans écrire leurs valeurs dans le dépôt.

## Fichiers générés

- `.github/dependabot.yml`
- `.github/workflows/pipeline.yml`
- `PIPELINE.md`
- `charts/api/Chart.yaml`
- `charts/api/templates/deployment.yaml`
- `charts/api/templates/httproute.yaml`
- `charts/api/templates/service.yaml`
- `charts/api/values-dev.yaml`
- `charts/api/values-production.yaml`
- `charts/api/values-staging.yaml`
- `charts/api/values.yaml`
- `deploy/argocd/application.yaml`
- `devops-builder.yaml`
- `docs/mise-en-route.md`
- `infra/cluster/install-k3s.sh`
- `platform/external-secrets/cluster-secret-store.yaml`
- `platform/gateway.yaml`
- `platform/install.sh`
- `scripts/ci-variables.sh`
- `scripts/test-kind.sh`
- `scripts/vault-setup.sh`
