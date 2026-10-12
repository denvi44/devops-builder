# Mise en route — Mon projet

<!-- Généré par DevOps Builder — à relire avant usage. -->

Les gestes à faire une fois, dans l'ordre, avant le premier pipeline. Chaque section se vérifie avant de passer à la suivante.

## Valeurs à adapter

À poser une fois dans le terminal ; les commandes suivantes les reprennent.

```bash
export VAULT_ADDR="http://127.0.0.1:8200"   # par kubectl port-forward (section du coffre)
```

## 1. Cluster et plateforme

Sur le nœud serveur : `sudo bash infra/cluster/install-k3s.sh`, puis récupérer le kubeconfig (`/etc/rancher/k3s/k3s.yaml` ou `/etc/rancher/rke2/rke2.yaml`, adresse du serveur à corriger).

Avec le kubeconfig du cluster, une fois :

```bash
kubectl config current-context
bash platform/install.sh
kubectl get pods -A | grep -v Running   # rien ne doit rester en attente
```

## 2. Coffre OpenBao

Initialiser puis desceller le serveur (une fois, puis descellement à chaque redémarrage) :

```bash
kubectl -n openbao exec -ti openbao-0 -- bao operator init -key-shares=5 -key-threshold=3   # clés et jeton racine : hors de l'hôte
kubectl -n openbao exec -ti openbao-0 -- bao operator unseal   # trois fois, trois clés différentes ; après chaque redémarrage
kubectl -n openbao exec -ti openbao-0 -- bao status
```

Joindre l'API du coffre depuis le poste :

```bash
kubectl -n openbao port-forward svc/openbao 8200:8200 &
```

Configurer le coffre (moteur KV, politiques, connexion d'External Secrets) ; le script est relançable :

```bash
export VAULT_TOKEN="<jeton racine>"
bash scripts/vault-setup.sh
```

Ensuite, créer un accès d'administration nominatif (OIDC, userpass) et révoquer le jeton racine :

```bash
curl -fsS -X POST -H "X-Vault-Token: $VAULT_TOKEN" "$VAULT_ADDR/v1/auth/token/revoke-self"
```

Vérifier : `curl -s $VAULT_ADDR/v1/sys/health | jq` (`sealed: false`, `initialized: true`).

## 3. Secrets de l'application

Écrire les valeurs dans OpenBao, une fois par environnement (et à chaque rotation) :

```bash
export VAULT_TOKEN="<jeton d'administration>"
MYSQL_PASSWORD="$(openssl rand -hex 24)" bash scripts/secrets-seed.sh dev
MYSQL_PASSWORD="$(openssl rand -hex 24)" bash scripts/secrets-seed.sh staging
MYSQL_PASSWORD="$(openssl rand -hex 24)" bash scripts/secrets-seed.sh production
```

## 4. External Secrets

Vérifier, après `platform/install.sh` et le premier déploiement :

```bash
kubectl get clustersecretstore mon-app   # READY True
kubectl -n mon-app get externalsecret   # STATUS SecretSynced
```

## 5. Variables CI

4 variable(s) à déclarer (liste dans `PIPELINE.md`). Le script les déclare avec l'outil de la forge, sans écrire les valeurs dans le dépôt :

```bash
bash scripts/ci-variables.sh --dry-run   # ce qui serait déclaré
bash scripts/ci-variables.sh
```

## 6. Premier déploiement

Pousser sur la branche principale : chaque environnement se déploie dans l'ordre, la production après approbation.

```bash
kubectl -n mon-app rollout status deployment/mon-app
kubectl -n mon-app get pods
```

## 7. Poste de développement

Les mêmes bases qu'en production, en version identique, sur le poste (ports liés à 127.0.0.1, mot de passe `dev`). Les fichiers de `dev/db/init/<base>/` sont joués à la création :

```bash
docker compose -f dev/db/compose.yaml up -d --wait
set -a && . dev/db/app.env && set +a   # variables de connexion pour l'application lancée sur le poste
docker compose -f dev/db/compose.yaml --profile outils up -d adminer   # http://127.0.0.1:8081
```

## 8. Entretien

- Rotation d'un mot de passe : nouvelle valeur par `scripts/secrets-seed.sh`, puis redéploiement ; External Secrets relit le coffre toutes les heures.
- Coffre : desceller après chaque redémarrage, ou configurer le descellement automatique (transit, KMS du cloud) ; sauvegarder le stockage intégré (`operator raft snapshot save`).
- Renovate : job planifié (quotidien) avec l'image renovate/renovate et `RENOVATE_TOKEN`.
