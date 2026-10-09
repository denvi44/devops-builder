# Mon projet — pipeline généré

Généré par DevOps Builder le AAAA-MM-JJ. Cible : Hôte Docker unique.

## Environnements

Ordre de promotion : la même image est déployée successivement dans chaque environnement.

| Environnement | Type | Approbation | Cluster | Espace de noms / projet |
| --- | --- | --- | --- | --- |
| Développement (`dev`) | Développement | non | — | `mon-app-dev` |
| Préproduction (`staging`) | Préproduction | non | — | `mon-app-staging` |
| Production (`production`) | Production | oui | — | `mon-app` |

## Briques

| Étape | Brique | Licence | Fiche |
| --- | --- | --- | --- |
| Source | GitHub | proprietary | vérifiée |
| Build | GitHub Actions | proprietary | vérifiée |
| Build | BuildKit (docker buildx) | Apache-2.0 | vérifiée |
| Build | Dependabot | proprietary | vérifiée |
| Tests & qualité | Tests unitaires | MIT | vérifiée |
| Tests & qualité | SonarQube | LGPL-3.0 | vérifiée |
| Artefacts | GitHub Container Registry | proprietary | vérifiée |
| Déploiement | Docker Compose | Apache-2.0 | vérifiée |
| Plateforme | Traefik | MIT | vérifiée |

## Étapes CI

Orchestrateur : GitHub Actions. Image publiée : `ghcr.io/OWNER/mon-app:<commit>`.

1. Tests unitaires
2. Qualité SonarQube
3. Build et publication de l'image (BuildKit (docker buildx))
4. Déploiement Docker Compose (SSH) — Développement (branche principale)
5. Déploiement Docker Compose (SSH) — Préproduction (branche principale)
6. Déploiement Docker Compose (SSH) — Production (branche principale, manuel)

## Variables CI

Les variables sans valeur sont à déclarer dans la CI ; les autres sont déjà écrites dans les fichiers.

| Variable | Secret | Valeur | Rôle |
| --- | --- | --- | --- |
| `SONAR_HOST_URL` | non | à déclarer | URL du serveur SonarQube |
| `SONAR_TOKEN` | oui | à déclarer | Jeton d'analyse SonarQube |
| `SSH_PRIVATE_KEY` | oui | à déclarer | Clé SSH de déploiement vers l'hôte Docker |
| `DEPLOY_HOST_DEV` | non | à déclarer | Hôte Docker cible (Développement) (utilisateur@hôte) |
| `DEPLOY_HOST_STAGING` | non | à déclarer | Hôte Docker cible (Préproduction) (utilisateur@hôte) |
| `DEPLOY_HOST_PRODUCTION` | non | à déclarer | Hôte Docker cible (Production) (utilisateur@hôte) |

## Diagnostics restants

Aucun.

## Notes

- Approbation (« Production ») : déclarer des relecteurs obligatoires sur l'environnement du dépôt (Settings › Environments › Required reviewers), sinon le déploiement part sans attendre.
- `scripts/ci-variables.sh` déclare les 6 variable(s) à renseigner avec GitHub (gh), sans écrire leurs valeurs dans le dépôt.

## Fichiers générés

- `.github/dependabot.yml`
- `.github/workflows/pipeline.yml`
- `PIPELINE.md`
- `deploy/docker-compose.yml`
- `devops-builder.yaml`
- `scripts/ci-variables.sh`
