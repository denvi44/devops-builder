# Mise en route — matrice

<!-- Généré par DevOps Builder — à relire avant usage. -->

Les gestes à faire une fois, dans l'ordre, avant le premier pipeline. Chaque section se vérifie avant de passer à la suivante.

## Valeurs à adapter

À poser une fois dans le terminal ; les commandes suivantes les reprennent.

```bash
read -rsp "Jeton de lecture du dépôt GitOps : " GITOPS_READ_TOKEN; echo; export GITOPS_READ_TOKEN
```

## 1. Cluster et plateforme

Sur le nœud serveur : `sudo bash infra/cluster/install-rke2.sh`, puis récupérer le kubeconfig (`/etc/rancher/k3s/k3s.yaml` ou `/etc/rancher/rke2/rke2.yaml`, adresse du serveur à corriger).

Avec le kubeconfig du cluster, une fois :

```bash
kubectl config current-context
bash platform/install.sh
kubectl get pods -A | grep -v Running   # rien ne doit rester en attente
```

## 2. Flux

Le dépôt GitOps (https://git.example.com/groupe/gitops.git) contient `deploy/kustomize/` tel que généré ici : le dépôt de l'application convient (les commits de la CI portent `[skip ci]`), ou un dépôt dédié où ce dossier est copié. `GITOPS_READ_TOKEN` : jeton en lecture seule sur ce dépôt, distinct de `GITOPS_TOKEN` (écriture, CI).

Flux installé sur le cluster, avec l'accès au dépôt GitOps, puis les ressources du projet :

```bash
flux install
flux create secret git gitops --url "https://git.example.com/groupe/gitops.git" --username ci --password "$GITOPS_READ_TOKEN"
kubectl apply -f deploy/flux/gitops.yaml
flux get all -A
```

## 3. Premier déploiement

Pousser sur la branche principale : chaque environnement se déploie dans l'ordre, la production après approbation.

```bash
kubectl -n mon-app rollout status deployment/mon-app
kubectl -n mon-app get pods
```
