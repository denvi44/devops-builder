# Mon projet — pipeline généré

Généré par DevOps Builder le AAAA-MM-JJ. Cible : Kubernetes managé (cloud).

## Environnements

Ordre de promotion : la même image est déployée successivement dans chaque environnement.

| Environnement | Type | Approbation | Cluster | Espace de noms / projet |
| --- | --- | --- | --- | --- |
| Production (`production`) | Production | non | Scaleway Kapsule `mon-cluster` | `mon-app` |

## Ports

| Composant | Port publié | Port du conteneur | Usage | Exposition |
| --- | --- | --- | --- | --- |
| mon-app | — | 8000 | application | Service mon-app port 80, espace de noms mon-app |
| SonarQube | — | 9000 | interface web | Service Kubernetes, espace de noms sonarqube |

## Briques

| Étape | Brique | Licence | Fiche |
| --- | --- | --- | --- |
| Source | Bitbucket Cloud | proprietary | vérifiée |
| Build | Woodpecker CI | Apache-2.0 | vérifiée |
| Build | BuildKit (docker buildx) | Apache-2.0 | vérifiée |
| Build | Renovate | AGPL-3.0 | vérifiée |
| Tests & qualité | Tests unitaires | MIT | vérifiée |
| Tests & qualité | SonarQube | LGPL-3.0 | vérifiée |
| Artefacts | Scaleway Container Registry | proprietary | vérifiée |
| Infrastructure | Scaleway | proprietary | vérifiée |
| Infrastructure | Scaleway Kapsule | proprietary | vérifiée |
| Infrastructure | Terraform | BSL-1.1 | vérifiée |
| Déploiement | Helm | Apache-2.0 | vérifiée |
| Plateforme | cert-manager | Apache-2.0 | vérifiée |

## Étapes CI

Orchestrateur : Woodpecker CI. Image publiée : `rg.fr-par.scw.cloud/mon-app/mon-app:<commit>`.

1. Tests unitaires
2. Qualité SonarQube
3. Build et publication de l'image (BuildKit (docker buildx))
4. Plan Terraform
5. Application Terraform (branche principale, manuel)
6. Déploiement Helm (branche principale)

## Variables CI

Les variables sans valeur sont à déclarer dans la CI ; les autres sont déjà écrites dans les fichiers.

| Variable | Secret | Valeur | Rôle |
| --- | --- | --- | --- |
| `SONAR_HOST_URL` | non | à déclarer | URL du serveur SonarQube |
| `SONAR_TOKEN` | oui | à déclarer | Jeton d'analyse SonarQube |
| `SCW_SECRET_KEY` | oui | à déclarer | Clé secrète d'API Scaleway |
| `SCW_ACCESS_KEY` | oui | à déclarer | Clé d'accès API Scaleway |
| `SCW_DEFAULT_PROJECT_ID` | oui | à déclarer | Projet Scaleway |
| `KUBECONFIG_DATA` | oui | à déclarer | Contenu du kubeconfig de Scaleway Kapsule (base64) |
| `RENOVATE_TOKEN` | oui | à déclarer | Jeton de la forge autorisé à ouvrir des merge requests (Renovate) |

## Diagnostics restants

- **Avertissement** (R34) — Scaleway Kapsule : « Nom du cluster » non renseigné : la valeur d'exemple « mon-cluster » sera écrite dans les fichiers.
- **Info** (R24) — Terraform est sous licence BSL-1.1.

## Notes

- Renovate : lancer l'image renovate/renovate dans un job planifié (quotidien) avec RENOVATE_TOKEN ; renovate.json règle son comportement.
- `scripts/test-kind.sh` déploie le pipeline dans un cluster kind jetable (chart Helm) : utile avant la première mise en production.

## Fichiers générés

- `.woodpecker.yml`
- `PIPELINE.md`
- `charts/mon-app/Chart.yaml`
- `charts/mon-app/templates/deployment.yaml`
- `charts/mon-app/templates/service.yaml`
- `charts/mon-app/values.yaml`
- `devops-builder.yaml`
- `infra/terraform/main.tf`
- `infra/terraform/variables.tf`
- `infra/terraform/versions.tf`
- `platform/install.sh`
- `renovate.json`
- `scripts/test-kind.sh`
