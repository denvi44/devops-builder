# Mise en route — Mon projet

<!-- Généré par DevOps Builder — à relire avant usage. -->

Les gestes à faire une fois, dans l'ordre, avant le premier pipeline. Chaque section se vérifie avant de passer à la suivante.

## Valeurs à adapter

À poser une fois dans le terminal ; les commandes suivantes les reprennent.

```bash
export REPO="propriétaire/dépôt"   # dépôt de l'application sur la forge
export AWS_ACCOUNT_ID="123456789012"
read -rsp "Jeton de lecture du dépôt GitOps : " GITOPS_READ_TOKEN; echo; export GITOPS_READ_TOKEN
```

## 1. Connexion de la CI au cloud

La CI s'authentifie par jeton OIDC (GitHub Actions), sans clé statique. Une fois par cloud :

**AWS** — fournisseur d'identité OIDC et rôle assumé par la CI ; sa valeur va dans `AWS_ROLE_ARN`.

```bash
aws iam create-open-id-connect-provider --url https://token.actions.githubusercontent.com --client-id-list sts.amazonaws.com
cat > /tmp/trust.json <<EOF
{"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"Federated": "arn:aws:iam::${AWS_ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com"}, "Action": "sts:AssumeRoleWithWebIdentity", "Condition": {"StringEquals": {"token.actions.githubusercontent.com:aud": "sts.amazonaws.com"}, "StringLike": {"token.actions.githubusercontent.com:sub": "repo:${REPO}:*"}}}]}
EOF
aws iam create-role --role-name mon-app-ci --assume-role-policy-document file:///tmp/trust.json
# droits du rôle : la pile crée des rôles IAM (EKS, External Secrets) ; à restreindre ensuite
aws iam attach-role-policy --role-name mon-app-ci --policy-arn arn:aws:iam::aws:policy/AdministratorAccess
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

## 3. Cluster et plateforme

Avec le kubeconfig du cluster, une fois :

```bash
kubectl config current-context
bash platform/install.sh
kubectl get pods -A | grep -v Running   # rien ne doit rester en attente
```

## 4. Argo CD

Le dépôt GitOps (https://git.example.com/groupe/gitops.git) contient `charts/mon-app/` tel que généré ici : le dépôt de l'application convient (les commits de la CI portent `[skip ci]`), ou un dépôt dédié où ce dossier est copié. `GITOPS_READ_TOKEN` : jeton en lecture seule sur ce dépôt, distinct de `GITOPS_TOKEN` (écriture, CI).

Argo CD connaît le dépôt par un secret étiqueté, puis les applications sont créées et suivies jusqu'à leur synchronisation :

```bash
kubectl -n argocd create secret generic gitops-repo --from-literal=type=git --from-literal=url="https://git.example.com/groupe/gitops.git" --from-literal=username=ci --from-literal=password="$GITOPS_READ_TOKEN"
kubectl -n argocd label secret gitops-repo argocd.argoproj.io/secret-type=repository
kubectl apply -f deploy/argocd/application.yaml
kubectl -n argocd wait application/mon-app-staging --for=jsonpath='{.status.sync.status}'=Synced --timeout=300s
kubectl -n argocd get applications
```

Ensuite, chaque pipeline met à jour l'étiquette de l'image dans le dépôt GitOps ; Argo CD l'applique à sa prochaine lecture du dépôt (trois minutes au plus).

## 5. Variables CI

6 variable(s) à déclarer (liste dans `PIPELINE.md`). Le script les déclare avec l'outil de la forge, sans écrire les valeurs dans le dépôt :

```bash
bash scripts/ci-variables.sh --dry-run   # ce qui serait déclaré
bash scripts/ci-variables.sh
```

## 6. Premier déploiement

Pousser sur la branche principale : chaque environnement se déploie dans l'ordre, la production après approbation.

```bash
kubectl -n mon-app rollout status deployment/mon-app
kubectl -n mon-app get pods
```
