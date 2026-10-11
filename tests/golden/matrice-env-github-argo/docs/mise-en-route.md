# Mise en route — matrice

<!-- Généré par DevOps Builder — à relire avant usage. -->

Les gestes à faire une fois, dans l'ordre, avant le premier pipeline. Chaque section se vérifie avant de passer à la suivante.

## Valeurs à adapter

À poser une fois dans le terminal ; les commandes suivantes les reprennent.

```bash
export GITOPS_REPO="git.example.com/groupe/gitops.git"   # même valeur que la variable CI
```

## 1. Cluster et plateforme

Sur le nœud serveur : `sudo bash infra/cluster/install-k3s.sh`, puis récupérer le kubeconfig (`/etc/rancher/k3s/k3s.yaml` ou `/etc/rancher/rke2/rke2.yaml`, adresse du serveur à corriger).

Avec le kubeconfig du cluster, une fois :

```bash
kubectl config current-context
bash platform/install.sh
kubectl get pods -A | grep -v Running   # rien ne doit rester en attente
```

## 2. Argo CD

Le dépôt GitOps (variable `GITOPS_REPO`) doit être connu d'Argo CD, puis les applications créées :

```bash
argocd repo add "https://$GITOPS_REPO" --username ci --password "<jeton de lecture>"
# adresse du dépôt GitOps à reporter dans deploy/argocd/application.yaml (repoURL)
kubectl apply -f deploy/argocd/application.yaml
argocd app list
```

## 3. Variables CI

2 variable(s) à déclarer (liste dans `PIPELINE.md`). Le script les déclare avec l'outil de la forge, sans écrire les valeurs dans le dépôt :

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
