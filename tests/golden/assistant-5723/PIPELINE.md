# Mon projet — pipeline généré

Généré par DevOps Builder le AAAA-MM-JJ. Cible : Hôte Docker unique ; exigence SecNumCloud.

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
| Source | Bitbucket Cloud | proprietary | vérifiée |
| Build | Woodpecker CI | Apache-2.0 | vérifiée |
| Build | BuildKit (docker buildx) | Apache-2.0 | vérifiée |
| Build | Renovate | AGPL-3.0 | vérifiée |
| Tests & qualité | Tests unitaires | MIT | vérifiée |
| Tests & qualité | SonarQube | LGPL-3.0 | vérifiée |
| Sécurité | Gitleaks | MIT | vérifiée |
| Sécurité | Trivy | Apache-2.0 | vérifiée |
| Sécurité | Cosign | Apache-2.0 | vérifiée |
| Artefacts | Harbor | Apache-2.0 | vérifiée |
| Déploiement | Docker Compose | Apache-2.0 | vérifiée |
| Plateforme | Traefik | MIT | vérifiée |

## Étapes CI

Orchestrateur : Woodpecker CI. Image publiée : `registry.example.com/mon-app/mon-app:<commit>`.

1. Tests unitaires
2. Qualité SonarQube
3. Recherche de secrets
4. Build et publication de l'image (BuildKit (docker buildx))
5. Scan de vulnérabilités Trivy
6. Signature de l'image (Cosign) (branche principale)
7. Déploiement Docker Compose (SSH) — Développement (branche principale)
8. Déploiement Docker Compose (SSH) — Préproduction (branche principale)
9. Déploiement Docker Compose (SSH) — Production (branche principale, manuel)

## Variables CI

Les variables sans valeur sont à déclarer dans la CI ; les autres sont déjà écrites dans les fichiers.

| Variable | Secret | Valeur | Rôle |
| --- | --- | --- | --- |
| `SONAR_HOST_URL` | non | à déclarer | URL du serveur SonarQube |
| `SONAR_TOKEN` | oui | à déclarer | Jeton d'analyse SonarQube |
| `REGISTRY_USER` | oui | à déclarer | Compte de publication sur registry.example.com |
| `REGISTRY_PASSWORD` | oui | à déclarer | Mot de passe ou jeton de publication sur registry.example.com |
| `SSH_PRIVATE_KEY` | oui | à déclarer | Clé SSH de déploiement vers l'hôte Docker |
| `DEPLOY_HOST_DEV` | non | à déclarer | Hôte Docker cible (Développement) (utilisateur@hôte) |
| `DEPLOY_HOST_STAGING` | non | à déclarer | Hôte Docker cible (Préproduction) (utilisateur@hôte) |
| `DEPLOY_HOST_PRODUCTION` | non | à déclarer | Hôte Docker cible (Production) (utilisateur@hôte) |
| `RENOVATE_TOKEN` | oui | à déclarer | Jeton de la forge autorisé à ouvrir des merge requests (Renovate) |

## Diagnostics restants

- **Avertissement** (R34) — Harbor : « Adresse du registre » non renseigné : la valeur d'exemple « registry.example.com » sera écrite dans les fichiers.
- **Info** (R23) — Harbor embarque déjà Trivy comme scanner ; l'étape Trivy en CI reste utile pour bloquer avant la publication.

## Notes

- Approbation (« Production ») : Woodpecker n'a pas de porte d'approbation : l'étape ne s'exécute que sur un pipeline lancé manuellement depuis l'interface (événement « manual »).
- Renovate : lancer l'image renovate/renovate dans un job planifié (quotidien) avec RENOVATE_TOKEN ; renovate.json règle son comportement.

## Fichiers générés

- `.woodpecker.yml`
- `PIPELINE.md`
- `deploy/docker-compose.yml`
- `devops-builder.yaml`
- `renovate.json`
