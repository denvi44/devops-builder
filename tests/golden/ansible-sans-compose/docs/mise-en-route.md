# Mise en route — Ansible seul

<!-- Généré par DevOps Builder — à relire avant usage. -->

Les gestes à faire une fois, dans l'ordre, avant le premier pipeline. Chaque section se vérifie avant de passer à la suivante. Les blocs se collent tels quels dans un terminal (bash ou zsh) ; les remarques sont sous chaque bloc.

## 1. Hôtes

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

## 2. Variables CI

2 variable(s) à déclarer (liste dans `PIPELINE.md`). Le script les déclare avec l'outil de la forge, sans écrire les valeurs dans le dépôt :

```bash
bash scripts/ci-variables.sh --dry-run
bash scripts/ci-variables.sh
```

- `bash scripts/ci-variables.sh --dry-run` : ce qui serait déclaré

## 3. Premier déploiement

Pousser sur la branche principale : chaque environnement se déploie dans l'ordre.
