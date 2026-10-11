# Mise en route — Mon projet

<!-- Généré par DevOps Builder — à relire avant usage. -->

Les gestes à faire une fois, dans l'ordre, avant le premier pipeline. Chaque section se vérifie avant de passer à la suivante.

## Valeurs à adapter

À poser une fois dans le terminal ; les commandes suivantes les reprennent.

```bash
export REPO="groupe/projet"   # dépôt de l'application sur la forge
export VAULT_ADDR="https://coffre.exemple.fr"
```

## 1. Coffre OpenBao

Configurer le coffre (moteur KV, politiques, connexion de la CI) ; le script est relançable :

```bash
export VAULT_TOKEN="<jeton racine>"
CI_REPO="$REPO" bash scripts/vault-setup.sh
# GitLab autohébergé : CI_ISSUER=https://gitlab.example.com
```

Ensuite, créer un accès d'administration nominatif (OIDC, userpass) et révoquer le jeton racine :

```bash
curl -fsS -X POST -H "X-Vault-Token: $VAULT_TOKEN" "$VAULT_ADDR/v1/auth/token/revoke-self"
```

Vérifier : `curl -s $VAULT_ADDR/v1/sys/health | jq` (`sealed: false`, `initialized: true`).

## 2. Secrets de l'application

Écrire les valeurs dans OpenBao, une fois par environnement (et à chaque rotation) :

```bash
export VAULT_TOKEN="<jeton d'administration>"
POSTGRESQL_PASSWORD="$(openssl rand -hex 24)" bash scripts/secrets-seed.sh staging
POSTGRESQL_PASSWORD="$(openssl rand -hex 24)" bash scripts/secrets-seed.sh production
```

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

## 4. Variables CI

6 variable(s) à déclarer (liste dans `PIPELINE.md`). Le script les déclare avec l'outil de la forge, sans écrire les valeurs dans le dépôt :

```bash
bash scripts/ci-variables.sh --dry-run   # ce qui serait déclaré
bash scripts/ci-variables.sh
```

## 5. Premier déploiement

Pousser sur la branche principale : chaque environnement se déploie dans l'ordre, la production après approbation.

```bash
ssh "<hôte>" "cd /opt/mon-app && docker compose -p mon-app ps"
```

## 6. Entretien

- Sauvegardes : `scripts/db-backup.sh` à planifier sur l'hôte (cron) ; copier les fichiers hors de la machine et tester une restauration.
- Rotation d'un mot de passe : nouvelle valeur par `scripts/secrets-seed.sh`, puis redéploiement.
- Renovate : job planifié (quotidien) avec l'image renovate/renovate et `RENOVATE_TOKEN`.
