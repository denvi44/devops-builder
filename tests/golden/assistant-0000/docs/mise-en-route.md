# Mise en route — Mon projet

<!-- Généré par DevOps Builder — à relire avant usage. -->

Les gestes à faire une fois, dans l'ordre, avant le premier pipeline. Chaque section se vérifie avant de passer à la suivante.

## Valeurs à adapter

À poser une fois dans le terminal ; les commandes suivantes les reprennent.

```bash
export REPO="groupe/projet"   # dépôt de l'application sur la forge
```

## 1. Hôtes

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

## 2. Variables CI

6 variable(s) à déclarer (liste dans `PIPELINE.md`). Le script les déclare avec l'outil de la forge, sans écrire les valeurs dans le dépôt :

```bash
bash scripts/ci-variables.sh --dry-run   # ce qui serait déclaré
bash scripts/ci-variables.sh
```

## 3. Premier déploiement

Pousser sur la branche principale : chaque environnement se déploie dans l'ordre.

```bash
ssh "<hôte>" "cd /opt/mon-app && docker compose -p mon-app ps"
```

## 4. Entretien

- Renovate : le job `renovate` tourne dans une planification de pipeline qui porte la variable `RENOVATE=1` (Build › Pipeline schedules, ou par l'API ci-dessous, jeton `api` dans `GITLAB_TOKEN`) ; `RENOVATE_TOKEN` : jeton de projet avec les droits `api` et `write_repository`.

```bash
sid=$(curl -fsS -H "PRIVATE-TOKEN: $GITLAB_TOKEN" -d description=Renovate -d ref=main --data-urlencode "cron=0 4 * * 1-5" "${CI_SERVER_URL:-https://gitlab.com}/api/v4/projects/$(printf %s "$REPO" | jq -sRr @uri)/pipeline_schedules" | jq -r .id)
curl -fsS -H "PRIVATE-TOKEN: $GITLAB_TOKEN" -d key=RENOVATE -d value=1 "${CI_SERVER_URL:-https://gitlab.com}/api/v4/projects/$(printf %s "$REPO" | jq -sRr @uri)/pipeline_schedules/$sid/variables" >/dev/null
```
