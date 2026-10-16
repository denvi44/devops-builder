# Mise en route — Mon projet

<!-- Généré par DevOps Builder — à relire avant usage. -->

Les gestes à faire une fois, dans l'ordre, avant le premier pipeline. Chaque section se vérifie avant de passer à la suivante.

## Valeurs à adapter

À poser une fois dans le terminal ; les commandes suivantes les reprennent.

```bash
export REPO="groupe/projet"   # dépôt de l'application sur la forge
```

## 1. Keycloak

Keycloak démarre avec un administrateur temporaire, à remplacer par un compte nominatif dans le realm master (Console › Users), puis supprimer :

```bash
# administrateur temporaire : admin-temporaire / KEYCLOAK_ADMIN_PASSWORD (deploy/secrets.sh)
ssh "<hôte>" "cd /opt/mon-app && docker compose -p mon-app logs keycloak | tail -n 5"
```

Décrire le realm « mon-app » (groupes admins et developpeurs, clients de l'application et des outils) :

```bash
export KEYCLOAK_USER="<administrateur>" KEYCLOAK_PASSWORD="<mot de passe>"
tofu -chdir=infra/keycloak init
tofu -chdir=infra/keycloak apply
curl -fsS https://auth.boutique.fr/realms/mon-app/.well-known/openid-configuration | jq -r .issuer
```

Ajouter les personnes au groupe « admins » (droits d'administration des outils) ou « developpeurs ».

Outils branchés : Grafana, SonarQube. Grafana : servi par Traefik à son adresse publique, secret par `deploy/secrets.sh`.

## 2. Secrets de l'application

Valeurs dans des variables CI, une par environnement : `scripts/ci-variables.sh` les déclare (section Variables CI). Générer chaque mot de passe avec `openssl rand -hex 24`.

## 3. Hôtes

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

- Production : `mon-app.example.com`

## 4. Variables CI

9 variable(s) à déclarer (liste dans `PIPELINE.md`). Le script les déclare avec l'outil de la forge, sans écrire les valeurs dans le dépôt :

```bash
bash scripts/ci-variables.sh --dry-run   # ce qui serait déclaré
bash scripts/ci-variables.sh
```

## 5. Premier déploiement

Pousser sur la branche principale : chaque environnement se déploie dans l'ordre.

```bash
ssh "<hôte>" "cd /opt/mon-app && docker compose -p mon-app ps"
```

## 6. SonarQube

SonarQube démarre avec le compte **admin / admin**, à changer aussitôt ; il se relie ensuite à Keycloak en SAML (client « sonarqube » du realm), et le groupe « admins » reçoit l'administration :

```bash
SONAR="https://sonarqube.boutique.fr"
IDP="https://auth.boutique.fr/realms/mon-app"
SONAR_ADMIN_PASSWORD="S$(openssl rand -hex 12)!a1"; echo "$SONAR_ADMIN_PASSWORD"   # à ranger
curl -fsS -u admin:admin -X POST "$SONAR/api/users/change_password" -d login=admin -d previousPassword=admin --data-urlencode "password=$SONAR_ADMIN_PASSWORD"
# certificat de signature du realm, lu dans ses métadonnées SAML
cert="$(curl -fsS "$IDP/protocol/saml/descriptor" | grep -o '<ds:X509Certificate>[^<]*' | head -n 1 | cut -d '>' -f 2)"
sonar() { curl -fsS -u "admin:$SONAR_ADMIN_PASSWORD" -X POST "$SONAR/api/$1" "${@:2}"; }
sonar settings/set -d key=sonar.core.serverBaseURL --data-urlencode "value=$SONAR"
sonar settings/set -d key=sonar.auth.saml.applicationId -d value=sonarqube
sonar settings/set -d key=sonar.auth.saml.providerName -d value=Keycloak
sonar settings/set -d key=sonar.auth.saml.providerId --data-urlencode "value=$IDP"
sonar settings/set -d key=sonar.auth.saml.loginUrl --data-urlencode "value=$IDP/protocol/saml"
sonar settings/set -d key=sonar.auth.saml.certificate.secured --data-urlencode "value=$cert"
sonar settings/set -d key=sonar.auth.saml.user.login -d value=login
sonar settings/set -d key=sonar.auth.saml.user.name -d value=name
sonar settings/set -d key=sonar.auth.saml.user.email -d value=email
sonar settings/set -d key=sonar.auth.saml.group.name -d value=groups
sonar settings/set -d key=sonar.auth.saml.enabled -d value=true
sonar user_groups/create -d name=admins >/dev/null
sonar permissions/add_group -d groupName=admins -d permission=admin
curl -fsS -o /dev/null -w "%{redirect_url}\n" "$SONAR/sessions/init/saml?return_to=/"   # adresse de connexion de Keycloak attendue
```

## 7. Sauvegardes

Sur l'hôte, une sauvegarde puis une restauration d'essai (la restauration remplace la base) :

```bash
sudo /opt/mon-app/db-backup.sh /opt/mon-app /var/backups/mon-app
last="$(sudo ls -t /var/backups/mon-app | head -n 1)"
sudo /opt/mon-app/db-restore.sh /opt/mon-app "/var/backups/mon-app/$last" --oui
```

## 8. Entretien

- Sauvegardes : `scripts/db-backup.sh` à planifier sur l'hôte (cron) ; copier les fichiers hors de la machine et tester une restauration (section Sauvegardes).
- Renovate : le job `renovate` tourne dans une planification de pipeline qui porte la variable `RENOVATE=1` (Build › Pipeline schedules, ou par l'API ci-dessous, jeton `api` dans `GITLAB_TOKEN`) ; `RENOVATE_TOKEN` : jeton de projet avec les droits `api` et `write_repository`.

```bash
sid=$(curl -fsS -H "PRIVATE-TOKEN: $GITLAB_TOKEN" -d description=Renovate -d ref=main --data-urlencode "cron=0 4 * * 1-5" "${CI_SERVER_URL:-https://gitlab.com}/api/v4/projects/$(printf %s "$REPO" | jq -sRr @uri)/pipeline_schedules" | jq -r .id)
curl -fsS -H "PRIVATE-TOKEN: $GITLAB_TOKEN" -d key=RENOVATE -d value=1 "${CI_SERVER_URL:-https://gitlab.com}/api/v4/projects/$(printf %s "$REPO" | jq -sRr @uri)/pipeline_schedules/$sid/variables" >/dev/null
```
