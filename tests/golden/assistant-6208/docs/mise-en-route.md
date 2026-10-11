# Mise en route — Mon projet

<!-- Généré par DevOps Builder — à relire avant usage. -->

Les gestes à faire une fois, dans l'ordre, avant le premier pipeline. Chaque section se vérifie avant de passer à la suivante.

## 1. État Terraform

Le stockage de l'état (Scaleway Object Storage) se crée avant le premier `init` : la pile ne le crée pas, elle s'en sert.

```bash
export AWS_ACCESS_KEY_ID="$SCW_ACCESS_KEY" AWS_SECRET_ACCESS_KEY="$SCW_SECRET_KEY"
aws s3api create-bucket --bucket mon-projet-tfstate --endpoint-url https://s3.fr-par.scw.cloud
aws s3api put-bucket-versioning --bucket mon-projet-tfstate --endpoint-url https://s3.fr-par.scw.cloud --versioning-configuration Status=Enabled
```

## 2. Premier apply

Le premier passage se fait depuis le poste (ou par le job manuel de la CI) ; les suivants passent par la CI.

```bash
terraform -chdir=infra/terraform init
terraform -chdir=infra/terraform plan -out=plan.tfplan
terraform -chdir=infra/terraform apply plan.tfplan
terraform -chdir=infra/terraform output
```

## 3. Cluster et plateforme

Avec le kubeconfig du cluster, une fois :

```bash
kubectl config current-context
bash platform/install.sh
kubectl get pods -A | grep -v Running   # rien ne doit rester en attente
```

## 4. Premier déploiement

Pousser sur la branche principale : chaque environnement se déploie dans l'ordre.

```bash
kubectl -n mon-app rollout status deployment/mon-app
kubectl -n mon-app get pods
```

## 5. Entretien

- Renovate : job planifié (quotidien) avec l'image renovate/renovate et `RENOVATE_TOKEN`.
