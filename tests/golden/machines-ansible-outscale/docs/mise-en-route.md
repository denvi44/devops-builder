# Mise en route — Mon projet

<!-- Généré par DevOps Builder — à relire avant usage. -->

Les gestes à faire une fois, dans l'ordre, avant le premier pipeline. Chaque section se vérifie avant de passer à la suivante.

## 1. État Terraform

Le stockage de l'état (Outscale Object Storage (OOS)) se crée avant le premier `init` : la pile ne le crée pas, elle s'en sert.

```bash
export AWS_ACCESS_KEY_ID="$OSC_ACCESS_KEY" AWS_SECRET_ACCESS_KEY="$OSC_SECRET_KEY"
aws s3api create-bucket --bucket mon-projet-tfstate --endpoint-url https://oos.eu-west-2.outscale.com
aws s3api put-bucket-versioning --bucket mon-projet-tfstate --endpoint-url https://oos.eu-west-2.outscale.com --versioning-configuration Status=Enabled
```

## 2. Premier apply

Le premier passage se fait depuis le poste (ou par le job manuel de la CI) ; les suivants passent par la CI.

```bash
cp infra/terraform/terraform.tfvars.example infra/terraform/terraform.tfvars   # valeurs à renseigner, fichier non versionné
tofu -chdir=infra/terraform init
tofu -chdir=infra/terraform plan -out=plan.tfplan
tofu -chdir=infra/terraform apply plan.tfplan
tofu -chdir=infra/terraform output
```

## 3. Hôtes

Les machines sont créées par la pile : cloud-init pose le compte `deploy`, la clé de la CI (`TF_VAR_ssh_public_key`) et Docker. Rien à préparer à la main. Pour joindre une machine depuis le poste :

```bash
bash scripts/tf-inventory.sh dev   # écrit l'inventaire de l'environnement
```

## 4. Variables CI

6 variable(s) à déclarer (liste dans `PIPELINE.md`). Le script les déclare avec l'outil de la forge, sans écrire les valeurs dans le dépôt :

```bash
bash scripts/ci-variables.sh --dry-run   # ce qui serait déclaré
bash scripts/ci-variables.sh
```

## 5. Premier déploiement

Pousser sur la branche principale : chaque environnement se déploie dans l'ordre, la production après approbation.

```bash
ssh "<hôte>" "cd /opt/mon-app && docker compose -p mon-app ps"
```

## 6. Entretien

- Renovate : job planifié (quotidien) avec l'image renovate/renovate et `RENOVATE_TOKEN`.
