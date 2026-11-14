# Mise en route — Mon projet

<!-- Généré par DevOps Builder — à relire avant usage. -->

Les gestes à faire une fois, dans l'ordre, avant le premier pipeline. Chaque section se vérifie avant de passer à la suivante. Les blocs se collent tels quels dans un terminal (bash ou zsh) ; les remarques sont sous chaque bloc.

## Valeurs à adapter

À poser une fois dans le terminal ; les commandes suivantes les reprennent.

```bash
export REPO="groupe/projet"
```

- `export REPO="groupe/projet"` : dépôt de l'application sur la forge

## 1. Essai à la main, sans CI

Le chemin le plus court pour voir tourner les outils du projet, avant de brancher la CI : sur un hôte Docker (labo, poste de travail, NAS), copier le dossier du projet puis, depuis ce dossier :

```bash
export COMPOSE_FILE=deploy/docker-compose.yml
docker compose up -d traefik prometheus grafana
docker compose ps
```

`docker compose ps` doit montrer chaque service `running` (ou `healthy`) ; le premier démarrage télécharge les images et peut prendre quelques minutes. Journal d'un service qui ne démarre pas : `docker compose logs --tail 30 <service>`.

Le service de l'application (`mon-app`) attend son image, construite et poussée par la CI : il se lance avec le premier déploiement.

`docker compose` absent (NAS, Unraid, vieux Docker) : télécharger le binaire autonome de Compose à côté du projet, sans rien installer sur le système, puis écrire `bin/docker-compose` à la place de `docker compose`.

```bash
mkdir -p bin && curl -SL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64 -o bin/docker-compose && chmod +x bin/docker-compose
bin/docker-compose version
```

## 2. État Terraform

Le stockage de l'état (Scaleway Object Storage) se crée avant le premier `init` : la pile ne le crée pas, elle s'en sert.

```bash
export AWS_ACCESS_KEY_ID="$SCW_ACCESS_KEY" AWS_SECRET_ACCESS_KEY="$SCW_SECRET_KEY"
aws s3api create-bucket --bucket mon-projet-tfstate --endpoint-url https://s3.fr-par.scw.cloud
aws s3api put-bucket-versioning --bucket mon-projet-tfstate --endpoint-url https://s3.fr-par.scw.cloud --versioning-configuration Status=Enabled
```

## 3. Premier apply

Le premier passage se fait depuis le poste (ou par le job manuel de la CI) ; les suivants passent par la CI.

```bash
cp infra/terraform/terraform.tfvars.example infra/terraform/terraform.tfvars
tofu -chdir=infra/terraform init
tofu -chdir=infra/terraform plan -out=plan.tfplan
tofu -chdir=infra/terraform apply plan.tfplan
tofu -chdir=infra/terraform output
```

- `cp infra/terraform/terraform.tfvars.example infr…` : valeurs à renseigner, fichier non versionné

## 4. Hôtes

Noms d'hôte de l'application : chacun pointe (enregistrement DNS A ou AAAA) vers l'hôte de son environnement, joignable depuis Internet sur les ports 80 et 443 ; Traefik y obtient seul le certificat (paramètre « Adresse publique de l'application » de la brique Traefik).

- Développement : `dev.mon-app.example.com`
- Recette : `recette.mon-app.example.com`
- Production : `mon-app.example.com`

Les machines sont créées par la pile : cloud-init pose le compte `deploy`, la clé de la CI (`TF_VAR_ssh_public_key`) et Docker. Rien à préparer à la main. Pour joindre une machine depuis le poste :

```bash
bash scripts/tf-inventory.sh dev
```

- `bash scripts/tf-inventory.sh dev` : écrit l'inventaire de l'environnement

## 5. Variables CI

7 variable(s) à déclarer (liste dans `PIPELINE.md`). Le script les déclare avec l'outil de la forge, sans écrire les valeurs dans le dépôt :

```bash
bash scripts/ci-variables.sh --dry-run
bash scripts/ci-variables.sh
```

- `bash scripts/ci-variables.sh --dry-run` : ce qui serait déclaré

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
