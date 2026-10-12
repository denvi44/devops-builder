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

## 2. Variables CI

4 variable(s) à déclarer (liste dans `PIPELINE.md`). Le script les déclare avec l'outil de la forge, sans écrire les valeurs dans le dépôt :

```bash
bash scripts/ci-variables.sh --dry-run   # ce qui serait déclaré
bash scripts/ci-variables.sh
```

## 3. Premier déploiement

Pousser sur la branche principale : chaque environnement se déploie dans l'ordre, la production après approbation.

```bash
kubectl -n mon-app rollout status deployment/mon-app
kubectl -n mon-app get pods
```

## 4. Sauvegardes

CloudNativePG sauvegarde vers s3://boutique-sauvegardes (plugin Barman Cloud) avec les identifiants du Secret `mon-app-backup-credentials`, à créer dans chaque espace de noms :

```bash
kubectl -n mon-app-dev create secret generic mon-app-backup-credentials --from-literal=ACCESS_KEY_ID="<clé>" --from-literal=ACCESS_SECRET_KEY="<secret>"
kubectl -n mon-app-staging create secret generic mon-app-backup-credentials --from-literal=ACCESS_KEY_ID="<clé>" --from-literal=ACCESS_SECRET_KEY="<secret>"
kubectl -n mon-app create secret generic mon-app-backup-credentials --from-literal=ACCESS_KEY_ID="<clé>" --from-literal=ACCESS_SECRET_KEY="<secret>"
```

Vérifier l'archivage et la sauvegarde quotidienne, puis restaurer pour essai dans un autre Cluster (`bootstrap.recovery`, voir la documentation du plugin) :

```bash
kubectl -n mon-app get cluster mon-app-pg -o jsonpath='{.status.conditions}'   # ContinuousArchiving
kubectl -n mon-app get scheduledbackup,backup
```

## 5. Poste de développement

Les mêmes bases qu'en production, en version identique, sur le poste (ports liés à 127.0.0.1, mot de passe `dev`). Les fichiers de `dev/db/init/<base>/` sont joués à la création :

```bash
docker compose -f dev/db/compose.yaml up -d --wait
set -a && . dev/db/app.env && set +a   # variables de connexion pour l'application lancée sur le poste
docker compose -f dev/db/compose.yaml --profile outils up -d adminer   # http://127.0.0.1:8081
```

## 6. Entretien

- Renovate : job planifié (quotidien) avec l'image renovate/renovate et `RENOVATE_TOKEN`.
