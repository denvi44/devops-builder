# Vault lu par la CI — pipeline généré

Généré par DevOps Builder le AAAA-MM-JJ. Cible : Kubernetes autogéré.

## Environnements

Ordre de promotion : la même image est déployée successivement dans chaque environnement.

| Environnement | Type | Approbation | Cluster | Espace de noms / projet |
| --- | --- | --- | --- | --- |
| Production (`production`) | Production | non | k3s | `boutique` |

## Ports

| Composant | Port publié | Port du conteneur | Usage | Exposition |
| --- | --- | --- | --- | --- |
| boutique | — | 8000 | application | Service boutique port 80, espace de noms boutique |
| PostgreSQL | — | 5432 | PostgreSQL | Service boutique-postgresql, espace de noms boutique, interne au cluster |

## Données

L'application lit l'URL de connexion complète dans la variable indiquée ; le mot de passe ne figure dans aucun fichier du dépôt.

| Base | Mode | Où | Variable de l'application | Mot de passe / URL | Sauvegarde |
| --- | --- | --- | --- | --- | --- |
| PostgreSQL 18 | autogérée | StatefulSet dans l'espace de noms de l'application | `DATABASE_URL` | Vault, `secret/<espace de noms>/postgresql` | à prévoir (Velero, instantanés) |

## Briques

| Étape | Brique | Licence | Fiche |
| --- | --- | --- | --- |
| Source | GitHub | proprietary | vérifiée |
| Build | GitHub Actions | proprietary | vérifiée |
| Build | BuildKit (docker buildx) | Apache-2.0 | vérifiée |
| Artefacts | GitHub Container Registry | proprietary | vérifiée |
| Infrastructure | k3s | Apache-2.0 | vérifiée |
| Données | PostgreSQL | PostgreSQL | vérifiée |
| Déploiement | Helm | Apache-2.0 | vérifiée |
| Plateforme | Vault | BSL-1.1 | vérifiée |

## Étapes CI

Orchestrateur : GitHub Actions. Image publiée : `ghcr.io/OWNER/boutique:<commit>`.

1. Build et publication de l'image (BuildKit (docker buildx))
2. Déploiement Helm (branche principale)

## Variables CI

Les variables sans valeur sont à déclarer dans la CI ; les autres sont déjà écrites dans les fichiers.

| Variable | Secret | Valeur | Rôle |
| --- | --- | --- | --- |
| `KUBECONFIG_DATA` | oui | à déclarer | Contenu du kubeconfig de k3s (base64) |
| `VAULT_ADDR` | non | `https://vault.exemple.fr` | Adresse de Vault joignable depuis la CI |
| `VAULT_TOKEN` | oui | à déclarer | Facultatif : jeton du coffre, si la connexion par JWT de la CI n'est pas configurée |

## Diagnostics restants

- **Avertissement** (R40) — PostgreSQL tourne dans le cluster et sert « Production », mais rien ne sauvegarde ses données : ajouter Velero, des instantanés de volumes ou les sauvegardes de l'opérateur, et tester la restauration.
- **Avertissement** (R41) — PostgreSQL est déployé en StatefulSet à une seule instance pour « Production » : ni réplication ni bascule. En production, préférer un opérateur ou un service managé.
- **Info** (R24) — Vault est sous licence BSL-1.1.

## Notes

- Secrets dans Vault (moteur KV v2 « secret », clés <espace de noms>/<brique>) : `scripts/secrets-seed.sh <environnement>` les écrit. La CI s'y connecte par JWT (rôle « boutique-deploy » sur auth/jwt, émetteur GitLab ou GitHub, politique de lecture de secret/data/<espace de noms>/*) ou par VAULT_TOKEN.
- `scripts/test-kind.sh` déploie le pipeline dans un cluster kind jetable (chart Helm) : utile avant la première mise en production.
- `scripts/ci-variables.sh` déclare les 2 variable(s) à renseigner avec GitHub (gh), sans écrire leurs valeurs dans le dépôt.

## Fichiers générés

- `.github/workflows/pipeline.yml`
- `PIPELINE.md`
- `charts/boutique/Chart.yaml`
- `charts/boutique/templates/deployment.yaml`
- `charts/boutique/templates/postgresql.yaml`
- `charts/boutique/templates/service.yaml`
- `charts/boutique/values.yaml`
- `devops-builder.yaml`
- `infra/cluster/install-k3s.sh`
- `scripts/ci-variables.sh`
- `scripts/secrets-fetch.sh`
- `scripts/secrets-seed.sh`
- `scripts/test-kind.sh`
