# matrice — pipeline généré

Généré par DevOps Builder le AAAA-MM-JJ. Cible : Kubernetes autogéré.

## Environnements

Ordre de promotion : la même image est déployée successivement dans chaque environnement.

| Environnement | Type | Approbation | Cluster | Espace de noms / projet |
| --- | --- | --- | --- | --- |
| Production (`production`) | Production | non | k3s | `mon-app` |

## Briques

| Étape | Brique | Licence | Fiche |
| --- | --- | --- | --- |
| Source | GitLab | MIT | vérifiée |
| Build | Jenkins | MIT | vérifiée |
| Build | BuildKit (docker buildx) | Apache-2.0 | vérifiée |
| Tests & qualité | Tests unitaires | MIT | vérifiée |
| Tests & qualité | SonarQube | LGPL-3.0 | vérifiée |
| Artefacts | Harbor | Apache-2.0 | vérifiée |
| Infrastructure | k3s | Apache-2.0 | vérifiée |
| Déploiement | Kustomize | Apache-2.0 | vérifiée |

## Étapes CI

Orchestrateur : Jenkins. Image publiée : `registry.example.com/mon-app/mon-app:<commit>`.

1. Tests unitaires
2. Qualité SonarQube
3. Build et publication de l'image (BuildKit (docker buildx))
4. Déploiement Kustomize (branche principale)

## Variables CI

Les variables sans valeur sont à déclarer dans la CI ; les autres sont déjà écrites dans les fichiers.

| Variable | Secret | Valeur | Rôle |
| --- | --- | --- | --- |
| `SONAR_HOST_URL` | non | à déclarer | URL du serveur SonarQube |
| `SONAR_TOKEN` | oui | à déclarer | Jeton d'analyse SonarQube |
| `REGISTRY_USER` | oui | à déclarer | Compte de publication sur registry.example.com |
| `REGISTRY_PASSWORD` | oui | à déclarer | Mot de passe ou jeton de publication sur registry.example.com |
| `KUBECONFIG_DATA` | oui | à déclarer | Contenu du kubeconfig de k3s (base64) |

## Diagnostics restants

- **Avertissement** (R34) — Harbor : « Adresse du registre » non renseigné : la valeur d'exemple « registry.example.com » sera écrite dans les fichiers.

## Notes

- `scripts/test-kind.sh` déploie le pipeline dans un cluster kind jetable (overlay Kustomize) : utile avant la première mise en production.

## Fichiers générés

- `Jenkinsfile`
- `PIPELINE.md`
- `deploy/kustomize/base/deployment.yaml`
- `deploy/kustomize/base/kustomization.yaml`
- `deploy/kustomize/base/service.yaml`
- `deploy/kustomize/overlays/production/kustomization.yaml`
- `devops-builder.yaml`
- `infra/cluster/install-k3s.sh`
- `platform/install.sh`
- `scripts/test-kind.sh`
