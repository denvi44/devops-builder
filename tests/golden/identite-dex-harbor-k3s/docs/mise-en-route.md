# Mise en route — Mon projet

<!-- Généré par DevOps Builder — à relire avant usage. -->

Les gestes à faire une fois, dans l'ordre, avant le premier pipeline. Chaque section se vérifie avant de passer à la suivante.

## 1. Cluster et plateforme

Sur le nœud serveur : `sudo bash infra/cluster/install-k3s.sh`, puis récupérer le kubeconfig (`/etc/rancher/k3s/k3s.yaml` ou `/etc/rancher/rke2/rke2.yaml`, adresse du serveur à corriger).

Avec le kubeconfig du cluster, une fois :

```bash
kubectl config current-context
bash platform/install.sh
kubectl get pods -A | grep -v Running   # rien ne doit rester en attente
```

## 2. Dex

Dex délègue la connexion à GitHub (Settings › Developer settings › OAuth Apps) : y créer une application OAuth avec l'adresse de retour `https://dex.boutique.fr/callback`, puis :

```bash
kubectl create namespace dex --dry-run=client -o yaml | kubectl apply -f -
kubectl -n dex create secret generic dex-secrets --from-literal=DEX_CONNECTOR_ID="<id>" --from-literal=DEX_CONNECTOR_SECRET="<secret>" --from-literal=GRAFANA_OIDC_SECRET="$(openssl rand -hex 24)" --from-literal=HARBOR_OIDC_SECRET="$(openssl rand -hex 24)"
```

Vérifier : `curl -fsS https://dex.boutique.fr/.well-known/openid-configuration | jq -r .issuer`.

Outils branchés : Grafana, Harbor. Grafana et Harbor : relancer `platform/install.sh`, qui reprend leurs secrets (Harbor passe en connexion OIDC, groupe « admins » administrateur).

SonarQube Community ne parle ni OIDC ni à Dex : brancher son authentification GitHub ou GitLab intégrée (Administration › Authentification), avec une application OAuth de la forge.

## 3. Variables CI

6 variable(s) à déclarer (liste dans `PIPELINE.md`). Le script les déclare avec l'outil de la forge, sans écrire les valeurs dans le dépôt :

```bash
bash scripts/ci-variables.sh --dry-run   # ce qui serait déclaré
bash scripts/ci-variables.sh
```

## 4. Premier déploiement

Pousser sur la branche principale : chaque environnement se déploie dans l'ordre, la production après approbation.

```bash
kubectl -n mon-app rollout status deployment/mon-app
kubectl -n mon-app get pods
```
