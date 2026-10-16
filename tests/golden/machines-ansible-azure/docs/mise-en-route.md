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

La CI s'authentifie par jeton OIDC (GitLab), sans clé statique, avec deux identités : celle des jobs d'infrastructure (plan, apply), aux droits étendus parce que la pile crée réseaux, clusters et rôles, et celle des autres jobs, limitée à ce qu'ils font. GitLab ne distingue pas les jobs dans son jeton : la séparation tient aux variables, à protéger (branche main seulement). Une fois par cloud :

**Azure** — deux applications Entra ID et leurs identifiants fédérés ; `AZURE_TENANT_ID` et `AZURE_SUBSCRIPTION_ID` en variables CI. Déploiement, sur le seul groupe de ressources du projet : lire les sorties de l'état Terraform.

```bash
INFRA_ID="$(az ad app create --display-name mon-app-ci-infra --query appId -o tsv)"
az ad sp create --id "$INFRA_ID" >/dev/null
az ad app federated-credential create --id "$INFRA_ID" --parameters '{"name": "ci-1", "issuer": "https://gitlab.com", "subject": "'"project_path:${REPO}:ref_type:branch:ref:main"'", "audiences": ["api://AzureADTokenExchange"]}'
az role assignment create --assignee "$INFRA_ID" --role "Contributor" --scope "/subscriptions/$(az account show --query id -o tsv)"
az role assignment create --assignee "$INFRA_ID" --role "Role Based Access Control Administrator" --scope "/subscriptions/$(az account show --query id -o tsv)"
echo "AZURE_INFRA_CLIENT_ID=$INFRA_ID"
APP_ID="$(az ad app create --display-name mon-app-ci --query appId -o tsv)"
az ad sp create --id "$APP_ID" >/dev/null
az ad app federated-credential create --id "$APP_ID" --parameters '{"name": "ci-1", "issuer": "https://gitlab.com", "subject": "'"project_path:${REPO}:ref_type:branch:ref:main"'", "audiences": ["api://AzureADTokenExchange"]}'
echo "AZURE_CLIENT_ID=$APP_ID"
# après le premier apply, quand le groupe de ressources rg-mon-app existe :
az role assignment create --assignee "$APP_ID" --role "Reader and Data Access" --scope "/subscriptions/$(az account show --query id -o tsv)/resourceGroups/rg-mon-app"
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

## 4. Hôtes

Noms d'hôte de l'application : chacun pointe (enregistrement DNS A ou AAAA) vers l'hôte de son environnement, joignable depuis Internet sur les ports 80 et 443 ; Traefik y obtient seul le certificat (paramètre « Adresse publique de l'application » de la brique Traefik).

- Développement : `dev.mon-app.example.com`
- Recette : `recette.mon-app.example.com`
- Production : `mon-app.example.com`

Les machines sont créées par la pile : cloud-init pose le compte `deploy`, la clé de la CI (`TF_VAR_ssh_public_key`) et Docker. Rien à préparer à la main. Pour joindre une machine depuis le poste :

```bash
bash scripts/tf-inventory.sh dev   # écrit l'inventaire de l'environnement
```

## 5. Variables CI

8 variable(s) à déclarer (liste dans `PIPELINE.md`). Le script les déclare avec l'outil de la forge, sans écrire les valeurs dans le dépôt :

```bash
bash scripts/ci-variables.sh --dry-run   # ce qui serait déclaré
bash scripts/ci-variables.sh
```

## 6. Premier déploiement

Pousser sur la branche principale : chaque environnement se déploie dans l'ordre, la production après approbation.

```bash
ssh "<hôte>" "cd /opt/mon-app && docker compose -p mon-app ps"
```

## 7. Entretien

- Renovate : le job `renovate` tourne dans une planification de pipeline qui porte la variable `RENOVATE=1` (Build › Pipeline schedules, ou par l'API ci-dessous, jeton `api` dans `GITLAB_TOKEN`) ; `RENOVATE_TOKEN` : jeton de projet avec les droits `api` et `write_repository`.

```bash
sid=$(curl -fsS -H "PRIVATE-TOKEN: $GITLAB_TOKEN" -d description=Renovate -d ref=main --data-urlencode "cron=0 4 * * 1-5" "${CI_SERVER_URL:-https://gitlab.com}/api/v4/projects/$(printf %s "$REPO" | jq -sRr @uri)/pipeline_schedules" | jq -r .id)
curl -fsS -H "PRIVATE-TOKEN: $GITLAB_TOKEN" -d key=RENOVATE -d value=1 "${CI_SERVER_URL:-https://gitlab.com}/api/v4/projects/$(printf %s "$REPO" | jq -sRr @uri)/pipeline_schedules/$sid/variables" >/dev/null
```
