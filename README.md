# DevOps Builder

Application de bureau Python, en Material Design, pour composer un pipeline DevOps en posant des briques issues du [CNCF Landscape](https://landscape.cncf.io/). Un moteur de règles bloque les combinaisons incohérentes avant de générer les fichiers à committer.

![Pipeline de référence](docs/captures/01-pipeline.png)

## Ce que fait l'application

- **Catalogue** : 132 fiches vérifiées (outils, services managés, fournisseurs cloud) et l'ensemble du Landscape consultable, soit 1 192 entrées. Les entrées sans fiche sont marquées « non vérifiées ».
- **Canevas** : neuf étapes en colonnes (source → observabilité). On y glisse des briques depuis la palette, ou on les ajoute par double-clic. Chaque outil n'accepte que ses étapes : pendant un glisser, les colonnes compatibles sont mises en évidence, les autres grisées, et un dépôt hors étape est refusé avec un message.
- **Contrôle continu** : 26 règles (R00 à R25) couvrant le placement dans les étapes, la cible d'hébergement, l'exclusivité de rôle, les dépendances, les contrats entre étapes, la forge, le cycle de vie, la licence et la conformité (SecNumCloud, clés statiques). Chaque diagnostic propose des corrections en un clic, annulables.
- **Génération** : définitions CI, déploiement, IaC et plateforme, avec un rapport `PIPELINE.md` qui liste les briques, les licences, les variables CI à déclarer et les avertissements restants.

![Diagnostics et corrections](docs/captures/02-diagnostics.png)

## Installation

Il faut Python 3.11 ou plus récent.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows : .venv\Scripts\activate
pip install -e .
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
| Paramètres du projet | F2 : cible, environnement, langage, SecNumCloud, OIDC, politique de licence |
| Générer | Ctrl+G : aperçu des fichiers, puis export en dossier ou en .zip |
| Annuler / rétablir | Ctrl+Z / Ctrl+Y |
| Rechercher | Ctrl+F ; Ctrl+2 pour le pipeline, Ctrl+3 pour les diagnostics |
| Thème sombre | Ctrl+T |

Trois projets d'exemple sont fournis dans **Fichier › Ouvrir un exemple** : un site web sur hôte Docker, une API sur k3s en GitOps et une plateforme AWS EKS en OpenTofu.

### En ligne de commande

```bash
devops-builder check projet.devops.yaml                 # code retour 1 si erreur bloquante
devops-builder generate projet.devops.yaml -o sortie/   # --force pour passer outre
```

## Ce qui est généré

| Domaine | Formats |
| --- | --- |
| CI | GitLab CI, GitHub Actions, Gitea Actions, Jenkinsfile, Woodpecker, Tekton, Azure Pipelines, AWS CodeBuild, Google Cloud Build |
| Déploiement | Docker Compose, chart Helm, Kustomize, Application Argo CD, Flux (GitRepository + Kustomization ou HelmRelease), playbooks Ansible |
| Infrastructure | Terraform / OpenTofu : providers, backend d'état, ressources AWS, Google Cloud, Azure, OVHcloud, Scaleway |
| Plateforme | `platform/install.sh` (charts Helm officiels) ou services Compose sur hôte Docker |
| Authentification cloud | OIDC par défaut : rôle IAM, Workload Identity Federation, fédération Entra ID |

Les fichiers générés sont un point de départ à relire. Les tests valident chaque sortie YAML contre les schémas officiels (GitLab CI, GitHub Workflows, Azure Pipelines, Cloud Build, Woodpecker, Compose) et passent les workflows GitHub dans actionlint. `terraform validate`, `helm lint` et `ansible-lint` ne sont pas exécutés : ils demandent un accès réseau aux registres de providers et de charts.

## Organisation du code

```
devops_builder/
  model.py          fiches, projet, format .devops.yaml
  catalog.py        chargement des fiches + index du Landscape
  rules.py          moteur de règles, handlers génériques, corrections
  ir.py             représentation intermédiaire neutre du pipeline
  generators/       ci, deploy, iac, platform, report
  ui/               interface PySide6 + qt-material
  data/catalog/     fiches YAML (une par outil)
  data/rules/       une règle YAML par fichier
  data/examples/    projets de référence
tools/
  build_landscape_index.py   rafraîchit l'index depuis landscape.yml
  screenshot.py              captures hors écran de l'interface
tests/              règles, générateurs, interface (hors écran)
```

### Ajouter un outil

Ajouter une entrée dans un fichier de `data/catalog/` : étape principale (`stage`) et, s'il le faut, étapes secondaires (`extra_stages`), rôles, cibles (`hosting`), capacités fournies et requises, forge, fournisseur, cycle de vie, date de vérification. Le schéma est validé au chargement.

Un outil ne peut être posé que dans `stage` ou `extra_stages`. Par exemple, Ansible va en Infrastructure ou Déploiement, et Trivy en Sécurité ou Tests & qualité. Les entrées non vérifiées du Landscape reçoivent des étapes déduites de leur sous-catégorie. La règle R25 bloque la génération si un fichier `.devops.yaml` édité à la main place une brique ailleurs, et propose de la déplacer.

### Ajouter une règle

Créer `data/rules/R25_....yaml` avec un `type` existant (`exclusive_role`, `conflict_pair`, `requires`, `lifecycle`, `target_mismatch`…), puis ajouter son cas dans `tests/test_rules.py`. Un nouveau type de règle s'écrit comme un handler dans `rules.py`.

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

95 tests : un par règle, l'application de chaque correction proposée, une matrice de 11 combinaisons CI × déploiement × cloud validées contre les schémas, et l'interface pilotée hors écran, y compris de vrais événements de glisser-déposer refusés et acceptés.

## Limites connues

- Les fiches sont datées du 8 octobre 2026 ; le cycle de vie des outils évolue vite (ingress-nginx, Kaniko, AWS App Mesh, Google Container Registry y sont déjà signalés).
- OKS (Outscale) n'a pas de ressource Terraform générée : sa prise en charge par le provider `outscale/outscale` reste à vérifier.
- Une brique issue du Landscape sans fiche n'est contrôlée par aucune règle et ne produit aucun fichier.
- L'authentification cloud par OIDC n'est générée que pour GitLab CI et GitHub Actions. Gitea Actions reprend les actions GitHub, mais l'émission du jeton dépend de l'instance. Jenkins, Woodpecker, Tekton, Azure Pipelines et Cloud Build reposent sur des secrets ou sur l'identité du service.
