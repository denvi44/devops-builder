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

**Google Cloud** — pool Workload Identity et deux comptes de service ; le nom complet du fournisseur va dans `GCP_WORKLOAD_IDENTITY_PROVIDER`. Déploiement : lire les sorties de l'état Terraform.

```bash
gcloud iam workload-identity-pools create ci --project mon-projet --location global
gcloud iam workload-identity-pools providers create-oidc ci --project mon-projet --location global --workload-identity-pool ci --issuer-uri https://gitlab.com --attribute-mapping "google.subject=assertion.sub,attribute.project_path=assertion.project_path" --attribute-condition "assertion.project_path == '${REPO}'"
NUM="$(gcloud projects describe mon-projet --format="value(projectNumber)")"
gcloud iam service-accounts create mon-app-ci --project mon-projet
gcloud iam service-accounts add-iam-policy-binding mon-app-ci@mon-projet.iam.gserviceaccount.com --role roles/iam.workloadIdentityUser --member "principalSet://iam.googleapis.com/projects/$NUM/locations/global/workloadIdentityPools/ci/attribute.project_path/${REPO}"
gcloud projects add-iam-policy-binding mon-projet --member serviceAccount:mon-app-ci@mon-projet.iam.gserviceaccount.com --role roles/storage.objectViewer
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
cp infra/terraform/terraform.tfvars.example infra/terraform/terraform.tfvars   # valeurs à renseigner, fichier non versionné
tofu -chdir=infra/terraform init
tofu -chdir=infra/terraform plan -out=plan.tfplan
tofu -chdir=infra/terraform apply plan.tfplan
tofu -chdir=infra/terraform output
```

## 4. Hôtes

Noms d'hôte de l'application : chacun pointe (enregistrement DNS A ou AAAA) vers l'hôte de son environnement, joignable depuis Internet sur les ports 80 et 443 ; Traefik y obtient seul le certificat (paramètre « Adresse publique de l'application » de la brique Traefik).

- Préproduction : `staging.mon-app.example.com`
- Production : `mon-app.example.com`

Les machines sont créées par la pile : cloud-init pose le compte `deploy`, la clé de la CI (`TF_VAR_ssh_public_key`) et Docker. Rien à préparer à la main. Pour joindre une machine depuis le poste :

```bash
bash scripts/tf-inventory.sh staging   # écrit l'inventaire de l'environnement
```

## 5. Variables CI

7 variable(s) à déclarer (liste dans `PIPELINE.md`). Le script les déclare avec l'outil de la forge, sans écrire les valeurs dans le dépôt :

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
