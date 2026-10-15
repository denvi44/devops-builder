# Journal des modifications

Format inspiré de [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/). Jusqu'à la 1.0, une version
mineure peut changer les fichiers générés ; chaque changement voulu est relu dans les projets de référence
(`tests/golden/`). Les fichiers projet de toutes les versions restent lisibles (voir `docs/format.md`).

## Non publié — lot 0.18 en cours

### Ajouté
- **Deux identités de CI par cloud** (AWS, Google Cloud, Azure, connexion OIDC) : les jobs d'infrastructure (plan,
  apply) prennent la leur, aux droits étendus (`AWS_INFRA_ROLE_ARN`, `GCP_INFRA_SERVICE_ACCOUNT`,
  `AZURE_INFRA_CLIENT_ID`) ; build et déploiement gardent une identité limitée à ce qu'ils font, déduit des étapes
  générées (pousser l'image, accéder au cluster, mettre à jour ECS, Cloud Run ou Container Apps, lire l'état).
  Avec GitHub, seul le plan ou l'apply obtient l'identité d'infrastructure ; avec GitLab, dont le jeton ne
  distingue pas les jobs, la séparation tient aux variables. Le mode d'emploi crée les deux. Ces droits réduits
  n'ont pas encore été éprouvés sur un vrai compte cloud.
- EKS : accès Kubernetes du rôle de déploiement par entrée d'accès, administrateurs déclarés dans
  `cluster_admin_arns` (l'identité qui applique la pile change après le premier apply).
- **Renovate hors GitHub** : job planifié dans GitLab CI (pipeline portant `RENOVATE=1`, les autres jobs exclus),
  workflow planifié pour Gitea Actions ; planification créée par l'API dans le mode d'emploi. Scénario
  `gitea-renovate` : Renovate lancé comme le workflow généré ouvre son tableau de bord et ses demandes de fusion
  sur une vraie forge Gitea.
- **Connexion unique de Harbor et SonarQube** : Harbor reçoit ses réglages OIDC par le chart et son adresse
  publique ; SonarQube Community, qui ne parle pas OIDC, est relié à Keycloak en SAML (client et attributs dans le
  realm, réglages par l'API dans le mode d'emploi), vérifié jusqu'à la page de connexion de Keycloak ; avec Dex,
  son authentification GitHub ou GitLab intégrée. Sur hôte Docker, Grafana et SonarQube sont servis par Traefik à
  l'adresse que connaît le fournisseur d'identité.
- Scénario `kind-plateforme` : `platform/install.sh` d'un projet à vingt-huit charts, chacun rendu avec les options
  générées et passé à kubeconform.
- Verrou d'état Terraform sur Scaleway et OVHcloud (`use_lockfile`, écriture conditionnelle documentée par les
  deux) ; Outscale OOS reste sans verrou.

### Corrigé
- **SonarQube ne s'installait pas sur Kubernetes** : le chart exige l'édition (Community) et un code de sonde.
- **Loki ne s'installait pas sur Kubernetes** : le chart exige un stockage ; disque du pod et schéma de test,
  stockage objet à poser en production.
- `platform/install.sh` avec Dex s'arrêtait (`set -u`) quand le secret d'un client n'était pas encore renseigné.
- Politique de confiance AWS de la CI avec GitLab : deux clés `StringEquals`, l'une écrasait l'autre (la condition
  sur l'audience du jeton disparaissait).
- Elasticsearch de SonarQube sur hôte Docker sans `vm.max_map_count` à régler ; dimensionnement de SonarQube porté à
  2,5 Gio (mesuré à 2,4 Gio au repos).
- Mode d'emploi : les outils branchés sur la connexion unique ne citent plus Vault ou Argo CD absents du projet.

## 0.17.0 — 2026-10-15 — Vérification sur une vraie infrastructure

Les fichiers générés sont exécutés pour de vrai sur les machines de GitHub Actions (onze scénarios, chaque nuit) ;
ces passages ont trouvé une dizaine de défauts, corrigés ci-dessous. Le déploiement réel sur un cloud
(apply puis destroy) attend un compte de test et viendra dans une 0.17.x.

### Ajouté
- Tests de bout en bout (`tools/e2e/run.py`, workflow « Bout en bout ») : les fichiers générés exécutés pour
  de vrai sur les machines de GitHub Actions. Trois scénarios pour commencer : chart Helm avec CloudNativePG
  dans kind, overlays Kustomize avec PostgreSQL et Valkey dans kind, hôte Docker avec Compose, sauvegarde
  puis restauration. Une application de démonstration (`tools/e2e/app`) ne répond 200 sur `/db` que si
  chaque base accepte une connexion authentifiée avec les secrets transmis par le pipeline.
- Second palier : OpenBao initialisé et configuré par les scripts générés puis lu par External Secrets
  (`kind-coffre-openbao`) ; Keycloak par son opérateur derrière Traefik, realm appliqué par OpenTofu puis relu
  sans écart, revendication `groups` vérifiée (`kind-identite-keycloak`). Preuves publiées en annotations.

### Ajouté (suite)
- Zabbix pris en charge sur hôte Docker et VM : images officielles 7.4 (serveur, interface web, agent 2) et base
  PostgreSQL dédiée, mot de passe par le circuit habituel (variables CI, SOPS ou coffre), interface derrière
  Traefik, section du mode d'emploi (mot de passe Admin à changer par l'API, agent vérifié). Keycloak, Dex et
  Zabbix apparaissent dans la vue Ports, et R39 signale leur conflit sur 8080 sans Traefik.

- Fiches Puppet, Chef Infra, Elasticsearch, Kibana, Logstash, ZAP, Burp Suite DAST, CircleCI et Drone CI, au niveau
  « à configurer à la main » : dans la palette et contrôlées par les règles (rôle déjà tenu, licence, cycle de
  vie). Leurs entrées du CNCF Landscape mènent à la fiche. Règle R51 : Drone CI, repris par Harness, avec
  remplacement par Woodpecker.

- Bases de Zabbix et de Keycloak sur l'hôte Docker sauvegardées et restaurées par `db-backup.sh` et
  `db-restore.sh`, comme celles de l'application.
- Scénarios de bout en bout `compose-sops` (clé age, brique, `secrets-seed.sh`, puis les lignes mêmes de la CI
  générée) et sauvegarde-restauration de Zabbix.
- **ZAP pris en charge (DAST)** : un job après le déploiement de l'environnement analysé (par défaut le dernier
  avant la production), avant le déploiement suivant, dans chaque CI générée. Scan de base (passif), complet
  ou d'API (OpenAPI) ; image officielle à version fixe (2.17.0) ; adresse analysée réglable par environnement ;
  `.zap/rules.tsv` généré (règles d'en-têtes et de cookies à FAIL) ; rapport HTML et JSON publié même en échec ;
  non bloquant par défaut, paramètre « Bloquant ». Section « Analyse dynamique » du mode d'emploi. Scénario de
  bout en bout `compose-zap` : le job extrait du workflow généré analyse l'application derrière Traefik, en root
  comme sur GitHub Actions et sous l'utilisateur de l'image comme sur GitLab CI.

- **Dimensionnement des machines** : besoin de chaque hôte Docker calculé à partir des services du fichier
  Compose généré (application, bases, Traefik, Keycloak, Zabbix, SonarQube, Prometheus, Grafana…), multiplié par
  les environnements qu'il porte ; section « Dimensionnement » de `PIPELINE.md` ; pour les machines créées par
  Terraform, type retenu comparé au besoin et plus petit type suffisant proposé sur chacun des six clouds.
  Règle R52 (machine sous-dimensionnée) avec correction en un clic, par environnement quand les machines
  diffèrent. Valeurs par service dans `data/sizing.yaml`, sourcées quand une documentation les donne (Keycloak,
  Grafana, SonarQube), estimées sinon.

- Scénarios de bout en bout `kind-argocd` (dépôt GitOps privé sur Gitea, Argo CD installé par
  `platform/install.sh` et branché par le mode d'emploi, job de déploiement de la CI joué dans alpine comme sur
  GitLab : l'étiquette poussée arrive dans le cluster, une relance sans changement ne casse rien) et `compose-dex`
  (découverte OpenID, connexion de l'application suivie jusqu'à la page d'autorisation de la forge, adresse de
  retour inconnue refusée). Un scénario seul se lance à la demande (entrée `scenario` du workflow).
- Paramètre « Dépôt GitOps » des briques Argo CD et Flux, repris dans les applications, la source Flux et la
  variable `GITOPS_REPO` ; mode d'emploi Argo CD sans la CLI `argocd` (secret de dépôt étiqueté, attente de la
  synchronisation), jeton de lecture saisi sans écho.

### Corrigé
- **GitOps (Argo CD, Flux) ne pouvait pas fonctionner tel que généré** : le dépôt surveillé était une adresse
  d'exemple codée en dur ; la CI ne changeait que l'étiquette de l'image, si bien que le dépôt restait
  `ghcr.io/OWNER/…` (Helm) ou `$CI_REGISTRY_IMAGE` que Kustomize ne développe pas ; `apk add yq` est ambigu sur
  Alpine 3.20 (`yq-go` maintenant) ; un pipeline relancé échouait sur un commit vide ; avec le dépôt de
  l'application comme dépôt GitOps, chaque mise à jour relançait le pipeline (commits marqués `[skip ci]`).
  La source Flux reçoit le secret d'accès créé par le mode d'emploi.
- **Dex sur hôte Docker démarrait sans application OAuth** : Compose remplaçait `$DEX_CONNECTOR_ID` et
  `$DEX_CONNECTOR_SECRET` de sa configuration par l'environnement du shell au déploiement, vide sur l'hôte, et
  `DEX_CONNECTOR_ID` n'était écrit nulle part. Les deux sont désormais lus par Dex dans `secrets/dex.env`. Le
  premier passage du scénario `compose-dex` réussissait parce que le harnais transmettait les secrets à
  `docker compose up` : il ne transmet plus que `IMAGE`, comme le déploiement par SSH.
- Étapes non bloquantes (Checkov, KICS, Snyk, Infracost, Floci) : Tekton, AWS CodeBuild et Google Cloud Build
  arrêtaient le pipeline à leur échec ; elles sont maintenant tolérées (`onError: continue`, `allowFailure`,
  échec signalé dans le journal de CodeBuild).
- **Binaire sops non vérifié** : la CI générée téléchargeait sops et l'exécutait, clé age en mémoire, sans
  contrôle ; son empreinte publiée est maintenant vérifiée (`sha256sum -c`) avant exécution.
- **Traefik sur hôte Docker ne faisait pas de HTTPS** : aucune configuration TLS, le port 443 répondait en HTTP
  clair. TLS sur l'entrée websecure, certificat Let's Encrypt (challenge TLS), redirection du port 80, volume
  des certificats ; adresse ACME facultative (paramètre « Contact Let's Encrypt »). Trouvé en préparant les
  tests de bout en bout de l'hôte Docker.
- Validation installée par pipx : les outils ajoutés à l'environnement de l'application
  (`pipx inject devops-builder shellcheck-py`) sont trouvés, alors qu'ils restaient « absents » ; le conseil
  d'installation propose `pipx inject` sous pipx ; un contrôle sans outil liste les fichiers générés qui le
  demandent (signalé lors du premier essai sur macOS).
- Python 3.15 refusé à l'installation avec un message clair (`requires-python`), au lieu d'un échec de PySide6,
  dont les versions 6.11 ne vont pas au-delà de Python 3.14 (vu lors de l'installation sur macOS).
- PySide6 limité aux 6.11 pour toutes les versions de Python : la 6.12.0 provoque aussi des erreurs de
  segmentation intermittentes sous Python 3.12 (vu sur la CI), pas seulement le plantage de sortie sous 3.11.
- Keycloak sur Kubernetes ne démarrait pas, deux défauts trouvés par les tests de bout en bout :
  `platform/install.sh` n'installait pas les CRD `keycloakoidcclients` et `keycloaksamlclients` de
  l'opérateur 26.8, qui ne devenait jamais disponible ; et l'image officielle, désignée dans la ressource
  `Keycloak`, était lancée avec `--optimized` et s'arrêtait en boucle (`startOptimized: false` ajouté).

## 0.16.1 — 2026-10-12

Préparation de l'ouverture du dépôt ; aucun changement des fichiers générés.

### Corrigé
- Sous Python 3.11, PySide6 6.12.0 fait planter l'interpréteur (« deallocating None », défaut de comptage de
  références de PySide6, masqué à partir de Python 3.12) : PySide6 est limité aux 6.11 sous Python 3.11.
  Trouvé en lançant la suite dans un environnement neuf, comme le fera la CI.

### Ajouté
- Licence Apache 2.0 (`LICENSE`, texte officiel vérifié par un test), `NOTICE` (attribution des données du
  CNCF Landscape), en-tête SPDX dans chaque fichier Python, métadonnées du paquet (expression de licence,
  adresses du dépôt GitHub).
- `docs/licences-tierces.md` : licence de chaque dépendance et des données embarquées, obligations de la LGPL
  de PySide6 pour les futurs exécutables.
- Fichiers du dépôt public : CI GitHub Actions (actions épinglées par empreinte), Dependabot, modèles de
  ticket et de demande de fusion, `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, `ROADMAP.md`.

## 0.16.0 — 2026-10-12

Gel du périmètre en vue de la 1.0 : aucune brique nouvelle, un contrat de compatibilité.

### Ajouté
- Niveau de prise en charge de chaque fiche : pris en charge, expérimental (avec la limite), à configurer à
  la main ; affiché dans la palette (β, ⚙), sur le canevas et dans Propriétés ; matrice publiée dans
  `docs/prise-en-charge.md`, contrôlée contre ce que les générateurs produisent.
- Règle R50 : une brique expérimentale rappelle sa limite.
- Fichiers projet : les champs inconnus d'une version plus récente sont conservés et signalés ; un format plus
  récent est refusé avec un message clair ; erreurs de lecture en français, avec la ligne ou le champ.
- Ligne de commande : codes de sortie stables (0, 1, 2), `--json` pour `check`, `generate` et `validate`,
  `--version` ; `docs/ligne-de-commande.md`.
- `docs/format.md` (champs, migrations, promesse de compatibilité) et ce journal.

### Modifié
- Un fichier projet absent ou illisible donne le code 2 et un message sur la sortie d'erreur, au lieu d'une
  trace Python ; l'interface affiche le message au lieu de s'arrêter.

### Tests
- Fichiers projet écrits par chaque version de la 0.1 à la 0.15 : ouverts, contrôlés, générés et réenregistrés
  sans perte de valeur.
- `DEVOPS_BUILDER_TOFU_MIRROR` désigne partout le dossier du miroir de providers (le test du realm Keycloak
  de la 0.15 l'attendait comme fichier de configuration, si bien qu'un des deux tests échouait toujours).

## 0.15.0 — 2026-10-12 — Connexion unique

- Keycloak sur hôte Docker (Traefik, base dédiée) ou par son opérateur sur Kubernetes ; realm en Terraform
  (groupes, revendication groups, client PKCE de l'application, client de chaque outil).
- Dex délégant à GitLab ou GitHub.
- OIDC branché sur Argo CD, Grafana et Vault / OpenBao ; `OIDC_ISSUER_URL` et `OIDC_CLIENT_ID` pour
  l'application. Règles R48 et R49 ; choix « Connexion unique » dans l'assistant.

## 0.14.0 — 2026-10-12 — Données

- Vue « Données » par environnement ; variable et format de connexion réglables (URL, JDBC, variables
  séparées), repris de l'analyse du code.
- `dev/db/` pour le poste de développement ; `scripts/db-restore.sh`.
- Sauvegardes CloudNativePG par le plugin Barman Cloud. Règles R46 et R47.

## 0.13.0 — 2026-10-11 — Mode d'emploi

- `docs/mise-en-route.md` généré pour chaque projet ; `scripts/vault-setup.sh` ; identité d'External Secrets
  par Terraform (EKS Pod Identity, Workload Identity de GKE et d'AKS).

## 0.12.0 — 2026-10-11 — Secrets

- Source des secrets : variables CI, SOPS + age, Vault / OpenBao (connexion JWT de la CI) ; External Secrets ;
  coffres des clouds écrits par Terraform. Règle R45.

## 0.11.0 — 2026-10-11 — Machines

- Machines créées par Terraform sur six clouds, chaînées à Ansible et au déploiement SSH
  (`scripts/tf-inventory.sh`).

## 0.10.0 — 2026-10-11 — Ansible

- Hôtes par environnement, `ansible.cfg`, `requirements.yml`, déploiement hôte par hôte ; brique ansible-lint.

## 0.9.0 — 2026-10-11 — Terraform et Floci

- Backends d'état chiffrés et verrouillés, providers à jour, TFLint, Infracost, Floci. Règle R44.

## 0.8.0 — 2026-10-09 — Étape Données

- Bases autogérées, CloudNativePG, bases managées, migrations de schéma. Règles R40 à R43.
- Format : étape `data` ajoutée, omise quand elle est vide.

## 0.7.0 — 2026-10-09 — L'application d'abord

- Analyse du dossier de l'application ; palette restreinte au projet ; commandes `scan` et `init`.

## 0.6.0 — 2026-10-09 — Environnements

- Environnements Bac à sable et Recette ; vue Ports ; hôte Docker partagé. Règle R39.
- Format : champs `host` et `port_offset` des environnements, omis quand ils ne servent pas.

## 0.5.0 — 2026-10-09 — Entretien du catalogue

- Contrôle des fiches, corrections réversibles, catalogue personnel, rafraîchissement du Landscape ;
  commandes `catalog-check`, `catalog-import`, `landscape-refresh`.

## 0.4.0 — 2026-10-09 — Validation et export

- Validation locale, test kind, écriture prudente (fichiers retouchés préservés), export Git, variables CI.
- Projets de référence et fichiers des versions précédentes dans les tests.

## 0.3.0 — 2026-10-09 — Environnements et assistant

- Chaîne d'environnements avec approbation ; assistant de démarrage. Règles R35 à R38.
- Format 2 : la liste `environments` remplace le champ `environment` (migration automatique).

## 0.2.0 — 2026-10-08 — Complétude

- Règles R26 à R34, paramètres typés, Renovate, Dependabot, scripts d'installation des clusters.

## 0.1.0 — 2026-10-08

- Catalogue, moteur de règles, générateurs et interface ; outils limités à leurs étapes (R25).
