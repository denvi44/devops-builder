# Mise en route — IaC AWS et Floci

<!-- Généré par DevOps Builder — à relire avant usage. -->

Les gestes à faire une fois, dans l'ordre, avant le premier pipeline. Chaque section se vérifie avant de passer à la suivante.

## Valeurs à adapter

À poser une fois dans le terminal ; les commandes suivantes les reprennent.

```bash
export REPO="propriétaire/dépôt"   # dépôt de l'application sur la forge
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

La CI s'authentifie par jeton OIDC (GitHub Actions), sans clé statique, avec deux identités : celle des jobs d'infrastructure (plan, apply), aux droits étendus parce que la pile crée réseaux, clusters et rôles, et celle des autres jobs, limitée à ce qu'ils font. Le jeton de GitHub porte l'environnement du job : seul le plan ou l'apply obtient l'identité d'infrastructure. Une fois par cloud :

**AWS** — fournisseur d'identité OIDC et rôles assumés par la CI ; les ARN affichés vont dans les variables CI. Un refus « AccessDenied » au déploiement nomme l'action manquante, à ajouter à la politique `deploiement`.

```bash
aws iam create-open-id-connect-provider --url https://token.actions.githubusercontent.com --client-id-list sts.amazonaws.com
# déploiement : pousser l'image, obtenir l'accès au cluster
cat > /tmp/trust-ci.json <<EOF
{"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"Federated": "arn:aws:iam::${AWS_ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com"}, "Action": "sts:AssumeRoleWithWebIdentity", "Condition": {"StringEquals": {"token.actions.githubusercontent.com:aud": "sts.amazonaws.com"}, "StringLike": {"token.actions.githubusercontent.com:sub": ["repo:${REPO}:ref:refs/heads/main", "repo:${REPO}:environment:staging", "repo:${REPO}:environment:production"]}}}]}
EOF
cat > /tmp/policy-ci.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "EcrConnexion",
      "Effect": "Allow",
      "Action": "ecr:GetAuthorizationToken",
      "Resource": "*"
    },
    {
      "Sid": "EcrImage",
      "Effect": "Allow",
      "Action": [
        "ecr:BatchCheckLayerAvailability",
        "ecr:BatchGetImage",
        "ecr:CompleteLayerUpload",
        "ecr:DescribeImages",
        "ecr:GetDownloadUrlForLayer",
        "ecr:InitiateLayerUpload",
        "ecr:PutImage",
        "ecr:UploadLayerPart"
      ],
      "Resource": "arn:aws:ecr:eu-west-3:${AWS_ACCOUNT_ID}:repository/boutique"
    },
    {
      "Sid": "EksKubeconfig",
      "Effect": "Allow",
      "Action": "eks:DescribeCluster",
      "Resource": [
        "arn:aws:eks:eu-west-3:${AWS_ACCOUNT_ID}:cluster/boutique"
      ]
    }
  ]
}
EOF
aws iam create-role --role-name boutique-ci --assume-role-policy-document file:///tmp/trust-ci.json
aws iam put-role-policy --role-name boutique-ci --policy-name deploiement --policy-document file:///tmp/policy-ci.json
echo "AWS_ROLE_ARN=arn:aws:iam::$AWS_ACCOUNT_ID:role/boutique-ci"
# infrastructure : la pile crée des rôles IAM (EKS, External Secrets) et des réseaux
cat > /tmp/trust-infra.json <<EOF
{"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"Federated": "arn:aws:iam::${AWS_ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com"}, "Action": "sts:AssumeRoleWithWebIdentity", "Condition": {"StringEquals": {"token.actions.githubusercontent.com:aud": "sts.amazonaws.com"}, "StringLike": {"token.actions.githubusercontent.com:sub": ["repo:${REPO}:ref:refs/heads/main", "repo:${REPO}:pull_request", "repo:${REPO}:environment:production"]}}}]}
EOF
aws iam create-role --role-name boutique-ci-infra --assume-role-policy-document file:///tmp/trust-infra.json
aws iam attach-role-policy --role-name boutique-ci-infra --policy-arn arn:aws:iam::aws:policy/AdministratorAccess
echo "AWS_INFRA_ROLE_ARN=arn:aws:iam::$AWS_ACCOUNT_ID:role/boutique-ci-infra"
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

EKS donne l'administration du cluster à l'identité qui applique la pile : celle du poste au premier apply, puis le rôle d'infrastructure de la CI. Pour garder l'accès, déclarer son rôle IAM dans `cluster_admin_arns` (terraform.tfvars) ; le rôle de déploiement de la CI y entre par `ci_deploy_role_arn`.

## 4. Secrets de l'application

Valeurs dans des variables CI, une par environnement : `scripts/ci-variables.sh` les déclare (section Variables CI). Générer chaque mot de passe avec `openssl rand -hex 24`.

## 5. Variables CI

10 variable(s) à déclarer (liste dans `PIPELINE.md`). Le script les déclare avec l'outil de la forge, sans écrire les valeurs dans le dépôt :

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

## 7. Poste de développement

Les mêmes bases qu'en production, en version identique, sur le poste (ports liés à 127.0.0.1, mot de passe `dev`). Les fichiers de `dev/db/init/<base>/` sont joués à la création :

```bash
docker compose -f dev/db/compose.yaml up -d --wait
set -a && . dev/db/app.env && set +a   # variables de connexion pour l'application lancée sur le poste
docker compose -f dev/db/compose.yaml --profile outils up -d adminer   # http://127.0.0.1:8081
```
