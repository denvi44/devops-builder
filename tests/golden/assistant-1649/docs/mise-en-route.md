# Mise en route — Mon projet

<!-- Généré par DevOps Builder — à relire avant usage. -->

Les gestes à faire une fois, dans l'ordre, avant le premier pipeline. Chaque section se vérifie avant de passer à la suivante.

## Valeurs à adapter

À poser une fois dans le terminal ; les commandes suivantes les reprennent.

```bash
export REPO="groupe/projet"   # dépôt de l'application sur la forge
```

## 1. État Terraform

Le stockage de l'état (Azure Blob Storage) se crée avant le premier `init` : la pile ne le crée pas, elle s'en sert.

```bash
az group create --name rg-mon-app --location francecentral
az storage account create --name monprojettfstate --resource-group rg-mon-app --sku Standard_ZRS --min-tls-version TLS1_2 --allow-blob-public-access false
az storage container create --name tfstate --account-name monprojettfstate --auth-mode login
```

## 2. Connexion de la CI au cloud

La CI s'authentifie par jeton OIDC (GitLab), sans clé statique. Une fois par cloud :

**Azure** — application Entra ID et identifiants fédérés ; `AZURE_CLIENT_ID`, `AZURE_TENANT_ID` et `AZURE_SUBSCRIPTION_ID` en variables CI.

```bash
APP_ID="$(az ad app create --display-name mon-app-ci --query appId -o tsv)"
az ad sp create --id "$APP_ID" >/dev/null
az ad app federated-credential create --id "$APP_ID" --parameters '{"name": "ci-1", "issuer": "https://gitlab.com", "subject": "'"project_path:${REPO}:ref_type:branch:ref:main"'", "audiences": ["api://AzureADTokenExchange"]}'
az role assignment create --assignee "$APP_ID" --role "Contributor" --scope "/subscriptions/$(az account show --query id -o tsv)"
az role assignment create --assignee "$APP_ID" --role "Role Based Access Control Administrator" --scope "/subscriptions/$(az account show --query id -o tsv)"
```

## 3. Premier apply

Le premier passage se fait depuis le poste (ou par le job manuel de la CI) ; les suivants passent par la CI.

```bash
terraform -chdir=infra/terraform init
terraform -chdir=infra/terraform plan -out=plan.tfplan
terraform -chdir=infra/terraform apply plan.tfplan
terraform -chdir=infra/terraform output
```

## 4. Variables CI

8 variable(s) à déclarer (liste dans `PIPELINE.md`). Le script les déclare avec l'outil de la forge, sans écrire les valeurs dans le dépôt :

```bash
bash scripts/ci-variables.sh --dry-run   # ce qui serait déclaré
bash scripts/ci-variables.sh
```

## 5. Premier déploiement

Pousser sur la branche principale : chaque environnement se déploie dans l'ordre, la production après approbation.

## 6. Entretien

- Renovate : job planifié (quotidien) avec l'image renovate/renovate et `RENOVATE_TOKEN`.
