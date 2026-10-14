# Mon projet — pipeline généré

Généré par DevOps Builder le AAAA-MM-JJ. Cible : Kubernetes managé (cloud).

## Environnements

Ordre de promotion : la même image est déployée successivement dans chaque environnement.

| Environnement | Type | Approbation | Cluster | Espace de noms / projet |
| --- | --- | --- | --- | --- |
| Préproduction (`staging`) | Préproduction | non | Azure Kubernetes Service `mon-cluster` | `mon-app-staging` |
| Production (`production`) | Production | oui | Azure Kubernetes Service `mon-cluster` | `mon-app` |

## Ports

| Environnement | Composant | Port publié | Port du conteneur | Usage | Exposition |
| --- | --- | --- | --- | --- | --- |
| Préproduction | mon-app | — | 8000 | application | Service mon-app port 80, espace de noms mon-app-staging |
| Préproduction | Prometheus | — | 9090 | interface et API | Service Kubernetes, espace de noms monitoring |
| Préproduction | Grafana | — | 3000 | interface web | Service Kubernetes, espace de noms monitoring |
| Production | mon-app | — | 8000 | application | Service mon-app port 80, espace de noms mon-app |
| Production | Prometheus | — | 9090 | interface et API | Service Kubernetes, espace de noms monitoring |
| Production | Grafana | — | 3000 | interface web | Service Kubernetes, espace de noms monitoring |

## Briques

| Étape | Brique | Licence | Fiche |
| --- | --- | --- | --- |
| Source | GitHub | proprietary | vérifiée |
| Build | Tekton | Apache-2.0 | vérifiée |
| Build | Buildah | Apache-2.0 | vérifiée |
| Build | Dependabot | proprietary | vérifiée |
| Tests & qualité | Tests unitaires | MIT | vérifiée |
| Sécurité | Gitleaks | MIT | vérifiée |
| Sécurité | Trivy | Apache-2.0 | vérifiée |
| Sécurité | Cosign | Apache-2.0 | vérifiée |
| Sécurité | ZAP (OWASP) | Apache-2.0 | vérifiée |
| Artefacts | Azure Container Registry | proprietary | vérifiée |
| Infrastructure | Microsoft Azure | proprietary | vérifiée |
| Infrastructure | Azure Kubernetes Service | proprietary | vérifiée |
| Infrastructure | OpenTofu | MPL-2.0 | vérifiée |
| Infrastructure | Azure Blob Storage | proprietary | vérifiée |
| Déploiement | Helm | Apache-2.0 | vérifiée |
| Plateforme | cert-manager | Apache-2.0 | vérifiée |
| Observabilité | Prometheus | Apache-2.0 | vérifiée |
| Observabilité | Grafana | AGPL-3.0 | vérifiée |

## Étapes CI

Orchestrateur : Tekton. Image publiée : `monappregistry.azurecr.io/mon-app:<commit>`.

1. Tests unitaires
2. Recherche de secrets
3. Build et publication de l'image (Buildah)
4. Scan de vulnérabilités Trivy
5. Signature de l'image (Cosign) (branche principale)
6. Plan OpenTofu
7. Application OpenTofu (branche principale, manuel)
8. Déploiement Helm — Préproduction (branche principale)
9. Analyse dynamique ZAP (scan d'API) — Préproduction (branche principale, non bloquant)
10. Déploiement Helm — Production (branche principale, manuel)

## Variables CI

Les variables sans valeur sont à déclarer dans la CI ; les autres sont déjà écrites dans les fichiers.

| Variable | Secret | Valeur | Rôle |
| --- | --- | --- | --- |
| `REGISTRY_USER` | oui | à déclarer | Compte de publication sur monappregistry.azurecr.io |
| `REGISTRY_PASSWORD` | oui | à déclarer | Mot de passe ou jeton de publication sur monappregistry.azurecr.io |
| `ZAP_TARGET_URL` | non | `https://api-recette.boutique.fr/openapi.json` | Adresse analysée par ZAP (définition OpenAPI de l'API) |
| `AZURE_CLIENT_ID` | non | à déclarer | Identifiant d'application Entra ID |
| `AZURE_TENANT_ID` | non | à déclarer | Identifiant du tenant Entra ID |
| `AZURE_SUBSCRIPTION_ID` | non | à déclarer | Identifiant d'abonnement Azure |

## Diagnostics restants

- **Avertissement** (R34) — Azure Container Registry : « Nom du registre ACR » non renseigné : la valeur d'exemple « monappregistry » sera écrite dans les fichiers.
- **Avertissement** (R34) — Azure Kubernetes Service : « Nom du cluster » non renseigné : la valeur d'exemple « mon-cluster » sera écrite dans les fichiers.
- **Avertissement** (R34) — Azure Blob Storage : « Compte de stockage » non renseigné : la valeur d'exemple « monprojettfstate » sera écrite dans les fichiers.
- **Info** (R50) — Tekton est expérimental : pas de porte d'approbation native : la production part d'un déclenchement manuel ; secrets de la CI à déclarer à la main.

## Notes

- Mise en route pas à pas, avec les commandes du projet : docs/mise-en-route.md.
- Approbation (« Production ») : Tekton n'a pas de porte d'approbation native : ces déploiements sont des pipelines séparés (tekton/pipeline-deploy-*.yaml), à lancer après validation (tkn pipeline start).
- ZAP analyse l'environnement « Préproduction » à l'adresse ZAP_TARGET_URL (https://api-recette.boutique.fr/openapi.json) après son déploiement ; rapport en artefact du job (zap-report.html). L'adresse doit être joignable depuis les machines de la CI. Le job signale sans bloquer ; paramètre « Bloquant » pour arrêter le pipeline.
- `scripts/test-kind.sh` déploie le pipeline dans un cluster kind jetable (chart Helm) : utile avant la première mise en production.

## Fichiers générés

- `.github/dependabot.yml`
- `.zap/rules.tsv`
- `PIPELINE.md`
- `charts/mon-app/Chart.yaml`
- `charts/mon-app/templates/deployment.yaml`
- `charts/mon-app/templates/service.yaml`
- `charts/mon-app/values-production.yaml`
- `charts/mon-app/values-staging.yaml`
- `charts/mon-app/values.yaml`
- `devops-builder.yaml`
- `docs/mise-en-route.md`
- `infra/terraform/.gitignore`
- `infra/terraform/main.tf`
- `infra/terraform/outputs.tf`
- `infra/terraform/variables.tf`
- `infra/terraform/versions.tf`
- `platform/install.sh`
- `scripts/test-kind.sh`
- `tekton/pipeline-deploy-production.yaml`
- `tekton/pipeline.yaml`
