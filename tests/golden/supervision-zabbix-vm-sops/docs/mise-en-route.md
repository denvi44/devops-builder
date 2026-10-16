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
ZABBIX_DB_PASSWORD="$(openssl rand -hex 24)" bash scripts/secrets-seed.sh production
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
ANSIBLE_CONFIG=ansible/ansible.cfg ansible-playbook -i ansible/inventory.ini ansible/site.yml
```

Noms d'hôte de l'application : chacun pointe (enregistrement DNS A ou AAAA) vers l'hôte de son environnement, joignable depuis Internet sur les ports 80 et 443 ; Traefik y obtient seul le certificat (paramètre « Adresse publique de l'application » de la brique Traefik).

- Production : `mon-app.example.com`

## 3. Variables CI

3 variable(s) à déclarer (liste dans `PIPELINE.md`). Le script les déclare avec l'outil de la forge, sans écrire les valeurs dans le dépôt :

```bash
bash scripts/ci-variables.sh --dry-run   # ce qui serait déclaré
bash scripts/ci-variables.sh
```

## 4. Premier déploiement

Pousser sur la branche principale : chaque environnement se déploie dans l'ordre.

```bash
ssh "<hôte>" "cd /opt/mon-app && docker compose -p mon-app ps"
```

## 5. Zabbix

L'interface répond sur https://zabbix.example.com une fois le premier déploiement fait ; le serveur crée le schéma de sa base au premier démarrage (une à deux minutes). Le compte **Admin / zabbix** est connu de tous : le changer aussitôt, ici par l'API (ou dans l'interface, Utilisateurs → Admin) :

```bash
ZBX="https://zabbix.example.com/api_jsonrpc.php"
ok='.result // error(.error | tostring)'   # réponse de l'API, ou son message d'erreur
ZABBIX_ADMIN_PASSWORD="$(openssl rand -hex 16)"; echo "$ZABBIX_ADMIN_PASSWORD"   # à ranger
tok="$(curl -fsS -H 'Content-Type: application/json-rpc' -d '{"jsonrpc":"2.0","method":"user.login","params":{"username":"Admin","password":"zabbix"},"id":1}' "$ZBX" | jq -er "$ok")"
curl -fsS -H 'Content-Type: application/json-rpc' -H "Authorization: Bearer $tok" -d "{\"jsonrpc\":\"2.0\",\"method\":\"user.update\",\"params\":{\"userid\":\"1\",\"current_passwd\":\"zabbix\",\"passwd\":\"$ZABBIX_ADMIN_PASSWORD\"},\"id\":2}" "$ZBX" | jq -e "$ok"
```

Vérifier que l'agent fourni répond : l'hôte « Zabbix server » (le serveur lui-même) doit être disponible (`available` = 1 sur son interface ; ses contrôles par défaut sont passifs, `active_available` reste à 0) :

```bash
tok="$(curl -fsS -H 'Content-Type: application/json-rpc' -d '{"jsonrpc":"2.0","method":"user.login","params":{"username":"Admin","password":"'"$ZABBIX_ADMIN_PASSWORD"'"},"id":1}' "$ZBX" | jq -er "$ok")"
curl -fsS -H 'Content-Type: application/json-rpc' -H "Authorization: Bearer $tok" -d '{"jsonrpc":"2.0","method":"host.get","params":{"output":["host","active_available"],"selectInterfaces":["available"],"filter":{"host":["Zabbix server"]}},"id":3}' "$ZBX" | jq -c '.result[0]'
```

Les autres machines se supervisent avec un agent 2 chacune (paquet `zabbix-agent2` du dépôt officiel, https://www.zabbix.com/download), `Server=` pointant vers cet hôte Docker, puis un hôte déclaré dans l'interface.

## 6. Sauvegardes

Sur l'hôte, une sauvegarde puis une restauration d'essai (la restauration remplace la base) :

```bash
sudo /opt/mon-app/db-backup.sh /opt/mon-app /var/backups/mon-app
last="$(sudo ls -t /var/backups/mon-app | head -n 1)"
sudo /opt/mon-app/db-restore.sh /opt/mon-app "/var/backups/mon-app/$last" --oui
```

## 7. Entretien

- Sauvegardes : `scripts/db-backup.sh` planifiée par Ansible ; copier les fichiers hors de la machine et tester une restauration (section Sauvegardes).
- Rotation d'un mot de passe : nouvelle valeur par `scripts/secrets-seed.sh`, puis redéploiement.
