# Mon projet — pipeline généré

Généré par DevOps Builder le AAAA-MM-JJ. Cible : Machines virtuelles (Ansible).

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
| Zabbix | — | 8080 | interface web | via Traefik |

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
| Plateforme | SOPS | MPL-2.0 | vérifiée |
| Observabilité | Zabbix | AGPL-3.0 | vérifiée |

## Étapes CI

Orchestrateur : GitHub Actions. Image publiée : `ghcr.io/OWNER/mon-app:<commit>`.

1. Tests unitaires
2. Recherche de secrets
3. Build et publication de l'image (BuildKit (docker buildx))
4. Scan de vulnérabilités Trivy
5. Signature de l'image (Cosign) (branche principale)
6. Déploiement Ansible + Compose (branche principale)

## Variables CI

Les variables sans valeur sont à déclarer dans la CI ; les autres sont déjà écrites dans les fichiers.

| Variable | Secret | Valeur | Rôle |
| --- | --- | --- | --- |
| `SOPS_AGE_KEY` | oui | à déclarer | Clé privée age qui déchiffre deploy/secrets/*.enc.env (age-keygen) |
| `SSH_PRIVATE_KEY` | oui | à déclarer | Clé SSH de déploiement vers les hôtes |
| `SSH_KNOWN_HOSTS` | non | à déclarer | Facultatif : clés d'hôte attendues (ssh-keyscan) ; sans elle, la clé est acceptée à la première connexion de chaque job |

## Diagnostics restants

- **Avertissement** (R34) — Ansible : « Hôtes de l'application » non renseigné : la valeur d'exemple « app1.example.com » sera écrite dans les fichiers.
- **Avertissement** (R34) — SOPS : « Destinataires age » non renseigné : la valeur d'exemple « age1ql3z7hjy54pw3hyww5ayyfg7zqgvc7w3j2elw8zmrj2kg5sfn9aqmcac8p » sera écrite dans les fichiers.

## Notes

- Mise en route pas à pas, avec les commandes du projet : docs/mise-en-route.md.
- Ansible : préparer chaque hôte une fois avec `ANSIBLE_CONFIG=ansible/ansible.cfg ansible-playbook -i ansible/inventory.ini ansible/site.yml` (Docker depuis son dépôt officiel, Debian, Ubuntu, RHEL et dérivées) ; le compte SSH doit avoir sudo sans mot de passe.
- Secrets par SOPS : renseigner la clé publique age dans la brique SOPS (.sops.yaml), puis `scripts/secrets-seed.sh <environnement>` chiffre les valeurs dans deploy/secrets/<environnement>.enc.env, à committer. La CI les déchiffre avec SOPS_AGE_KEY.
- Zabbix : interface sur https://zabbix.example.com ; compte Admin / zabbix au premier accès, à changer aussitôt (docs/mise-en-route.md). L'agent fourni supervise le serveur Zabbix lui-même ; les autres hôtes reçoivent chacun un agent.
- `scripts/ci-variables.sh` déclare les 3 variable(s) à renseigner avec GitHub (gh), sans écrire leurs valeurs dans le dépôt.

## Fichiers générés

- `.github/dependabot.yml`
- `.github/workflows/pipeline.yml`
- `.sops.yaml`
- `PIPELINE.md`
- `ansible/ansible.cfg`
- `ansible/deploy.yml`
- `ansible/inventory.ini`
- `ansible/requirements.yml`
- `ansible/site.yml`
- `deploy/docker-compose.yml`
- `deploy/secrets.sh`
- `devops-builder.yaml`
- `docs/mise-en-route.md`
- `scripts/ci-variables.sh`
- `scripts/db-backup.sh`
- `scripts/db-restore.sh`
- `scripts/secrets-fetch.sh`
- `scripts/secrets-seed.sh`
