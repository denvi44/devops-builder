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

3 variable(s) à déclarer (liste dans `PIPELINE.md`). Le script les déclare avec l'outil de la forge, sans écrire les valeurs dans le dépôt :

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

## 4. Analyse dynamique (ZAP)

Le job ZAP analyse l'application juste après son déploiement : l'adresse `ZAP_TARGET_URL` doit répondre depuis les machines de la CI (une préproduction réservée au réseau interne demande un runner dans ce réseau). Vérifier, puis lancer la même analyse depuis le poste pour voir le rapport avant le pipeline (le dossier `.zap` doit être inscriptible par l'utilisateur de l'image) :

```bash
curl -fsS -o /dev/null -w '%{http_code}\n' "https://dev.boutique.fr"   # 200 (ou 30x) attendu
chmod a+w .zap
docker run --rm -v "$PWD/.zap:/zap/wrk:rw" ghcr.io/zaproxy/zaproxy:2.17.0 zap-full-scan.py -t "https://dev.boutique.fr" -c rules.tsv -r zap-report.html -I; echo "code $?"   # 0 : rien de bloquant, 1 : règle FAIL, 3 : erreur
```

Rapport : `.zap/zap-report.html` (à ne pas committer) ; dans la CI, artefact du job. Une alerte sans objet se passe à `IGNORE` dans `.zap/rules.tsv`, avec la raison en commentaire ; une alerte à corriger sans attendre passe à `FAIL`.
