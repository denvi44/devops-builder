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
| Préproduction | mon-app | — | 8000 | application | Service mon-app port 80, espace de noms mon-app-staging, exposé par Traefik |
| Préproduction | CloudNativePG | — | 5432 | PostgreSQL | Service mon-app-pg-rw, espace de noms mon-app-staging, interne au cluster |
| Préproduction | Valkey | — | 6379 | Valkey | Service mon-app-valkey, espace de noms mon-app-staging, interne au cluster |
| Préproduction | Traefik | — | 80 | HTTP | Service Kubernetes, espace de noms traefik |
| Préproduction | Traefik | — | 443 | HTTPS | Service Kubernetes, espace de noms traefik |
| Préproduction | OpenBao | — | 8200 | API et interface | Service Kubernetes, espace de noms openbao |
| Préproduction | Prometheus | — | 9090 | interface et API | Service Kubernetes, espace de noms monitoring |
| Préproduction | Grafana | — | 3000 | interface web | Service Kubernetes, espace de noms monitoring |
| Production | mon-app | — | 8000 | application | Service mon-app port 80, espace de noms mon-app, exposé par Traefik |
| Production | CloudNativePG | — | 5432 | PostgreSQL | Service mon-app-pg-rw, espace de noms mon-app, interne au cluster |
| Production | Valkey | — | 6379 | Valkey | Service mon-app-valkey, espace de noms mon-app, interne au cluster |
| Production | Traefik | — | 80 | HTTP | Service Kubernetes, espace de noms traefik |
| Production | Traefik | — | 443 | HTTPS | Service Kubernetes, espace de noms traefik |
| Production | OpenBao | — | 8200 | API et interface | Service Kubernetes, espace de noms openbao |
| Production | Prometheus | — | 9090 | interface et API | Service Kubernetes, espace de noms monitoring |
| Production | Grafana | — | 3000 | interface web | Service Kubernetes, espace de noms monitoring |

## Données

L'application lit l'URL de connexion complète dans la variable indiquée ; le mot de passe ne figure dans aucun fichier du dépôt.

| Base | Mode | Où | Variable de l'application | Mot de passe / URL | Sauvegarde |
| --- | --- | --- | --- | --- | --- |
| CloudNativePG | opérateur Kubernetes | Cluster CloudNativePG dans l'espace de noms de l'application | `DATABASE_URL` | Secret `mon-app-pg-app` créé par l'opérateur | plugin Barman Cloud ou instantanés de volumes, à configurer |
| Valkey 8 | autogérée | StatefulSet dans l'espace de noms de l'application | `REDIS_URL` | OpenBao, clé `<espace de noms>/valkey` (External Secrets) | à prévoir (Velero, instantanés) |

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
| Données | CloudNativePG | Apache-2.0 | vérifiée |
| Données | Valkey | BSD-3-Clause | vérifiée |
| Déploiement | Kustomize | Apache-2.0 | vérifiée |
| Plateforme | Traefik | MIT | vérifiée |
| Plateforme | cert-manager | Apache-2.0 | vérifiée |
| Plateforme | OpenBao | MPL-2.0 | vérifiée |
| Plateforme | External Secrets Operator | Apache-2.0 | vérifiée |
| Observabilité | Prometheus | Apache-2.0 | vérifiée |
| Observabilité | Grafana | AGPL-3.0 | vérifiée |

## Étapes CI

Orchestrateur : GitLab CI. Image publiée : `$CI_REGISTRY_IMAGE:<commit>`.

1. Tests unitaires
2. Recherche de secrets
3. Build et publication de l'image (BuildKit (docker buildx))
4. Scan de vulnérabilités Trivy
5. Signature de l'image (Cosign) (branche principale)
6. Déploiement Kustomize — Préproduction (branche principale)
7. Déploiement Kustomize — Production (branche principale, manuel)

## Variables CI

Les variables sans valeur sont à déclarer dans la CI ; les autres sont déjà écrites dans les fichiers.

| Variable | Secret | Valeur | Rôle |
| --- | --- | --- | --- |
| `KUBECONFIG_DATA_STAGING` | oui | à déclarer | Contenu du kubeconfig de k3s (Préproduction) (base64) |
| `KUBECONFIG_DATA_PRODUCTION` | oui | à déclarer | Contenu du kubeconfig de k3s (Production) (base64) |
| `RENOVATE_TOKEN` | oui | à déclarer | Jeton de la forge autorisé à ouvrir des merge requests (Renovate) |

## Diagnostics restants

- **Avertissement** (R40) — CloudNativePG tourne dans le cluster et sert « Production », mais rien ne sauvegarde ses données : ajouter Velero, des instantanés de volumes ou les sauvegardes de l'opérateur, et tester la restauration.

## Notes

- Mise en route pas à pas, avec les commandes du projet : docs/mise-en-route.md.
- Approbation (« Production ») : le job attend un déclenchement manuel dans GitLab ; protéger l'environnement (Settings › CI/CD › Protected environments) pour restreindre qui peut le lancer.
- Secrets dans OpenBao (moteur KV v2 « secret », clés <espace de noms>/<brique>) : `scripts/secrets-seed.sh <environnement>` les écrit. La CI s'y connecte par JWT (rôle « mon-app-ci » sur auth/jwt, émetteur GitLab ou GitHub, politique de lecture de secret/data/<espace de noms>/*) ou par VAULT_TOKEN.
- External Secrets : le ClusterSecretStore « mon-app » (platform/external-secrets/cluster-secret-store.yaml, appliqué par platform/install.sh) lit OpenBao et chaque ExternalSecret recrée le Secret de base de données attendu par l'application ; scripts/vault-setup.sh configure la connexion Kubernetes et le rôle « external-secrets ».
- CloudNativePG : l'opérateur est installé par platform/install.sh ; le Cluster crée le Secret « <cluster>-app » (clé uri) lu par l'application. Sauvegardes : configurer le plugin Barman Cloud vers un stockage objet, ou des instantanés de volumes.
- Renovate : lancer l'image renovate/renovate dans un job planifié (quotidien) avec RENOVATE_TOKEN ; renovate.json règle son comportement.
- `scripts/test-kind.sh` déploie le pipeline dans un cluster kind jetable (overlay Kustomize) : utile avant la première mise en production.
- `scripts/ci-variables.sh` déclare les 3 variable(s) à renseigner avec GitLab (glab), sans écrire leurs valeurs dans le dépôt.

## Fichiers générés

- `.gitlab-ci.yml`
- `PIPELINE.md`
- `deploy/kustomize/base/cloudnative-pg.yaml`
- `deploy/kustomize/base/deployment.yaml`
- `deploy/kustomize/base/kustomization.yaml`
- `deploy/kustomize/base/service.yaml`
- `deploy/kustomize/base/valkey.yaml`
- `deploy/kustomize/overlays/production/externalsecrets.yaml`
- `deploy/kustomize/overlays/production/kustomization.yaml`
- `deploy/kustomize/overlays/staging/externalsecrets.yaml`
- `deploy/kustomize/overlays/staging/kustomization.yaml`
- `devops-builder.yaml`
- `docs/mise-en-route.md`
- `infra/cluster/install-k3s.sh`
- `platform/external-secrets/cluster-secret-store.yaml`
- `platform/install.sh`
- `renovate.json`
- `scripts/ci-variables.sh`
- `scripts/secrets-seed.sh`
- `scripts/test-kind.sh`
- `scripts/vault-setup.sh`
