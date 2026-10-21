# Journal des modifications

Format inspiré de [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/). Jusqu'à la 1.0, une version
mineure peut changer les fichiers générés ; chaque changement voulu est relu dans les projets de référence
(`tests/golden/`). Les fichiers projet de toutes les versions restent lisibles (voir `docs/format.md`).

## 0.26.0 — non publié — Réseau privé, répartiteur de charge, clés Helm et noms de Service éprouvés

### Ajouté
- **Capacité « répartiteur de charge »** (deuxième de la feuille de route 1.1) : une brique par cloud — Amazon Elastic Load Balancing (NLB), Google Cloud Load Balancing, Azure Load Balancer, Scaleway Load Balancer, OVHcloud Load Balancer, Outscale LBU — qui place un répartiteur TCP devant chaque groupe de machines créé par la pile (ports web, sonde TCP, Traefik garde le TLS). L'adresse est une sortie `lb_<groupe>` : le DNS pointe vers elle. Sur AWS et Outscale, le répartiteur utilise le réseau privé du projet s'il existe, sinon le réseau par défaut. Sur Kubernetes, aucune ressource n'est écrite : le Service ou l'entrée demande le répartiteur au cloud (une note le dit).
  - OVHcloud (fiche expérimentale) : répartiteur, pool et écouteurs sur le réseau privé (la règle R29 l'exige) ; les machines ne sont pas encore sur ce réseau, leurs adresses sont à ajouter au pool à la main. Outscale : fiche expérimentale, non essayée sur un compte.
- Six piles de référence `repartiteur-machines-*`.
- **Capacité « réseau privé »** (première de la feuille de route 1.1) : une brique par cloud — Amazon VPC, Google Cloud VPC, Azure Virtual Network, Scaleway VPC, OVHcloud Private Network, Outscale Net — qui crée le réseau une fois dans la pile OpenTofu (sous-réseaux calculés dans la plage choisie) et le rattache aux clusters, aux machines et aux bases du projet. La palette ne propose que la brique du cloud du projet.
  - AWS : sous-réseaux publics (machines) et privés (EKS, RDS) sur deux zones, passerelle NAT selon le choix (`auto` = seulement avec EKS), groupe de sous-réseaux et groupe de sécurité de la base. Les quatre variables saisies à la main (`vpc_id`, `subnet_ids`, `db_subnet_group`, `db_security_group_ids`) disparaissent.
  - Google Cloud : réseau et sous-réseau pour GKE et les machines, Cloud NAT au choix, Cloud SQL en adresse privée.
  - Azure : un seul réseau virtuel pour les machines, AKS (Azure CNI) et le serveur flexible (sous-réseau délégué, zone DNS privée).
  - Scaleway : réseau privé rattaché à Kapsule, aux instances et à la base managée.
  - OVHcloud (cluster seulement) et Outscale (machines) : fiches expérimentales, non essayées sur un compte.
- **Scénarios `aws-ec2-chaine` et `aws-ecs-floci`** : le VPC est créé par la pile jouée sur Floci.
- Cinq piles de référence avec cluster et base, six avec machines (`reseau-prive-*`), passées à `tofu validate` avec les providers par la CI.
- **Scénario `aws-ecs-floci`** : la pile du modèle AWS ECS Fargate (ECR, RDS PostgreSQL, Secrets Manager) appliquée sur Floci. La suppression de la base RDS ne se termine pas dans Floci : le scénario borne le `destroy` à quatre minutes.
- **Scénario `kind-plateforme`** : une deuxième instance nommée de Grafana, SonarQube, Jenkins, Gitea, Zot et Jaeger ; chaque option `--set` est contrôlée contre les valeurs du chart (clé plate à point non échappée), et le Service rendu de chaque instance contre celui qu'attend le routage.

### Corrigé
- **Argo CD derrière l'entrée** : l'option `configs.params.server.insecure` n'avait aucun effet, la clé du chart étant plate (`server.insecure`) ; elle est écrite `configs.params.server\.insecure`.
- **SonarQube** : le Service du chart est `<release>-sonarqube` (et non `sonarqube`), ce qui concerne la route Gateway API.
- **Argo CD** : le Service du chart est `argo-cd-argocd-server`, pour la route Gateway API.
- **scripts/tf-floci.sh** crée le groupe de sous-réseaux RDS que la pile suppose existant, et rend la base jetable (sans protection contre la suppression ni instantané final) : l'`apply` d'une pile avec RDS passe sur Floci.

## 0.25.1 — 2026-10-19 — Chaîne des machines éprouvée sur Floci

### Ajouté
- **Scénario `aws-ec2-chaine`** : le modèle AWS EC2 joué sans compte cloud. La pile OpenTofu est appliquée sur Floci, `scripts/tf-inventory.sh` relit l'état gardé pour écrire l'inventaire, puis `site.yml` et `deploy.yml` d'Ansible s'exécutent par SSH, l'application répond derrière Traefik et se rejoue sans échec, avant le `destroy`.
- **`TF_DIR`** pour `scripts/tf-inventory.sh` : lire la pile d'un autre dossier que `infra/terraform`.

### Corrigé
- **ansible/site.yml** n'utilise plus les variables de faits injectées (`ansible_os_family`, `ansible_distribution`…), dépréciées depuis ansible-core 2.19 et retirées plus tard : `ansible_facts['os_family']` à la place. Relevé par le scénario `aws-ec2-chaine`.

### Modifié
- `KEEP=1 scripts/tf-floci.sh apply` garde aussi le dossier de travail (l'état local) et l'indique.

## 0.25.0 — 2026-10-19 — Préparation de la 1.0

### Ajouté
- **Scénario de bout en bout `compose-bases-dediees`** : Gitea sur PostgreSQL, Grafana sur MariaDB et une seconde instance de Grafana sur PostgreSQL, derrière Traefik en HTTPS ; santé de l'application et tables créées dans chaque base vérifiées chaque nuit.
- **Exécutable macOS Intel** (`macos-x86_64`) dans les publications, avec attestation et somme SHA-256.

### Modifié
- Feuille de route : état des versions 0.21 à 0.25 et liste de ce qui reste avant la 1.0.

## 0.24.0 — 2026-10-19 — Bases dédiées : MariaDB, MySQL et Harbor

Le choix « Base de données » s'étend : MariaDB et MySQL pour Gitea et Grafana, et Harbor (Kubernetes) peut utiliser un PostgreSQL à lui.

### Ajouté
- **Autres moteurs** : Gitea et Grafana acceptent `mariadb` et `mysql` en plus de `postgresql` (service Compose avec l'image, le volume, la sonde de santé et la variable de mot de passe du moteur ; sur Kubernetes, un StatefulSet, CloudNativePG ne gérant que PostgreSQL). SonarQube reste en PostgreSQL seulement.
- **Harbor** : `postgresql` dédié sur Kubernetes (`database.type=external` dans install.sh, Cluster CloudNativePG ou StatefulSet). Harbor n'a pas de service Compose.

## 0.23.0 — 2026-10-19 — Une base de données par outil

Gitea, SonarQube et Grafana peuvent avoir leur propre PostgreSQL, sur l'hôte Docker comme sur Kubernetes.

### Ajouté
- **Base PostgreSQL dédiée par outil** : paramètre « Base de données » (`integree` par défaut, `postgresql`) sur Gitea, SonarQube et Grafana, par instance. Hôte Docker : un service `<outil>-db` avec son volume, son mot de passe dans `deploy/secrets.sh` (variable `<OUTIL>_DB_PASSWORD`) et une dépendance « healthy ». Kubernetes : `platform/db-<outil>.yaml` (Cluster CloudNativePG avec l'opérateur, sinon StatefulSet et Secret tiré à l'installation) et les options Helm qui branchent le chart sur cette base. Sans ce choix, rien ne change. Les clés Helm suivent la documentation des charts et sont à vérifier à la première installation.

## 0.22.0 — 2026-10-19 — Adresses et registres en HTTP

Les adresses IP sont signalées là où elles ne marchent pas, et un registre auto-hébergé sans HTTPS est déclaré sur les clients qui le refusent par défaut.

### Ajouté
- **Adresses IP** : la règle **R56** avertit quand l'adresse publique d'un outil, celle de l'application ou le
  domaine des outils est une adresse IP (refusée par un Ingress, sans certificat Let's Encrypt, une IP ne pouvant
  pas porter plusieurs noms). Les registres, eux, peuvent être une IP.
- **Registre auto-hébergé en HTTP simple** (Harbor, Zot, Distribution sur une IP ou `localhost`) : les hôtes Docker
  déployés par Ansible reçoivent `insecure-registries` (`/etc/docker/daemon.json` fusionné sans perte, Docker
  redémarré si le fichier change), k3s reçoit `deploy/registries.yaml`, et une note explique le réglage à faire
  côté CI (Docker, BuildKit, Kaniko, podman).

## 0.21.0 — 2026-10-18 — Pipelines types, accueil et vue Réseau

Douze pipelines complets, prêts à ouvrir et à ajuster : un Kubernetes managé pour chacun des six fournisseurs du
catalogue, et des variantes sans Kubernetes ; un écran d'accueil qui dit par où commencer. Avec Traefik sur hôte Docker, les interfaces web passent derrière lui : les fichiers générés de ces projets changent (voir « Modifié »).

### Modifié
- **Outils derrière Traefik** (hôte Docker avec Traefik) : Grafana, SonarQube, Jenkins, Gitea, console MinIO,
  interface Jaeger et registres Zot / Distribution ne publient plus leur port sur l'hôte ; ils sont servis en HTTPS
  par Traefik, à l'adresse `<outil>.<domaine des outils>` ou au paramètre « Adresse publique » (`hostname`) de la
  brique. Prometheus et Loki, sans authentification, ne sont plus publiés du tout (Grafana les interroge sur le
  réseau Compose). Restent publiés les ports « machine » : OTLP (Jaeger, collecteur), SSH de Gitea, API S3 de
  MinIO. Sans Traefik, rien ne change. Le plan de ports, R39 et la vue Réseau suivent.

- **Entrée Kubernetes** (Traefik, ingress-nginx, Envoy Gateway) : jusqu'ici, le contrôleur d'entrée était installé
  mais rien n'était routé. Le chart Helm (`templates/ingress.yaml`) et les overlays Kustomize (`ingress.yaml`)
  créent désormais l'Ingress de l'application, un nom d'hôte par environnement (paramètre « Adresse publique de
  l'application », maintenant aussi sur Kubernetes et sur ingress-nginx et Envoy Gateway), et `platform/install.sh`
  place Grafana, SonarQube, Jenkins, Gitea, Zot, Harbor, Argo CD, Argo Workflows et Chaos Mesh derrière le contrôleur (classe `traefik` ou `nginx`). Avec Envoy
  Gateway, qui n'a pas d'Ingress : une HTTPRoute par application (chart ou overlay) et `platform/gateway.yaml`
  (GatewayClass, Gateway HTTP, routes des briques). Jaeger, dont le chart n'a pas de réglage d'Ingress fiable, a le
  sien dans `platform/ingress.yaml`. Argo CD derrière l'entrée parle en clair (`configs.params.server.insecure`).
  **HTTPS** quand cert-manager est dans le pipeline : `platform/cluster-issuer.yaml` (ClusterIssuer Let's Encrypt,
  challenge HTTP-01 ; contact facultatif : paramètre « Contact Let's Encrypt »), Ingress de l'application et des
  briques avec `tls` et l'annotation cert-manager, et, avec Envoy Gateway, un listener HTTPS par nom d'hôte sur la
  Gateway (cert-manager installé avec la Gateway API activée). **R54** (information) propose d'ajouter cert-manager
  à une entrée Kubernetes restée en HTTP. Chaque nom d'hôte doit pointer vers l'entrée avant l'émission (cert-manager) ; noms des Services à vérifier.
  Le contrôleur embarqué de k3s est reconnu. Les projets Kubernetes avec un contrôleur voient donc leurs fichiers
  changer et un avertissement R34 de plus (adresse d'exemple).

### Ajouté
- **Plusieurs instances d'un même outil** : deux Grafana, deux Gitea, deux SonarQube… Chaque brique d'un outil
  « multi » porte un nom d'instance (champ `instance`, propriétés de la brique, demande à l'ajout). L'instance
  nommée a son service Compose (`grafana-equipe-b`) ou sa release Helm, ses volumes, son adresse, ses ports
  décalés sans entrée, son Ingress ou sa HTTPRoute et son certificat. Plan de ports et vue Réseau suivent. Règle
  R55 (nom invalide, doublon, outil à instance unique). Les projets existants ne changent pas.
- **Modèles de pipeline par fournisseur** (`devops_builder/modeles.py`) : AWS (EKS, ECS Fargate, EC2), Google
  Cloud (GKE, Cloud Run), Azure (AKS, machines virtuelles), OVHcloud (Managed Kubernetes, instances), Scaleway
  (Kapsule, instance Docker) et Outscale (SecNumCloud, machines). Chacun réunit les services du fournisseur
  (registre, base managée, coffre de secrets, supervision, état OpenTofu), la connexion de la CI au cloud et les
  contrôles de sécurité ; aucune erreur bloquante, seules les valeurs propres au projet restent signalées (R34).
  Menu Fichier › Nouveau depuis un modèle de fournisseur, et `devops-builder template [modèle] -o projet.devops.yaml`.
- **Écran « Par où commencer ? »** : un projet vide ne montre plus trois panneaux vides, mais cinq départs (assistant
  conseillé, modèle de fournisseur, exemple, projet enregistré, construction à la main) ; les panneaux viennent avec
  la première brique. Bandeau **Prochaine étape** (erreurs bloquantes, valeurs d'exemple à renseigner, dossier de
  l'application, génération). Audité dans les deux thèmes et à 200 %.
- Guide : page « Pipelines types par fournisseur cloud ». Douze projets de référence ajoutés aux tests, et le
  corpus de compatibilité des fichiers projet de la 0.20.

- **Vue Réseau** (Vues › Réseau, Ctrl+Maj+R) : le schéma d'un environnement en plan 2D ou en isométrique 3D, avec
  les flux et leurs ports, et les erreurs posées sur les composants (pastille de forme distincte par gravité, texte
  dans la liste « Composants et constats », correction applicable, accès à la brique) ; constats propres au réseau :
  service publié sans passer par l'entrée, application en HTTP simple, cluster sans point d'entrée ; export PNG.

### Corrigé
- L'anneau de focus suit le contrôle quand le pipeline (ou tout parent) défile, et est rogné par la zone visible, au lieu de rester en l'air.

### Modifié
- Barre d'outils réduite à Nouveau, Ouvrir, Enregistrer, Annuler, Rétablir et Valider (Paramètres et Générer sont
  dans l'en-tête du projet, le thème dans Affichage) ; les filtres du catalogue sont repliés sous « Filtres ».

## 0.20.0 — 2026-10-16 — Qualité produit

Accessibilité de l'application vérifiée et corrigée, messages d'erreur en français, deux à trois fois plus
rapide sur un gros projet, et un guide de l'utilisateur avec quatre tutoriels. Les fichiers générés changent
pour l'hôte Docker avec Traefik (adresse publique de l'application par environnement).

### Ajouté
- **Audit d'accessibilité automatisé** (`devops_builder/ui/audit.py`, `tools/audit_accessibilite.py`) sur la
  fenêtre principale, les onze dialogues et l'assistant, dans les deux thèmes : nom accessible, clavier, focus
  mesuré à l'écran, contrastes, titres, langue, raccourcis, texte coupé à 200 % ; critères de l'EN 301 549
  (WCAG 2.1 AA) et du RGAA en regard. Deux jobs de CI lisent l'arbre de l'application comme Orca (AT-SPI) et
  comme NVDA (UI Automation, Windows). État et limites : `docs/accessibilite.md`.
- **Taille du texte** réglable de 100 à 200 % (Affichage, Ctrl++ et Ctrl+-), retenue d'une session à l'autre ;
  à 150 % et plus, le nom du projet passe sur sa propre ligne, les messages des diagnostics se replient.
- **Anneau de focus** de deux pixels, au contraste vérifié, autour du contrôle actif.
- **Annonces aux lecteurs d'écran** : chaque message de la barre d'état ; l'ajout et le déplacement d'une
  brique disent l'étape et la position.
- **Alt+↑ et Alt+↓** déplacent une brique dans son étape (le glisser avait seul cette possibilité).
- **Guide de l'utilisateur** (`docs/guide/`, site publié par GitHub Pages) : prise en main, clavier, et quatre
  tutoriels de bout en bout — hôte Docker, k3s en GitOps, Amazon EKS, souverain SecNumCloud sur Outscale. Un test
  vérifie que chaque fichier cité par un tutoriel est généré et que chaque paramètre à renseigner y est nommé.
- **Adresse publique de l'application** (brique Traefik, hôte Docker et machines virtuelles) : la production
  prend le nom saisi, les autres environnements un préfixe (staging.boutique.fr) sauf surcharge ; R34 tant
  qu'il garde sa valeur d'exemple, et le mode d'emploi liste les noms à faire pointer vers chaque hôte.
- **R53** : cible d'hébergement inconnue (fichier modifié à la main), bloquante, avec les corrections.
- `devops-builder projet.devops.yaml` ouvre le projet dans l'interface.

### Corrigé
- Accessibilité : textes de Qt en anglais (« Close », « Cancel », boutons des boîtes de message, menus
  contextuels) ; focus presque invisible sur la plupart des contrôles ; avertissements en orange à 3,5:1,
  boutons d'action à 2,8:1 et boutons principaux à 4:1 (4,5:1 et plus désormais) ; icônes d'étape exposées
  comme images sans nom ; zones de défilement et onglets sans nom.
- Hôte Docker avec Traefik : la règle visait `<app>.example.com`, identique dans chaque environnement ; la
  préproduction réclamait le certificat de la production.
- Messages d'erreur : un fichier projet qui n'est pas en UTF-8 arrêtait la ligne de commande sur une trace
  Python ; les erreurs du système (« [Errno 21] Is a directory »), de YAML (« mapping values are not allowed
  here ») et des commandes sont traduites, avec la cause et la piste ; une fiche personnelle illisible est
  signalée au lieu d'interrompre le chargement du catalogue.
- Validation : quand les playbooks échouent faute de collection Ansible, elle donne la commande
  `ansible-galaxy collection install -r ansible/requirements.yml`.

### Performances
- libyaml pour écrire les fichiers générés et lire ou écrire le projet (texte identique sur les 183 projets de
  référence et 301 fichiers projet) : sur 167 briques et cinq environnements, évaluation des règles en 0,07 s
  au lieu de 0,23 s, génération en 0,17 s au lieu de 0,45 s, ajout d'une brique dans l'interface en 0,2 s au
  lieu de 0,3 s ; la suite de tests passe de 5 à 3,5 minutes. Un test garde ces temps.

## 0.19.0 — 2026-10-15 — Distribution

S'installe sans cloner le dépôt : paquet PyPI ou exécutable autonome, chacun avec sa preuve de provenance.
Les fichiers générés ne changent pas.

### Ajouté
- **Paquet PyPI `izinum-devops-builder`** (« devops-builder » y était déjà pris ; la commande reste
  `devops-builder`) : `pipx install izinum-devops-builder`. Sous pipx, les conseils d'installation des linters
  deviennent `pipx inject izinum-devops-builder …`.
- **Exécutables sans Python** pour Linux x86-64, Windows x86-64 et macOS Apple Silicon (`DevOps Builder.app`),
  construits par PyInstaller et éprouvés sur chaque système avant publication (version, `check`, `generate`,
  démarrage de l'interface). Non signés pour l'instant : le README dit comment passer SmartScreen et Gatekeeper.
  Leur dossier `LICENCES` joint la LGPL de Qt et PySide6 (bibliothèques remplaçables, adresses des sources), la
  licence de Python et celles des polices d'icônes (`docs/licences-tierces.md`).
- **Attestations de provenance** (SLSA, `gh attestation verify`) pour chaque exécutable et le paquet, et
  `SHA256SUMS` dans chaque publication ; le paquet PyPI porte aussi les attestations PEP 740.
- **Workflow « Publication »** : une version se publie depuis Actions, sans étiquette créée à la main ; il vérifie
  version, journal et étiquette libre, relance les tests, publie sur PyPI par publication de confiance (aucun
  secret stocké), puis crée l'étiquette et la publication GitHub avec les notes tirées du journal. Sur une branche,
  il construit et éprouve sans publier.
- **CI complète** : un job installe OpenTofu et un miroir des providers (`tools/miroir_tofu.py`), kubeconform,
  sops, age et Ansible ; chaque pile Terraform des projets de référence passe `tofu validate`, et un test sauté y
  fait échouer la CI. La CI tourne aussi sur les branches `lot-*`.

### Corrigé
- Ligne de commande : une sortie redirigée sous Windows (page de code cp1252) ne s'arrête plus sur un caractère
  qu'elle ne sait pas écrire.
- Validation : quand les playbooks échouent faute de collection Ansible sur le poste, elle donne la commande
  `ansible-galaxy collection install -r ansible/requirements.yml`.

## 0.18.0 — 2026-10-15 — Fermer les limites qui piègent

Droits de la CI séparés, verrou d'état sur les clouds européens, connexion unique de Harbor et SonarQube,
Renovate hors GitHub ; trois charts qui ne s'installaient pas (SonarQube, Loki) ou dépréciés (Grafana, Tempo),
trouvés par le nouveau scénario `kind-plateforme`.

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
- Mode d'emploi Argo CD : attente de la première synchronisation portée à dix minutes (un passage de bout en bout a
  dépassé cinq minutes).

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

### Corrigé
- L'anneau de focus suit le contrôle quand le pipeline (ou tout parent) défile, et est rogné par la zone visible, au lieu de rester en l'air.

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
