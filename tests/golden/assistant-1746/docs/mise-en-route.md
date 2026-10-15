# Mise en route — Mon projet

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
aws s3api create-bucket --bucket mon-projet-tfstate --region eu-west-3 --create-bucket-configuration LocationConstraint=eu-west-3
aws s3api put-bucket-versioning --bucket mon-projet-tfstate --versioning-configuration Status=Enabled
aws s3api put-public-access-block --bucket mon-projet-tfstate --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
```

## 2. Connexion de la CI au cloud

La CI s'authentifie par jeton OIDC (GitLab), sans clé statique, avec deux identités : celle des jobs d'infrastructure (plan, apply), aux droits étendus parce que la pile crée réseaux, clusters et rôles, et celle des autres jobs, limitée à ce qu'ils font. GitLab ne distingue pas les jobs dans son jeton : la séparation tient aux variables, à protéger (branche main seulement). Une fois par cloud :

**AWS** — fournisseur d'identité OIDC et rôles assumés par la CI ; les ARN affichés vont dans les variables CI. Un refus « AccessDenied » au déploiement nomme l'action manquante, à ajouter à la politique `deploiement`.

```bash
aws iam create-open-id-connect-provider --url https://gitlab.com --client-id-list sts.amazonaws.com
# déploiement : pousser l'image, mettre à jour le service ECS
cat > /tmp/trust-ci.json <<EOF
{"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"Federated": "arn:aws:iam::${AWS_ACCOUNT_ID}:oidc-provider/gitlab.com"}, "Action": "sts:AssumeRoleWithWebIdentity", "Condition": {"StringEquals": {"gitlab.com:aud": "sts.amazonaws.com", "gitlab.com:sub": "project_path:${REPO}:ref_type:branch:ref:main"}}}]}
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
      "Resource": "arn:aws:ecr:eu-west-3:${AWS_ACCOUNT_ID}:repository/mon-app"
    },
    {
      "Sid": "EcsDeploiement",
      "Effect": "Allow",
      "Action": [
        "ecs:DescribeServices",
        "ecs:UpdateService"
      ],
      "Resource": [
        "arn:aws:ecs:eu-west-3:${AWS_ACCOUNT_ID}:service/mon-cluster-ecs/mon-app",
        "arn:aws:ecs:eu-west-3:${AWS_ACCOUNT_ID}:service/mon-cluster-ecs/mon-app-dev",
        "arn:aws:ecs:eu-west-3:${AWS_ACCOUNT_ID}:service/mon-cluster-ecs/mon-app-staging"
      ]
    }
  ]
}
EOF
aws iam create-role --role-name mon-app-ci --assume-role-policy-document file:///tmp/trust-ci.json
aws iam put-role-policy --role-name mon-app-ci --policy-name deploiement --policy-document file:///tmp/policy-ci.json
echo "AWS_ROLE_ARN=arn:aws:iam::$AWS_ACCOUNT_ID:role/mon-app-ci"
# infrastructure : la pile crée des rôles IAM (EKS, External Secrets) et des réseaux
cat > /tmp/trust-infra.json <<EOF
{"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"Federated": "arn:aws:iam::${AWS_ACCOUNT_ID}:oidc-provider/gitlab.com"}, "Action": "sts:AssumeRoleWithWebIdentity", "Condition": {"StringEquals": {"gitlab.com:aud": "sts.amazonaws.com", "gitlab.com:sub": "project_path:${REPO}:ref_type:branch:ref:main"}}}]}
EOF
aws iam create-role --role-name mon-app-ci-infra --assume-role-policy-document file:///tmp/trust-infra.json
aws iam attach-role-policy --role-name mon-app-ci-infra --policy-arn arn:aws:iam::aws:policy/AdministratorAccess
echo "AWS_INFRA_ROLE_ARN=arn:aws:iam::$AWS_ACCOUNT_ID:role/mon-app-ci-infra"
```

## 3. Premier apply

Le premier passage se fait depuis le poste (ou par le job manuel de la CI) ; les suivants passent par la CI.

```bash
tofu -chdir=infra/terraform init
tofu -chdir=infra/terraform plan -out=plan.tfplan
tofu -chdir=infra/terraform apply plan.tfplan
tofu -chdir=infra/terraform output
```

## 4. Variables CI

6 variable(s) à déclarer (liste dans `PIPELINE.md`). Le script les déclare avec l'outil de la forge, sans écrire les valeurs dans le dépôt :

```bash
bash scripts/ci-variables.sh --dry-run   # ce qui serait déclaré
bash scripts/ci-variables.sh
```

## 5. Premier déploiement

Pousser sur la branche principale : chaque environnement se déploie dans l'ordre, la production après approbation.

## 6. Entretien

- Renovate : le job `renovate` tourne dans une planification de pipeline qui porte la variable `RENOVATE=1` (Build › Pipeline schedules, ou par l'API ci-dessous, jeton `api` dans `GITLAB_TOKEN`) ; `RENOVATE_TOKEN` : jeton de projet avec les droits `api` et `write_repository`.

```bash
sid=$(curl -fsS -H "PRIVATE-TOKEN: $GITLAB_TOKEN" -d description=Renovate -d ref=main --data-urlencode "cron=0 4 * * 1-5" "${CI_SERVER_URL:-https://gitlab.com}/api/v4/projects/$(printf %s "$REPO" | jq -sRr @uri)/pipeline_schedules" | jq -r .id)
curl -fsS -H "PRIVATE-TOKEN: $GITLAB_TOKEN" -d key=RENOVATE -d value=1 "${CI_SERVER_URL:-https://gitlab.com}/api/v4/projects/$(printf %s "$REPO" | jq -sRr @uri)/pipeline_schedules/$sid/variables" >/dev/null
```
