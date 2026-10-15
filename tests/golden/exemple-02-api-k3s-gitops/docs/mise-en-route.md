# Mise en route — API sur k3s en GitOps

<!-- Généré par DevOps Builder — à relire avant usage. -->

Les gestes à faire une fois, dans l'ordre, avant le premier pipeline. Chaque section se vérifie avant de passer à la suivante.

## Valeurs à adapter

À poser une fois dans le terminal ; les commandes suivantes les reprennent.

```bash
read -rsp "Jeton de lecture du dépôt GitOps : " GITOPS_READ_TOKEN; echo; export GITOPS_READ_TOKEN
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

## 3. External Secrets

Vérifier, après `platform/install.sh` et le premier déploiement :

```bash
kubectl get clustersecretstore api   # READY True
```

## 4. Argo CD

Le dépôt GitOps (https://git.example.com/groupe/gitops.git) contient `charts/api/` tel que généré ici : le dépôt de l'application convient (les commits de la CI portent `[skip ci]`), ou un dépôt dédié où ce dossier est copié. `GITOPS_READ_TOKEN` : jeton en lecture seule sur ce dépôt, distinct de `GITOPS_TOKEN` (écriture, CI).

Argo CD connaît le dépôt par un secret étiqueté, puis les applications sont créées et suivies jusqu'à leur synchronisation :

```bash
kubectl -n argocd create secret generic gitops-repo --from-literal=type=git --from-literal=url="https://git.example.com/groupe/gitops.git" --from-literal=username=ci --from-literal=password="$GITOPS_READ_TOKEN"
kubectl -n argocd label secret gitops-repo argocd.argoproj.io/secret-type=repository
kubectl apply -f deploy/argocd/application.yaml
kubectl -n argocd wait application/api-dev --for=jsonpath='{.status.sync.status}'=Synced --timeout=600s
kubectl -n argocd get applications
```

Ensuite, chaque pipeline met à jour l'étiquette de l'image dans le dépôt GitOps ; Argo CD l'applique à sa prochaine lecture du dépôt (trois minutes au plus).

## 5. Variables CI

2 variable(s) à déclarer (liste dans `PIPELINE.md`). Le script les déclare avec l'outil de la forge, sans écrire les valeurs dans le dépôt :

```bash
bash scripts/ci-variables.sh --dry-run   # ce qui serait déclaré
bash scripts/ci-variables.sh
```

## 6. Premier déploiement

Pousser sur la branche principale : chaque environnement se déploie dans l'ordre, la production après approbation.

```bash
kubectl -n api rollout status deployment/api
kubectl -n api get pods
```

## 7. Entretien

- Coffre : desceller après chaque redémarrage, ou configurer le descellement automatique (transit, KMS du cloud) ; sauvegarder le stockage intégré (`operator raft snapshot save`).
