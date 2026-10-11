# Mon projet — pipeline généré

Généré par DevOps Builder le AAAA-MM-JJ. Cible : Kubernetes managé (cloud).

## Environnements

Ordre de promotion : la même image est déployée successivement dans chaque environnement.

| Environnement | Type | Approbation | Cluster | Espace de noms / projet |
| --- | --- | --- | --- | --- |
| Production (`production`) | Production | non | Outscale Kubernetes as a Service (OKS) `mon-cluster` | `mon-app` |

## Ports

| Composant | Port publié | Port du conteneur | Usage | Exposition |
| --- | --- | --- | --- | --- |
| mon-app | — | 8000 | application | Service mon-app port 80, espace de noms mon-app |
| SonarQube | — | 9000 | interface web | Service Kubernetes, espace de noms sonarqube |
| Harbor | — | 80 | HTTP | Service Kubernetes, espace de noms harbor |
| Harbor | — | 443 | HTTPS (portail et registre) | Service Kubernetes, espace de noms harbor |
| Argo CD | — | 8080 | API et interface (service 80/443) | Service Kubernetes, espace de noms argocd |

## Briques

| Étape | Brique | Licence | Fiche |
| --- | --- | --- | --- |
| Source | Bitbucket Cloud | proprietary | vérifiée |
| Build | Woodpecker CI | Apache-2.0 | vérifiée |
| Build | BuildKit (docker buildx) | Apache-2.0 | vérifiée |
| Build | Renovate | AGPL-3.0 | vérifiée |
| Tests & qualité | Tests unitaires | MIT | vérifiée |
| Tests & qualité | SonarQube | LGPL-3.0 | vérifiée |
| Artefacts | Harbor | Apache-2.0 | vérifiée |
| Infrastructure | Outscale | proprietary | vérifiée |
| Infrastructure | Outscale Kubernetes as a Service (OKS) | proprietary | vérifiée |
| Infrastructure | OpenTofu | MPL-2.0 | vérifiée |
| Infrastructure | Outscale Object Storage (OOS) | proprietary | vérifiée |
| Déploiement | Helm | Apache-2.0 | vérifiée |
| Déploiement | Argo CD | Apache-2.0 | vérifiée |
| Plateforme | cert-manager | Apache-2.0 | vérifiée |

## Étapes CI

Orchestrateur : Woodpecker CI. Image publiée : `registry.example.com/mon-app/mon-app:<commit>`.

1. Tests unitaires
2. Qualité SonarQube
3. Build et publication de l'image (BuildKit (docker buildx))
4. Plan OpenTofu
5. Application OpenTofu (branche principale, manuel)
6. Mise à jour GitOps (Argo CD) (branche principale)

## Variables CI

Les variables sans valeur sont à déclarer dans la CI ; les autres sont déjà écrites dans les fichiers.

| Variable | Secret | Valeur | Rôle |
| --- | --- | --- | --- |
| `SONAR_HOST_URL` | non | à déclarer | URL du serveur SonarQube |
| `SONAR_TOKEN` | oui | à déclarer | Jeton d'analyse SonarQube |
| `REGISTRY_USER` | oui | à déclarer | Compte de publication sur registry.example.com |
| `REGISTRY_PASSWORD` | oui | à déclarer | Mot de passe ou jeton de publication sur registry.example.com |
| `OSC_ACCESS_KEY` | oui | à déclarer | Clé d'accès Outscale |
| `OSC_SECRET_KEY` | oui | à déclarer | Clé secrète Outscale |
| `GITOPS_TOKEN` | oui | à déclarer | Jeton autorisé à pousser sur le dépôt GitOps |
| `GITOPS_REPO` | non | à déclarer | Dépôt GitOps surveillé, sans schéma (hôte/groupe/depot.git) |
| `RENOVATE_TOKEN` | oui | à déclarer | Jeton de la forge autorisé à ouvrir des merge requests (Renovate) |

## Diagnostics restants

- **Avertissement** (R34) — Harbor : « Adresse du registre » non renseigné : la valeur d'exemple « registry.example.com » sera écrite dans les fichiers.
- **Avertissement** (R34) — Outscale Kubernetes as a Service (OKS) : « Nom du cluster » non renseigné : la valeur d'exemple « mon-cluster » sera écrite dans les fichiers.
- **Avertissement** (R34) — Outscale Object Storage (OOS) : « Bucket de l'état Terraform » non renseigné : la valeur d'exemple « mon-projet-tfstate » sera écrite dans les fichiers.
- **Info** (R31) — Aucun fichier n'est généré pour Outscale Kubernetes as a Service (OKS) dans cette configuration : à configurer à la main (listé dans PIPELINE.md).

## Notes

- Renovate : lancer l'image renovate/renovate dans un job planifié (quotidien) avec RENOVATE_TOKEN ; renovate.json règle son comportement.
- `scripts/test-kind.sh` déploie le pipeline dans un cluster kind jetable (chart Helm) : utile avant la première mise en production.

## À configurer à la main

Ces briques sont dans le pipeline mais aucun générateur ne les prend en charge :

- Outscale Kubernetes as a Service (OKS)

## Fichiers générés

- `.woodpecker.yml`
- `PIPELINE.md`
- `charts/mon-app/Chart.yaml`
- `charts/mon-app/templates/deployment.yaml`
- `charts/mon-app/templates/service.yaml`
- `charts/mon-app/values.yaml`
- `deploy/argocd/application.yaml`
- `devops-builder.yaml`
- `infra/terraform/.gitignore`
- `infra/terraform/main.tf`
- `infra/terraform/variables.tf`
- `infra/terraform/versions.tf`
- `platform/install.sh`
- `renovate.json`
- `scripts/test-kind.sh`
