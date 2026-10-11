# matrice — pipeline généré

Généré par DevOps Builder le AAAA-MM-JJ. Cible : Machines virtuelles (Ansible).

## Environnements

Ordre de promotion : la même image est déployée successivement dans chaque environnement.

| Environnement | Type | Approbation | Cluster | Espace de noms / projet |
| --- | --- | --- | --- | --- |
| Production (`production`) | Production | non | — | `mon-app` |

## Ports

| Composant | Port publié | Port du conteneur | Usage | Exposition |
| --- | --- | --- | --- | --- |
| mon-app | 8000 | 8000 | application | publié sur l'hôte Docker |
| zot | 5000 | 5000 | registre OCI | publié sur l'hôte Docker |
| Gitea | 3001 | 3000 | interface web | publié sur l'hôte Docker |
| Gitea | 2222 | 22 | SSH Git | publié sur l'hôte Docker |

## Briques

| Étape | Brique | Licence | Fiche |
| --- | --- | --- | --- |
| Source | Gitea | MIT | vérifiée |
| Build | Gitea Actions | MIT | vérifiée |
| Build | Buildah | Apache-2.0 | vérifiée |
| Tests & qualité | Tests unitaires | MIT | vérifiée |
| Artefacts | zot | Apache-2.0 | vérifiée |
| Infrastructure | Ansible | GPL-3.0 | vérifiée |
| Déploiement | Docker Compose | Apache-2.0 | vérifiée |

## Étapes CI

Orchestrateur : Gitea Actions. Image publiée : `registry.example.com/mon-app/mon-app:<commit>`.

1. Tests unitaires
2. Build et publication de l'image (Buildah)
3. Déploiement Ansible + Compose (branche principale)

## Variables CI

Les variables sans valeur sont à déclarer dans la CI ; les autres sont déjà écrites dans les fichiers.

| Variable | Secret | Valeur | Rôle |
| --- | --- | --- | --- |
| `REGISTRY_USER` | oui | à déclarer | Compte de publication sur registry.example.com |
| `REGISTRY_PASSWORD` | oui | à déclarer | Mot de passe ou jeton de publication sur registry.example.com |
| `SSH_PRIVATE_KEY` | oui | à déclarer | Clé SSH de déploiement vers les hôtes |
| `SSH_KNOWN_HOSTS` | non | à déclarer | Facultatif : clés d'hôte attendues (ssh-keyscan) ; sans elle, la clé est acceptée à la première connexion de chaque job |

## Diagnostics restants

- **Avertissement** (R34) — zot : « Adresse du registre » non renseigné : la valeur d'exemple « registry.example.com » sera écrite dans les fichiers.
- **Avertissement** (R34) — Ansible : « Hôtes de l'application » non renseigné : la valeur d'exemple « app1.example.com » sera écrite dans les fichiers.

## Notes

- Ansible : préparer chaque hôte une fois avec `ANSIBLE_CONFIG=ansible/ansible.cfg ansible-playbook -i ansible/inventory.ini ansible/site.yml` (Docker depuis son dépôt officiel, Debian, Ubuntu, RHEL et dérivées) ; le compte SSH doit avoir sudo sans mot de passe.
- `scripts/ci-variables.sh` déclare les 4 variable(s) à renseigner avec Gitea (API), sans écrire leurs valeurs dans le dépôt.

## Fichiers générés

- `.gitea/workflows/pipeline.yml`
- `PIPELINE.md`
- `ansible/ansible.cfg`
- `ansible/deploy.yml`
- `ansible/inventory.ini`
- `ansible/requirements.yml`
- `ansible/site.yml`
- `deploy/docker-compose.yml`
- `devops-builder.yaml`
- `scripts/ci-variables.sh`
