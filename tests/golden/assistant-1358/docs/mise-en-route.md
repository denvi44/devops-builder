# Mise en route — Mon projet

<!-- Généré par DevOps Builder — à relire avant usage. -->

Les gestes à faire une fois, dans l'ordre, avant le premier pipeline. Chaque section se vérifie avant de passer à la suivante.

## Valeurs à adapter

À poser une fois dans le terminal ; les commandes suivantes les reprennent.

```bash
export REPO="groupe/projet"   # dépôt de l'application sur la forge
read -rsp "Jeton de lecture du dépôt GitOps : " GITOPS_READ_TOKEN; echo; export GITOPS_READ_TOKEN
```

## 1. État Terraform

Le stockage de l'état (OVHcloud Object Storage) se crée avant le premier `init` : la pile ne le crée pas, elle s'en sert.

```bash
export AWS_ACCESS_KEY_ID="$OVH_S3_ACCESS_KEY" AWS_SECRET_ACCESS_KEY="$OVH_S3_SECRET_KEY"
aws s3api create-bucket --bucket mon-projet-tfstate --endpoint-url https://s3.gra.io.cloud.ovh.net
aws s3api put-bucket-versioning --bucket mon-projet-tfstate --endpoint-url https://s3.gra.io.cloud.ovh.net --versioning-configuration Status=Enabled
```

## 2. Premier apply

Le premier passage se fait depuis le poste (ou par le job manuel de la CI) ; les suivants passent par la CI.

```bash
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
kubectl -n argocd wait application/mon-app --for=jsonpath='{.status.sync.status}'=Synced --timeout=600s
kubectl -n argocd get applications
```

Ensuite, chaque pipeline met à jour l'étiquette de l'image dans le dépôt GitOps ; Argo CD l'applique à sa prochaine lecture du dépôt (trois minutes au plus).

## 5. Variables CI

12 variable(s) à déclarer (liste dans `PIPELINE.md`). Le script les déclare avec l'outil de la forge, sans écrire les valeurs dans le dépôt :

```bash
bash scripts/ci-variables.sh --dry-run   # ce qui serait déclaré
bash scripts/ci-variables.sh
```

## 6. Premier déploiement

Pousser sur la branche principale : chaque environnement se déploie dans l'ordre.

```bash
kubectl -n mon-app rollout status deployment/mon-app
kubectl -n mon-app get pods
```

## 7. Entretien

- Renovate : le job `renovate` tourne dans une planification de pipeline qui porte la variable `RENOVATE=1` (Build › Pipeline schedules, ou par l'API ci-dessous, jeton `api` dans `GITLAB_TOKEN`) ; `RENOVATE_TOKEN` : jeton de projet avec les droits `api` et `write_repository`.

```bash
sid=$(curl -fsS -H "PRIVATE-TOKEN: $GITLAB_TOKEN" -d description=Renovate -d ref=main --data-urlencode "cron=0 4 * * 1-5" "${CI_SERVER_URL:-https://gitlab.com}/api/v4/projects/$(printf %s "$REPO" | jq -sRr @uri)/pipeline_schedules" | jq -r .id)
curl -fsS -H "PRIVATE-TOKEN: $GITLAB_TOKEN" -d key=RENOVATE -d value=1 "${CI_SERVER_URL:-https://gitlab.com}/api/v4/projects/$(printf %s "$REPO" | jq -sRr @uri)/pipeline_schedules/$sid/variables" >/dev/null
```
