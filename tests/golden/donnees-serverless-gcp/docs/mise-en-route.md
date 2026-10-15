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

La CI s'authentifie par jeton OIDC (GitLab), sans clé statique, avec deux identités : celle des jobs d'infrastructure (plan, apply), aux droits étendus parce que la pile crée réseaux, clusters et rôles, et celle des autres jobs, limitée à ce qu'ils font. GitLab ne distingue pas les jobs dans son jeton : la séparation tient aux variables, à protéger (branche main seulement). Une fois par cloud :

**Google Cloud** — pool Workload Identity et deux comptes de service ; le nom complet du fournisseur va dans `GCP_WORKLOAD_IDENTITY_PROVIDER`. Déploiement : pousser l'image, déployer sur Cloud Run.

```bash
gcloud iam workload-identity-pools create ci --project mon-projet --location global
gcloud iam workload-identity-pools providers create-oidc ci --project mon-projet --location global --workload-identity-pool ci --issuer-uri https://gitlab.com --attribute-mapping "google.subject=assertion.sub,attribute.project_path=assertion.project_path" --attribute-condition "assertion.project_path == '${REPO}'"
NUM="$(gcloud projects describe mon-projet --format="value(projectNumber)")"
gcloud iam service-accounts create mon-app-ci --project mon-projet
gcloud iam service-accounts add-iam-policy-binding mon-app-ci@mon-projet.iam.gserviceaccount.com --role roles/iam.workloadIdentityUser --member "principalSet://iam.googleapis.com/projects/$NUM/locations/global/workloadIdentityPools/ci/attribute.project_path/${REPO}"
gcloud projects add-iam-policy-binding mon-projet --member serviceAccount:mon-app-ci@mon-projet.iam.gserviceaccount.com --role roles/artifactregistry.writer
gcloud projects add-iam-policy-binding mon-projet --member serviceAccount:mon-app-ci@mon-projet.iam.gserviceaccount.com --role roles/run.developer
gcloud projects add-iam-policy-binding mon-projet --member serviceAccount:mon-app-ci@mon-projet.iam.gserviceaccount.com --role roles/iam.serviceAccountUser
echo "GCP_SERVICE_ACCOUNT=mon-app-ci@mon-projet.iam.gserviceaccount.com"
gcloud iam service-accounts create mon-app-ci-infra --project mon-projet
gcloud iam service-accounts add-iam-policy-binding mon-app-ci-infra@mon-projet.iam.gserviceaccount.com --role roles/iam.workloadIdentityUser --member "principalSet://iam.googleapis.com/projects/$NUM/locations/global/workloadIdentityPools/ci/attribute.project_path/${REPO}"
gcloud projects add-iam-policy-binding mon-projet --member serviceAccount:mon-app-ci-infra@mon-projet.iam.gserviceaccount.com --role roles/editor
gcloud projects add-iam-policy-binding mon-projet --member serviceAccount:mon-app-ci-infra@mon-projet.iam.gserviceaccount.com --role roles/resourcemanager.projectIamAdmin
echo "GCP_INFRA_SERVICE_ACCOUNT=mon-app-ci-infra@mon-projet.iam.gserviceaccount.com"
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

## 4. Secrets de l'application

Brancher l'URL de connexion au service — Cloud Run : `gcloud run deploy --set-secrets DATABASE_URL=<secret>:latest` et, pour Cloud SQL, `--add-cloudsql-instances <projet>:<région>:<instance>`.

## 5. Variables CI

6 variable(s) à déclarer (liste dans `PIPELINE.md`). Le script les déclare avec l'outil de la forge, sans écrire les valeurs dans le dépôt :

```bash
bash scripts/ci-variables.sh --dry-run   # ce qui serait déclaré
bash scripts/ci-variables.sh
```

## 6. Premier déploiement

Pousser sur la branche principale : chaque environnement se déploie dans l'ordre.

## 7. Poste de développement

Les mêmes bases qu'en production, en version identique, sur le poste (ports liés à 127.0.0.1, mot de passe `dev`). Les fichiers de `dev/db/init/<base>/` sont joués à la création :

```bash
docker compose -f dev/db/compose.yaml up -d --wait
set -a && . dev/db/app.env && set +a   # variables de connexion pour l'application lancée sur le poste
docker compose -f dev/db/compose.yaml --profile outils up -d adminer   # http://127.0.0.1:8081
```

## 8. Entretien

- Renovate : le job `renovate` tourne dans une planification de pipeline qui porte la variable `RENOVATE=1` (Build › Pipeline schedules, ou par l'API ci-dessous, jeton `api` dans `GITLAB_TOKEN`) ; `RENOVATE_TOKEN` : jeton de projet avec les droits `api` et `write_repository`.

```bash
sid=$(curl -fsS -H "PRIVATE-TOKEN: $GITLAB_TOKEN" -d description=Renovate -d ref=main --data-urlencode "cron=0 4 * * 1-5" "${CI_SERVER_URL:-https://gitlab.com}/api/v4/projects/$(printf %s "$REPO" | jq -sRr @uri)/pipeline_schedules" | jq -r .id)
curl -fsS -H "PRIVATE-TOKEN: $GITLAB_TOKEN" -d key=RENOVATE -d value=1 "${CI_SERVER_URL:-https://gitlab.com}/api/v4/projects/$(printf %s "$REPO" | jq -sRr @uri)/pipeline_schedules/$sid/variables" >/dev/null
```
