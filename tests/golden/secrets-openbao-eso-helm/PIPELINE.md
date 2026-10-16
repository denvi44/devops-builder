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
| Développement | mon-app | — | 8000 | application | Service mon-app port 80, espace de noms mon-app-dev, exposé par Traefik |
| Développement | MySQL | — | 3306 | MySQL | Service mon-app-mysql, espace de noms mon-app-dev, interne au cluster |
| Développement | Traefik | — | 80 | HTTP | Service Kubernetes, espace de noms traefik |
| Développement | Traefik | — | 443 | HTTPS | Service Kubernetes, espace de noms traefik |
| Développement | OpenBao | — | 8200 | API et interface | Service Kubernetes, espace de noms openbao |
| Développement | Prometheus | — | 9090 | interface et API | Service Kubernetes, espace de noms monitoring |
| Développement | Grafana | — | 3000 | interface web | Service Kubernetes, espace de noms monitoring |
| Préproduction | mon-app | — | 8000 | application | Service mon-app port 80, espace de noms mon-app-staging, exposé par Traefik |
| Préproduction | MySQL | — | 3306 | MySQL | Service mon-app-mysql, espace de noms mon-app-staging, interne au cluster |
| Préproduction | Traefik | — | 80 | HTTP | Service Kubernetes, espace de noms traefik |
| Préproduction | Traefik | — | 443 | HTTPS | Service Kubernetes, espace de noms traefik |
| Préproduction | OpenBao | — | 8200 | API et interface | Service Kubernetes, espace de noms openbao |
| Préproduction | Prometheus | — | 9090 | interface et API | Service Kubernetes, espace de noms monitoring |
| Préproduction | Grafana | — | 3000 | interface web | Service Kubernetes, espace de noms monitoring |
| Production | mon-app | — | 8000 | application | Service mon-app port 80, espace de noms mon-app, exposé par Traefik |
| Production | MySQL | — | 3306 | MySQL | Service mon-app-mysql, espace de noms mon-app, interne au cluster |
| Production | Traefik | — | 80 | HTTP | Service Kubernetes, espace de noms traefik |
| Production | Traefik | — | 443 | HTTPS | Service Kubernetes, espace de noms traefik |
| Production | OpenBao | — | 8200 | API et interface | Service Kubernetes, espace de noms openbao |
| Production | Prometheus | — | 9090 | interface et API | Service Kubernetes, espace de noms monitoring |
| Production | Grafana | — | 3000 | interface web | Service Kubernetes, espace de noms monitoring |

## Données

L'application lit l'URL de connexion complète dans la variable indiquée ; le mot de passe ne figure dans aucun fichier du dépôt.

| Base | Mode | Où | Variable de l'application | Mot de passe / URL | Sauvegarde |
| --- | --- | --- | --- | --- | --- |
| MySQL 8.4 | autogérée | StatefulSet dans l'espace de noms de l'application | `DATABASE_URL` | OpenBao, clé `<espace de noms>/mysql` (External Secrets) | à prévoir (Velero, instantanés) |

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
| Données | MySQL | GPL-2.0 | vérifiée |
| Déploiement | Helm | Apache-2.0 | vérifiée |
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
6. Déploiement Helm — Développement (branche principale)
7. Déploiement Helm — Préproduction (branche principale)
8. Déploiement Helm — Production (branche principale, manuel)

## Variables CI

Les variables sans valeur sont à déclarer dans la CI ; les autres sont déjà écrites dans les fichiers.

| Variable | Secret | Valeur | Rôle |
| --- | --- | --- | --- |
| `KUBECONFIG_DATA_DEV` | oui | à déclarer | Contenu du kubeconfig de k3s (Développement) (base64) |
| `KUBECONFIG_DATA_STAGING` | oui | à déclarer | Contenu du kubeconfig de k3s (Préproduction) (base64) |
| `KUBECONFIG_DATA_PRODUCTION` | oui | à déclarer | Contenu du kubeconfig de k3s (Production) (base64) |
| `RENOVATE_TOKEN` | oui | à déclarer | Jeton de la forge autorisé à ouvrir des merge requests (Renovate) |

## Diagnostics restants

- **Avertissement** (R34) — Traefik : « Adresse publique de l'application » non renseigné : la valeur d'exemple « mon-app.example.com » sera écrite dans les fichiers.
- **Avertissement** (R40) — MySQL tourne dans le cluster et sert « Production », mais rien ne sauvegarde ses données : ajouter Velero, des instantanés de volumes ou les sauvegardes de l'opérateur, et tester la restauration.
- **Avertissement** (R41) — MySQL est déployé en StatefulSet à une seule instance pour « Production » : ni réplication ni bascule. En production, préférer un opérateur ou un service managé.

## Notes

- Mise en route pas à pas, avec les commandes du projet : docs/mise-en-route.md.
- Approbation (« Production ») : le job attend un déclenchement manuel dans GitLab ; protéger l'environnement (Settings › CI/CD › Protected environments) pour restreindre qui peut le lancer.
- Secrets dans OpenBao (moteur KV v2 « secret », clés <espace de noms>/<brique>) : `scripts/secrets-seed.sh <environnement>` les écrit. La CI s'y connecte par JWT (rôle « mon-app-ci » sur auth/jwt, émetteur GitLab ou GitHub, politique de lecture de secret/data/<espace de noms>/*) ou par VAULT_TOKEN.
- External Secrets : le ClusterSecretStore « mon-app » (platform/external-secrets/cluster-secret-store.yaml, appliqué par platform/install.sh) lit OpenBao et chaque ExternalSecret recrée le Secret de base de données attendu par l'application ; scripts/vault-setup.sh configure la connexion Kubernetes et le rôle « external-secrets ».
- Poste de développement : `docker compose -f dev/db/compose.yaml up -d` lance les bases du projet (même version), `dev/db/app.env` donne leurs variables de connexion.
- Renovate : job « renovate » de .gitlab-ci.yml, lancé par une planification de pipeline portant la variable RENOVATE=1 (docs/mise-en-route.md) ; les autres jobs ne tournent pas dans ces pipelines.
- `scripts/test-kind.sh` déploie le pipeline dans un cluster kind jetable (chart Helm) : utile avant la première mise en production.
- `scripts/ci-variables.sh` déclare les 4 variable(s) à renseigner avec GitLab (glab), sans écrire leurs valeurs dans le dépôt.

## Fichiers générés

- `.gitlab-ci.yml`
- `PIPELINE.md`
- `charts/mon-app/Chart.yaml`
- `charts/mon-app/templates/deployment.yaml`
- `charts/mon-app/templates/externalsecrets.yaml`
- `charts/mon-app/templates/mysql.yaml`
- `charts/mon-app/templates/service.yaml`
- `charts/mon-app/values-dev.yaml`
- `charts/mon-app/values-production.yaml`
- `charts/mon-app/values-staging.yaml`
- `charts/mon-app/values.yaml`
- `dev/db/app.env`
- `dev/db/compose.yaml`
- `dev/db/init/mysql/README.md`
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
