# DevOps Builder

Application de bureau Python, en Material Design, pour composer un pipeline DevOps en posant des briques issues du [CNCF Landscape](https://landscape.cncf.io/). Un moteur de règles bloque les combinaisons incohérentes avant de générer les fichiers à committer.

![Pipeline de référence](docs/captures/01-pipeline.png)

## Ce que fait l'application

- **Catalogue** : 132 fiches vérifiées (outils, services managés, fournisseurs cloud) et l'ensemble du Landscape consultable, soit 1 192 entrées. Les entrées sans fiche sont marquées « non vérifiées ».
- **Canevas** : neuf étapes en colonnes (source → observabilité). On y glisse des briques depuis la palette, ou on les ajoute par double-clic. Chaque outil n'accepte que ses étapes : pendant un glisser, les colonnes compatibles sont mises en évidence, les autres grisées, et un dépôt hors étape est refusé avec un message.
- **Assistant de démarrage** : **Nouveau** pose cinq pages de questions (langage, forge, hébergement, cloud, environnements, sécurité, qualité, dépendances, observabilité, IaC) et construit un pipeline complet sans erreur bloquante. Les clouds proposés suivent l'hébergement choisi et l'exigence SecNumCloud. Ctrl+Maj+N ouvre un projet vide.
- **Environnements et promotion** : une chaîne ordonnée, par exemple développement → préproduction → production. La même image est promue d'un environnement au suivant, avec approbation avant la production. Chaque environnement peut viser son propre cluster et surcharger les paramètres d'une brique (nom du cluster, service Cloud Run…). Les variables CI, les namespaces, les values Helm et les overlays Kustomize sont déclinés par environnement.
- **Suggestions** : la fiche d'une brique propose les briques souvent associées (Trivy, Syft et Cosign après un build d'image, External Secrets avec un cluster managé…). Seules celles qui sont absentes et posables sur la cible apparaissent.
- **Contrôle continu** : 39 règles (R00 à R38) couvrant le placement dans les étapes, la complétude du pipeline, la cible d'hébergement, l'exclusivité de rôle, les dépendances, les contrats entre étapes, la forge, le cycle de vie, les paramètres, la licence, la conformité (SecNumCloud, clés statiques) et les environnements (approbation de la production, cluster de chaque environnement, identifiants, collisions de namespaces). Chaque diagnostic propose des corrections en un clic, annulables.
- **Complétude** : un pipeline incomplet n'est plus déclaré prêt. C'est le cas d'une image construite sans registre, d'étapes sans orchestrateur CI, d'un outil privé d'une capacité requise (forge, CNI, coffre de secrets…) ou d'une cible Kubernetes sans cluster. Une brique pour laquelle aucun fichier n'est produit est signalée (R31), selon la même logique que le rapport.
- **Paramètres typés** : les briques qui ont des réglages (clusters, registres, buckets, fournisseurs) affichent un formulaire avec listes de régions et contrôle des formats de nommage de chaque cloud. Une clé mal orthographiée est détectée avec la correction proposée, et une valeur d'exemple restée en place est signalée. Les valeurs saisies, comme le rôle IAM ou le projet GCP, sont écrites dans la CI au lieu d'être laissées à déclarer.
- **Génération** : définitions CI, déploiement, IaC et plateforme, avec un rapport `PIPELINE.md` qui liste les briques, les licences, les variables CI à déclarer et les avertissements restants.
- **Validation locale** : le bouton **Valider** passe les fichiers générés aux outils installés sur le poste (schémas officiels, actionlint, ShellCheck, kubeconform, Kustomize, Helm, OpenTofu ou Terraform, Docker Compose, Ansible). Un outil absent est signalé avec sa commande d'installation sans bloquer les autres contrôles. Un registre injoignable fait sauter le contrôle au lieu de l'afficher en échec.
- **Test dans kind** : `scripts/test-kind.sh` déploie le chart Helm ou l'overlay Kustomize d'un environnement dans un cluster kind jetable, puis le supprime. Avec le dossier du code, l'image est construite et chargée, et l'application doit répondre en HTTP sans redémarrer. Sans le code, les manifestes sont soumis à l'API en dry-run serveur. Le test se lance depuis **Valider** (journal en direct) ou en ligne de commande.
- **Écriture prudente** : un manifeste `.devops-builder/manifest.json` garde l'empreinte de chaque fichier écrit. À l'export suivant, les différences sont affichées fichier par fichier. Un fichier retouché à la main, ou présent sans venir de DevOps Builder, n'est remplacé que si on le coche.
- **Export Git** : les fichiers sont committés sur une nouvelle branche, poussés, puis la demande de fusion est ouverte. GitLab la crée à la réception (options de push), GitHub via `gh` s'il est connecté. Pour Gitea, Bitbucket et Azure DevOps, ou à défaut, un lien de création pré-rempli est proposé. La copie de travail revient sur la branche de départ, et l'export est refusé si elle a des modifications non commitées.
- **Variables CI** : `scripts/ci-variables.sh` déclare les variables « à déclarer » de `PIPELINE.md` avec l'outil de la forge : `glab` pour GitLab (masquage quand le format le permet), `gh` pour GitHub (secrets et variables), l'API Gitea, `az` pour Azure Pipelines. Les valeurs viennent de l'environnement, d'un fichier (`NOM_FILE`) ou d'une saisie masquée ; elles ne sont jamais écrites dans le dépôt. `--dry-run` montre ce qui serait déclaré.

![Diagnostics et corrections](docs/captures/02-diagnostics.png)

![Paramètres typés](docs/captures/04-parametres.png)

![Assistant de démarrage](docs/captures/05-assistant.png)

![Environnements](docs/captures/06-environnements.png)

![Surcharges par environnement](docs/captures/07-surcharges.png)

![Validation locale](docs/captures/08-validation.png)

![Différences avant écriture](docs/captures/09-differences.png)

![Export Git](docs/captures/10-export-git.png)

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
| Nouveau projet | Ctrl+N : assistant ; Ctrl+Maj+N : projet vide |
| Paramètres du projet | F2 : cible, langage, SecNumCloud, OIDC, politique de licence ; onglet Environnements |
| Surcharger un paramètre | Sélectionner la brique, choisir l'environnement au-dessus du formulaire ; un champ vide hérite de la valeur commune |
| Générer | Ctrl+G : aperçu des fichiers, puis export vers Git, dans un dossier (avec différences) ou en .zip |
| Valider | Ctrl+Maj+V : contrôles locaux, puis test dans kind |
| Annuler / rétablir | Ctrl+Z / Ctrl+Y |
| Rechercher | Ctrl+F ; Ctrl+2 pour le pipeline, Ctrl+3 pour les diagnostics |
| Thème sombre | Ctrl+T |

Trois projets d'exemple sont fournis dans **Fichier › Ouvrir un exemple** : un site web sur hôte Docker, une API sur k3s en GitOps et une plateforme AWS EKS en OpenTofu.

### En ligne de commande

```bash
devops-builder check projet.devops.yaml                 # code retour 1 si erreur bloquante
devops-builder generate projet.devops.yaml -o sortie/   # --dry-run, --overwrite, --force
devops-builder validate projet.devops.yaml              # --offline, -v ; code retour 1 si un contrôle échoue
devops-builder test-kind projet.devops.yaml --env dev --app-dir ../code
devops-builder export-git projet.devops.yaml --repo ../depot   # --branch, --no-push, --no-request
```

`generate` n'écrase plus les fichiers retouchés à la main : il les liste, et `--overwrite` les remplace.

## Ce qui est généré

| Domaine | Formats |
| --- | --- |
| CI | GitLab CI, GitHub Actions, Gitea Actions, Jenkinsfile, Woodpecker, Tekton, Azure Pipelines, AWS CodeBuild, Google Cloud Build |
| Déploiement | Docker Compose, chart Helm, Kustomize, Application Argo CD, Flux (GitRepository + Kustomization ou HelmRelease), playbooks Ansible |
| Infrastructure | Terraform / OpenTofu : providers, backend d'état, ressources AWS, Google Cloud, Azure, OVHcloud, Scaleway |
| Clusters autogérés | Scripts d'installation k3s, RKE2, kubeadm, MicroK8s, kind, minikube, réglés selon le CNI et l'entrée choisis (par exemple, k3s sans Flannel ni Traefik intégrés quand Cilium et Traefik sont dans le pipeline) |
| Plateforme | `platform/install.sh` (charts Helm officiels, sans réinstaller ce que le cluster fournit déjà) ou services Compose sur hôte Docker |
| Dépendances | `renovate.json`, `.github/dependabot.yml` (écosystèmes déduits du langage, du build, de la CI et de l'IaC) |
| Observabilité managée | Module CloudWatch sur EKS, Azure Monitor (Log Analytics) sur AKS ; Cloud Monitoring, intégré à GKE, est noté dans le rapport |
| Authentification cloud | OIDC par défaut : rôle IAM, Workload Identity Federation, fédération Entra ID |
| Outillage local | `scripts/test-kind.sh` (Helm ou Kustomize), `scripts/ci-variables.sh` (GitLab, GitHub, Gitea, Azure Pipelines) |
| Promotion | Un job de déploiement par environnement, enchaînés dans l'ordre. Approbation : job manuel (GitLab), environnement avec relecteurs (GitHub, Gitea, Azure Pipelines), `input` (Jenkins), événement manuel (Woodpecker), fichiers séparés à déclencher après validation (Tekton, CodeBuild, Cloud Build) |

Les fichiers générés sont un point de départ à relire. Les tests valident chaque sortie YAML contre les schémas officiels (GitLab CI, GitHub Workflows, Azure Pipelines, Cloud Build, Woodpecker, Compose, Renovate, Dependabot) et passent les workflows GitHub dans actionlint. Les tests n'exécutent pas `tofu validate` ni `helm lint`, qui demandent l'accès aux registres de providers et de charts ; le bouton **Valider** les lance sur le poste quand les outils et le réseau sont disponibles.

## Organisation du code

```
devops_builder/
  model.py          fiches, projet, format .devops.yaml
  catalog.py        chargement des fiches + index du Landscape
  rules.py          moteur de règles, handlers génériques, corrections
  ir.py             représentation intermédiaire neutre du pipeline
  generators/       ci, deploy, iac, platform, extras (dépendances, clusters), report
  ui/               interface PySide6 + qt-material
  params.py         validation et valeurs effectives des paramètres (surcharges par environnement)
  starter.py        assistant de démarrage : réponses → projet
  validate.py       contrôles locaux des fichiers générés
  sync.py           différences et écriture prudente (manifeste d'empreintes)
  gitexport.py      branche, commit, push, demande de fusion
  suggest.py        briques souvent associées
  data/catalog/     fiches YAML (une par outil)
  data/params.yaml  schémas des paramètres de briques
  data/suggestions.yaml  briques souvent associées
  data/rules/       une règle YAML par fichier
  data/examples/    projets de référence
tools/
  build_landscape_index.py   rafraîchit l'index depuis landscape.yml
  screenshot.py              captures hors écran de l'interface
tests/              règles, générateurs, interface (hors écran)
```

### Ajouter un outil

Ajouter une entrée dans un fichier de `data/catalog/` : étape principale (`stage`) et, s'il le faut, étapes secondaires (`extra_stages`), rôles, cibles (`hosting`), capacités fournies et requises, forge, fournisseur, cycle de vie, date de vérification. Le schéma est validé au chargement.

Si l'outil a des réglages, décrire ses paramètres dans `data/params.yaml` : libellé, type, valeur par défaut (`{app}` = nom de l'image du projet), valeur d'exemple, liste de choix ou de suggestions, motif et explication du format. Le formulaire et les règles R32 à R34 s'en déduisent. Une valeur par défaut qui ne respecte pas son propre motif est refusée au chargement.

Un outil ne peut être posé que dans `stage` ou `extra_stages`. Par exemple, Ansible va en Infrastructure ou Déploiement, et Trivy en Sécurité ou Tests & qualité. Les entrées non vérifiées du Landscape reçoivent des étapes déduites de leur sous-catégorie. La règle R25 bloque la génération si un fichier `.devops.yaml` édité à la main place une brique ailleurs, et propose de la déplacer.

### Ajouter une règle

Créer `data/rules/R39_....yaml` avec un `type` existant (`exclusive_role`, `conflict_pair`, `requires`, `requires_generic`, `lifecycle`, `target_mismatch`, `params`…), puis ajouter son cas dans `tests/test_rules.py`. Un nouveau type de règle s'écrit comme un handler dans `rules.py`.

### Rafraîchir le Landscape

```bash
curl -LO https://raw.githubusercontent.com/cncf/landscape/master/landscape.yml
python tools/build_landscape_index.py landscape.yml
```

Le script signale les entrées ajoutées, retirées et nouvellement archivées, pour savoir quelles fiches revoir.

## Tests

```bash
pip install -e ".[dev]"
QT_QPA_PLATFORM=offscreen pytest
```

243 tests : un par règle, l'application de chaque correction proposée, une matrice de combinaisons CI × déploiement × cloud × environnements validées contre les schémas, avec contrôle qu'aucune brique n'y reste sans fichier, les 4 590 combinaisons de l'assistant (aucune ne doit produire d'erreur bloquante), la validation, l'écriture prudente, l'export Git vers des dépôts locaux (dont les options de push GitLab), les scripts kind et variables CI contre des outils factices et une fausse API Gitea, et l'interface pilotée hors écran : glisser-déposer, formulaire de paramètres, surcharges, éditeur d'environnements, assistant, dialogues de validation, de différences et d'export. Toute exception levée dans un slot Qt fait échouer le test en cours.

## Limites connues

- Les fiches sont datées du 8 octobre 2026 ; le cycle de vie des outils évolue vite (ingress-nginx, Kaniko, AWS App Mesh, Google Container Registry y sont déjà signalés).
- OKS (Outscale) et Azure Container Apps n'ont pas de ressource Terraform générée : seul un commentaire est écrit, et R31 les signale. La prise en charge d'OKS par le provider `outscale/outscale` reste à vérifier.
- RKE2 : le contrôleur d'entrée embarqué dépend de la version ; le script indique comment le désactiver mais ne le fait pas.
- Renovate hors GitHub : `renovate.json` est généré, mais le job planifié qui lance Renovate reste à créer (expliqué dans `PIPELINE.md`).
- Argo CD et Flux : avec un cluster par environnement, les clusters distants doivent être enregistrés auprès de l'instance GitOps (`argocd cluster add`, ou un Flux par cluster) ; c'est indiqué dans `PIPELINE.md`.
- Woodpecker, Tekton, CodeBuild et Cloud Build n'ont pas de porte d'approbation native : la production part d'un déclenchement manuel ou d'un fichier séparé, et la restriction de qui peut le lancer se règle dans l'outil.
- Le contrôle Helm demande `helm` sur le poste, et le test kind demande Docker, kind et kubectl. Le script kind a été vérifié en dry-run contre un vrai serveur d'API Kubernetes, et son déploiement complet seulement avec des outils factices.
- `scripts/ci-variables.sh` ne couvre pas Jenkins, Woodpecker, Tekton, CodeBuild ni Cloud Build : leurs secrets restent à déclarer à la main (liste dans `PIPELINE.md`).
- Export Git : la pull request GitHub demande `gh auth login` ; sans cela, et pour Gitea, Bitbucket et Azure DevOps, il faut cliquer le lien de création proposé.
- Une brique issue du Landscape sans fiche n'est contrôlée par aucune règle et ne produit aucun fichier.
- L'authentification cloud par OIDC n'est générée que pour GitLab CI et GitHub Actions. Gitea Actions reprend les actions GitHub, mais l'émission du jeton dépend de l'instance. Jenkins, Woodpecker, Tekton, Azure Pipelines et Cloud Build reposent sur des secrets ou sur l'identité du service.
