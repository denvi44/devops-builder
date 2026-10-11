# matrice — pipeline généré

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

## Briques

| Étape | Brique | Licence | Fiche |
| --- | --- | --- | --- |
| Source | GitLab | MIT | vérifiée |
| Build | GitLab CI | MIT | vérifiée |
| Build | BuildKit (docker buildx) | Apache-2.0 | vérifiée |
| Tests & qualité | Tests unitaires | MIT | vérifiée |
| Sécurité | Trivy | Apache-2.0 | vérifiée |
| Déploiement | Docker Compose | Apache-2.0 | vérifiée |
| Plateforme | Traefik | MIT | vérifiée |
| Observabilité | Prometheus | Apache-2.0 | vérifiée |

## Étapes CI

Orchestrateur : GitLab CI. Image publiée : `$CI_REGISTRY_IMAGE:<commit>`.

1. Tests unitaires
2. Build et publication de l'image (BuildKit (docker buildx))
3. Scan de vulnérabilités Trivy
4. Déploiement Docker Compose (SSH) (branche principale)

## Variables CI

Les variables sans valeur sont à déclarer dans la CI ; les autres sont déjà écrites dans les fichiers.

| Variable | Secret | Valeur | Rôle |
| --- | --- | --- | --- |
| `SSH_PRIVATE_KEY` | oui | à déclarer | Clé SSH de déploiement vers l'hôte Docker |
| `SSH_KNOWN_HOSTS` | non | à déclarer | Facultatif : clés d'hôte attendues (ssh-keyscan) ; sans elle, la clé est acceptée à la première connexion de chaque job |
| `DEPLOY_HOST` | non | à déclarer | Hôte Docker cible (utilisateur@hôte) |

## Diagnostics restants

Aucun.

## Notes

- `scripts/ci-variables.sh` déclare les 3 variable(s) à renseigner avec GitLab (glab), sans écrire leurs valeurs dans le dépôt.

## Fichiers générés

- `.gitlab-ci.yml`
- `PIPELINE.md`
- `deploy/docker-compose.yml`
- `devops-builder.yaml`
- `scripts/ci-variables.sh`
