# Mise en route — Mon projet

<!-- Généré par DevOps Builder — à relire avant usage. -->

Les gestes à faire une fois, dans l'ordre, avant le premier pipeline. Chaque section se vérifie avant de passer à la suivante.

## Valeurs à adapter

À poser une fois dans le terminal ; les commandes suivantes les reprennent.

```bash
export GITOPS_REPO="git.example.com/groupe/gitops.git"   # même valeur que la variable CI
```

## 1. État Terraform

Le stockage de l'état (OVHcloud Object Storage) se crée avant le premier `init` : la pile ne le crée pas, elle s'en sert.

```bash
export AWS_ACCESS_KEY_ID="$OVH_S3_ACCESS_KEY" AWS_SECRET_ACCESS_KEY="$OVH_S3_SECRET_KEY"
aws s3api create-bucket --bucket mon-projet-tfstate --endpoint-url https://s3.gra.io.cloud.ovh.net
aws s3api put-bucket-versioning --bucket mon-projet-tfstate --endpoint-url https://s3.gra.io.cloud.ovh.net --versioning-configuration Status=Enabled
```

## 2. Premier apply

Le premier passage se fait depuis le poste (ou par le job manuel de la CI) ; les suivants passent par la CI.

```bash
tofu -chdir=infra/terraform init
tofu -chdir=infra/terraform plan -out=plan.tfplan
tofu -chdir=infra/terraform apply plan.tfplan
tofu -chdir=infra/terraform output
```

## 3. Cluster et plateforme

Avec le kubeconfig du cluster, une fois :

```bash
kubectl config current-context
bash platform/install.sh
kubectl get pods -A | grep -v Running   # rien ne doit rester en attente
```

## 4. Argo CD

Le dépôt GitOps (variable `GITOPS_REPO`) doit être connu d'Argo CD, puis les applications créées :

```bash
argocd repo add "https://$GITOPS_REPO" --username ci --password "<jeton de lecture>"
# adresse du dépôt GitOps à reporter dans deploy/argocd/application.yaml (repoURL)
kubectl apply -f deploy/argocd/application.yaml
argocd app list
```

## 5. Variables CI

12 variable(s) à déclarer (liste dans `PIPELINE.md`). Le script les déclare avec l'outil de la forge, sans écrire les valeurs dans le dépôt :

```bash
bash scripts/ci-variables.sh --dry-run   # ce qui serait déclaré
bash scripts/ci-variables.sh
```

## 6. Premier déploiement

Pousser sur la branche principale : chaque environnement se déploie dans l'ordre.

```bash
kubectl -n mon-app rollout status deployment/mon-app
kubectl -n mon-app get pods
```

## 7. Entretien

- Renovate : job planifié (quotidien) avec l'image renovate/renovate et `RENOVATE_TOKEN`.
