# Mon projet — pipeline généré

Généré par DevOps Builder le AAAA-MM-JJ. Cible : Hôte Docker unique.

## Environnements

Ordre de promotion : la même image est déployée successivement dans chaque environnement.

| Environnement | Type | Approbation | Cluster | Espace de noms / projet |
| --- | --- | --- | --- | --- |
| Développement (`dev`) | Développement | non | — | `mon-app-dev` |
| Préproduction (`staging`) | Préproduction | non | — | `mon-app-staging` |
| Production (`production`) | Production | oui | — | `mon-app` |

## Ports

Hôte partagé `vm-hors-prod` : Développement (+0), Préproduction (+10000). Les ports publiés de chaque environnement sont dans `deploy/env/<environnement>.env`.

| Environnement | Composant | Port publié | Port du conteneur | Usage | Exposition |
| --- | --- | --- | --- | --- | --- |
| Développement | mon-app | — | 8000 | application | via Traefik, hôte mon-app-dev.example.com |
| Développement | Traefik | 80 | 80 | HTTP | publié sur l'hôte Docker |
| Développement | Traefik | 443 | 443 | HTTPS | publié sur l'hôte Docker |
| Développement | Prometheus | 9090 | 9090 | interface et API | publié sur l'hôte Docker |
| Développement | Grafana | 3000 | 3000 | interface web | publié sur l'hôte Docker |
| Préproduction | mon-app | — | 8000 | application | via Traefik, hôte mon-app-staging.example.com |
| Préproduction | Traefik | 10080 | 80 | HTTP | publié sur l'hôte Docker |
| Préproduction | Traefik | 10443 | 443 | HTTPS | publié sur l'hôte Docker |
| Préproduction | Prometheus | 19090 | 9090 | interface et API | publié sur l'hôte Docker |
| Préproduction | Grafana | 13000 | 3000 | interface web | publié sur l'hôte Docker |
| Production | mon-app | — | 8000 | application | via Traefik, hôte mon-app.example.com |
| Production | Traefik | 80 | 80 | HTTP | publié sur l'hôte Docker |
| Production | Traefik | 443 | 443 | HTTPS | publié sur l'hôte Docker |
| Production | Prometheus | 9090 | 9090 | interface et API | publié sur l'hôte Docker |
| Production | Grafana | 3000 | 3000 | interface web | publié sur l'hôte Docker |

## Dimensionnement

Besoin estimé à partir des services Compose de l'hôte (marge de 25 %), pour chaque environnement porté, plus le système et Docker. Un ordre de grandeur pour une charge modeste, à confirmer par la supervision.

Services : mon-app (512 Mio, estimé), traefik (128 Mio, estimé), prometheus (1024 Mio, estimé), grafana (512 Mio).

| Machines | Environnements | Besoin | Type retenu | Verdict |
| --- | --- | --- | --- | --- |
| `vm-hors-prod` | dev, staging | 2 vCPU, 5,8 Gio | hôte existant | prévoir au moins 2 vCPU et 5,8 Gio |
| `production` | production | 1 vCPU, 3,2 Gio | hôte existant | prévoir au moins 1 vCPU et 3,2 Gio |

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
| Déploiement | Docker Compose | Apache-2.0 | vérifiée |
| Plateforme | Traefik | MIT | vérifiée |
| Observabilité | Prometheus | Apache-2.0 | vérifiée |
| Observabilité | Grafana | AGPL-3.0 | vérifiée |

## Étapes CI

Orchestrateur : GitLab CI. Image publiée : `$CI_REGISTRY_IMAGE:<commit>`.

1. Tests unitaires
2. Recherche de secrets
3. Build et publication de l'image (BuildKit (docker buildx))
4. Scan de vulnérabilités Trivy
5. Signature de l'image (Cosign) (branche principale)
6. Déploiement Docker Compose (SSH) — Développement (branche principale)
7. Déploiement Docker Compose (SSH) — Préproduction (branche principale)
8. Déploiement Docker Compose (SSH) — Production (branche principale, manuel)

## Variables CI

Les variables sans valeur sont à déclarer dans la CI ; les autres sont déjà écrites dans les fichiers.

| Variable | Secret | Valeur | Rôle |
| --- | --- | --- | --- |
| `SSH_PRIVATE_KEY` | oui | à déclarer | Clé SSH de déploiement vers l'hôte Docker |
| `SSH_KNOWN_HOSTS` | non | à déclarer | Facultatif : clés d'hôte attendues (ssh-keyscan) ; sans elle, la clé est acceptée à la première connexion de chaque job |
| `DEPLOY_HOST_DEV` | non | à déclarer | Hôte Docker cible (Développement) (utilisateur@hôte) |
| `DEPLOY_HOST_STAGING` | non | à déclarer | Hôte Docker cible (Préproduction) (utilisateur@hôte) |
| `DEPLOY_HOST_PRODUCTION` | non | à déclarer | Hôte Docker cible (Production) (utilisateur@hôte) |
| `RENOVATE_TOKEN` | oui | à déclarer | Jeton de la forge autorisé à ouvrir des merge requests (Renovate) |

## Diagnostics restants

Aucun.

## Notes

- Mise en route pas à pas, avec les commandes du projet : docs/mise-en-route.md.
- Approbation (« Production ») : le job attend un déclenchement manuel dans GitLab ; protéger l'environnement (Settings › CI/CD › Protected environments) pour restreindre qui peut le lancer.
- Plusieurs environnements partagent un hôte Docker : leurs ports publiés sont décalés (deploy/env/<environnement>.env, copié en .env à côté du fichier Compose).
- Renovate : lancer l'image renovate/renovate dans un job planifié (quotidien) avec RENOVATE_TOKEN ; renovate.json règle son comportement.
- `scripts/ci-variables.sh` déclare les 6 variable(s) à renseigner avec GitLab (glab), sans écrire leurs valeurs dans le dépôt.

## Fichiers générés

- `.gitlab-ci.yml`
- `PIPELINE.md`
- `deploy/docker-compose.yml`
- `deploy/env/dev.env`
- `deploy/env/production.env`
- `deploy/env/staging.env`
- `devops-builder.yaml`
- `docs/mise-en-route.md`
- `renovate.json`
- `scripts/ci-variables.sh`
