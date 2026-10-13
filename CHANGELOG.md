# Journal des modifications

Format inspiré de [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/). Jusqu'à la 1.0, une version
mineure peut changer les fichiers générés ; chaque changement voulu est relu dans les projets de référence
(`tests/golden/`). Les fichiers projet de toutes les versions restent lisibles (voir `docs/format.md`).

## Non publié — lot 0.17 en cours

### Ajouté
- Tests de bout en bout (`tools/e2e/run.py`, workflow « Bout en bout ») : les fichiers générés exécutés pour
  de vrai sur les machines de GitHub Actions. Trois scénarios pour commencer : chart Helm avec CloudNativePG
  dans kind, overlays Kustomize avec PostgreSQL et Valkey dans kind, hôte Docker avec Compose, sauvegarde
  puis restauration. Une application de démonstration (`tools/e2e/app`) ne répond 200 sur `/db` que si
  chaque base accepte une connexion authentifiée avec les secrets transmis par le pipeline.

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
