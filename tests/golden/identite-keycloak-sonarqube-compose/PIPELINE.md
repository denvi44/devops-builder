# Mon projet — pipeline généré

Généré par DevOps Builder le AAAA-MM-JJ. Cible : Hôte Docker unique.

## Environnements

Ordre de promotion : la même image est déployée successivement dans chaque environnement.

| Environnement | Type | Approbation | Cluster | Espace de noms / projet |
| --- | --- | --- | --- | --- |
| Production (`production`) | Production | non | — | `mon-app` |

## Ports

| Composant | Port publié | Port du conteneur | Usage | Exposition |
| --- | --- | --- | --- | --- |
| mon-app | — | 8000 | application | via Traefik, hôte mon-app.example.com |
| Traefik | 80 | 80 | HTTP | publié sur l'hôte Docker |
| Traefik | 443 | 443 | HTTPS | publié sur l'hôte Docker |
| Prometheus | — | 9090 | interface et API | réseau interne Compose, non publié |
| Grafana | — | 3000 | interface web | via Traefik, hôte grafana.boutique.fr |
| Grafana | — | 3000 | interface web | via Traefik, hôte grafana.boutique.fr |
| SonarQube | — | 9000 | interface web | via Traefik, hôte sonarqube.boutique.fr |
| Keycloak | — | 8080 | interface et OIDC | via Traefik, hôte auth.boutique.fr |

## Dimensionnement

Besoin estimé à partir des services Compose de l'hôte (marge de 25 %), pour chaque environnement porté, plus le système et Docker. Un ordre de grandeur pour une charge modeste, à confirmer par la supervision.

Services : mon-app (512 Mio, estimé), traefik (128 Mio, estimé), prometheus (1024 Mio, estimé), grafana (512 Mio), sonarqube (2560 Mio), keycloak (1250 Mio), keycloak-db (512 Mio, estimé).

| Environnements | Besoin | Type retenu | Verdict |
| --- | --- | --- | --- |
| production | 2 vCPU, 8,4 Gio | hôte existant | prévoir au moins 2 vCPU et 8,4 Gio |

## Briques

| Étape | Brique | Licence | Fiche |
| --- | --- | --- | --- |
| Source | GitLab | MIT | vérifiée |
| Build | GitLab CI | MIT | vérifiée |
| Build | BuildKit (docker buildx) | Apache-2.0 | vérifiée |
| Build | Renovate | AGPL-3.0 | vérifiée |
| Tests & qualité | Tests unitaires | MIT | vérifiée |
| Tests & qualité | SonarQube | LGPL-3.0 | vérifiée |
| Sécurité | Gitleaks | MIT | vérifiée |
| Sécurité | Trivy | Apache-2.0 | vérifiée |
| Sécurité | Cosign | Apache-2.0 | vérifiée |
| Déploiement | Docker Compose | Apache-2.0 | vérifiée |
| Plateforme | Traefik | MIT | vérifiée |
| Plateforme | Keycloak | Apache-2.0 | vérifiée |
| Observabilité | Prometheus | Apache-2.0 | vérifiée |
| Observabilité | Grafana | AGPL-3.0 | vérifiée |
| Observabilité | Grafana | AGPL-3.0 | vérifiée |

## Étapes CI

Orchestrateur : GitLab CI. Image publiée : `$CI_REGISTRY_IMAGE:<commit>`.

1. Tests unitaires
2. Qualité SonarQube
3. Recherche de secrets
4. Build et publication de l'image (BuildKit (docker buildx))
5. Scan de vulnérabilités Trivy
6. Signature de l'image (Cosign) (branche principale)
7. Déploiement Docker Compose (SSH) (branche principale)

## Variables CI

Les variables sans valeur sont à déclarer dans la CI ; les autres sont déjà écrites dans les fichiers.

| Variable | Secret | Valeur | Rôle |
| --- | --- | --- | --- |
| `SONAR_HOST_URL` | non | à déclarer | URL du serveur SonarQube |
| `SONAR_TOKEN` | oui | à déclarer | Jeton d'analyse SonarQube |
| `KEYCLOAK_DB_PASSWORD` | oui | à déclarer | Mot de passe de la base de Keycloak |
| `KEYCLOAK_ADMIN_PASSWORD` | oui | à déclarer | Mot de passe de l'administrateur temporaire du premier démarrage de Keycloak |
| `GRAFANA_OIDC_SECRET` | oui | à déclarer | Secret du client OIDC grafana (sortie grafana_client_secret de infra/keycloak) ; vide : connexion OIDC inactive |
| `SSH_PRIVATE_KEY` | oui | à déclarer | Clé SSH de déploiement vers l'hôte Docker |
| `SSH_KNOWN_HOSTS` | non | à déclarer | Facultatif : clés d'hôte attendues (ssh-keyscan) ; sans elle, la clé est acceptée à la première connexion de chaque job |
| `DEPLOY_HOST` | non | à déclarer | Hôte Docker cible (utilisateur@hôte) |
| `RENOVATE_TOKEN` | oui | à déclarer | Jeton de la forge autorisé à ouvrir des merge requests (Renovate) |

## Diagnostics restants

- **Avertissement** (R34) — Traefik : « Adresse publique de l'application » non renseigné : la valeur d'exemple « mon-app.example.com » sera écrite dans les fichiers.
- **Avertissement** (R55) — Deux briques portent le même identifiant « grafana » : donner un nom d'instance différent à chacune (une seule est générée).

## Notes

- Mise en route pas à pas, avec les commandes du projet : docs/mise-en-route.md.
- Keycloak : émetteur OIDC https://auth.boutique.fr/realms/mon-app ; l'application reçoit OIDC_ISSUER_URL et OIDC_CLIENT_ID (client public, PKCE) ; clients des outils : Grafana, SonarQube, droits d'administration au groupe « admins ». Le realm est décrit en Terraform dans infra/keycloak/ (docs/mise-en-route.md).
- Renovate : job « renovate » de .gitlab-ci.yml, lancé par une planification de pipeline portant la variable RENOVATE=1 (docs/mise-en-route.md) ; les autres jobs ne tournent pas dans ces pipelines.
- `scripts/ci-variables.sh` déclare les 9 variable(s) à renseigner avec GitLab (glab), sans écrire leurs valeurs dans le dépôt.

## Fichiers générés

- `.gitlab-ci.yml`
- `PIPELINE.md`
- `deploy/docker-compose.yml`
- `deploy/secrets.sh`
- `devops-builder.yaml`
- `docs/mise-en-route.md`
- `infra/keycloak/.gitignore`
- `infra/keycloak/main.tf`
- `infra/keycloak/outputs.tf`
- `infra/keycloak/variables.tf`
- `infra/keycloak/versions.tf`
- `renovate.json`
- `scripts/ci-variables.sh`
- `scripts/db-backup.sh`
- `scripts/db-restore.sh`
