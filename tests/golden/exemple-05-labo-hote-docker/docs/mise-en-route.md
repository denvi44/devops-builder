# Mise en route — Labo DevOps sur hôte Docker

<!-- Généré par DevOps Builder — à relire avant usage. -->

Les gestes à faire une fois, dans l'ordre, pour démarrer la plateforme. Chaque section se vérifie avant de passer à la suivante. Les blocs se collent tels quels dans un terminal (bash ou zsh) ; les remarques sont sous chaque bloc.

## Valeurs à adapter

À poser une fois dans le terminal ; les commandes suivantes les reprennent.

```bash
export HOTE="192.168.1.10"
```

- `export HOTE="192.168.1.10"` : adresse de l'hôte Docker (nom ou IP)

## 1. Démarrer la plateforme

Sur l'hôte Docker (Docker installé), copier le dossier du projet puis, depuis ce dossier :

```bash
ZABBIX_DB_PASSWORD="$(openssl rand -hex 24)" sh deploy/secrets.sh deploy/secrets
export COMPOSE_FILE=deploy/docker-compose.yml
docker compose up -d
docker compose ps
```

La première commande tire les mots de passe au hasard et les écrit dans `deploy/secrets/` (à ne pas partager). Elle ne se lance qu'une fois : relancée, elle changerait les mots de passe alors que les bases gardent les anciens.

`docker compose ps` doit montrer chaque service `running` (ou `healthy`) ; le premier démarrage télécharge les images et peut prendre quelques minutes. Journal d'un service qui ne démarre pas : `docker compose logs --tail 30 <service>`.

Les interfaces répondent ensuite ici :

- Prometheus (interface et API) : `http://$HOTE:9090`
- Grafana (interface web) : `http://$HOTE:3000`
- Gitea (interface web) : `http://$HOTE:3001`
- Zabbix (interface web) : `http://$HOTE:8080`

`docker compose` absent (NAS, Unraid, vieux Docker) : télécharger le binaire autonome de Compose à côté du projet, sans rien installer sur le système, puis écrire `bin/docker-compose` à la place de `docker compose`.

```bash
mkdir -p bin && curl -SL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64 -o bin/docker-compose && chmod +x bin/docker-compose
bin/docker-compose version
```

Arrêter la plateforme sans perdre ses données (elles restent dans les volumes Docker) :

```bash
docker compose down
```

## 2. Zabbix

L'interface répond sur http://<hôte>:8080 une fois le premier déploiement fait ; le serveur crée le schéma de sa base au premier démarrage (une à deux minutes). Le compte **Admin / zabbix** est connu de tous : le changer aussitôt, ici par l'API (ou dans l'interface, Utilisateurs → Admin) :

```bash
ZBX="http://$HOTE:8080/api_jsonrpc.php"
ok='.result // error(.error | tostring)'
ZABBIX_ADMIN_PASSWORD="$(openssl rand -hex 16)"; echo "$ZABBIX_ADMIN_PASSWORD"
tok="$(curl -fsS -H 'Content-Type: application/json-rpc' -d '{"jsonrpc":"2.0","method":"user.login","params":{"username":"Admin","password":"zabbix"},"id":1}' "$ZBX" | jq -er "$ok")"
curl -fsS -H 'Content-Type: application/json-rpc' -H "Authorization: Bearer $tok" -d "{\"jsonrpc\":\"2.0\",\"method\":\"user.update\",\"params\":{\"userid\":\"1\",\"current_passwd\":\"zabbix\",\"passwd\":\"$ZABBIX_ADMIN_PASSWORD\"},\"id\":2}" "$ZBX" | jq -e "$ok"
```

- `ok='.result // error(.error | tostring)'` : réponse de l'API, ou son message d'erreur
- `ZABBIX_ADMIN_PASSWORD="$(openssl rand -hex 16)"; echo "$ZABBIX_ADMIN_PAS…` : à ranger

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

## 3. Sauvegardes

Depuis le dossier du projet, une sauvegarde puis une restauration d'essai (la restauration remplace la base) :

```bash
export COMPOSE_PROJECT_NAME=labo-devops-sur-hote-docker
sh scripts/db-backup.sh "$PWD/deploy" "$PWD/sauvegardes"
last="$(ls -t sauvegardes | head -n 1)"
sh scripts/db-restore.sh "$PWD/deploy" "$PWD/sauvegardes/$last" --oui
```

## 4. Entretien

- Sauvegardes : `scripts/db-backup.sh` à planifier sur l'hôte (cron) ; copier les fichiers hors de la machine et tester une restauration (section Sauvegardes).
