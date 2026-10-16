# Site web sur un hôte Docker

**Objectif** : une application Python et sa base PostgreSQL, construites par GitLab CI et déployées par SSH
avec Docker Compose sur deux serveurs, préproduction puis production, derrière Traefik en HTTPS.

**Il faut** : un projet GitLab ; deux serveurs Linux joignables en SSH (un par environnement), avec Docker et
son extension Compose ; un nom de domaine dont on peut gérer les enregistrements DNS. Durée : une heure environ,
dont la plus grande part pour préparer les serveurs.

![Le pipeline créé par l'assistant : GitLab, GitLab CI, BuildKit, Renovate, tests unitaires, Gitleaks, Trivy,
Cosign, PostgreSQL, Docker Compose, Traefik, Prometheus et Grafana répartis dans leurs étapes](../captures/hote-docker.png)

## 1. Décrire le projet

Fichier › Nouveau projet (Ctrl+N) ouvre l'assistant.

1. **Application** : désigner le dossier de l'application si on l'a sous la main (« Choisir… » puis
   « Analyser ») ; l'assistant y lit le langage, le port, le Dockerfile et les bases de données. Sinon, saisir :
   nom *Boutique*, langage *Python*, image *boutique*, port *8000*.
2. **Code et intégration continue** : forge *GitLab* ; la CI native, GitLab CI, est choisie d'office.
3. **Hébergement** : *Un serveur avec Docker*, avec l'option « Serveurs existants ».
4. **Environnements et options** : *Préproduction → production* ; laisser cochées la sécurité (Gitleaks, Trivy,
   Cosign) et les mises à jour des dépendances (Renovate) ; base de données *PostgreSQL* ; secrets
   *Variables de la CI*.
5. **Récapitulatif** : « Créer le projet ».

Enregistrer aussitôt le projet (Ctrl+S), par exemple sous `boutique.devops.yaml`.

## 2. Renseigner l'adresse publique

Un seul diagnostic reste, un avertissement (R34) : la brique **Traefik** garde la valeur d'exemple de son
paramètre « Adresse publique de l'application ». Sélectionner Traefik dans l'étape Plateforme, puis, dans le
panneau Propriétés, saisir le nom de la production, par exemple `boutique.fr`.

La préproduction reçoit `staging.boutique.fr`. Pour un autre nom, choisir l'environnement Préproduction
au-dessus du formulaire et saisir sa valeur : c'est une surcharge, propre à cet environnement.

## 3. Générer

Projet › Générer les fichiers (Ctrl+G) montre l'aperçu de chaque fichier. Choisir « Écrire dans un dossier… »
et désigner la copie de travail du dépôt de l'application, ou « Exporter vers Git… » pour obtenir une branche et
une demande de fusion. On obtient notamment :

| Fichier | Rôle |
| --- | --- |
| `.gitlab-ci.yml` | tests, analyse des secrets (Gitleaks), image construite par BuildKit, analyse (Trivy) et signature (Cosign), puis un job de déploiement par environnement ; la production attend une approbation manuelle |
| `deploy/docker-compose.yml` | l'application, PostgreSQL (volume nommé, réseau interne, non publié), Traefik, Prometheus et Grafana |
| `deploy/secrets.sh` | écrit, à partir des variables de la CI, les mots de passe et l'URL de connexion lus par les conteneurs |
| `scripts/db-backup.sh`, `scripts/db-restore.sh` | sauvegarde et restauration de la base, copiées sur chaque hôte |
| `scripts/ci-variables.sh` | déclare les variables de la CI avec `glab`, sans écrire leurs valeurs dans le dépôt |
| `dev/db/compose.yaml`, `dev/db/app.env` | la même base sur le poste de développement |
| `renovate.json` | réglages de Renovate |
| `PIPELINE.md` | environnements, ports, variables, dimensionnement estimé des hôtes |
| `docs/mise-en-route.md` | les gestes à faire une fois, dans l'ordre |

## 4. Mettre en route

Suivre `docs/mise-en-route.md` ; en résumé :

1. **Secrets** : un mot de passe par environnement (`openssl rand -hex 24`), en variables de la CI.
2. **Hôtes** : sur chaque serveur, un compte `deploy` membre du groupe docker, avec la clé publique de la CI ;
   la clé privée va dans `SSH_PRIVATE_KEY`. Faire pointer `staging.boutique.fr` et `boutique.fr` vers leur
   serveur, ports 80 et 443 ouverts : Traefik obtient seul les certificats.
3. **Variables de la CI** : `bash scripts/ci-variables.sh --dry-run`, puis sans `--dry-run`. `PIPELINE.md`
   les décrit une à une (`DEPLOY_HOST_STAGING` vaut par exemple `deploy@203.0.113.10`).
4. **Premier déploiement** : pousser sur la branche principale. La préproduction se déploie ; la production
   attend qu'on lance son job dans GitLab.
5. **Sauvegardes** : sur un hôte, une sauvegarde puis une restauration d'essai, avec les commandes données ;
   planifier ensuite `db-backup.sh` (cron) et copier les sauvegardes hors de la machine.

## 5. Vérifier

- Dans DevOps Builder, Projet › Valider (Ctrl+Maj+V) passe les fichiers aux outils installés sur le poste :
  schéma de GitLab CI, `docker compose config`, ShellCheck, schéma de Renovate. Un outil absent est signalé
  avec la façon de l'installer.
- Sur l'hôte : `ssh deploy@<hôte> "cd /opt/boutique && docker compose -p boutique ps"`.
- Dans un navigateur : `https://staging.boutique.fr`, puis `https://boutique.fr` après l'approbation.

## Aller plus loin

- **Hôte partagé** : pour réunir préproduction et production sur une seule machine, cocher dans l'assistant
  « Environnements hors production sur un même hôte Docker » ; les ports publiés sont alors décalés et
  `PIPELINE.md` les liste (Ctrl+Maj+P pour la vue des ports).
- **Secrets chiffrés dans le dépôt** : choisir *Chiffrés dans le dépôt (SOPS + age)* ; le tutoriel
  [souverain](souverain.md) en montre la mise en place.
- **Supervision** : Grafana est publié sur le port 3000 de chaque hôte ; le mettre derrière Traefik ou un
  pare-feu avant d'ouvrir le serveur.
