# Mise en route — IaC AWS et Floci

<!-- Généré par DevOps Builder — à relire avant usage. -->

Les gestes à faire une fois, dans l'ordre, avant le premier pipeline. Chaque section se vérifie avant de passer à la suivante.

## Valeurs à adapter

À poser une fois dans le terminal ; les commandes suivantes les reprennent.

```bash
export REPO="groupe/projet"   # dépôt de l'application sur la forge
export AWS_ACCOUNT_ID="123456789012"
```

## 1. État Terraform

Le stockage de l'état (Amazon S3) se crée avant le premier `init` : la pile ne le crée pas, elle s'en sert.

```bash
aws s3api create-bucket --bucket boutique-tfstate --region eu-west-3 --create-bucket-configuration LocationConstraint=eu-west-3
aws s3api put-bucket-versioning --bucket boutique-tfstate --versioning-configuration Status=Enabled
aws s3api put-public-access-block --bucket boutique-tfstate --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
```

## 2. Connexion de la CI au cloud

La CI s'authentifie par jeton OIDC (GitLab), sans clé statique. Une fois par cloud :

**AWS** — fournisseur d'identité OIDC et rôle assumé par la CI ; sa valeur va dans `AWS_ROLE_ARN`.

```bash
aws iam create-open-id-connect-provider --url https://gitlab.com --client-id-list sts.amazonaws.com
cat > /tmp/trust.json <<EOF
{"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"Federated": "arn:aws:iam::${AWS_ACCOUNT_ID}:oidc-provider/gitlab.com"}, "Action": "sts:AssumeRoleWithWebIdentity", "Condition": {"StringEquals": {"gitlab.com:aud": "sts.amazonaws.com"}, "StringEquals": {"gitlab.com:sub": "project_path:${REPO}:ref_type:branch:ref:main"}}}]}
EOF
aws iam create-role --role-name boutique-ci --assume-role-policy-document file:///tmp/trust.json
# droits du rôle : la pile crée des rôles IAM (EKS, External Secrets) ; à restreindre ensuite
aws iam attach-role-policy --role-name boutique-ci --policy-arn arn:aws:iam::aws:policy/AdministratorAccess
```

## 3. Premier apply

Le premier passage se fait depuis le poste (ou par le job manuel de la CI) ; les suivants passent par la CI.

```bash
cp infra/terraform/terraform.tfvars.example infra/terraform/terraform.tfvars   # valeurs à renseigner, fichier non versionné
tofu -chdir=infra/terraform init
tofu -chdir=infra/terraform plan -out=plan.tfplan
tofu -chdir=infra/terraform apply plan.tfplan
tofu -chdir=infra/terraform output
```

## 4. Secrets de l'application

Valeurs dans des variables CI, une par environnement : `scripts/ci-variables.sh` les déclare (section Variables CI). Générer chaque mot de passe avec `openssl rand -hex 24`.

## 5. Variables CI

9 variable(s) à déclarer (liste dans `PIPELINE.md`). Le script les déclare avec l'outil de la forge, sans écrire les valeurs dans le dépôt :

```bash
bash scripts/ci-variables.sh --dry-run   # ce qui serait déclaré
bash scripts/ci-variables.sh
```

## 6. Premier déploiement

Pousser sur la branche principale : chaque environnement se déploie dans l'ordre, la production après approbation.

```bash
kubectl -n boutique rollout status deployment/boutique
kubectl -n boutique get pods
```
