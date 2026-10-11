# Mon projet — pipeline généré

Généré par DevOps Builder le AAAA-MM-JJ. Cible : Machines virtuelles (Ansible) ; exigence SecNumCloud.

## Environnements

Ordre de promotion : la même image est déployée successivement dans chaque environnement.

| Environnement | Type | Approbation | Cluster | Espace de noms / projet |
| --- | --- | --- | --- | --- |
| Préproduction (`staging`) | Préproduction | non | — | `mon-app-staging` |
| Production (`production`) | Production | oui | — | `mon-app` |

## Ports

| Environnement | Composant | Port publié | Port du conteneur | Usage | Exposition |
| --- | --- | --- | --- | --- | --- |
| Préproduction | mon-app | — | 8000 | application | via Traefik, hôte mon-app.example.com |
| Préproduction | Traefik | 80 | 80 | HTTP | publié sur l'hôte Docker |
| Préproduction | Traefik | 443 | 443 | HTTPS | publié sur l'hôte Docker |
| Préproduction | SonarQube | 9002 | 9000 | interface web | publié sur l'hôte Docker |
| Production | mon-app | — | 8000 | application | via Traefik, hôte mon-app.example.com |
| Production | Traefik | 80 | 80 | HTTP | publié sur l'hôte Docker |
| Production | Traefik | 443 | 443 | HTTPS | publié sur l'hôte Docker |
| Production | SonarQube | 9002 | 9000 | interface web | publié sur l'hôte Docker |

## Briques

| Étape | Brique | Licence | Fiche |
| --- | --- | --- | --- |
| Source | GitHub | proprietary | vérifiée |
| Build | GitHub Actions | proprietary | vérifiée |
| Build | BuildKit (docker buildx) | Apache-2.0 | vérifiée |
| Build | Dependabot | proprietary | vérifiée |
| Tests & qualité | Tests unitaires | MIT | vérifiée |
| Tests & qualité | SonarQube | LGPL-3.0 | vérifiée |
| Sécurité | Gitleaks | MIT | vérifiée |
| Sécurité | Trivy | Apache-2.0 | vérifiée |
| Sécurité | Cosign | Apache-2.0 | vérifiée |
| Artefacts | GitHub Container Registry | proprietary | vérifiée |
| Infrastructure | Ansible | GPL-3.0 | vérifiée |
| Déploiement | Docker Compose | Apache-2.0 | vérifiée |
| Plateforme | Traefik | MIT | vérifiée |

## Étapes CI

Orchestrateur : GitHub Actions. Image publiée : `ghcr.io/OWNER/mon-app:<commit>`.

1. Tests unitaires
2. Qualité SonarQube
3. Recherche de secrets
4. Build et publication de l'image (BuildKit (docker buildx))
5. Scan de vulnérabilités Trivy
6. Signature de l'image (Cosign) (branche principale)
7. Déploiement Ansible + Compose — Préproduction (branche principale)
8. Déploiement Ansible + Compose — Production (branche principale, manuel)

## Variables CI

Les variables sans valeur sont à déclarer dans la CI ; les autres sont déjà écrites dans les fichiers.

| Variable | Secret | Valeur | Rôle |
| --- | --- | --- | --- |
| `SONAR_HOST_URL` | non | à déclarer | URL du serveur SonarQube |
| `SONAR_TOKEN` | oui | à déclarer | Jeton d'analyse SonarQube |
| `SSH_PRIVATE_KEY` | oui | à déclarer | Clé SSH de déploiement vers les hôtes |
| `SSH_KNOWN_HOSTS` | non | à déclarer | Facultatif : clés d'hôte attendues (ssh-keyscan) ; sans elle, la clé est acceptée à la première connexion de chaque job |

## Diagnostics restants

- **Avertissement** (R34) — Ansible : « Hôtes de l'application » non renseigné : la valeur d'exemple « app1.example.com » sera écrite dans les fichiers.

## Notes

- Approbation (« Production ») : déclarer des relecteurs obligatoires sur l'environnement du dépôt (Settings › Environments › Required reviewers), sinon le déploiement part sans attendre.
- Ansible : préparer chaque hôte une fois avec `ANSIBLE_CONFIG=ansible/ansible.cfg ansible-playbook -i ansible/inventories/staging.ini ansible/site.yml` (Docker depuis son dépôt officiel, Debian, Ubuntu, RHEL et dérivées) ; le compte SSH doit avoir sudo sans mot de passe.
- `scripts/ci-variables.sh` déclare les 4 variable(s) à renseigner avec GitHub (gh), sans écrire leurs valeurs dans le dépôt.

## Fichiers générés

- `.github/dependabot.yml`
- `.github/workflows/pipeline.yml`
- `PIPELINE.md`
- `ansible/ansible.cfg`
- `ansible/deploy.yml`
- `ansible/inventories/production.ini`
- `ansible/inventories/staging.ini`
- `ansible/requirements.yml`
- `ansible/site.yml`
- `deploy/docker-compose.yml`
- `devops-builder.yaml`
- `scripts/ci-variables.sh`
