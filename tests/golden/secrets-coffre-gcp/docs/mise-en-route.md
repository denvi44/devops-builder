# Mise en route — Mon projet

<!-- Généré par DevOps Builder — à relire avant usage. -->

Les gestes à faire une fois, dans l'ordre, avant le premier pipeline. Chaque section se vérifie avant de passer à la suivante.

## Valeurs à adapter

À poser une fois dans le terminal ; les commandes suivantes les reprennent.

```bash
export REPO="groupe/projet"   # dépôt de l'application sur la forge
```

## 1. État Terraform

Le stockage de l'état (Google Cloud Storage) se crée avant le premier `init` : la pile ne le crée pas, elle s'en sert.

```bash
gcloud storage buckets create gs://mon-projet-tfstate --project mon-projet --location europe-west9 --uniform-bucket-level-access --public-access-prevention
gcloud storage buckets update gs://mon-projet-tfstate --versioning
```

## 2. Connexion de la CI au cloud

La CI s'authentifie par jeton OIDC (GitLab), sans clé statique. Une fois par cloud :

**Google Cloud** — pool Workload Identity et compte de service ; le nom complet du fournisseur va dans `GCP_WORKLOAD_IDENTITY_PROVIDER`.

```bash
gcloud iam workload-identity-pools create ci --project mon-projet --location global
gcloud iam workload-identity-pools providers create-oidc ci --project mon-projet --location global --workload-identity-pool ci --issuer-uri https://gitlab.com --attribute-mapping "google.subject=assertion.sub,attribute.project_path=assertion.project_path" --attribute-condition "assertion.project_path == '${REPO}'"
gcloud iam service-accounts create mon-app-ci --project mon-projet
NUM="$(gcloud projects describe mon-projet --format="value(projectNumber)")"
gcloud iam service-accounts add-iam-policy-binding mon-app-ci@mon-projet.iam.gserviceaccount.com --role roles/iam.workloadIdentityUser --member "principalSet://iam.googleapis.com/projects/$NUM/locations/global/workloadIdentityPools/ci/attribute.project_path/${REPO}"
gcloud projects add-iam-policy-binding mon-projet --member serviceAccount:mon-app-ci@mon-projet.iam.gserviceaccount.com --role roles/editor
gcloud projects add-iam-policy-binding mon-projet --member serviceAccount:mon-app-ci@mon-projet.iam.gserviceaccount.com --role roles/resourcemanager.projectIamAdmin
echo "GCP_WORKLOAD_IDENTITY_PROVIDER=projects/$NUM/locations/global/workloadIdentityPools/ci/providers/ci"
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

Avec le kubeconfig du cluster, une fois après le premier apply (le script lit les sorties de la pile) :

```bash
kubectl config current-context
bash platform/install.sh
kubectl get pods -A | grep -v Running   # rien ne doit rester en attente
```

## 5. Secrets de l'application

Google Cloud SQL, Valkey : la pile Terraform écrit ces secrets à l'apply ; vérifier :

```bash
gcloud secrets describe mon-app-staging-cloud-sql
```

## 6. External Secrets

La pile Terraform donne au contrôleur la lecture du coffre (identité de charge de travail) ; installer External Secrets après l'apply, ou le redémarrer : `kubectl -n external-secrets rollout restart deployment external-secrets`.

Vérifier, après `platform/install.sh` et le premier déploiement :

```bash
kubectl get clustersecretstore mon-app   # READY True
kubectl -n mon-app get externalsecret   # STATUS SecretSynced
```

## 7. Variables CI

5 variable(s) à déclarer (liste dans `PIPELINE.md`). Le script les déclare avec l'outil de la forge, sans écrire les valeurs dans le dépôt :

```bash
bash scripts/ci-variables.sh --dry-run   # ce qui serait déclaré
bash scripts/ci-variables.sh
```

## 8. Premier déploiement

Pousser sur la branche principale : chaque environnement se déploie dans l'ordre, la production après approbation.

```bash
kubectl -n mon-app rollout status deployment/mon-app
kubectl -n mon-app get pods
```

## 9. Poste de développement

Les mêmes bases qu'en production, en version identique, sur le poste (ports liés à 127.0.0.1, mot de passe `dev`). Les fichiers de `dev/db/init/<base>/` sont joués à la création :

```bash
docker compose -f dev/db/compose.yaml up -d --wait
set -a && . dev/db/app.env && set +a   # variables de connexion pour l'application lancée sur le poste
docker compose -f dev/db/compose.yaml --profile outils up -d adminer   # http://127.0.0.1:8081
```

## 10. Entretien

- Rotation d'un mot de passe : nouvelle valeur par `scripts/secrets-seed.sh` (ou par la pile), puis redéploiement ; External Secrets relit le coffre toutes les heures.
- Renovate : le job `renovate` tourne dans une planification de pipeline qui porte la variable `RENOVATE=1` (Build › Pipeline schedules, ou par l'API ci-dessous, jeton `api` dans `GITLAB_TOKEN`) ; `RENOVATE_TOKEN` : jeton de projet avec les droits `api` et `write_repository`.

```bash
sid=$(curl -fsS -H "PRIVATE-TOKEN: $GITLAB_TOKEN" -d description=Renovate -d ref=main --data-urlencode "cron=0 4 * * 1-5" "${CI_SERVER_URL:-https://gitlab.com}/api/v4/projects/$(printf %s "$REPO" | jq -sRr @uri)/pipeline_schedules" | jq -r .id)
curl -fsS -H "PRIVATE-TOKEN: $GITLAB_TOKEN" -d key=RENOVATE -d value=1 "${CI_SERVER_URL:-https://gitlab.com}/api/v4/projects/$(printf %s "$REPO" | jq -sRr @uri)/pipeline_schedules/$sid/variables" >/dev/null
```
