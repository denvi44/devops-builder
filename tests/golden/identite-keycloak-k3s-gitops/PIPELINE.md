# Mon projet — pipeline généré

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
| Développement | mon-app | — | 8000 | application | Service mon-app port 80, espace de noms mon-app-dev, exposé par Traefik, hôte dev.mon-app.example.com |
| Développement | Argo CD | — | 8080 | API et interface (service 80/443) | Service Kubernetes, espace de noms argocd, exposé par Traefik, hôte argocd.boutique.fr |
| Développement | Traefik | — | 80 | HTTP | Service Kubernetes, espace de noms traefik |
| Développement | Traefik | — | 443 | HTTPS | Service Kubernetes, espace de noms traefik |
| Développement | OpenBao | — | 8200 | API et interface | Service Kubernetes, espace de noms openbao |
| Développement | Prometheus | — | 9090 | interface et API | Service Kubernetes, espace de noms monitoring |
| Développement | Grafana | — | 3000 | interface web | Service Kubernetes, espace de noms monitoring, exposé par Traefik, hôte grafana.boutique.fr |
| Préproduction | mon-app | — | 8000 | application | Service mon-app port 80, espace de noms mon-app-staging, exposé par Traefik, hôte staging.mon-app.example.com |
| Préproduction | Argo CD | — | 8080 | API et interface (service 80/443) | Service Kubernetes, espace de noms argocd, exposé par Traefik, hôte argocd.boutique.fr |
| Préproduction | Traefik | — | 80 | HTTP | Service Kubernetes, espace de noms traefik |
| Préproduction | Traefik | — | 443 | HTTPS | Service Kubernetes, espace de noms traefik |
| Préproduction | OpenBao | — | 8200 | API et interface | Service Kubernetes, espace de noms openbao |
| Préproduction | Prometheus | — | 9090 | interface et API | Service Kubernetes, espace de noms monitoring |
| Préproduction | Grafana | — | 3000 | interface web | Service Kubernetes, espace de noms monitoring, exposé par Traefik, hôte grafana.boutique.fr |
| Production | mon-app | — | 8000 | application | Service mon-app port 80, espace de noms mon-app, exposé par Traefik, hôte mon-app.example.com |
| Production | Argo CD | — | 8080 | API et interface (service 80/443) | Service Kubernetes, espace de noms argocd, exposé par Traefik, hôte argocd.boutique.fr |
| Production | Traefik | — | 80 | HTTP | Service Kubernetes, espace de noms traefik |
| Production | Traefik | — | 443 | HTTPS | Service Kubernetes, espace de noms traefik |
| Production | OpenBao | — | 8200 | API et interface | Service Kubernetes, espace de noms openbao |
| Production | Prometheus | — | 9090 | interface et API | Service Kubernetes, espace de noms monitoring |
| Production | Grafana | — | 3000 | interface web | Service Kubernetes, espace de noms monitoring, exposé par Traefik, hôte grafana.boutique.fr |

## Briques

| Étape | Brique | Licence | Fiche |
| --- | --- | --- | --- |
| Source | GitHub | proprietary | vérifiée |
| Build | GitHub Actions | proprietary | vérifiée |
| Build | BuildKit (docker buildx) | Apache-2.0 | vérifiée |
| Build | Dependabot | proprietary | vérifiée |
| Tests & qualité | Tests unitaires | MIT | vérifiée |
| Sécurité | Gitleaks | MIT | vérifiée |
| Sécurité | Trivy | Apache-2.0 | vérifiée |
| Sécurité | Cosign | Apache-2.0 | vérifiée |
| Artefacts | GitHub Container Registry | proprietary | vérifiée |
| Infrastructure | k3s | Apache-2.0 | vérifiée |
| Déploiement | Helm | Apache-2.0 | vérifiée |
| Déploiement | Argo CD | Apache-2.0 | vérifiée |
| Plateforme | Traefik | MIT | vérifiée |
| Plateforme | cert-manager | Apache-2.0 | vérifiée |
| Plateforme | OpenBao | MPL-2.0 | vérifiée |
| Plateforme | External Secrets Operator | Apache-2.0 | vérifiée |
| Plateforme | Keycloak | Apache-2.0 | vérifiée |
| Observabilité | Prometheus | Apache-2.0 | vérifiée |
| Observabilité | Grafana | AGPL-3.0 | vérifiée |

## Étapes CI

Orchestrateur : GitHub Actions. Image publiée : `ghcr.io/OWNER/mon-app:<commit>`.

1. Tests unitaires
2. Recherche de secrets
3. Build et publication de l'image (BuildKit (docker buildx))
4. Scan de vulnérabilités Trivy
5. Signature de l'image (Cosign) (branche principale)
6. Mise à jour GitOps (Argo CD) — Développement (branche principale)
7. Mise à jour GitOps (Argo CD) — Préproduction (branche principale)
8. Mise à jour GitOps (Argo CD) — Production (branche principale, manuel)

## Variables CI

Les variables sans valeur sont à déclarer dans la CI ; les autres sont déjà écrites dans les fichiers.

| Variable | Secret | Valeur | Rôle |
| --- | --- | --- | --- |
| `GITOPS_TOKEN` | oui | à déclarer | Jeton autorisé à pousser sur le dépôt GitOps |
| `GITOPS_REPO` | non | à déclarer | Dépôt GitOps surveillé, sans schéma (hôte/groupe/depot.git) |

## Diagnostics restants

- **Avertissement** (R34) — Argo CD : « Dépôt GitOps » non renseigné : la valeur d'exemple « https://git.example.com/groupe/gitops.git » sera écrite dans les fichiers.
- **Avertissement** (R34) — Traefik : « Adresse publique de l'application » non renseigné : la valeur d'exemple « mon-app.example.com » sera écrite dans les fichiers.

## Notes

- Mise en route pas à pas, avec les commandes du projet : docs/mise-en-route.md.
- Approbation (« Production ») : déclarer des relecteurs obligatoires sur l'environnement du dépôt (Settings › Environments › Required reviewers), sinon le déploiement part sans attendre.
- External Secrets : le ClusterSecretStore « mon-app » (platform/external-secrets/cluster-secret-store.yaml, appliqué par platform/install.sh) lit OpenBao et les ExternalSecret de l'application s'y réfèrent ; scripts/vault-setup.sh configure la connexion Kubernetes et le rôle « external-secrets ».
- Keycloak : émetteur OIDC https://auth.boutique.fr/realms/mon-app ; l'application reçoit OIDC_ISSUER_URL et OIDC_CLIENT_ID (client public, PKCE) ; clients des outils : OpenBao, Argo CD, Grafana, droits d'administration au groupe « admins ». Le realm est décrit en Terraform dans infra/keycloak/ (docs/mise-en-route.md).
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
- `charts/mon-app/values-dev.yaml`
- `charts/mon-app/values-production.yaml`
- `charts/mon-app/values-staging.yaml`
- `charts/mon-app/values.yaml`
- `deploy/argocd/application.yaml`
- `devops-builder.yaml`
- `docs/mise-en-route.md`
- `infra/cluster/install-k3s.sh`
- `infra/keycloak/.gitignore`
- `infra/keycloak/main.tf`
- `infra/keycloak/outputs.tf`
- `infra/keycloak/variables.tf`
- `infra/keycloak/versions.tf`
- `platform/external-secrets/cluster-secret-store.yaml`
- `platform/install.sh`
- `platform/keycloak/keycloak.yaml`
- `platform/values/argo-cd.yaml`
- `platform/values/grafana.yaml`
- `scripts/ci-variables.sh`
- `scripts/test-kind.sh`
- `scripts/vault-setup.sh`
