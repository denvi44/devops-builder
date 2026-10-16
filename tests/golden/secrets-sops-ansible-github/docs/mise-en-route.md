# Mise en route — Mon projet

<!-- Généré par DevOps Builder — à relire avant usage. -->

Les gestes à faire une fois, dans l'ordre, avant le premier pipeline. Chaque section se vérifie avant de passer à la suivante.

## 1. Secrets de l'application

Une paire de clés age pour le projet. La clé publique va dans la brique SOPS (paramètre « Destinataires age ») : régénérer le projet pour mettre `.sops.yaml` à jour. La clé privée va dans la variable CI `SOPS_AGE_KEY`.

```bash
mkdir -p ~/.config/sops/age
age-keygen -o ~/.config/sops/age/keys.txt   # affiche la clé publique age1…
export SOPS_AGE_KEY_FILE=~/.config/sops/age/keys.txt
```

Puis, avec `.sops.yaml` à jour, chiffrer les valeurs de chaque environnement :

```bash
POSTGRESQL_PASSWORD="$(openssl rand -hex 24)" VALKEY_PASSWORD="$(openssl rand -hex 24)" bash scripts/secrets-seed.sh staging
POSTGRESQL_PASSWORD="$(openssl rand -hex 24)" VALKEY_PASSWORD="$(openssl rand -hex 24)" bash scripts/secrets-seed.sh production
git add deploy/secrets/*.enc.env .sops.yaml && git commit -m "secrets chiffrés"
```

Nouvelle clé publique (arrivée ou départ) : la brique, puis `sops updatekeys deploy/secrets/*.enc.env`.

## 2. Hôtes

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

## 3. Variables CI

3 variable(s) à déclarer (liste dans `PIPELINE.md`). Le script les déclare avec l'outil de la forge, sans écrire les valeurs dans le dépôt :

```bash
bash scripts/ci-variables.sh --dry-run   # ce qui serait déclaré
bash scripts/ci-variables.sh
```

## 4. Premier déploiement

Pousser sur la branche principale : chaque environnement se déploie dans l'ordre, la production après approbation.

```bash
ssh "<hôte>" "cd /opt/mon-app && docker compose -p mon-app ps"
```

## 5. Sauvegardes

Sur l'hôte, une sauvegarde puis une restauration d'essai (la restauration remplace la base) :

```bash
sudo /opt/mon-app-staging/db-backup.sh /opt/mon-app-staging /var/backups/mon-app-staging
last="$(sudo ls -t /var/backups/mon-app-staging | head -n 1)"
sudo /opt/mon-app-staging/db-restore.sh /opt/mon-app-staging "/var/backups/mon-app-staging/$last" --oui
```

## 6. Poste de développement

Les mêmes bases qu'en production, en version identique, sur le poste (ports liés à 127.0.0.1, mot de passe `dev`). Les fichiers de `dev/db/init/<base>/` sont joués à la création :

```bash
docker compose -f dev/db/compose.yaml up -d --wait
set -a && . dev/db/app.env && set +a   # variables de connexion pour l'application lancée sur le poste
docker compose -f dev/db/compose.yaml --profile outils up -d adminer   # http://127.0.0.1:8081
```

## 7. Entretien

- Sauvegardes : `scripts/db-backup.sh` planifiée par Ansible ; copier les fichiers hors de la machine et tester une restauration (section Sauvegardes).
- Rotation d'un mot de passe : nouvelle valeur par `scripts/secrets-seed.sh`, puis redéploiement.
