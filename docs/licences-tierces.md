# Licences tierces

DevOps Builder est distribué sous la licence Apache 2.0 (`LICENSE`, `NOTICE`). Ce fichier recense ce qu'il
utilise ou embarque, et ce que chaque licence demande. Un test vérifie que chaque dépendance déclarée dans
`pyproject.toml` figure ici.

## Dépendances d'exécution

Installées par `pip` à côté de l'application : DevOps Builder ne les redistribue pas dans son paquet.

| Paquet | Licence | Usage |
| --- | --- | --- |
| PySide6 (avec shiboken6) | LGPL-3.0-only (ou GPL-2.0 / GPL-3.0) | Interface Qt, liée dynamiquement |
| qt-material | BSD-2-Clause | Thème Material |
| QtAwesome (avec QtPy) | MIT | Icônes ; embarque les polices d'icônes, dont Material Design Icons 6 utilisées par l'interface |
| pydantic (avec pydantic-core, annotated-types, typing-inspection) | MIT | Modèle du projet et des fiches |
| PyYAML | MIT | Lecture et écriture YAML |
| Jinja2, MarkupSafe (requis par qt-material) | BSD-3-Clause | Gabarits du thème |
| typing-extensions | PSF-2.0 | Compatibilité des annotations |

**PySide6 et la LGPL** : utiliser PySide6 installé par `pip` depuis une application Apache 2.0 est permis ;
la LGPL ne s'étend pas au code qui l'importe. Pour les exécutables autonomes prévus au lot 0.19, il faudra :
garder les bibliothèques Qt et PySide6 remplaçables (dossier d'installation plutôt qu'un fichier unique
extrait au lancement), joindre le texte de la LGPL-3.0 et de la GPL-3.0, et indiquer où obtenir les sources
de Qt et de PySide6 dans la version utilisée.

**Polices d'icônes** : redistribuées seulement dans un exécutable autonome. Avant le lot 0.19, vérifier la
licence de Material Design Icons 6.9.96 sur le site de Pictogrammers et la joindre à l'exécutable (à vérifier).

## Données embarquées

| Fichier | Origine | Licence |
| --- | --- | --- |
| `devops_builder/data/landscape_index.json` | Index dérivé de `landscape.yml` du [CNCF Landscape](https://github.com/cncf/landscape) : noms, catégories, maturité, adresses | Apache 2.0 (également proposé sous CC BY 4.0 par la CNCF) ; attribution dans `NOTICE`. Aucun logo ni donnée Crunchbase n'est repris |
| `devops_builder/data/catalog/`, `rules/`, `params.yaml`, `ports.yaml`, `suggestions.yaml`, `examples/` | Écrits pour DevOps Builder | Apache 2.0 |

Les fiches citent les noms des outils et leurs licences ; les marques appartiennent à leurs détenteurs.

## Outils facultatifs

Installés par `pip install -e ".[validate]"` ou `".[dev]"`, lancés comme programmes séparés, jamais
redistribués :

| Paquet | Licence | Note |
| --- | --- | --- |
| check-jsonschema | Apache-2.0 | Schémas des CI et des fichiers générés |
| actionlint-py | MIT (actionlint : MIT) | Contrôle des workflows GitHub Actions |
| shellcheck-py | MIT (ShellCheck : GPL-3.0) | Le binaire ShellCheck est lancé comme programme séparé |
| pytest, ruff | MIT | Tests et analyse du code |

Les outils appelés par la validation (Helm, kubeconform, OpenTofu, Ansible…) ne sont ni installés ni
redistribués par DevOps Builder : ils sont cherchés sur le poste.

## Fichiers générés

Les fichiers qu'il produit pour un projet (CI, charts, Terraform, scripts, documentation) appartiennent à
l'utilisateur et peuvent être placés sous la licence de son choix.
