# Ansible — pipeline généré

Généré par DevOps Builder le AAAA-MM-JJ. Cible : Machines virtuelles (Ansible).

## Environnements

Ordre de promotion : la même image est déployée successivement dans chaque environnement.

| Environnement | Type | Approbation | Cluster | Espace de noms / projet |
| --- | --- | --- | --- | --- |
| Préproduction (`staging`) | Préproduction | non | — | `site-staging` |
| Production (`production`) | Production | oui | — | `site` |

## Ports

| Environnement | Composant | Port publié | Port du conteneur | Usage | Exposition |
| --- | --- | --- | --- | --- | --- |
| Préproduction | site | — | 8000 | application | via Traefik, hôte site.example.com |
| Préproduction | Traefik | 80 | 80 | HTTP | publié sur l'hôte Docker |
| Préproduction | Traefik | 443 | 443 | HTTPS | publié sur l'hôte Docker |
| Production | site | — | 8000 | application | via Traefik, hôte site.example.com |
| Production | Traefik | 80 | 80 | HTTP | publié sur l'hôte Docker |
| Production | Traefik | 443 | 443 | HTTPS | publié sur l'hôte Docker |

## Briques

| Étape | Brique | Licence | Fiche |
| --- | --- | --- | --- |
| Source | GitLab | MIT | vérifiée |
| Build | GitLab CI | MIT | vérifiée |
| Build | BuildKit (docker buildx) | Apache-2.0 | vérifiée |
| Tests & qualité | ansible-lint | GPL-3.0 | vérifiée |
| Artefacts | Harbor | Apache-2.0 | vérifiée |
| Infrastructure | Ansible | GPL-3.0 | vérifiée |
| Déploiement | Docker Compose | Apache-2.0 | vérifiée |
| Plateforme | Traefik | MIT | vérifiée |

## Étapes CI

Orchestrateur : GitLab CI. Image publiée : `registry.exemple.fr/site/site:<commit>`.

1. Build et publication de l'image (BuildKit (docker buildx))
2. Déploiement Ansible + Compose — Préproduction (branche principale)
3. Déploiement Ansible + Compose — Production (branche principale, manuel)

## Variables CI

Les variables sans valeur sont à déclarer dans la CI ; les autres sont déjà écrites dans les fichiers.

| Variable | Secret | Valeur | Rôle |
| --- | --- | --- | --- |
| `REGISTRY_USER` | oui | à déclarer | Compte de publication sur registry.exemple.fr |
| `REGISTRY_PASSWORD` | oui | à déclarer | Mot de passe ou jeton de publication sur registry.exemple.fr |
| `SSH_PRIVATE_KEY` | oui | à déclarer | Clé SSH de déploiement vers les hôtes |
| `SSH_KNOWN_HOSTS` | non | à déclarer | Facultatif : clés d'hôte attendues (ssh-keyscan) ; sans elle, la clé est acceptée à la première connexion de chaque job |

## Diagnostics restants

- **Info** (R31) — Aucun fichier n'est généré pour ansible-lint dans cette configuration : à configurer à la main (listé dans PIPELINE.md).

## Notes

- Approbation (« Production ») : le job attend un déclenchement manuel dans GitLab ; protéger l'environnement (Settings › CI/CD › Protected environments) pour restreindre qui peut le lancer.
- Ansible : préparer chaque hôte une fois avec `ANSIBLE_CONFIG=ansible/ansible.cfg ansible-playbook -i ansible/inventories/staging.ini ansible/site.yml` (Docker depuis son dépôt officiel, Debian, Ubuntu, RHEL et dérivées) ; le compte SSH doit avoir sudo sans mot de passe.
- `scripts/ci-variables.sh` déclare les 4 variable(s) à renseigner avec GitLab (glab), sans écrire leurs valeurs dans le dépôt.

## À configurer à la main

Ces briques sont dans le pipeline mais aucun générateur ne les prend en charge :

- ansible-lint

## Fichiers générés

- `.gitlab-ci.yml`
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
