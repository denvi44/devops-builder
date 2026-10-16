# Contribuer à DevOps Builder

Merci de votre intérêt. DevOps Builder est un projet en français : interface, documentation, messages,
tickets et revues se font en français.

## Avant de commencer

- Une anomalie, une fiche à corriger ou un outil à prendre en charge : ouvrir un ticket avec le modèle qui
  convient. Une vulnérabilité : jamais en ticket public, voir [SECURITY.md](SECURITY.md).
- Pour un changement important (nouveau générateur, nouvelle règle, changement du format du fichier projet),
  ouvrir d'abord un ticket pour en discuter.
- Jusqu'à la 1.0, le périmètre est gelé : on ferme des écarts plutôt que d'ajouter des briques (voir
  [ROADMAP.md](ROADMAP.md) et `docs/prise-en-charge.md`).

## Poste de développement

Python 3.11 ou plus récent.

```bash
python -m venv .venv
source .venv/bin/activate              # Windows : .venv\Scripts\activate
pip install -e ".[dev]"
QT_QPA_PLATFORM=offscreen python -m pytest -q
ruff check .
```

Sous Linux, Qt demande `libegl1`, `libgl1`, `libxkbcommon0` et `libfontconfig1`. Les tests qui demandent un
outil absent du poste (OpenTofu, Helm, kubeconform, Ansible, PostgreSQL, Keycloak…) sont sautés ; la CI du
dépôt lance le reste. `DEVOPS_BUILDER_TOFU_MIRROR=<dossier d'un miroir de providers>` active `tofu validate`
sur toutes les piles générées.

## Projets de référence

`tests/golden/` contient tout ce que génèrent environ 190 projets. Un changement voulu des fichiers générés :

```bash
UPDATE_GOLDEN=1 python -m pytest tests/test_regression.py
git diff tests/golden
```

Chaque ligne changée doit s'expliquer, dans la demande de fusion. Une différence inattendue est une
régression, même si elle semble anodine.

## Ajouter ou corriger une fiche

Les fiches sont dans `devops_builder/data/catalog/*.yaml`. Une fiche décrit l'outil (étape, rôles, capacités
fournies et requises, cibles d'hébergement, licence SPDX, dépôt) et son **niveau de prise en charge** :

- `support: supported` (défaut) : un générateur produit ses fichiers et ils passent l'outil de référence
  dans les tests ;
- `support: experimental` avec `support_note` : générés, avec une limite connue ;
- `support: manual` : aucun générateur ; la brique sert aux règles et à la documentation.

`tests/test_support.py` confronte ce niveau à ce que les générateurs produisent réellement. Après un
changement : `python -m devops_builder.support > docs/prise-en-charge.md`.

## Ajouter une règle

Une règle est un fichier `devops_builder/data/rules/RNN_nom.yaml` (identifiant, famille, gravité, type,
message) ; un nouveau type demande une fonction `@handler("type")` dans `devops_builder/rules.py`. Ajouter
un cas à `CASES` dans `tests/test_rules.py` : un test vérifie que chaque règle en a un.

## Ajouter ou modifier un générateur

Les générateurs sont dans `devops_builder/generators/`, assemblés par `render()`. Un générateur déclare les
briques qu'il couvre (`ir.cover(...)`) ; une brique non couverte apparaît dans « À configurer à la main ».
Ajouter un projet de référence dans `tests/snapshot.py` (`extra_cases`) qui l'exerce, et une validation par
l'outil de référence (schéma, linter, `tofu validate`, ShellCheck) dans les tests.

## Conventions

- Textes visibles en français ; code et identifiants en anglais.
- Chaque fichier Python commence par `# SPDX-License-Identifier: Apache-2.0`.
- Le format du fichier projet ne se casse pas : un champ ajouté est facultatif et n'est écrit que s'il sert ;
  sinon `format_version` augmente et une migration est ajoutée (`docs/format.md`).
- Les codes de sortie et la sortie `--json` de la ligne de commande sont un contrat
  (`docs/ligne-de-commande.md`).
- Une ligne dans `CHANGELOG.md` pour chaque changement visible.
- Accessibilité : chaque contrôle de l'interface a un nom accessible, et l'information ne passe jamais par la
  couleur seule ; `tests/test_accessibilite.py` passe l'audit (noms, clavier, focus, contrastes, langue, texte à
  200 %) sur chaque dialogue : un dialogue ajouté se déclare dans `dialogs_of` (`devops_builder/ui/audit.py`).
  Une icône décorative est une `DecorativeIcon`, pas un `QLabel` avec une image ; un message à faire lire passe
  par la barre d'état ou par `a11y.announce`.
- Messages d'erreur : jamais une trace ni un message système brut ; `messages.explain` traduit les erreurs du
  système, de YAML et des commandes lancées.
- Guide : un tutoriel cite des fichiers que son projet génère vraiment (`tests/test_guide.py`) ; un changement
  de l'interface ou des fichiers générés met à jour `docs/guide/` (`mkdocs build --strict` pour vérifier).

## Publier une version

Aucune étiquette ne se crée à la main :

1. Sur `main`, la version est à jour dans `pyproject.toml` et `devops_builder/__init__.py`, et `CHANGELOG.md` a sa
   section `## X.Y.Z — date — titre` (elle devient les notes de la publication).
2. Actions → **Publication** → Run workflow, sur `main`, avec la version `X.Y.Z`.
3. Le workflow vérifie la version, le journal et que l'étiquette est libre, relance les tests, construit le paquet
   et les exécutables (Linux, Windows, macOS), les éprouve, les atteste, publie sur PyPI, puis crée l'étiquette
   `vX.Y.Z` et la publication GitHub avec les fichiers et `SHA256SUMS`.

La publication sur PyPI est « de confiance » : PyPI reconnaît le dépôt `denvi44/devops-builder`, le workflow
`publication.yml` et l'environnement GitHub `pypi` ; aucun mot de passe ni jeton n'est stocké. Poussé sur une
autre branche qui touche `packaging/` ou le workflow, celui-ci ne fait qu'un essai, sans rien publier.

## Licence des contributions

Le projet est sous licence Apache 2.0. Comme le prévoit sa section 5, une contribution proposée au projet est
faite sous cette même licence, sans accord de contributeur séparé. Ne proposez que du code que vous avez le
droit de publier ainsi.
