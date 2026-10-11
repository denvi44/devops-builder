# Mise en route — Mon projet

<!-- Généré par DevOps Builder — à relire avant usage. -->

Les gestes à faire une fois, dans l'ordre, avant le premier pipeline. Chaque section se vérifie avant de passer à la suivante.

## 1. État Terraform

Le stockage de l'état (Google Cloud Storage) se crée avant le premier `init` : la pile ne le crée pas, elle s'en sert.

```bash
gcloud storage buckets create gs://mon-projet-tfstate --project mon-projet --location europe-west9 --uniform-bucket-level-access --public-access-prevention
gcloud storage buckets update gs://mon-projet-tfstate --versioning
```

## 2. Premier apply

Le premier passage se fait depuis le poste (ou par le job manuel de la CI) ; les suivants passent par la CI.

```bash
terraform -chdir=infra/terraform init
terraform -chdir=infra/terraform plan -out=plan.tfplan
terraform -chdir=infra/terraform apply plan.tfplan
terraform -chdir=infra/terraform output
```

## 3. Premier déploiement

Pousser sur la branche principale : chaque environnement se déploie dans l'ordre.

## 4. Entretien

- Renovate : job planifié (quotidien) avec l'image renovate/renovate et `RENOVATE_TOKEN`.
