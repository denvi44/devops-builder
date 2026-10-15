# Mise en route — Mon projet

<!-- Généré par DevOps Builder — à relire avant usage. -->

Les gestes à faire une fois, dans l'ordre, avant le premier pipeline. Chaque section se vérifie avant de passer à la suivante.

## Valeurs à adapter

À poser une fois dans le terminal ; les commandes suivantes les reprennent.

```bash
export REPO="propriétaire/dépôt"   # dépôt de l'application sur la forge
read -rsp "Jeton de lecture du dépôt GitOps : " GITOPS_READ_TOKEN; echo; export GITOPS_READ_TOKEN
```

## 1. État Terraform

Le stockage de l'état (Azure Blob Storage) se crée avant le premier `init` : la pile ne le crée pas, elle s'en sert.

```bash
az group create --name rg-mon-app --location francecentral
az storage account create --name monprojettfstate --resource-group rg-mon-app --sku Standard_ZRS --min-tls-version TLS1_2 --allow-blob-public-access false
az storage container create --name tfstate --account-name monprojettfstate --auth-mode login
```

## 2. Connexion de la CI au cloud

La CI s'authentifie par jeton OIDC (GitHub Actions), sans clé statique, avec deux identités : celle des jobs d'infrastructure (plan, apply), aux droits étendus parce que la pile crée réseaux, clusters et rôles, et celle des autres jobs, limitée à ce qu'ils font. Le jeton de GitHub porte l'environnement du job : seul le plan ou l'apply obtient l'identité d'infrastructure. Une fois par cloud :

**Azure** — deux applications Entra ID et leurs identifiants fédérés ; `AZURE_TENANT_ID` et `AZURE_SUBSCRIPTION_ID` en variables CI. Déploiement, sur le seul groupe de ressources du projet : pousser l'image.

```bash
INFRA_ID="$(az ad app create --display-name mon-app-ci-infra --query appId -o tsv)"
az ad sp create --id "$INFRA_ID" >/dev/null
az ad app federated-credential create --id "$INFRA_ID" --parameters '{"name": "ci-1", "issuer": "https://token.actions.githubusercontent.com", "subject": "'"repo:${REPO}:ref:refs/heads/main"'", "audiences": ["api://AzureADTokenExchange"]}'
az ad app federated-credential create --id "$INFRA_ID" --parameters '{"name": "ci-2", "issuer": "https://token.actions.githubusercontent.com", "subject": "'"repo:${REPO}:pull_request"'", "audiences": ["api://AzureADTokenExchange"]}'
az ad app federated-credential create --id "$INFRA_ID" --parameters '{"name": "ci-3", "issuer": "https://token.actions.githubusercontent.com", "subject": "'"repo:${REPO}:environment:production"'", "audiences": ["api://AzureADTokenExchange"]}'
az role assignment create --assignee "$INFRA_ID" --role "Contributor" --scope "/subscriptions/$(az account show --query id -o tsv)"
az role assignment create --assignee "$INFRA_ID" --role "Role Based Access Control Administrator" --scope "/subscriptions/$(az account show --query id -o tsv)"
echo "AZURE_INFRA_CLIENT_ID=$INFRA_ID"
APP_ID="$(az ad app create --display-name mon-app-ci --query appId -o tsv)"
az ad sp create --id "$APP_ID" >/dev/null
az ad app federated-credential create --id "$APP_ID" --parameters '{"name": "ci-1", "issuer": "https://token.actions.githubusercontent.com", "subject": "'"repo:${REPO}:ref:refs/heads/main"'", "audiences": ["api://AzureADTokenExchange"]}'
az ad app federated-credential create --id "$APP_ID" --parameters '{"name": "ci-2", "issuer": "https://token.actions.githubusercontent.com", "subject": "'"repo:${REPO}:environment:dev"'", "audiences": ["api://AzureADTokenExchange"]}'
az ad app federated-credential create --id "$APP_ID" --parameters '{"name": "ci-3", "issuer": "https://token.actions.githubusercontent.com", "subject": "'"repo:${REPO}:environment:staging"'", "audiences": ["api://AzureADTokenExchange"]}'
az ad app federated-credential create --id "$APP_ID" --parameters '{"name": "ci-4", "issuer": "https://token.actions.githubusercontent.com", "subject": "'"repo:${REPO}:environment:production"'", "audiences": ["api://AzureADTokenExchange"]}'
echo "AZURE_CLIENT_ID=$APP_ID"
# après le premier apply, quand le groupe de ressources rg-mon-app existe :
az role assignment create --assignee "$APP_ID" --role "AcrPush" --scope "/subscriptions/$(az account show --query id -o tsv)/resourceGroups/rg-mon-app"
```

## 3. Premier apply

Le premier passage se fait depuis le poste (ou par le job manuel de la CI) ; les suivants passent par la CI.

```bash
tofu -chdir=infra/terraform init
tofu -chdir=infra/terraform plan -out=plan.tfplan
tofu -chdir=infra/terraform apply plan.tfplan
tofu -chdir=infra/terraform output
```

## 4. Cluster et plateforme

Avec le kubeconfig du cluster, une fois :

```bash
kubectl config current-context
bash platform/install.sh
kubectl get pods -A | grep -v Running   # rien ne doit rester en attente
```

## 5. Argo CD

Le dépôt GitOps (https://git.example.com/groupe/gitops.git) contient `charts/mon-app/` tel que généré ici : le dépôt de l'application convient (les commits de la CI portent `[skip ci]`), ou un dépôt dédié où ce dossier est copié. `GITOPS_READ_TOKEN` : jeton en lecture seule sur ce dépôt, distinct de `GITOPS_TOKEN` (écriture, CI).

Argo CD connaît le dépôt par un secret étiqueté, puis les applications sont créées et suivies jusqu'à leur synchronisation :

```bash
kubectl -n argocd create secret generic gitops-repo --from-literal=type=git --from-literal=url="https://git.example.com/groupe/gitops.git" --from-literal=username=ci --from-literal=password="$GITOPS_READ_TOKEN"
kubectl -n argocd label secret gitops-repo argocd.argoproj.io/secret-type=repository
kubectl apply -f deploy/argocd/application.yaml
kubectl -n argocd wait application/mon-app-dev --for=jsonpath='{.status.sync.status}'=Synced --timeout=600s
kubectl -n argocd get applications
```

Ensuite, chaque pipeline met à jour l'étiquette de l'image dans le dépôt GitOps ; Argo CD l'applique à sa prochaine lecture du dépôt (trois minutes au plus).

## 6. Variables CI

10 variable(s) à déclarer (liste dans `PIPELINE.md`). Le script les déclare avec l'outil de la forge, sans écrire les valeurs dans le dépôt :

```bash
bash scripts/ci-variables.sh --dry-run   # ce qui serait déclaré
bash scripts/ci-variables.sh
```

## 7. Premier déploiement

Pousser sur la branche principale : chaque environnement se déploie dans l'ordre, la production après approbation.

```bash
kubectl -n mon-app rollout status deployment/mon-app
kubectl -n mon-app get pods
```
