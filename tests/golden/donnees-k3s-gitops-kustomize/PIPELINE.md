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
| Préproduction | MongoDB | — | 27017 | MongoDB | Service mon-app-mongodb, espace de noms mon-app-staging, interne au cluster |
| Préproduction | Valkey | — | 6379 | Valkey | Service mon-app-valkey, espace de noms mon-app-staging, interne au cluster |
| Préproduction | Argo CD | — | 8080 | API et interface (service 80/443) | Service Kubernetes, espace de noms argocd |
| Préproduction | Traefik | — | 80 | HTTP | Service Kubernetes, espace de noms traefik |
| Préproduction | Traefik | — | 443 | HTTPS | Service Kubernetes, espace de noms traefik |
| Préproduction | Prometheus | — | 9090 | interface et API | Service Kubernetes, espace de noms monitoring |
| Préproduction | Grafana | — | 3000 | interface web | Service Kubernetes, espace de noms monitoring, exposé par Traefik, hôte grafana.example.com |
| Production | mon-app | — | 8000 | application | Service mon-app port 80, espace de noms mon-app, exposé par Traefik, hôte mon-app.example.com |
| Production | MongoDB | — | 27017 | MongoDB | Service mon-app-mongodb, espace de noms mon-app, interne au cluster |
| Production | Valkey | — | 6379 | Valkey | Service mon-app-valkey, espace de noms mon-app, interne au cluster |
| Production | Argo CD | — | 8080 | API et interface (service 80/443) | Service Kubernetes, espace de noms argocd |
| Production | Traefik | — | 80 | HTTP | Service Kubernetes, espace de noms traefik |
| Production | Traefik | — | 443 | HTTPS | Service Kubernetes, espace de noms traefik |
| Production | Prometheus | — | 9090 | interface et API | Service Kubernetes, espace de noms monitoring |
| Production | Grafana | — | 3000 | interface web | Service Kubernetes, espace de noms monitoring, exposé par Traefik, hôte grafana.example.com |

## Données

L'application lit l'URL de connexion complète dans la variable indiquée ; le mot de passe ne figure dans aucun fichier du dépôt.

| Base | Mode | Où | Variable de l'application | Mot de passe / URL | Sauvegarde |
| --- | --- | --- | --- | --- | --- |
| MongoDB 8.0 | autogérée | StatefulSet dans l'espace de noms de l'application | `MONGODB_URI` | Secret `mon-app-mongodb` (GitOps : External Secrets ou SOPS) | à prévoir (Velero, instantanés) |
| Valkey 8 | autogérée | StatefulSet dans l'espace de noms de l'application | `REDIS_URL` | Secret `mon-app-valkey` (GitOps : External Secrets ou SOPS) | à prévoir (Velero, instantanés) |

## Briques

| Étape | Brique | Licence | Fiche |
| --- | --- | --- | --- |
| Source | GitLab | MIT | vérifiée |
| Build | GitLab CI | MIT | vérifiée |
| Build | BuildKit (docker buildx) | Apache-2.0 | vérifiée |
| Build | Renovate | AGPL-3.0 | vérifiée |
| Tests & qualité | Tests unitaires | MIT | vérifiée |
| Sécurité | Gitleaks | MIT | vérifiée |
| Sécurité | Trivy | Apache-2.0 | vérifiée |
| Sécurité | Cosign | Apache-2.0 | vérifiée |
| Infrastructure | k3s | Apache-2.0 | vérifiée |
| Données | MongoDB | SSPL-1.0 | vérifiée |
| Données | Valkey | BSD-3-Clause | vérifiée |
| Déploiement | Kustomize | Apache-2.0 | vérifiée |
| Déploiement | Argo CD | Apache-2.0 | vérifiée |
| Plateforme | Traefik | MIT | vérifiée |
| Plateforme | cert-manager | Apache-2.0 | vérifiée |
| Observabilité | Prometheus | Apache-2.0 | vérifiée |
| Observabilité | Grafana | AGPL-3.0 | vérifiée |

## Étapes CI

Orchestrateur : GitLab CI. Image publiée : `$CI_REGISTRY_IMAGE:<commit>`.

1. Tests unitaires
2. Recherche de secrets
3. Build et publication de l'image (BuildKit (docker buildx))
4. Scan de vulnérabilités Trivy
5. Signature de l'image (Cosign) (branche principale)
6. Mise à jour GitOps (Argo CD) — Préproduction (branche principale)
7. Mise à jour GitOps (Argo CD) — Production (branche principale, manuel)

## Variables CI

Les variables sans valeur sont à déclarer dans la CI ; les autres sont déjà écrites dans les fichiers.

| Variable | Secret | Valeur | Rôle |
| --- | --- | --- | --- |
| `GITOPS_TOKEN` | oui | à déclarer | Jeton autorisé à pousser sur le dépôt GitOps |
| `GITOPS_REPO` | non | à déclarer | Dépôt GitOps surveillé, sans schéma (hôte/groupe/depot.git) |
| `RENOVATE_TOKEN` | oui | à déclarer | Jeton de la forge autorisé à ouvrir des merge requests (Renovate) |

## Diagnostics restants

- **Avertissement** (R34) — Argo CD : « Dépôt GitOps » non renseigné : la valeur d'exemple « https://git.example.com/groupe/gitops.git » sera écrite dans les fichiers.
- **Avertissement** (R34) — Traefik : « Adresse publique de l'application » non renseigné : la valeur d'exemple « mon-app.example.com » sera écrite dans les fichiers.
- **Avertissement** (R40) — MongoDB tourne dans le cluster et sert « Production », mais rien ne sauvegarde ses données : ajouter Velero, des instantanés de volumes ou les sauvegardes de l'opérateur, et tester la restauration.
- **Avertissement** (R41) — MongoDB est déployé en StatefulSet à une seule instance pour « Production » : ni réplication ni bascule. En production, préférer un opérateur ou un service managé.
- **Info** (R24) — MongoDB est sous licence SSPL-1.0.

## Notes

- Mise en route pas à pas, avec les commandes du projet : docs/mise-en-route.md.
- Approbation (« Production ») : le job attend un déclenchement manuel dans GitLab ; protéger l'environnement (Settings › CI/CD › Protected environments) pour restreindre qui peut le lancer.
- Bases de données avec GitOps : la CI ne touche pas au cluster ; créer dans chaque espace de noms le Secret « mon-app-mongodb » (clés password et url), « mon-app-valkey » (clés password et url), par External Secrets ou SOPS.
- Poste de développement : `docker compose -f dev/db/compose.yaml up -d` lance les bases du projet (même version), `dev/db/app.env` donne leurs variables de connexion.
- MongoDB : l'application se connecte avec le compte administrateur initial ; créer un compte dédié aux droits limités avant la production.
- Renovate : job « renovate » de .gitlab-ci.yml, lancé par une planification de pipeline portant la variable RENOVATE=1 (docs/mise-en-route.md) ; les autres jobs ne tournent pas dans ces pipelines.
- `scripts/test-kind.sh` déploie le pipeline dans un cluster kind jetable (overlay Kustomize) : utile avant la première mise en production.
- `scripts/ci-variables.sh` déclare les 3 variable(s) à renseigner avec GitLab (glab), sans écrire leurs valeurs dans le dépôt.

## Fichiers générés

- `.gitlab-ci.yml`
- `PIPELINE.md`
- `deploy/argocd/application.yaml`
- `deploy/kustomize/base/deployment.yaml`
- `deploy/kustomize/base/kustomization.yaml`
- `deploy/kustomize/base/mongodb.yaml`
- `deploy/kustomize/base/service.yaml`
- `deploy/kustomize/base/valkey.yaml`
- `deploy/kustomize/overlays/production/ingress.yaml`
- `deploy/kustomize/overlays/production/kustomization.yaml`
- `deploy/kustomize/overlays/staging/ingress.yaml`
- `deploy/kustomize/overlays/staging/kustomization.yaml`
- `dev/db/app.env`
- `dev/db/compose.yaml`
- `dev/db/init/mongodb/README.md`
- `devops-builder.yaml`
- `docs/mise-en-route.md`
- `infra/cluster/install-k3s.sh`
- `platform/install.sh`
- `renovate.json`
- `scripts/ci-variables.sh`
- `scripts/test-kind.sh`
