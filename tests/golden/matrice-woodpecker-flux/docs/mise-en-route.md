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

## 2. Flux

Flux installé sur le cluster, avec l'accès au dépôt GitOps, puis les ressources du projet :

```bash
flux install
flux create secret git gitops --url "https://$GITOPS_REPO" --username ci --password "<jeton>"
# adresse du dépôt et secretRef à reporter dans deploy/flux/gitops.yaml (GitRepository)
kubectl apply -f deploy/flux/gitops.yaml
flux get all -A
```

## 3. Premier déploiement

Pousser sur la branche principale : chaque environnement se déploie dans l'ordre.

```bash
kubectl -n mon-app rollout status deployment/mon-app
kubectl -n mon-app get pods
```
