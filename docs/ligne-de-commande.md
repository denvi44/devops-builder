# Ligne de commande

`devops-builder` sans argument lance l'interface graphique ; avec une commande, il travaille sans écran
(CI, scripts). `devops-builder --version` affiche la version, `devops-builder <commande> --help` les options.

## Codes de sortie

Ils font partie du contrat stable : un script peut s'y fier d'une version à l'autre.

| Code | Sens |
| --- | --- |
| 0 | Succès |
| 1 | Problème trouvé : erreur bloquante des règles, contrôle de validation en échec, réponses incomplètes de `init`, export Git impossible, fiche à corriger (`catalog-check`), entrée introuvable (`catalog-import`) |
| 2 | Utilisation incorrecte (option inconnue, argument manquant) ou fichier illisible : projet absent, YAML invalide, champ invalide, format plus récent que l'application, dossier à analyser absent |

`test-kind` rend le code de sortie du script de test (`scripts/test-kind.sh`), ou 2 si le pipeline ne
déploie ni chart Helm ni overlay Kustomize. Les messages d'erreur d'un fichier illisible vont sur la sortie
d'erreur ; un fichier qui contient des champs inconnus de la version est lu, ses champs sont signalés sur la
sortie d'erreur et conservés (voir [format.md](format.md)).

## Commandes

| Commande | Rôle |
| --- | --- |
| `devops-builder check projet.devops.yaml` | Évaluer les règles ; `--json` |
| `devops-builder generate projet.devops.yaml -o sortie/` | Générer les fichiers ; `--dry-run`, `--overwrite`, `--force`, `--json` |
| `devops-builder validate projet.devops.yaml` | Passer les fichiers générés aux outils de référence ; `--offline`, `-v`, `--json` |
| `devops-builder test-kind projet.devops.yaml` | Déployer dans un cluster kind jetable ; `--env`, `--app-dir`, `--keep` |
| `devops-builder export-git projet.devops.yaml --repo ../depot` | Committer sur une branche et ouvrir la demande de fusion ; `--branch`, `--message`, `--remote`, `--no-push`, `--no-request`, `--overwrite` |
| `devops-builder catalog-check` | Contrôler les fiches (dépôts, Landscape, cycle de vie) ; `--offline`, `--refresh`, `--apply`, `--report` |
| `devops-builder catalog-import "Nom"` | Créer une fiche personnelle depuis le Landscape ; `--id`, `--stage`, `--license`, `--offline` |
| `devops-builder landscape-refresh` | Rafraîchir l'index du Landscape ; `--source`, `--reset` |
| `devops-builder scan ../mon-app` | Analyser le dossier d'une application ; `--json` |
| `devops-builder init ../mon-app -o mon-app.devops.yaml` | Créer un projet depuis l'analyse ; `--hosting`, `--cloud`, `--database`, `--envs` |

`generate` n'écrase pas un fichier retouché à la main : il le liste (`kept` en JSON), et `--overwrite` le
remplace.

## Sortie `--json`

`check`, `generate` et `validate` écrivent un seul objet JSON sur la sortie standard, quel que soit le
résultat (y compris une génération refusée). Champs communs :

- `schema` : **1** — version de cette sortie ; un champ retiré ou renommé l'augmente, un champ ajouté non ;
- `command`, `version` (de l'application), `ok` (vrai si le code de sortie est 0).

| Commande | Champs propres |
| --- | --- |
| `check` | `project`, `blocking` (nombre), `diagnostics`, `unknown_fields` |
| `generate` | `project`, `output`, `dry_run`, `written` (nombre), `kept`, `files`, `unsupported`, `unknown_fields` ; refusée : `error`, `diagnostics` |
| `validate` | `project`, `summary`, `results` ; refusée : `error`, `diagnostics` |

Un diagnostic : `rule` (R00…), `severity` (`bloquant`, `avertissement`, `info`), `family`, `message`,
`bricks` (identifiants des briques concernées), `actions` (libellés des corrections proposées).
Un fichier de `generate` : `path`, `status` (`nouveau`, `mis à jour`, `identique`, `modifié à la main`, `existant`, `obsolète`), `selected`,
`deletion`, `added`, `removed`. Un contrôle de `validate` : `id`, `label`, `status` (`ok`, `échec`, `absent`,
`ignoré`), `files`, `seconds`, `output`, `hint`.

`scan --json` décrit l'application analysée ; il ne porte pas encore les champs communs.
