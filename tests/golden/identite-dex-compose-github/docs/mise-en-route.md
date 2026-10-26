# Mise en route — Mon projet

<!-- Généré par DevOps Builder — à relire avant usage. -->

Les gestes à faire une fois, dans l'ordre, avant le premier pipeline. Chaque section se vérifie avant de passer à la suivante.

## 1. Dex

Dex délègue la connexion à GitHub (Settings › Developer settings › OAuth Apps) : y créer une application OAuth avec l'adresse de retour `https://dex.boutique.fr/callback`, puis :

```bash
# DEX_CONNECTOR_ID dans la configuration (compose), DEX_CONNECTOR_SECRET et les secrets des clients en variables CI (section Variables CI)
```

Vérifier : `curl -fsS https://dex.boutique.fr/.well-known/openid-configuration | jq -r .issuer`.

Outils branchés : Grafana. Grafana : servi par Traefik à son adresse publique, secret par `deploy/secrets.sh`.

## 2. Secrets de l'application

Valeurs dans des variables CI, une par environnement : `scripts/ci-variables.sh` les déclare (section Variables CI). Générer chaque mot de passe avec `openssl rand -hex 24`.

## 3. Hôtes

Sur chaque hôte : un compte `deploy` avec la clé publique de la CI (la clé privée va dans `SSH_PRIVATE_KEY`) et sudo sans mot de passe.

```bash
ssh-keygen -t ed25519 -N '' -f ci_deploy -C ci-deploy   # sur le poste
sudo useradd -m -s /bin/bash deploy
sudo install -d -m 700 -o deploy -g deploy /home/deploy/.ssh
sudo tee /home/deploy/.ssh/authorized_keys < ci_deploy.pub
echo 'deploy ALL=(ALL) NOPASSWD:ALL' | sudo tee /etc/sudoers.d/deploy
```

Empreinte des hôtes dans `SSH_KNOWN_HOSTS` (facultatif, recommandé) : `ssh-keyscan <hôte>`.

Préparer les hôtes (Docker depuis son dépôt officiel), une fois par environnement :

```bash
pip install 'ansible-core>=2.21,<2.22' && ansible-galaxy collection install -r ansible/requirements.yml
ANSIBLE_CONFIG=ansible/ansible.cfg ansible-playbook -i ansible/inventories/staging.ini ansible/site.yml
ANSIBLE_CONFIG=ansible/ansible.cfg ansible-playbook -i ansible/inventories/production.ini ansible/site.yml
```

Noms d'hôte de l'application : chacun pointe (enregistrement DNS A ou AAAA) vers l'hôte de son environnement, joignable depuis Internet sur les ports 80 et 443 ; Traefik y obtient seul le certificat (paramètre « Adresse publique de l'application » de la brique Traefik).

- Préproduction : `staging.mon-app.example.com`
- Production : `mon-app.example.com`

## 4. Variables CI

8 variable(s) à déclarer (liste dans `PIPELINE.md`). Le script les déclare avec l'outil de la forge, sans écrire les valeurs dans le dépôt :

```bash
bash scripts/ci-variables.sh --dry-run   # ce qui serait déclaré
bash scripts/ci-variables.sh
```

## 5. Premier déploiement

Pousser sur la branche principale : chaque environnement se déploie dans l'ordre, la production après approbation.

```bash
ssh "<hôte>" "cd /opt/mon-app && docker compose -p mon-app ps"
```

## 6. Essai à la main, sans CI

Pour essayer la pile sur un hôte Docker sans passer par la CI (labo, poste de travail, NAS), copier le dossier du projet sur l'hôte puis, depuis ce dossier :

```bash
DEX_CONNECTOR_ID="$(openssl rand -hex 24)" DEX_CONNECTOR_SECRET="$(openssl rand -hex 24)" GRAFANA_OIDC_SECRET="$(openssl rand -hex 24)" sh deploy/secrets.sh deploy/secrets   # écrit deploy/secrets/ (ne pas le partager)
export COMPOSE_FILE=deploy/docker-compose.yml   # les commandes compose s'appliquent au projet
docker compose version   # absente ? voir la remarque ci-dessous
docker compose config --services     # les services du projet
docker compose up -d <service> ...   # ceux à lancer ; sans nom : tous
docker compose ps
```

Les services de l'application ont besoin de leur image (construite et poussée par la CI) : à l'essai, ne lancer que les services de plateforme (bases, Zabbix, Keycloak…).

`docker compose` absent (NAS, Unraid, vieux Docker) : télécharger le binaire autonome de Compose à côté du projet, sans rien installer sur le système.

```bash
mkdir -p bin && curl -SL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64 -o bin/docker-compose && chmod +x bin/docker-compose
bin/docker-compose version   # puis bin/docker-compose à la place de docker compose
```
