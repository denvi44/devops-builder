# Ansible seul — pipeline généré

Généré par DevOps Builder le AAAA-MM-JJ. Cible : Machines virtuelles (Ansible).

## Environnements

Ordre de promotion : la même image est déployée successivement dans chaque environnement.

| Environnement | Type | Approbation | Cluster | Espace de noms / projet |
| --- | --- | --- | --- | --- |
| Production (`production`) | Production | non | — | `site` |

## Ports

| Composant | Port publié | Port du conteneur | Usage | Exposition |
| --- | --- | --- | --- | --- |
| site | — | 8000 | application | port du conteneur |

## Briques

| Étape | Brique | Licence | Fiche |
| --- | --- | --- | --- |
| Source | GitHub | proprietary | vérifiée |
| Build | GitHub Actions | proprietary | vérifiée |
| Build | BuildKit (docker buildx) | Apache-2.0 | vérifiée |
| Artefacts | GitHub Container Registry | proprietary | vérifiée |
| Infrastructure | Ansible | GPL-3.0 | vérifiée |

## Étapes CI

Orchestrateur : GitHub Actions. Image publiée : `ghcr.io/OWNER/site:<commit>`.

1. Build et publication de l'image (BuildKit (docker buildx))
2. Déploiement Ansible (branche principale)

## Variables CI

Les variables sans valeur sont à déclarer dans la CI ; les autres sont déjà écrites dans les fichiers.

| Variable | Secret | Valeur | Rôle |
| --- | --- | --- | --- |
| `SSH_PRIVATE_KEY` | oui | à déclarer | Clé SSH de déploiement vers les hôtes |
| `SSH_KNOWN_HOSTS` | non | à déclarer | Facultatif : clés d'hôte attendues (ssh-keyscan) ; sans elle, la clé est acceptée à la première connexion de chaque job |

## Diagnostics restants

- **Avertissement** (R34) — Ansible : « Hôtes de l'application » non renseigné : la valeur d'exemple « app1.example.com » sera écrite dans les fichiers.

## Notes

- Ansible : préparer chaque hôte une fois avec `ANSIBLE_CONFIG=ansible/ansible.cfg ansible-playbook -i ansible/inventory.ini ansible/site.yml` (Docker depuis son dépôt officiel, Debian, Ubuntu, RHEL et dérivées) ; le compte SSH doit avoir sudo sans mot de passe.
- Ansible sans brique Docker Compose : l'application est lancée seule, d'après une définition Compose écrite dans ansible/deploy.yml.
- `scripts/ci-variables.sh` déclare les 2 variable(s) à renseigner avec GitHub (gh), sans écrire leurs valeurs dans le dépôt.

## Fichiers générés

- `.github/workflows/pipeline.yml`
- `PIPELINE.md`
- `ansible/ansible.cfg`
- `ansible/deploy.yml`
- `ansible/inventory.ini`
- `ansible/requirements.yml`
- `ansible/site.yml`
- `devops-builder.yaml`
- `scripts/ci-variables.sh`
