# Mon projet — pipeline généré

Généré par DevOps Builder le AAAA-MM-JJ. Cible : Kubernetes autogéré.

## Environnements

Ordre de promotion : la même image est déployée successivement dans chaque environnement.

| Environnement | Type | Approbation | Cluster | Espace de noms / projet |
| --- | --- | --- | --- | --- |
| Préproduction (`staging`) | Préproduction | non | k3s | `mon-app-staging` |
| Production (`production`) | Production | oui | k3s | `mon-app` |

## Ports

| Environnement | Composant | Port publié | Port du conteneur | Usage | Exposition |
| --- | --- | --- | --- | --- | --- |
| Préproduction | mon-app | — | 8000 | application | Service mon-app port 80, espace de noms mon-app-staging, exposé par Traefik, hôte staging.mon-app.example.com |
| Préproduction | CloudNativePG | — | 5432 | PostgreSQL | Service mon-app-pg-rw, espace de noms mon-app-staging, interne au cluster |
| Préproduction | Gitea | — | 3000 | interface web | Service Kubernetes, espace de noms gitea, exposé par Traefik, hôte gitea.example.com |
| Préproduction | Gitea | — | 22 | SSH Git | Service Kubernetes, espace de noms gitea |
| Préproduction | SonarQube | — | 9000 | interface web | Service Kubernetes, espace de noms sonarqube, exposé par Traefik, hôte sonarqube.example.com |
| Préproduction | Traefik | — | 80 | HTTP | Service Kubernetes, espace de noms traefik |
| Préproduction | Traefik | — | 443 | HTTPS | Service Kubernetes, espace de noms traefik |
| Préproduction | Prometheus | — | 9090 | interface et API | Service Kubernetes, espace de noms monitoring |
| Préproduction | Grafana | — | 3000 | interface web | Service Kubernetes, espace de noms monitoring, exposé par Traefik, hôte grafana.example.com |
| Préproduction | Grafana | — | 3000 | interface web | Service Kubernetes, espace de noms monitoring, exposé par Traefik, hôte grafana.example.com |
| Production | mon-app | — | 8000 | application | Service mon-app port 80, espace de noms mon-app, exposé par Traefik, hôte mon-app.example.com |
| Production | CloudNativePG | — | 5432 | PostgreSQL | Service mon-app-pg-rw, espace de noms mon-app, interne au cluster |
| Production | Gitea | — | 3000 | interface web | Service Kubernetes, espace de noms gitea, exposé par Traefik, hôte gitea.example.com |
| Production | Gitea | — | 22 | SSH Git | Service Kubernetes, espace de noms gitea |
| Production | SonarQube | — | 9000 | interface web | Service Kubernetes, espace de noms sonarqube, exposé par Traefik, hôte sonarqube.example.com |
| Production | Traefik | — | 80 | HTTP | Service Kubernetes, espace de noms traefik |
| Production | Traefik | — | 443 | HTTPS | Service Kubernetes, espace de noms traefik |
| Production | Prometheus | — | 9090 | interface et API | Service Kubernetes, espace de noms monitoring |
| Production | Grafana | — | 3000 | interface web | Service Kubernetes, espace de noms monitoring, exposé par Traefik, hôte grafana.example.com |
| Production | Grafana | — | 3000 | interface web | Service Kubernetes, espace de noms monitoring, exposé par Traefik, hôte grafana.example.com |

## Données

L'application lit l'URL de connexion complète dans la variable indiquée ; le mot de passe ne figure dans aucun fichier du dépôt.

| Base | Mode | Où | Variable de l'application | Mot de passe / URL | Sauvegarde |
| --- | --- | --- | --- | --- | --- |
| CloudNativePG | opérateur Kubernetes | Cluster CloudNativePG dans l'espace de noms de l'application | `DATABASE_URL` | Secret `<release>-pg-app` créé par l'opérateur | plugin Barman Cloud ou instantanés de volumes, à configurer |

## Briques

| Étape | Brique | Licence | Fiche |
| --- | --- | --- | --- |
| Source | GitHub | proprietary | vérifiée |
| Source | Gitea | MIT | vérifiée |
| Build | GitHub Actions | proprietary | vérifiée |
| Build | BuildKit (docker buildx) | Apache-2.0 | vérifiée |
| Build | Dependabot | proprietary | vérifiée |
| Tests & qualité | Tests unitaires | MIT | vérifiée |
| Tests & qualité | SonarQube | LGPL-3.0 | vérifiée |
| Sécurité | Gitleaks | MIT | vérifiée |
| Sécurité | Trivy | Apache-2.0 | vérifiée |
| Sécurité | Cosign | Apache-2.0 | vérifiée |
| Artefacts | GitHub Container Registry | proprietary | vérifiée |
| Infrastructure | k3s | Apache-2.0 | vérifiée |
| Données | CloudNativePG | Apache-2.0 | vérifiée |
| Déploiement | Helm | Apache-2.0 | vérifiée |
| Plateforme | Traefik | MIT | vérifiée |
| Plateforme | cert-manager | Apache-2.0 | vérifiée |
| Observabilité | Prometheus | Apache-2.0 | vérifiée |
| Observabilité | Grafana | AGPL-3.0 | vérifiée |
| Observabilité | Grafana | AGPL-3.0 | vérifiée |

## Étapes CI

Orchestrateur : GitHub Actions. Image publiée : `ghcr.io/OWNER/mon-app:<commit>`.

1. Tests unitaires
2. Qualité SonarQube
3. Recherche de secrets
4. Build et publication de l'image (BuildKit (docker buildx))
5. Scan de vulnérabilités Trivy
6. Signature de l'image (Cosign) (branche principale)
7. Déploiement Helm — Préproduction (branche principale)
8. Déploiement Helm — Production (branche principale, manuel)

## Variables CI

Les variables sans valeur sont à déclarer dans la CI ; les autres sont déjà écrites dans les fichiers.

| Variable | Secret | Valeur | Rôle |
| --- | --- | --- | --- |
| `SONAR_HOST_URL` | non | à déclarer | URL du serveur SonarQube |
| `SONAR_TOKEN` | oui | à déclarer | Jeton d'analyse SonarQube |
| `KUBECONFIG_DATA_STAGING` | oui | à déclarer | Contenu du kubeconfig de k3s (Préproduction) (base64) |
| `KUBECONFIG_DATA_PRODUCTION` | oui | à déclarer | Contenu du kubeconfig de k3s (Production) (base64) |

## Diagnostics restants

- **Avertissement** (R34) — Traefik : « Adresse publique de l'application » non renseigné : la valeur d'exemple « mon-app.example.com » sera écrite dans les fichiers.
- **Avertissement** (R40) — CloudNativePG tourne dans le cluster et sert « Production », mais rien ne sauvegarde ses données : ajouter Velero, des instantanés de volumes ou les sauvegardes de l'opérateur, et tester la restauration.
- **Avertissement** (R55) — Deux briques portent le même identifiant « grafana » : donner un nom d'instance différent à chacune (une seule est générée).

## Notes

- Mise en route pas à pas, avec les commandes du projet : docs/mise-en-route.md.
- Approbation (« Production ») : déclarer des relecteurs obligatoires sur l'environnement du dépôt (Settings › Environments › Required reviewers), sinon le déploiement part sans attendre.
- Bases dédiées : une base PostgreSQL par outil dans platform/db-<instance>.yaml (Cluster CloudNativePG avec l'opérateur, sinon StatefulSet). Les réglages Helm qui branchent l'outil sur sa base (clés --set de install.sh) suivent la documentation de chaque chart : les vérifier à la première installation.
- HTTPS Kubernetes : platform/cluster-issuer.yaml (Let's Encrypt, challenge HTTP-01) ; chaque nom d'hôte doit pointer vers l'adresse publique du contrôleur d'entrée avant l'émission du certificat.
- Poste de développement : `docker compose -f dev/db/compose.yaml up -d` lance les bases du projet (même version), `dev/db/app.env` donne leurs variables de connexion.
- CloudNativePG : l'opérateur est installé par platform/install.sh ; le Cluster crée le Secret « <cluster>-app » (clés uri, jdbc-uri, host, user, password) lu par l'application. Sauvegardes : renseigner « Destination des sauvegardes » dans la brique (plugin Barman Cloud), ou des instantanés de volumes.
- `scripts/test-kind.sh` déploie le pipeline dans un cluster kind jetable (chart Helm) : utile avant la première mise en production.
- `scripts/ci-variables.sh` déclare les 4 variable(s) à renseigner avec GitHub (gh), sans écrire leurs valeurs dans le dépôt.

## Fichiers générés

- `.github/dependabot.yml`
- `.github/workflows/pipeline.yml`
- `PIPELINE.md`
- `charts/mon-app/Chart.yaml`
- `charts/mon-app/templates/cloudnative-pg.yaml`
- `charts/mon-app/templates/deployment.yaml`
- `charts/mon-app/templates/ingress.yaml`
- `charts/mon-app/templates/service.yaml`
- `charts/mon-app/values-production.yaml`
- `charts/mon-app/values-staging.yaml`
- `charts/mon-app/values.yaml`
- `dev/db/app.env`
- `dev/db/compose.yaml`
- `dev/db/init/postgresql/README.md`
- `devops-builder.yaml`
- `docs/mise-en-route.md`
- `infra/cluster/install-k3s.sh`
- `platform/cluster-issuer.yaml`
- `platform/db-gitea.yaml`
- `platform/db-grafana.yaml`
- `platform/db-sonarqube.yaml`
- `platform/install.sh`
- `scripts/ci-variables.sh`
- `scripts/test-kind.sh`
