# Mise en route — matrice

<!-- Généré par DevOps Builder — à relire avant usage. -->

Les gestes à faire une fois, dans l'ordre, avant le premier pipeline. Chaque section se vérifie avant de passer à la suivante. Les blocs se collent tels quels dans un terminal (bash ou zsh) ; les remarques sont sous chaque bloc.

## 1. Essai à la main, sans CI

Le chemin le plus court pour voir tourner les outils du projet, avant de brancher la CI : sur un hôte Docker (labo, poste de travail, NAS), copier le dossier du projet puis, depuis ce dossier :

```bash
export COMPOSE_FILE=deploy/docker-compose.yml
docker compose up -d zot gitea
docker compose ps
```

`docker compose ps` doit montrer chaque service `running` (ou `healthy`) ; le premier démarrage télécharge les images et peut prendre quelques minutes. Journal d'un service qui ne démarre pas : `docker compose logs --tail 30 <service>`.

Les interfaces répondent ensuite ici :

- Gitea (interface web) : `http://<adresse de l'hôte>:3001`

Le service de l'application (`mon-app`) attend son image, construite et poussée par la CI : il se lance avec le premier déploiement.

`docker compose` absent (NAS, Unraid, vieux Docker) : télécharger le binaire autonome de Compose à côté du projet, sans rien installer sur le système, puis écrire `bin/docker-compose` à la place de `docker compose`.

```bash
mkdir -p bin && curl -SL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64 -o bin/docker-compose && chmod +x bin/docker-compose
bin/docker-compose version
```

## 2. Hôtes

Sur chaque hôte : un compte `deploy` avec la clé publique de la CI (la clé privée va dans `SSH_PRIVATE_KEY`) et sudo sans mot de passe.

```bash
ssh-keygen -t ed25519 -N '' -f ci_deploy -C ci-deploy
sudo useradd -m -s /bin/bash deploy
sudo install -d -m 700 -o deploy -g deploy /home/deploy/.ssh
sudo tee /home/deploy/.ssh/authorized_keys < ci_deploy.pub
echo 'deploy ALL=(ALL) NOPASSWD:ALL' | sudo tee /etc/sudoers.d/deploy
```

- `ssh-keygen -t ed25519 -N '' -f ci_deploy -C ci-d…` : sur le poste

Empreinte des hôtes dans `SSH_KNOWN_HOSTS` (facultatif, recommandé) : `ssh-keyscan <hôte>`.

Préparer les hôtes (Docker depuis son dépôt officiel), une fois par environnement :

```bash
pip install 'ansible-core>=2.21,<2.22' && ansible-galaxy collection install -r ansible/requirements.yml
ANSIBLE_CONFIG=ansible/ansible.cfg ansible-playbook -i ansible/inventory.ini ansible/site.yml
```

## 3. Variables CI

4 variable(s) à déclarer (liste dans `PIPELINE.md`). Le script les déclare avec l'outil de la forge, sans écrire les valeurs dans le dépôt :

```bash
bash scripts/ci-variables.sh --dry-run
bash scripts/ci-variables.sh
```

- `bash scripts/ci-variables.sh --dry-run` : ce qui serait déclaré

## 4. Premier déploiement

Pousser sur la branche principale : chaque environnement se déploie dans l'ordre.

```bash
ssh "<hôte>" "cd /opt/mon-app && docker compose -p mon-app ps"
```
