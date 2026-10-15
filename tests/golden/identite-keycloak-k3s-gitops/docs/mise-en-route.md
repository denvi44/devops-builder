# Mise en route — Mon projet

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

## 2. Keycloak

Keycloak démarre avec un administrateur temporaire, à remplacer par un compte nominatif dans le realm master (Console › Users), puis supprimer :

```bash
kubectl -n keycloak wait keycloak/keycloak --for=condition=Ready --timeout=300s
kubectl -n keycloak get secret keycloak-initial-admin -o jsonpath='{.data.username}' | base64 -d; echo
kubectl -n keycloak get secret keycloak-initial-admin -o jsonpath='{.data.password}' | base64 -d; echo
```

Décrire le realm « mon-app » (groupes admins et developpeurs, clients de l'application et des outils) :

```bash
export KEYCLOAK_USER="<administrateur>" KEYCLOAK_PASSWORD="<mot de passe>"
tofu -chdir=infra/keycloak init
tofu -chdir=infra/keycloak apply
curl -fsS https://auth.boutique.fr/realms/mon-app/.well-known/openid-configuration | jq -r .issuer
```

Ajouter les personnes au groupe « admins » (droits d'administration des outils) ou « developpeurs ».

Outils branchés : OpenBao, Argo CD, Grafana. Vault / OpenBao : relancer `scripts/vault-setup.sh` avec `OIDC_CLIENT_SECRET` pour la connexion des personnes ; Argo CD et Grafana : relancer `platform/install.sh`, qui reprend leurs secrets.

## 3. Coffre OpenBao

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

## 4. External Secrets

Vérifier, après `platform/install.sh` et le premier déploiement :

```bash
kubectl get clustersecretstore mon-app   # READY True
```

## 5. Argo CD

Le dépôt GitOps (https://git.example.com/groupe/gitops.git) contient `charts/mon-app/` tel que généré ici : le dépôt de l'application convient (les commits de la CI portent `[skip ci]`), ou un dépôt dédié où ce dossier est copié. `GITOPS_READ_TOKEN` : jeton en lecture seule sur ce dépôt, distinct de `GITOPS_TOKEN` (écriture, CI).

Argo CD connaît le dépôt par un secret étiqueté, puis les applications sont créées et suivies jusqu'à leur synchronisation :

```bash
kubectl -n argocd create secret generic gitops-repo --from-literal=type=git --from-literal=url="https://git.example.com/groupe/gitops.git" --from-literal=username=ci --from-literal=password="$GITOPS_READ_TOKEN"
kubectl -n argocd label secret gitops-repo argocd.argoproj.io/secret-type=repository
kubectl apply -f deploy/argocd/application.yaml
kubectl -n argocd wait application/mon-app-dev --for=jsonpath='{.status.sync.status}'=Synced --timeout=300s
kubectl -n argocd get applications
```

Ensuite, chaque pipeline met à jour l'étiquette de l'image dans le dépôt GitOps ; Argo CD l'applique à sa prochaine lecture du dépôt (trois minutes au plus).

## 6. Variables CI

2 variable(s) à déclarer (liste dans `PIPELINE.md`). Le script les déclare avec l'outil de la forge, sans écrire les valeurs dans le dépôt :

```bash
bash scripts/ci-variables.sh --dry-run   # ce qui serait déclaré
bash scripts/ci-variables.sh
```

## 7. Premier déploiement

Pousser sur la branche principale : chaque environnement se déploie dans l'ordre, la production après approbation.

```bash
kubectl -n mon-app rollout status deployment/mon-app
kubectl -n mon-app get pods
```

## 8. Entretien

- Coffre : desceller après chaque redémarrage, ou configurer le descellement automatique (transit, KMS du cloud) ; sauvegarder le stockage intégré (`operator raft snapshot save`).
