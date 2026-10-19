# Format du fichier projet (`.devops.yaml`)

Format courant : **2**. Le fichier est du YAML lisible et modifiable à la main ; l'application l'écrit dans
l'ordre des champs ci-dessous.

## Promesse de compatibilité

- **Un fichier écrit par une version plus ancienne s'ouvre toujours.** Ses anciennes formes sont converties à
  la lecture (voir « Migrations ») ; les tests ouvrent, contrôlent, génèrent et réenregistrent des fichiers
  écrits par chaque version publiée depuis la 0.1 (`tests/data/legacy/`), sans perdre de valeur.
- **Un fichier écrit par une version plus récente du même format s'ouvre aussi.** Les champs que la version
  ne connaît pas sont gardés tels quels et réécrits à l'enregistrement ; l'application les signale dans la
  barre d'état, la ligne de commande dans sa sortie.
- **Un fichier d'un format plus récent est refusé** avec un message qui demande de mettre l'application à jour,
  plutôt que d'être lu à moitié.
- Un champ ajouté par une nouvelle version est facultatif et n'est écrit que s'il sert, pour que les versions
  précédentes du même format relisent le fichier. Un changement qui ne peut pas être lu ainsi augmente
  `format_version` et ajoute une migration.

## Champs du projet

| Champ | Type | Défaut | Rôle |
| --- | --- | --- | --- |
| `format_version` | entier | 2 | Version du format ; absente, le fichier est lu comme format 1 |
| `name` | texte | « Nouveau projet » | Nom affiché et repris dans les fichiers générés |
| `description` | texte | vide | Texte libre |
| `target` | texte | `docker-host` | Cible : `docker-host`, `vm`, `kubernetes`, `kubernetes-managed` (un service serverless est une brique de l'étape Déploiement, la cible reste `docker-host`) |
| `environments` | liste | un environnement `production` | Environnements, dans l'ordre de promotion (ci-dessous) |
| `secnumcloud` | oui / non | non | Restreint les fournisseurs aux offres qualifiées SecNumCloud |
| `cloud_auth` | `oidc` ou `static` | `oidc` | Authentification de la CI auprès du cloud |
| `license_policy` | `any` ou `oss-only` | `any` | Refuser les outils sous licence non libre |
| `app` | dictionnaire | — | Application déployée (ci-dessous) |
| `stages` | dictionnaire | toutes les étapes vides | Briques par étape (ci-dessous) |

### Environnement

| Champ | Type | Défaut | Rôle |
| --- | --- | --- | --- |
| `id` | texte | obligatoire | Identifiant, repris dans les noms de fichiers et de jobs |
| `label` | texte | vide | Nom affiché |
| `kind` | `sandbox`, `dev`, `recette`, `staging`, `production` | `production` | Type, qui décide des règles appliquées |
| `approval` | oui / non | non | Approbation avant déploiement |
| `cluster` | texte | aucun | Cluster dédié à l'environnement |
| `host` | texte | vide (non écrit) | Hôte dédié (ajouté en 0.6) |
| `port_offset` | entier | aucun (non écrit) | Décalage des ports publiés (ajouté en 0.6) |
| `overrides` | dictionnaire | vide | Paramètres de brique propres à l'environnement, par identifiant de brique |

Les champs d'un environnement sont contrôlés strictement : une clé inconnue y est une erreur, pour qu'une
faute de frappe ne passe pas inaperçue.

### Application (`app`)

| Champ | Type | Défaut |
| --- | --- | --- |
| `language` | texte | `python` |
| `image_name` | texte | `mon-app` |
| `port` | entier | 8000 |
| `source` | texte | vide (non écrit) : dossier de l'application sur le poste |

### Étapes et briques (`stages`)

Les clés sont les étapes du pipeline : `source`, `build`, `test`, `security`, `artifacts`, `infrastructure`,
`data` (ajoutée en 0.8, non écrite si vide), `deploy`, `platform`, `observability`. Chaque étape est une liste
de briques :

| Champ | Type | Rôle |
| --- | --- | --- |
| `uid` | texte | Identifiant de la brique dans le projet (8 caractères) |
| `tool` | texte | Identifiant de la fiche du catalogue, ou d'une entrée du Landscape (`lsc-…`) |
| `params` | dictionnaire | Paramètres de la brique ; leur liste et leur type sont donnés par la fiche |
| `instance` | texte | Nom de l'instance (0.21, non écrit si vide) : plusieurs briques du même outil se distinguent par ce nom. Identifiant de service : `<outil>-<nom>` ; lettres minuscules, chiffres et tirets |

## Migrations

| Depuis | Vers | Changement |
| --- | --- | --- |
| format 1 (0.1, 0.2) | 2 | Le champ unique `environment` devient la liste `environments` |
| 0.7 | 0.8 | Les bases de données rangées en Plateforme restent acceptées là ; les nouvelles vont dans Données |
| `lsc-…` | fiche | Une entrée du Landscape devenue fiche garde son ancien identifiant comme alias |
