# Mise en route — Vault lu par la CI

<!-- Généré par DevOps Builder — à relire avant usage. -->

Les gestes à faire une fois, dans l'ordre, avant le premier pipeline. Chaque section se vérifie avant de passer à la suivante.

## Valeurs à adapter

À poser une fois dans le terminal ; les commandes suivantes les reprennent.

```bash
export REPO="propriétaire/dépôt"   # dépôt de l'application sur la forge
export VAULT_ADDR="https://vault.exemple.fr"
```

## 1. Cluster et plateforme

Sur le nœud serveur : `sudo bash infra/cluster/install-k3s.sh`, puis récupérer le kubeconfig (`/etc/rancher/k3s/k3s.yaml` ou `/etc/rancher/rke2/rke2.yaml`, adresse du serveur à corriger).

## 2. Coffre Vault

Configurer le coffre (moteur KV, politiques, connexion de la CI) ; le script est relançable :

```bash
export VAULT_TOKEN="<jeton racine>"
CI_REPO="$REPO" bash scripts/vault-setup.sh
```

Ensuite, créer un accès d'administration nominatif (OIDC, userpass) et révoquer le jeton racine :

```bash
curl -fsS -X POST -H "X-Vault-Token: $VAULT_TOKEN" "$VAULT_ADDR/v1/auth/token/revoke-self"
```

Vérifier : `curl -s $VAULT_ADDR/v1/sys/health | jq` (`sealed: false`, `initialized: true`).

## 3. Secrets de l'application

Écrire les valeurs dans Vault, une fois par environnement (et à chaque rotation) :

```bash
export VAULT_TOKEN="<jeton d'administration>"
POSTGRESQL_PASSWORD="$(openssl rand -hex 24)" bash scripts/secrets-seed.sh production
```

## 4. Variables CI

2 variable(s) à déclarer (liste dans `PIPELINE.md`). Le script les déclare avec l'outil de la forge, sans écrire les valeurs dans le dépôt :

```bash
bash scripts/ci-variables.sh --dry-run   # ce qui serait déclaré
bash scripts/ci-variables.sh
```

## 5. Premier déploiement

Pousser sur la branche principale : chaque environnement se déploie dans l'ordre.

```bash
kubectl -n boutique rollout status deployment/boutique
kubectl -n boutique get pods
```

## 6. Poste de développement

Les mêmes bases qu'en production, en version identique, sur le poste (ports liés à 127.0.0.1, mot de passe `dev`). Les fichiers de `dev/db/init/<base>/` sont joués à la création :

```bash
docker compose -f dev/db/compose.yaml up -d --wait
set -a && . dev/db/app.env && set +a   # variables de connexion pour l'application lancée sur le poste
docker compose -f dev/db/compose.yaml --profile outils up -d adminer   # http://127.0.0.1:8081
```

## 7. Entretien

- Rotation d'un mot de passe : nouvelle valeur par `scripts/secrets-seed.sh`, puis redéploiement.
