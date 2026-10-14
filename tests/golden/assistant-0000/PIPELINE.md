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
| Prometheus | 9090 | 9090 | interface et API | publié sur l'hôte Docker |
| Grafana | 3000 | 3000 | interface web | publié sur l'hôte Docker |
| SonarQube | 9002 | 9000 | interface web | publié sur l'hôte Docker |

## Dimensionnement

Besoin estimé à partir des services Compose de l'hôte (marge de 25 %), pour chaque environnement porté, plus le système et Docker. Un ordre de grandeur pour une charge modeste, à confirmer par la supervision.

Services : mon-app (512 Mio, estimé), traefik (128 Mio, estimé), prometheus (1024 Mio, estimé), grafana (512 Mio), sonarqube (2048 Mio).

| Environnements | Besoin | Type retenu | Verdict |
| --- | --- | --- | --- |
| production | 2 vCPU, 5,7 Gio | hôte existant | prévoir au moins 2 vCPU et 5,7 Gio |

## Briques

| Étape | Brique | Licence | Fiche |
| --- | --- | --- | --- |
| Source | GitLab | MIT | vérifiée |
| Build | GitLab CI | MIT | vérifiée |
| Build | BuildKit (docker buildx) | Apache-2.0 | vérifiée |
| Build | Renovate | AGPL-3.0 | vérifiée |
| Tests & qualité | Tests unitaires | MIT | vérifiée |
| Tests & qualité | SonarQube | LGPL-3.0 | vérifiée |
| Déploiement | Docker Compose | Apache-2.0 | vérifiée |
| Plateforme | Traefik | MIT | vérifiée |
| Observabilité | Prometheus | Apache-2.0 | vérifiée |
| Observabilité | Grafana | AGPL-3.0 | vérifiée |

## Étapes CI

Orchestrateur : GitLab CI. Image publiée : `$CI_REGISTRY_IMAGE:<commit>`.

1. Tests unitaires
2. Qualité SonarQube
3. Build et publication de l'image (BuildKit (docker buildx))
4. Déploiement Docker Compose (SSH) (branche principale)

## Variables CI

Les variables sans valeur sont à déclarer dans la CI ; les autres sont déjà écrites dans les fichiers.

| Variable | Secret | Valeur | Rôle |
| --- | --- | --- | --- |
| `SONAR_HOST_URL` | non | à déclarer | URL du serveur SonarQube |
| `SONAR_TOKEN` | oui | à déclarer | Jeton d'analyse SonarQube |
| `SSH_PRIVATE_KEY` | oui | à déclarer | Clé SSH de déploiement vers l'hôte Docker |
| `SSH_KNOWN_HOSTS` | non | à déclarer | Facultatif : clés d'hôte attendues (ssh-keyscan) ; sans elle, la clé est acceptée à la première connexion de chaque job |
| `DEPLOY_HOST` | non | à déclarer | Hôte Docker cible (utilisateur@hôte) |
| `RENOVATE_TOKEN` | oui | à déclarer | Jeton de la forge autorisé à ouvrir des merge requests (Renovate) |

## Diagnostics restants

Aucun.

## Notes

- Mise en route pas à pas, avec les commandes du projet : docs/mise-en-route.md.
- Renovate : lancer l'image renovate/renovate dans un job planifié (quotidien) avec RENOVATE_TOKEN ; renovate.json règle son comportement.
- `scripts/ci-variables.sh` déclare les 6 variable(s) à renseigner avec GitLab (glab), sans écrire leurs valeurs dans le dépôt.

## Fichiers générés

- `.gitlab-ci.yml`
- `PIPELINE.md`
- `deploy/docker-compose.yml`
- `devops-builder.yaml`
- `docs/mise-en-route.md`
- `renovate.json`
- `scripts/ci-variables.sh`
