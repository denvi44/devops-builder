# Mise en route — Mon projet

<!-- Généré par DevOps Builder — à relire avant usage. -->

Les gestes à faire une fois, dans l'ordre, avant le premier pipeline. Chaque section se vérifie avant de passer à la suivante.

## Valeurs à adapter

À poser une fois dans le terminal ; les commandes suivantes les reprennent.

```bash
export REPO="groupe/projet"   # dépôt de l'application sur la forge
```

## 1. Secrets de l'application

Valeurs dans des variables CI, une par environnement : `scripts/ci-variables.sh` les déclare (section Variables CI). Générer chaque mot de passe avec `openssl rand -hex 24`.

## 2. Hôtes

Sur chaque hôte : un compte `deploy` avec la clé publique de la CI (la clé privée va dans `SSH_PRIVATE_KEY`), membre du groupe docker, Docker et son extension Compose installés.

```bash
ssh-keygen -t ed25519 -N '' -f ci_deploy -C ci-deploy   # sur le poste
sudo useradd -m -s /bin/bash deploy
sudo install -d -m 700 -o deploy -g deploy /home/deploy/.ssh
sudo tee /home/deploy/.ssh/authorized_keys < ci_deploy.pub
sudo usermod -aG docker deploy
```

Empreinte des hôtes dans `SSH_KNOWN_HOSTS` (facultatif, recommandé) : `ssh-keyscan <hôte>`.

Noms d'hôte de l'application : chacun pointe (enregistrement DNS A ou AAAA) vers l'hôte de son environnement, joignable depuis Internet sur les ports 80 et 443 ; Traefik y obtient seul le certificat (paramètre « Adresse publique de l'application » de la brique Traefik).

- Préproduction : `staging.mon-app.example.com`
- Production : `mon-app.example.com`

## 3. Variables CI

9 variable(s) à déclarer (liste dans `PIPELINE.md`). Le script les déclare avec l'outil de la forge, sans écrire les valeurs dans le dépôt :

```bash
bash scripts/ci-variables.sh --dry-run   # ce qui serait déclaré
bash scripts/ci-variables.sh
```

## 4. Premier déploiement

Pousser sur la branche principale : chaque environnement se déploie dans l'ordre, la production après approbation.

```bash
ssh "<hôte>" "cd /opt/mon-app && docker compose -p mon-app ps"
```

## 5. Zabbix

L'interface répond sur https://zabbix.boutique.fr une fois le premier déploiement fait ; le serveur crée le schéma de sa base au premier démarrage (une à deux minutes). Le compte **Admin / zabbix** est connu de tous : le changer aussitôt, ici par l'API (ou dans l'interface, Utilisateurs → Admin) :

```bash
ZBX="https://zabbix.boutique.fr/api_jsonrpc.php"
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
sudo /opt/mon-app-staging/db-backup.sh /opt/mon-app-staging /var/backups/mon-app-staging
last="$(sudo ls -t /var/backups/mon-app-staging | head -n 1)"
sudo /opt/mon-app-staging/db-restore.sh /opt/mon-app-staging "/var/backups/mon-app-staging/$last" --oui
```

## 7. Poste de développement

Les mêmes bases qu'en production, en version identique, sur le poste (ports liés à 127.0.0.1, mot de passe `dev`). Les fichiers de `dev/db/init/<base>/` sont joués à la création :

```bash
docker compose -f dev/db/compose.yaml up -d --wait
set -a && . dev/db/app.env && set +a   # variables de connexion pour l'application lancée sur le poste
docker compose -f dev/db/compose.yaml --profile outils up -d adminer   # http://127.0.0.1:8081
```

## 8. Entretien

- Sauvegardes : `scripts/db-backup.sh` à planifier sur l'hôte (cron) ; copier les fichiers hors de la machine et tester une restauration (section Sauvegardes).
- Renovate : le job `renovate` tourne dans une planification de pipeline qui porte la variable `RENOVATE=1` (Build › Pipeline schedules, ou par l'API ci-dessous, jeton `api` dans `GITLAB_TOKEN`) ; `RENOVATE_TOKEN` : jeton de projet avec les droits `api` et `write_repository`.

```bash
sid=$(curl -fsS -H "PRIVATE-TOKEN: $GITLAB_TOKEN" -d description=Renovate -d ref=main --data-urlencode "cron=0 4 * * 1-5" "${CI_SERVER_URL:-https://gitlab.com}/api/v4/projects/$(printf %s "$REPO" | jq -sRr @uri)/pipeline_schedules" | jq -r .id)
curl -fsS -H "PRIVATE-TOKEN: $GITLAB_TOKEN" -d key=RENOVATE -d value=1 "${CI_SERVER_URL:-https://gitlab.com}/api/v4/projects/$(printf %s "$REPO" | jq -sRr @uri)/pipeline_schedules/$sid/variables" >/dev/null
```
