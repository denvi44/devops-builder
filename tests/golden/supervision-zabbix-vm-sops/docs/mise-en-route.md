# Mise en route — Mon projet

<!-- Généré par DevOps Builder — à relire avant usage. -->

Les gestes à faire une fois, dans l'ordre, avant le premier pipeline. Chaque section se vérifie avant de passer à la suivante. Les blocs se collent tels quels dans un terminal (bash ou zsh) ; les remarques sont sous chaque bloc.

## 1. Essai à la main, sans CI

Le chemin le plus court pour voir tourner les outils du projet, avant de brancher la CI : sur un hôte Docker (labo, poste de travail, NAS), copier le dossier du projet puis, depuis ce dossier :

```bash
ZABBIX_DB_PASSWORD="$(openssl rand -hex 24)" sh deploy/secrets.sh deploy/secrets
export COMPOSE_FILE=deploy/docker-compose.yml
docker compose up -d traefik zabbix-server zabbix-web zabbix-agent zabbix-db zabbix-agent-host
docker compose ps
```

La première commande tire les mots de passe au hasard et les écrit dans `deploy/secrets/` (à ne pas partager). Elle ne se lance qu'une fois : relancée, elle changerait les mots de passe alors que les bases gardent les anciens.

`docker compose ps` doit montrer chaque service `running` (ou `healthy`) ; le premier démarrage télécharge les images et peut prendre quelques minutes. Journal d'un service qui ne démarre pas : `docker compose logs --tail 30 <service>`.

Le service de l'application (`mon-app`) attend son image, construite et poussée par la CI : il se lance avec le premier déploiement.

`docker compose` absent (NAS, Unraid, vieux Docker) : télécharger le binaire autonome de Compose à côté du projet, sans rien installer sur le système, puis écrire `bin/docker-compose` à la place de `docker compose`.

```bash
mkdir -p bin && curl -SL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64 -o bin/docker-compose && chmod +x bin/docker-compose
bin/docker-compose version
```

## 2. Secrets de l'application

Une paire de clés age pour le projet. La clé publique va dans la brique SOPS (paramètre « Destinataires age ») : régénérer le projet pour mettre `.sops.yaml` à jour. La clé privée va dans la variable CI `SOPS_AGE_KEY`.

```bash
mkdir -p ~/.config/sops/age
age-keygen -o ~/.config/sops/age/keys.txt
export SOPS_AGE_KEY_FILE=~/.config/sops/age/keys.txt
```

- `age-keygen -o ~/.config/sops/age/keys.txt` : affiche la clé publique age1…

Puis, avec `.sops.yaml` à jour, chiffrer les valeurs de chaque environnement :

```bash
ZABBIX_DB_PASSWORD="$(openssl rand -hex 24)" bash scripts/secrets-seed.sh production
git add deploy/secrets/*.enc.env .sops.yaml && git commit -m "secrets chiffrés"
```

Nouvelle clé publique (arrivée ou départ) : la brique, puis `sops updatekeys deploy/secrets/*.enc.env`.

## 3. Hôtes

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

Noms d'hôte de l'application : chacun pointe (enregistrement DNS A ou AAAA) vers l'hôte de son environnement, joignable depuis Internet sur les ports 80 et 443 ; Traefik y obtient seul le certificat (paramètre « Adresse publique de l'application » de la brique Traefik).

- Production : `mon-app.example.com`

## 4. Variables CI

3 variable(s) à déclarer (liste dans `PIPELINE.md`). Le script les déclare avec l'outil de la forge, sans écrire les valeurs dans le dépôt :

```bash
bash scripts/ci-variables.sh --dry-run
bash scripts/ci-variables.sh
```

- `bash scripts/ci-variables.sh --dry-run` : ce qui serait déclaré

## 5. Premier déploiement

Pousser sur la branche principale : chaque environnement se déploie dans l'ordre.

```bash
ssh "<hôte>" "cd /opt/mon-app && docker compose -p mon-app ps"
```

## 6. Zabbix

L'interface répond sur https://zabbix.example.com une fois le premier déploiement fait ; le serveur crée le schéma de sa base au premier démarrage (une à deux minutes). Le compte **Admin / zabbix** est connu de tous : le changer aussitôt, ici par l'API (ou dans l'interface, Utilisateurs → Admin) :

```bash
ZBX="https://zabbix.example.com/api_jsonrpc.php"
ok='.result // error(.error | tostring)'
ZABBIX_ADMIN_PASSWORD="$(openssl rand -hex 16)"; echo "$ZABBIX_ADMIN_PASSWORD"
tok="$(curl -fsS -H 'Content-Type: application/json-rpc' -d '{"jsonrpc":"2.0","method":"user.login","params":{"username":"Admin","password":"zabbix"},"id":1}' "$ZBX" | jq -er "$ok")"
curl -fsS -H 'Content-Type: application/json-rpc' -H "Authorization: Bearer $tok" -d "{\"jsonrpc\":\"2.0\",\"method\":\"user.update\",\"params\":{\"userid\":\"1\",\"current_passwd\":\"zabbix\",\"passwd\":\"$ZABBIX_ADMIN_PASSWORD\"},\"id\":2}" "$ZBX" | jq -e "$ok"
```

- `ok='.result // error(.error | tostring)'` : réponse de l'API, ou son message d'erreur
- `ZABBIX_ADMIN_PASSWORD="$(openssl rand -hex 16)";…` : à ranger

Vérifier que l'agent fourni répond : l'hôte « Zabbix server » (le serveur lui-même) doit être disponible (`available` = 1 sur son interface ; ses contrôles par défaut sont passifs, `active_available` reste à 0) :

```bash
tok="$(curl -fsS -H 'Content-Type: application/json-rpc' -d '{"jsonrpc":"2.0","method":"user.login","params":{"username":"Admin","password":"'"$ZABBIX_ADMIN_PASSWORD"'"},"id":1}' "$ZBX" | jq -er "$ok")"
curl -fsS -H 'Content-Type: application/json-rpc' -H "Authorization: Bearer $tok" -d '{"jsonrpc":"2.0","method":"host.get","params":{"output":["host","active_available"],"selectInterfaces":["available"],"filter":{"host":["Zabbix server"]}},"id":3}' "$ZBX" | jq -c '.result[0]'
```

Déclarer l'hôte Docker : le service `zabbix-agent-host` mesure la machine (processeur, mémoire, disques, visibles sous `/hostfs`) et ses conteneurs. Zabbix le connaît une fois l'hôte « Docker host » créé avec les modèles Linux et Docker :

```bash
zbx() { curl -fsS -H 'Content-Type: application/json-rpc' -H "Authorization: Bearer $tok" -d "$1" "$ZBX"; }
gid="$(zbx '{"jsonrpc":"2.0","method":"hostgroup.get","params":{"filter":{"name":["Linux servers"]}},"id":4}' | jq -er '.result[0].groupid')"
tpl="$(zbx '{"jsonrpc":"2.0","method":"template.get","params":{"filter":{"host":["Linux by Zabbix agent","Docker by Zabbix agent 2"]},"output":["templateid"]},"id":5}' | jq -ec '[.result[] | {templateid}] | select(length == 2)')"
zbx "$(jq -n --arg gid "$gid" --argjson tpl "$tpl" '{jsonrpc:"2.0",method:"host.create",params:{host:"Docker host",groups:[{groupid:$gid}],templates:$tpl,interfaces:[{type:1,main:1,useip:0,ip:"",dns:"host.docker.internal",port:"10050"}]},id:6}')" | jq -e "$ok"
```

Une à deux minutes plus tard, son interface doit être disponible (`available` = 1) ; les conteneurs apparaissent ensuite dans Surveillance → Hôtes → Dernières données :

```bash
zbx '{"jsonrpc":"2.0","method":"host.get","params":{"output":["host"],"selectInterfaces":["available","error"],"filter":{"host":["Docker host"]}},"id":7}' | jq -c '.result[0]'
```

S'il reste indisponible, un pare-feu de l'hôte bloque sans doute le port 10050 depuis les réseaux de Docker (172.16.0.0/12). Le modèle Docker ne découvre que les conteneurs en marche : un conteneur arrêté sort de la supervision au lieu de lever une alerte, sauf à passer la règle « Containers discovery » sur `docker.containers.discovery[true]`.

Les autres machines se supervisent avec un agent 2 chacune (paquet `zabbix-agent2` du dépôt officiel, https://www.zabbix.com/download), `Server=` et `ServerActive=` pointant vers cet hôte Docker (port 10051 publié), puis un hôte déclaré dans l'interface.

## 7. Sauvegardes

Sur l'hôte, une sauvegarde puis une restauration d'essai (la restauration remplace la base) :

```bash
sudo /opt/mon-app/db-backup.sh /opt/mon-app /var/backups/mon-app
last="$(sudo ls -t /var/backups/mon-app | head -n 1)"
sudo /opt/mon-app/db-restore.sh /opt/mon-app "/var/backups/mon-app/$last" --oui
```

## 8. Entretien

- Sauvegardes : `scripts/db-backup.sh` planifiée par Ansible ; copier les fichiers hors de la machine et tester une restauration (section Sauvegardes).
- Rotation d'un mot de passe : nouvelle valeur par `scripts/secrets-seed.sh`, puis redéploiement.
