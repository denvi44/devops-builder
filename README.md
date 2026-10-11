# DevOps Builder

Application de bureau Python, en Material Design, pour composer un pipeline DevOps en posant des briques issues du [CNCF Landscape](https://landscape.cncf.io/). Un moteur de règles bloque les combinaisons incohérentes avant de générer les fichiers à committer.

![Pipeline de référence](docs/captures/01-pipeline.png)

![Analyse de l'application](docs/captures/14-application.png)

![Étape Données](docs/captures/15-donnees.png)

## Ce que fait l'application

- **L'application d'abord** : on désigne le dossier de l'application (carte de l'application dans la barre du projet, première page de l'assistant, ou `devops-builder init`). L'analyse lit, sans rien exécuter, le langage et son cadre (FastAPI, Django, Flask, Express, Next.js, Spring Boot, Gin, ASP.NET…), le port (EXPOSE du Dockerfile, sinon le port usuel du cadre), le Dockerfile, la CI et la forge déjà en place (fichiers de CI, dépôt distant), un chart Helm, Kustomize, Compose, Terraform ou OpenTofu, les tests, Renovate ou Dependabot, les bases de données (pilotes PostgreSQL, MySQL, MariaDB, MongoDB et Redis dans les dépendances, schéma Prisma, services Compose) et les migrations (Alembic, Django, Prisma, Knex, Sequelize, goose, golang-migrate). Chaque détection donne sa preuve, et les briques qui en découlent sont proposées : sans Dockerfile, l'image est construite par Buildpacks.
- **Choix restreints par défaut** : la palette ne montre que les briques adaptées au projet. Elle écarte ce que la cible, la forge, la politique de licence, SecNumCloud ou le fournisseur cloud refuseraient, ainsi que les rôles déjà tenus (une forge, une CI, un GitOps, un CNI…). Une recherche montre tout, en grisant ce qui ne convient pas avec la raison ; « Adapté au projet » se décoche pour tout voir.
- **Données** : une étape « Données » entre Infrastructure et Déploiement. PostgreSQL, MariaDB, MySQL, MongoDB, Valkey et Redis tournent à côté de l'application : service Compose non publié sur l'hôte, avec volume, contrôle de santé et sauvegarde (`scripts/db-backup.sh`, planifiée par Ansible), ou StatefulSet sur Kubernetes. CloudNativePG gère PostgreSQL dans le cluster (une instance hors production, trois en production) ; Amazon RDS, Cloud SQL, Azure Database, Scaleway et OVHcloud sont décrits en Terraform, une instance par environnement, protégée et répliquée en production. L'application lit toujours l'URL complète dans `DATABASE_URL`, `MONGODB_URI` ou `REDIS_URL` ; le mot de passe est une variable CI secrète que `deploy/secrets.sh` ou un Secret Kubernetes lui transmet, jamais un fichier du dépôt. La brique « Migrations de schéma » lance la commande de l'application avec son image avant chaque démarrage (service Compose `migrate` ou initContainer). L'assistant demande la base et le cache, et choisit la brique selon l'hébergement : service managé du cloud, opérateur sur Kubernetes, conteneur sur un hôte Docker.
- **Terraform / OpenTofu** : l'état vit dans le stockage objet du fournisseur, chiffré et verrouillé sur S3 (`use_lockfile`), et dans les stockages compatibles S3 de Scaleway, OVHcloud et Outscale, avec les clés posées par la CI. Sans état distant, R44 prévient que chaque pipeline recréerait les ressources. Les variables sans valeur deviennent des variables CI `TF_VAR_<nom>` et un `terraform.tfvars.example` ; `outputs.tf` donne les points d'accès des clusters, des registres et des bases ; `.gitignore` écarte état et plans. Le plan vérifie le format (`fmt -check`), l'apply manuel est sérialisé (`resource_group` GitLab, `concurrency` GitHub). Providers aws 6, google 7, azurerm 4, ovh 2, module EKS 21 ; OpenTofu 1.13 est installé dans le job, l'image officielle ne servant plus depuis la 1.10 qu'à copier le binaire ; Terraform 1.16. TFLint et Infracost s'ajoutent comme briques.
- **Floci**, l'émulateur AWS local et libre : `dev/floci/compose.yaml` et `dev/floci/aws.env` pour le poste, Floci à côté des tests unitaires dans la CI (GitLab, GitHub, Gitea, Woodpecker), et `scripts/tf-floci.sh` qui joue la pile AWS sur l'émulateur, sans compte ni identifiants : `plan` dans la CI (non bloquant), `apply` puis `destroy` en local. L'analyse de l'application le propose quand elle trouve un SDK AWS ou LocalStack.
- **Ansible** : les hôtes de chaque environnement se règlent dans la brique (paramètre « Hôtes de l'application », surchargé par environnement) au lieu d'un exemple figé dans l'inventaire. `ansible/ansible.cfg` (lu via `ANSIBLE_CONFIG`), `ansible/requirements.yml` (community.docker épinglée) et ansible-core 2.21 installé dans le job. Les hôtes se connectent au registre privé avant de tirer l'image (GitLab, GHCR, Harbor, Scaleway… ; pour ECR, Artifact Registry et ACR, l'identité de la machine), le déploiement passe un hôte après l'autre et attend que les services soient prêts. `site.yml` installe Docker depuis son dépôt officiel (Debian, Ubuntu, RHEL et dérivées). Sans brique Docker Compose, l'application est lancée seule. `SSH_KNOWN_HOSTS` (facultatif) fixe les clés d'hôte, pour Ansible comme pour le déploiement SSH. La brique ansible-lint contrôle les playbooks.
- **Catalogue** : 150 fiches vérifiées (outils, services managés, fournisseurs cloud) et l'ensemble du Landscape consultable, soit 1 202 entrées. Les entrées sans fiche sont marquées « non vérifiées ».
- **Canevas** : dix étapes en colonnes (source → observabilité). On y glisse des briques depuis la palette, ou on les ajoute par double-clic. Chaque outil n'accepte que ses étapes : pendant un glisser, les colonnes compatibles sont mises en évidence, les autres grisées, et un dépôt hors étape est refusé avec un message.
- **Assistant de démarrage** : **Nouveau** pose cinq pages de questions (langage, forge, hébergement, cloud, environnements, sécurité, qualité, dépendances, observabilité, IaC) et construit un pipeline complet sans erreur bloquante. Les clouds proposés suivent l'hébergement choisi et l'exigence SecNumCloud. Ctrl+Maj+N ouvre un projet vide.
- **Environnements et promotion** : une chaîne ordonnée de bac à sable, développement, recette, préproduction et production, par exemple développement → recette → production. La même image est promue d'un environnement au suivant, avec approbation avant la production. Chaque environnement peut viser son propre cluster et surcharger les paramètres d'une brique (nom du cluster, service Cloud Run…). Les variables CI, les namespaces, les values Helm et les overlays Kustomize sont déclinés par environnement.
- **Ports** : la vue « Ports » (Ctrl+Maj+P) liste, pour chaque environnement, le port de l'application et ceux des briques (Grafana, Prometheus, Traefik, MinIO…), avec leur usage et leur exposition ; le rapport `PIPELINE.md` reprend le tableau et la fiche d'une brique ses ports. La règle R39 bloque deux services publiés sur le même port d'un hôte Docker et propose la correction. Des environnements qui partagent un hôte Docker (champ « Hôte Docker partagé ») voient leurs ports décalés de 10 000, production d'abord : les ports deviennent des variables du fichier Compose, et `deploy/env/<environnement>.env` est copié en `.env` lors du déploiement (SSH ou Ansible).
- **Suggestions** : la fiche d'une brique propose les briques souvent associées (Trivy, Syft et Cosign après un build d'image, External Secrets avec un cluster managé…). Seules celles qui sont absentes et posables sur la cible apparaissent.
- **Contrôle continu** : 45 règles (R00 à R44) couvrant le placement dans les étapes, la complétude du pipeline, la cible d'hébergement, l'exclusivité de rôle, les dépendances, les contrats entre étapes, la forge, le cycle de vie, les paramètres, la licence, la conformité (SecNumCloud, clés statiques) et les environnements (approbation de la production, cluster de chaque environnement, identifiants, collisions de namespaces, conflits de ports) les données (base sans sauvegarde ou à instance unique en production sur Kubernetes, deux bases du même type) et l'état Terraform (local dans la CI). Chaque diagnostic propose des corrections en un clic, annulables.
- **Complétude** : un pipeline incomplet n'est plus déclaré prêt. C'est le cas d'une image construite sans registre, d'étapes sans orchestrateur CI, d'un outil privé d'une capacité requise (forge, CNI, coffre de secrets…) ou d'une cible Kubernetes sans cluster. Une brique pour laquelle aucun fichier n'est produit est signalée (R31), selon la même logique que le rapport.
- **Paramètres typés** : les briques qui ont des réglages (clusters, registres, buckets, fournisseurs) affichent un formulaire avec listes de régions et contrôle des formats de nommage de chaque cloud. Une clé mal orthographiée est détectée avec la correction proposée, et une valeur d'exemple restée en place est signalée. Les valeurs saisies, comme le rôle IAM ou le projet GCP, sont écrites dans la CI au lieu d'être laissées à déclarer.
- **Génération** : définitions CI, déploiement, IaC et plateforme, avec un rapport `PIPELINE.md` qui liste les briques, les licences, les variables CI à déclarer et les avertissements restants.
- **Validation locale** : le bouton **Valider** passe les fichiers générés aux outils installés sur le poste (schémas officiels, actionlint, ShellCheck, kubeconform, Kustomize, Helm, OpenTofu ou Terraform, Docker Compose, Ansible). Un outil absent est signalé avec sa commande d'installation sans bloquer les autres contrôles. Un registre injoignable fait sauter le contrôle au lieu de l'afficher en échec.
- **Test dans kind** : `scripts/test-kind.sh` déploie le chart Helm ou l'overlay Kustomize d'un environnement dans un cluster kind jetable, puis le supprime. Avec le dossier du code, l'image est construite et chargée, et l'application doit répondre en HTTP sans redémarrer. Sans le code, les manifestes sont soumis à l'API en dry-run serveur. Le test se lance depuis **Valider** (journal en direct) ou en ligne de commande.
- **Écriture prudente** : un manifeste `.devops-builder/manifest.json` garde l'empreinte de chaque fichier écrit. À l'export suivant, les différences sont affichées fichier par fichier. Un fichier retouché à la main, ou présent sans venir de DevOps Builder, n'est remplacé que si on le coche.
- **Export Git** : les fichiers sont committés sur une nouvelle branche, poussés, puis la demande de fusion est ouverte. GitLab la crée à la réception (options de push), GitHub via `gh` s'il est connecté. Pour Gitea, Bitbucket et Azure DevOps, ou à défaut, un lien de création pré-rempli est proposé. La copie de travail revient sur la branche de départ, et l'export est refusé si elle a des modifications non commitées.
- **Entretien du catalogue** (menu Catalogue) : chaque fiche est comparée au Landscape et, en ligne, à son dépôt GitHub ou GitLab.com. Le contrôle signale les dépôts archivés, les licences changées (une licence devenue non libre est « à corriger »), les dépôts renommés ou introuvables, l'absence d'activité depuis 18 mois, les fiches vérifiées il y a plus de 6 mois, les références vers des fiches inexistantes et les capacités que personne ne fournit. Les corrections proposées s'appliquent en un clic et restent réversibles ; les réponses des forges sont gardées 24 h, et un jeton GitHub (`GITHUB_TOKEN` ou `gh auth login`) lève la limite de 60 requêtes par heure.
- **Catalogue personnel** : une entrée du Landscape sans fiche devient une fiche vérifiée (clic droit dans la palette, ou bouton dans Propriétés). Le formulaire est pré-rempli, la licence peut être lue sur le dépôt, et la fiche passe les mêmes contrôles que les fiches livrées. Les briques déjà posées avec l'entrée brute suivent la nouvelle fiche. Les fiches personnelles (`fiches/*.yaml`) et les corrections des fiches livrées (`corrections.yaml`) vivent dans `~/.devops-builder/catalog/` ; `DEVOPS_BUILDER_HOME` désigne un autre dossier, par exemple un dépôt Git partagé par l'équipe. Les fichiers de l'application ne sont jamais modifiés.
- **Landscape à jour** : le bouton « Rafraîchir le Landscape » télécharge le `landscape.yml` du CNCF, reconstruit l'index dans le dossier personnel et liste les ajouts, retraits et projets nouvellement archivés ; « Index livré » revient à celui de la version.
- **Variables CI** : `scripts/ci-variables.sh` déclare les variables « à déclarer » de `PIPELINE.md` avec l'outil de la forge : `glab` pour GitLab (masquage quand le format le permet), `gh` pour GitHub (secrets et variables), l'API Gitea, `az` pour Azure Pipelines. Les valeurs viennent de l'environnement, d'un fichier (`NOM_FILE`) ou d'une saisie masquée ; elles ne sont jamais écrites dans le dépôt. `--dry-run` montre ce qui serait déclaré.

![Diagnostics et corrections](docs/captures/02-diagnostics.png)

![Paramètres typés](docs/captures/04-parametres.png)

![Assistant de démarrage](docs/captures/05-assistant.png)

![Environnements](docs/captures/06-environnements.png)

![Surcharges par environnement](docs/captures/07-surcharges.png)

![Validation locale](docs/captures/08-validation.png)

![Différences avant écriture](docs/captures/09-differences.png)

![Export Git](docs/captures/10-export-git.png)

![Entretien du catalogue](docs/captures/11-entretien.png)

![Fiche créée depuis le Landscape](docs/captures/12-fiche.png)

![Ports par environnement](docs/captures/13-ports.png)

## Installation

Il faut Python 3.11 ou plus récent.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows : .venv\Scripts\activate
pip install -e .                   # ou pip install -e ".[validate]" pour les linters Python
devops-builder                     # ou : python -m devops_builder
```

Sous Linux, Qt a besoin des bibliothèques système habituelles (`libxkbcommon`, `libEGL`, `fontconfig`).

## Utilisation

| Action | Comment |
| --- | --- |
| Ajouter une brique | Glisser depuis le catalogue, ou double-clic / Entrée |
| Déplacer une brique | Glisser vers une colonne compatible, ou Alt+← / Alt+→ (saute à l'étape autorisée suivante) |
| Retirer une brique | Suppr, ou bouton dans Propriétés |
| Corriger un diagnostic | Sélectionner le diagnostic puis cliquer une correction (Entrée applique la première) |
| Nouveau projet | Ctrl+N : assistant, qui commence par le dossier de l'application ; Ctrl+Maj+N : projet vide |
| Application | Ctrl+Maj+A, ou la carte de l'application dans la barre du projet : dossier, analyse, langage, port |
| Paramètres du projet | F2 : cible, langage, SecNumCloud, OIDC, politique de licence ; onglet Environnements (type, cluster, hôte Docker partagé, décalage des ports) |
| Ports | Ctrl+Maj+P, ou le bouton « Ports » de la barre du projet |
| Surcharger un paramètre | Sélectionner la brique, choisir l'environnement au-dessus du formulaire ; un champ vide hérite de la valeur commune |
| Générer | Ctrl+G : aperçu des fichiers, puis export vers Git, dans un dossier (avec différences) ou en .zip |
| Valider | Ctrl+Maj+V : contrôles locaux, puis test dans kind |
| Annuler / rétablir | Ctrl+Z / Ctrl+Y |
| Rechercher | Ctrl+F ; Ctrl+2 pour le pipeline, Ctrl+3 pour les diagnostics |
| Thème sombre | Ctrl+T |

Quatre projets d'exemple sont fournis dans **Fichier › Ouvrir un exemple** : un site web sur hôte Docker, une API sur k3s en GitOps, une plateforme AWS EKS en OpenTofu et une boutique avec PostgreSQL, Valkey et migrations sur un hôte partagé.

### En ligne de commande

```bash
devops-builder check projet.devops.yaml                 # code retour 1 si erreur bloquante
devops-builder generate projet.devops.yaml -o sortie/   # --dry-run, --overwrite, --force
devops-builder validate projet.devops.yaml              # --offline, -v ; code retour 1 si un contrôle échoue
devops-builder test-kind projet.devops.yaml --env dev --app-dir ../code
devops-builder export-git projet.devops.yaml --repo ../depot   # --branch, --no-push, --no-request
devops-builder catalog-check                            # --offline, --refresh, --apply, --report rapport.md
devops-builder catalog-import "Keptn"                   # --id, --stage, --license, --offline
devops-builder landscape-refresh                        # --source landscape.yml, --reset
devops-builder scan ../mon-app                          # --json : ce que l'analyse trouve
devops-builder init ../mon-app -o mon-app.devops.yaml   # --hosting, --cloud, --envs, --database
```

`generate` n'écrase plus les fichiers retouchés à la main : il les liste, et `--overwrite` les remplace.

## Ce qui est généré

| Domaine | Formats |
| --- | --- |
| CI | GitLab CI, GitHub Actions, Gitea Actions, Jenkinsfile, Woodpecker, Tekton, Azure Pipelines, AWS CodeBuild, Google Cloud Build |
| Déploiement | Docker Compose, chart Helm, Kustomize, Application Argo CD, Flux (GitRepository + Kustomization ou HelmRelease), playbooks Ansible |
| Données | Services Compose (volume, santé, `deploy/secrets.sh`, `scripts/db-backup.sh`), StatefulSet et Secret dans le chart ou la base Kustomize, Cluster CloudNativePG, Terraform des bases managées (`outputs.tf`), service `migrate` ou initContainer de migrations |
| Infrastructure | Terraform / OpenTofu : providers épinglés, backend d'état chiffré et verrouillé (S3, GCS, Blob, Scaleway, OVHcloud, Outscale), ressources AWS, Google Cloud, Azure, OVHcloud, Scaleway, `outputs.tf`, `terraform.tfvars.example`, `.gitignore`, `.tflint.hcl` |
| Clusters autogérés | Scripts d'installation k3s, RKE2, kubeadm, MicroK8s, kind, minikube, réglés selon le CNI et l'entrée choisis (par exemple, k3s sans Flannel ni Traefik intégrés quand Cilium et Traefik sont dans le pipeline) |
| Plateforme | `platform/install.sh` (charts Helm officiels, sans réinstaller ce que le cluster fournit déjà) ou services Compose sur hôte Docker |
| Dépendances | `renovate.json`, `.github/dependabot.yml` (écosystèmes déduits du langage, du build, de la CI et de l'IaC) |
| Observabilité managée | Module CloudWatch sur EKS, Azure Monitor (Log Analytics) sur AKS ; Cloud Monitoring, intégré à GKE, est noté dans le rapport |
| Authentification cloud | OIDC par défaut : rôle IAM, Workload Identity Federation, fédération Entra ID |
| Outillage local | `scripts/test-kind.sh` (Helm ou Kustomize), `scripts/ci-variables.sh` (GitLab, GitHub, Gitea, Azure Pipelines), `scripts/tf-floci.sh` et `dev/floci/` (émulateur AWS) |
| Promotion | Un job de déploiement par environnement, enchaînés dans l'ordre. Approbation : job manuel (GitLab), environnement avec relecteurs (GitHub, Gitea, Azure Pipelines), `input` (Jenkins), événement manuel (Woodpecker), fichiers séparés à déclencher après validation (Tekton, CodeBuild, Cloud Build) |

Les fichiers générés sont un point de départ à relire. Les tests valident chaque sortie YAML contre les schémas officiels (GitLab CI, GitHub Workflows, Azure Pipelines, Cloud Build, Woodpecker, Compose, Renovate, Dependabot) et passent les workflows GitHub dans actionlint. `helm lint` n'est pas lancé par les tests ; `tofu validate` l'est sur toutes les piles de l'instantané quand `DEVOPS_BUILDER_TOFU_MIRROR` désigne un miroir local de providers (le module EKS, servi par le registre, y est remplacé par un module factice). Le bouton **Valider** lance les deux sur le poste quand les outils et le réseau sont disponibles.

## Organisation du code

```
devops_builder/
  model.py          fiches, projet, format .devops.yaml
  catalog.py        chargement des fiches + index du Landscape
  rules.py          moteur de règles, handlers génériques, corrections
  ir.py             représentation intermédiaire neutre du pipeline
  generators/       ci, deploy, data (bases), iac, platform, extras (dépendances, clusters), report
  ui/               interface PySide6 + qt-material
  params.py         validation et valeurs effectives des paramètres (surcharges par environnement)
  starter.py        assistant de démarrage : réponses → projet
  validate.py       contrôles locaux des fichiers générés
  sync.py           différences et écriture prudente (manifeste d'empreintes)
  gitexport.py      branche, commit, push, demande de fusion
  health.py         entretien du catalogue (Landscape, GitHub, GitLab.com)
  catalog_edit.py   fiches personnelles et corrections
  landscape.py      index du Landscape : construction, rafraîchissement, écarts
  userdata.py       dossier personnel (DEVOPS_BUILDER_HOME)
  ports.py          ports par environnement, hôtes partagés, conflits
  databases.py      bases du pipeline : moteurs, modes (autogérée, opérateur, managée), connexion
  appscan.py        analyse du dossier de l'application
  compat.py         briques adaptées au projet (filtre de la palette)
  data/ports.yaml   ports par défaut des briques et leur usage
  suggest.py        briques souvent associées
  data/catalog/     fiches YAML (une par outil)
  data/params.yaml  schémas des paramètres de briques
  data/suggestions.yaml  briques souvent associées
  data/rules/       une règle YAML par fichier
  data/examples/    projets de référence
tools/
  build_landscape_index.py   rafraîchit l'index depuis landscape.yml
  screenshot.py              captures hors écran de l'interface
tests/              règles, générateurs, interface (hors écran), non-régression
  golden/           sorties figées de 149 projets (exemples, matrice, échantillon de l'assistant, environnements, ports, données, IaC, Floci et Ansible)
  data/legacy/      projets enregistrés par les versions 0.1, 0.3, 0.7 et 0.8
  minihelm.py       rendu des gabarits Helm générés, sans le binaire helm
tools/compare_captures.py  écart visuel entre deux séries de captures
```

### Ajouter un outil

Pour un usage personnel ou d'équipe, passer par le catalogue personnel (palette › clic droit › Créer une fiche, ou `devops-builder catalog-import`). Pour l'ajouter à l'application, ajouter une entrée dans un fichier de `data/catalog/` : étape principale (`stage`) et, s'il le faut, étapes secondaires (`extra_stages`), rôles, cibles (`hosting`), capacités fournies et requises, forge, fournisseur, cycle de vie, date de vérification. Le schéma est validé au chargement.

Si l'outil a des réglages, décrire ses paramètres dans `data/params.yaml` : libellé, type, valeur par défaut (`{app}` = nom de l'image du projet), valeur d'exemple, liste de choix ou de suggestions, motif et explication du format. Le formulaire et les règles R32 à R34 s'en déduisent. Une valeur par défaut qui ne respecte pas son propre motif est refusée au chargement.

Un outil ne peut être posé que dans `stage` ou `extra_stages`. Par exemple, Ansible va en Infrastructure ou Déploiement, et Trivy en Sécurité ou Tests & qualité. Les entrées non vérifiées du Landscape reçoivent des étapes déduites de leur sous-catégorie. La règle R25 bloque la génération si un fichier `.devops.yaml` édité à la main place une brique ailleurs, et propose de la déplacer.

### Ajouter une règle

Créer `data/rules/R45_....yaml` avec un `type` existant (`exclusive_role`, `conflict_pair`, `requires`, `requires_generic`, `lifecycle`, `target_mismatch`, `params`…), puis ajouter son cas dans `tests/test_rules.py`. Un nouveau type de règle s'écrit comme un handler dans `rules.py`.

### Rafraîchir le Landscape

Depuis l'application ou avec `devops-builder landscape-refresh`, pour son propre index. Pour l'index livré avec l'application :

```bash
curl -LO https://raw.githubusercontent.com/cncf/landscape/master/landscape.yml
python tools/build_landscape_index.py landscape.yml
```

Les deux signalent les entrées ajoutées, retirées et nouvellement archivées, pour savoir quelles fiches revoir.

## Tests

```bash
pip install -e ".[dev]"
QT_QPA_PLATFORM=offscreen pytest
```

586 tests : un par règle, l'application de chaque correction proposée, une matrice de combinaisons CI × déploiement × cloud × environnements validées contre les schémas, avec contrôle qu'aucune brique n'y reste sans fichier, les 15 300 combinaisons de l'assistant (aucune ne doit produire d'erreur bloquante), la validation, l'écriture prudente, l'export Git vers des dépôts locaux (dont les options de push GitLab), les scripts kind et variables CI contre des outils factices et une fausse API Gitea, l'entretien du catalogue contre une fausse API GitHub et GitLab, l'analyse d'applications Python, Node.js, Java, Go et .NET (dont leurs bases et migrations), les bases de données sur chaque cible (rendu du chart, Kustomize, script de secrets exécuté, format Terraform), l'état et les variables Terraform de chaque cloud, Floci dans chaque CI, les playbooks Ansible passés à `--syntax-check` et ansible-lint, la cohérence entre l'assistant et le filtre de la palette, le catalogue personnel et le rafraîchissement du Landscape, et l'interface pilotée hors écran : glisser-déposer, formulaire de paramètres, surcharges, éditeur d'environnements, assistant, dialogues de validation, de différences, d'export, d'entretien, de fiche, de ports et d'application, et la largeur minimale de la fenêtre (1 280 px au plus). Toute exception levée dans un slot Qt fait échouer le test en cours. Les tests utilisent un dossier personnel jetable : un catalogue personnel présent sur le poste ne les influence pas.

### Non-régression

`tests/test_regression.py` compare tout ce que génèrent 149 projets (fichiers et diagnostics) à l'instantané de `tests/golden/`, et recharge les projets enregistrés par les versions précédentes. Après un changement voulu :

```bash
UPDATE_GOLDEN=1 pytest tests/test_regression.py
git diff tests/golden          # chaque ligne changée doit s'expliquer
```

Pour l'interface, `tools/screenshot.py` refait les captures et `tools/compare_captures.py docs/captures nouvelles/` mesure l'écart avec celles de la version précédente.

## Limites connues

- Les fiches sont datées du 8 octobre 2026 ; le cycle de vie des outils évolue vite (ingress-nginx, Kaniko, AWS App Mesh, Google Container Registry y sont déjà signalés).
- Bases de données : les gabarits Helm sont vérifiés par un rendu interne (`tests/minihelm.py`) puis kubeconform, pas par `helm template` ; les ressources Terraform des bases managées par `tofu fmt`, pas par `tofu validate` (registres de providers injoignables pendant les tests). Sur un service serverless (Cloud Run, ECS, Azure Container Apps), l'URL de connexion se branche à la main ; `PIPELINE.md` donne la commande. Le mot de passe d'une base autogérée se limite aux caractères sûrs dans une URL (lettres, chiffres, `. _ ~ -`).
- Terraform : azurerm reste en 4.x (la 5.0 de juillet 2026 change des schémas, migration à valider). Les backends Scaleway, OVHcloud et Outscale n'ont pas de verrou d'état : la CI sérialise les apply, mais deux apply lancés à la main en même temps restent possibles. Un seul état porte tous les environnements.
- Floci : dans la CI, l'émulateur tourne sans socket Docker ; le plan passe, mais EKS, RDS ou Lambda ne peuvent être créés qu'en local, et un `apply` sur Floci échoue sur les ressources qui référencent un réseau existant (VPC, groupe de sous-réseaux) donné par une valeur factice. Jenkins, Tekton, Azure Pipelines, CodeBuild et Cloud Build ne démarrent pas Floci (`PIPELINE.md` le signale).
- OKS (Outscale) et Azure Container Apps n'ont pas de ressource Terraform générée : seul un commentaire est écrit, et R31 les signale. La prise en charge d'OKS par le provider `outscale/outscale` reste à vérifier.
- RKE2 : le contrôleur d'entrée embarqué dépend de la version ; le script indique comment le désactiver mais ne le fait pas.
- Renovate hors GitHub : `renovate.json` est généré, mais le job planifié qui lance Renovate reste à créer (expliqué dans `PIPELINE.md`).
- Argo CD et Flux : avec un cluster par environnement, les clusters distants doivent être enregistrés auprès de l'instance GitOps (`argocd cluster add`, ou un Flux par cluster) ; c'est indiqué dans `PIPELINE.md`.
- Woodpecker, Tekton, CodeBuild et Cloud Build n'ont pas de porte d'approbation native : la production part d'un déclenchement manuel ou d'un fichier séparé, et la restriction de qui peut le lancer se règle dans l'outil.
- Le contrôle Helm demande `helm` sur le poste, et le test kind demande Docker, kind et kubectl. Le script kind a été vérifié en dry-run contre un vrai serveur d'API Kubernetes, et son déploiement complet seulement avec des outils factices.
- `scripts/ci-variables.sh` ne couvre pas Jenkins, Woodpecker, Tekton, CodeBuild ni Cloud Build : leurs secrets restent à déclarer à la main (liste dans `PIPELINE.md`).
- Export Git : la pull request GitHub demande `gh auth login` ; sans cela, et pour Gitea, Bitbucket et Azure DevOps, il faut cliquer le lien de création proposé.
- Une brique issue du Landscape sans fiche n'est contrôlée par aucune règle et ne produit aucun fichier : en faire une fiche personnelle. Une fiche personnelle est contrôlée par les règles, mais aucun générateur ne la connaît : elle apparaît dans « À configurer à la main ».
- L'entretien n'interroge que GitHub et GitLab.com ; un dépôt hébergé ailleurs (Gitea, Codeberg, GitLab autohébergé) n'est suivi que par le Landscape et la date de vérification.
- L'authentification cloud par OIDC n'est générée que pour GitLab CI et GitHub Actions. Gitea Actions reprend les actions GitHub, mais l'émission du jeton dépend de l'instance. Jenkins, Woodpecker, Tekton, Azure Pipelines et Cloud Build reposent sur des secrets ou sur l'identité du service.
