# Premier labo : des outils sur un hôte Docker

**Objectif** : le chemin le plus court vers quelque chose qui tourne. Une forge (Gitea), une supervision
(Zabbix, qui mesure aussi l'hôte et ses conteneurs), Prometheus et Grafana, lancés à la main sur une machine
qui a Docker. Pas d'application à construire, pas de CI, pas de nom de domaine.

**Il faut** : une machine Linux avec Docker (un serveur, une machine virtuelle, un NAS comme Unraid) ; `curl` et
`jq` sur le poste pour la partie Zabbix. Durée : une vingtaine de minutes, téléchargement des images compris.

## 1. Ouvrir l'exemple

Sur l'écran « Par où commencer ? », choisir l'exemple **Labo DevOps sur hôte Docker** (ou Fichier › Ouvrir un
exemple). Le projet s'ouvre sans aucun diagnostic.

C'est un projet **sans application** (« plateforme seule ») : Projet › Paramètres du projet, case « Projet sans
application ». L'application, la CI et le registre n'y ont plus d'objet ; une brique qui construit, analyse ou
livre une application y est signalée (R59), avec son retrait en un clic.

Pour ajouter un outil, le glisser depuis le catalogue : SonarQube, Keycloak, une base PostgreSQL… Deux outils
qui publient le même port sont signalés (R39) : Jenkins et Zabbix veulent tous deux le port 8080.

## 2. Générer

Projet › Générer les fichiers (Ctrl+G), puis « Archive .zip… ». L'archive s'extrait dans son propre dossier,
`labo-devops-sur-hote-docker`. On obtient :

| Fichier | Rôle |
| --- | --- |
| `deploy/docker-compose.yml` | Gitea, Zabbix (serveur, interface, base, deux agents), Prometheus et Grafana |
| `deploy/secrets.sh` | écrit les mots de passe lus par les conteneurs |
| `scripts/db-backup.sh`, `scripts/db-restore.sh` | sauvegarde et restauration de la base de Zabbix |
| `PIPELINE.md` | ports publiés, mémoire à prévoir sur l'hôte |
| `docs/mise-en-route.md` | les commandes de ce projet, dans l'ordre |

## 3. Démarrer

Copier l'archive sur l'hôte, l'extraire, puis suivre `docs/mise-en-route.md`, section « Démarrer la
plateforme ». Les blocs se collent tels quels dans un terminal, bash ou zsh : ils ne contiennent aucun
commentaire, les remarques sont sous chaque bloc.

En résumé : une commande tire les mots de passe au hasard (une seule fois), `docker compose up -d` lance la pile,
et le guide liste l'adresse de chaque interface (Gitea, Grafana, Prometheus, Zabbix). Si `docker compose`
n'existe pas sur l'hôte (Unraid, vieux Docker), le guide donne la commande qui télécharge Compose à côté du
projet, sans rien installer.

## 4. Superviser l'hôte et ses conteneurs

Section « Zabbix » du guide : changer le mot de passe du compte Admin, connu de tous, puis déclarer l'hôte
Docker. Zabbix affiche alors le processeur, la mémoire et les disques de la machine, et l'état de chaque
conteneur.

L'agent qui mesure l'hôte lit le socket Docker, ce qui lui donne des droits étendus sur la machine : c'est le
prix de la supervision des conteneurs. Pour s'en passer, décocher « Superviser l'hôte Docker » dans les
paramètres de la brique Zabbix.

## Et ensuite

- Arrêter sans rien perdre : `docker compose down` ; les données restent dans les volumes.
- Passer à une vraie application : décocher « Projet sans application », puis suivre le tutoriel
  [Site web sur un hôte Docker](hote-docker.md).
