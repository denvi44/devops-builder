# Mon projet — pipeline généré

Généré par DevOps Builder le AAAA-MM-JJ. Cible : Machines virtuelles (Ansible).

## Environnements

Ordre de promotion : la même image est déployée successivement dans chaque environnement.

| Environnement | Type | Approbation | Cluster | Espace de noms / projet |
| --- | --- | --- | --- | --- |
| Préproduction (`staging`) | Préproduction | non | — | `mon-app-staging` |
| Production (`production`) | Production | oui | — | `mon-app` |

## Ports

| Environnement | Composant | Port publié | Port du conteneur | Usage | Exposition |
| --- | --- | --- | --- | --- | --- |
| Préproduction | mon-app | — | 8000 | application | via Traefik, hôte staging.mon-app.example.com |
| Préproduction | Traefik | 80 | 80 | HTTP | publié sur l'hôte Docker |
| Préproduction | Traefik | 443 | 443 | HTTPS | publié sur l'hôte Docker |
| Préproduction | Prometheus | — | 9090 | interface et API | réseau interne Compose, non publié |
| Préproduction | Grafana | — | 3000 | interface web | via Traefik, hôte grafana.example.com |
| Préproduction | Dex | — | 5556 | OIDC | via Traefik, hôte dex.boutique.fr |
| Production | mon-app | — | 8000 | application | via Traefik, hôte mon-app.example.com |
| Production | Traefik | 80 | 80 | HTTP | publié sur l'hôte Docker |
| Production | Traefik | 443 | 443 | HTTPS | publié sur l'hôte Docker |
| Production | Prometheus | — | 9090 | interface et API | réseau interne Compose, non publié |
| Production | Grafana | — | 3000 | interface web | via Traefik, hôte grafana.example.com |
| Production | Dex | — | 5556 | OIDC | via Traefik, hôte dex.boutique.fr |

## Dimensionnement

Besoin estimé à partir des services Compose de l'hôte (marge de 25 %), pour chaque environnement porté, plus le système et Docker. Un ordre de grandeur pour une charge modeste, à confirmer par la supervision.

Services : mon-app (512 Mio, estimé), traefik (128 Mio, estimé), prometheus (1024 Mio, estimé), grafana (512 Mio), dex (64 Mio, estimé).

| Machines | Environnements | Besoin | Type retenu | Verdict |
| --- | --- | --- | --- | --- |
| `staging` | staging | 1 vCPU, 3,2 Gio | hôte existant | prévoir au moins 1 vCPU et 3,2 Gio |
| `production` | production | 1 vCPU, 3,2 Gio | hôte existant | prévoir au moins 1 vCPU et 3,2 Gio |

## Briques

| Étape | Brique | Licence | Fiche |
| --- | --- | --- | --- |
| Source | GitHub | proprietary | vérifiée |
| Build | GitHub Actions | proprietary | vérifiée |
| Build | BuildKit (docker buildx) | Apache-2.0 | vérifiée |
| Build | Dependabot | proprietary | vérifiée |
| Tests & qualité | Tests unitaires | MIT | vérifiée |
| Sécurité | Gitleaks | MIT | vérifiée |
| Sécurité | Trivy | Apache-2.0 | vérifiée |
| Sécurité | Cosign | Apache-2.0 | vérifiée |
| Artefacts | GitHub Container Registry | proprietary | vérifiée |
| Infrastructure | Ansible | GPL-3.0 | vérifiée |
| Déploiement | Docker Compose | Apache-2.0 | vérifiée |
| Plateforme | Traefik | MIT | vérifiée |
| Plateforme | Dex | Apache-2.0 | vérifiée |
| Observabilité | Prometheus | Apache-2.0 | vérifiée |
| Observabilité | Grafana | AGPL-3.0 | vérifiée |

## Étapes CI

Orchestrateur : GitHub Actions. Image publiée : `ghcr.io/OWNER/mon-app:<commit>`.

1. Tests unitaires
2. Recherche de secrets
3. Build et publication de l'image (BuildKit (docker buildx))
4. Scan de vulnérabilités Trivy
5. Signature de l'image (Cosign) (branche principale)
6. Déploiement Ansible + Compose — Préproduction (branche principale)
7. Déploiement Ansible + Compose — Production (branche principale, manuel)

## Variables CI

Les variables sans valeur sont à déclarer dans la CI ; les autres sont déjà écrites dans les fichiers.

| Variable | Secret | Valeur | Rôle |
| --- | --- | --- | --- |
| `DEX_CONNECTOR_ID_STAGING` | oui | à déclarer | Identifiant (Client ID) de l'application OAuth créée sur la forge pour Dex (Préproduction) |
| `DEX_CONNECTOR_SECRET_STAGING` | oui | à déclarer | Secret de l'application OAuth créée sur la forge pour Dex (Préproduction) |
| `GRAFANA_OIDC_SECRET_STAGING` | oui | à déclarer | Secret du client OIDC grafana dans Dex (openssl rand -hex 24) (Préproduction) |
| `SSH_PRIVATE_KEY` | oui | à déclarer | Clé SSH de déploiement vers les hôtes |
| `SSH_KNOWN_HOSTS` | non | à déclarer | Facultatif : clés d'hôte attendues (ssh-keyscan) ; sans elle, la clé est acceptée à la première connexion de chaque job |
| `DEX_CONNECTOR_ID_PRODUCTION` | oui | à déclarer | Identifiant (Client ID) de l'application OAuth créée sur la forge pour Dex (Production) |
| `DEX_CONNECTOR_SECRET_PRODUCTION` | oui | à déclarer | Secret de l'application OAuth créée sur la forge pour Dex (Production) |
| `GRAFANA_OIDC_SECRET_PRODUCTION` | oui | à déclarer | Secret du client OIDC grafana dans Dex (openssl rand -hex 24) (Production) |

## Diagnostics restants

- **Avertissement** (R34) — Ansible : « Hôtes de l'application » non renseigné : la valeur d'exemple « app1.example.com » sera écrite dans les fichiers.
- **Avertissement** (R34) — Traefik : « Adresse publique de l'application » non renseigné : la valeur d'exemple « mon-app.example.com » sera écrite dans les fichiers.
- **Info** (R50) — Dex est expérimental : exécuté de bout en bout sur hôte Docker (jusqu'à la page d'autorisation de la forge) ; sur Kubernetes, valeurs du chart vérifiées sans exécution.

## Notes

- Mise en route pas à pas, avec les commandes du projet : docs/mise-en-route.md.
- Approbation (« Production ») : déclarer des relecteurs obligatoires sur l'environnement du dépôt (Settings › Environments › Required reviewers), sinon le déploiement part sans attendre.
- Ansible : préparer chaque hôte une fois avec `ANSIBLE_CONFIG=ansible/ansible.cfg ansible-playbook -i ansible/inventories/staging.ini ansible/site.yml` (Docker depuis son dépôt officiel, Debian, Ubuntu, RHEL et dérivées) ; le compte SSH doit avoir sudo sans mot de passe.
- Dex : émetteur OIDC https://dex.boutique.fr ; l'application reçoit OIDC_ISSUER_URL et OIDC_CLIENT_ID (client public, PKCE) ; clients des outils : Grafana, droits d'administration au groupe « admins ». La connexion passe par la forge : créer son application OAuth (docs/mise-en-route.md).
- `scripts/ci-variables.sh` déclare les 8 variable(s) à renseigner avec GitHub (gh), sans écrire leurs valeurs dans le dépôt.

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
- `deploy/secrets.sh`
- `devops-builder.yaml`
- `docs/mise-en-route.md`
- `scripts/ci-variables.sh`
