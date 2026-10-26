# Mise en route — Modèle Azure VM

<!-- Généré par DevOps Builder — à relire avant usage. -->

Les gestes à faire une fois, dans l'ordre, avant le premier pipeline. Chaque section se vérifie avant de passer à la suivante.

## Valeurs à adapter

À poser une fois dans le terminal ; les commandes suivantes les reprennent.

```bash
export REPO="propriétaire/dépôt"   # dépôt de l'application sur la forge
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

**Azure** — deux applications Entra ID et leurs identifiants fédérés ; `AZURE_TENANT_ID` et `AZURE_SUBSCRIPTION_ID` en variables CI. Déploiement, sur le seul groupe de ressources du projet : lire les sorties de l'état Terraform.

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
az ad app federated-credential create --id "$APP_ID" --parameters '{"name": "ci-2", "issuer": "https://token.actions.githubusercontent.com", "subject": "'"repo:${REPO}:environment:staging"'", "audiences": ["api://AzureADTokenExchange"]}'
az ad app federated-credential create --id "$APP_ID" --parameters '{"name": "ci-3", "issuer": "https://token.actions.githubusercontent.com", "subject": "'"repo:${REPO}:environment:production"'", "audiences": ["api://AzureADTokenExchange"]}'
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

## 4. Secrets de l'application

Une paire de clés age pour le projet. La clé publique va dans la brique SOPS (paramètre « Destinataires age ») : régénérer le projet pour mettre `.sops.yaml` à jour. La clé privée va dans la variable CI `SOPS_AGE_KEY`.

```bash
mkdir -p ~/.config/sops/age
age-keygen -o ~/.config/sops/age/keys.txt   # affiche la clé publique age1…
export SOPS_AGE_KEY_FILE=~/.config/sops/age/keys.txt
```

Puis, avec `.sops.yaml` à jour, chiffrer les valeurs de chaque environnement :

```bash
POSTGRESQL_PASSWORD="$(openssl rand -hex 24)" bash scripts/secrets-seed.sh staging
POSTGRESQL_PASSWORD="$(openssl rand -hex 24)" bash scripts/secrets-seed.sh production
git add deploy/secrets/*.enc.env .sops.yaml && git commit -m "secrets chiffrés"
```

Nouvelle clé publique (arrivée ou départ) : la brique, puis `sops updatekeys deploy/secrets/*.enc.env`.

## 5. Hôtes

Noms d'hôte de l'application : chacun pointe (enregistrement DNS A ou AAAA) vers l'hôte de son environnement, joignable depuis Internet sur les ports 80 et 443 ; Traefik y obtient seul le certificat (paramètre « Adresse publique de l'application » de la brique Traefik).

- Préproduction : `staging.mon-app.example.com`
- Production : `mon-app.example.com`

Les machines sont créées par la pile : cloud-init pose le compte `deploy`, la clé de la CI (`TF_VAR_ssh_public_key`) et Docker. Rien à préparer à la main. Pour joindre une machine depuis le poste :

```bash
bash scripts/tf-inventory.sh staging   # écrit l'inventaire de l'environnement
```

## 6. Variables CI

8 variable(s) à déclarer (liste dans `PIPELINE.md`). Le script les déclare avec l'outil de la forge, sans écrire les valeurs dans le dépôt :

```bash
bash scripts/ci-variables.sh --dry-run   # ce qui serait déclaré
bash scripts/ci-variables.sh
```

## 7. Premier déploiement

Pousser sur la branche principale : chaque environnement se déploie dans l'ordre, la production après approbation.

```bash
ssh "<hôte>" "cd /opt/mon-app && docker compose -p mon-app ps"
```

## 8. Essai à la main, sans CI

Pour essayer la pile sur un hôte Docker sans passer par la CI (labo, poste de travail, NAS), copier le dossier du projet sur l'hôte puis, depuis ce dossier :

```bash
POSTGRESQL_PASSWORD="$(openssl rand -hex 24)" sh deploy/secrets.sh deploy/secrets   # écrit deploy/secrets/ (ne pas le partager)
export COMPOSE_FILE=deploy/docker-compose.yml   # les commandes compose s'appliquent au projet
docker compose version   # absente ? voir la remarque ci-dessous
docker compose config --services     # les services du projet
docker compose up -d <service> ...   # ceux à lancer ; sans nom : tous
docker compose ps
```

Les services de l'application ont besoin de leur image (construite et poussée par la CI) : à l'essai, ne lancer que les services de plateforme (bases, Zabbix, Keycloak…).

`docker compose` absent (NAS, Unraid, vieux Docker) : télécharger le binaire autonome de Compose à côté du projet, sans rien installer sur le système.

```bash
mkdir -p bin && curl -SL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64 -o bin/docker-compose && chmod +x bin/docker-compose
bin/docker-compose version   # puis bin/docker-compose à la place de docker compose
```

## 9. Sauvegardes

Sur l'hôte, une sauvegarde puis une restauration d'essai (la restauration remplace la base) :

```bash
sudo /opt/mon-app-staging/db-backup.sh /opt/mon-app-staging /var/backups/mon-app-staging
last="$(sudo ls -t /var/backups/mon-app-staging | head -n 1)"
sudo /opt/mon-app-staging/db-restore.sh /opt/mon-app-staging "/var/backups/mon-app-staging/$last" --oui
```

## 10. Poste de développement

Les mêmes bases qu'en production, en version identique, sur le poste (ports liés à 127.0.0.1, mot de passe `dev`). Les fichiers de `dev/db/init/<base>/` sont joués à la création :

```bash
docker compose -f dev/db/compose.yaml up -d --wait
set -a && . dev/db/app.env && set +a   # variables de connexion pour l'application lancée sur le poste
docker compose -f dev/db/compose.yaml --profile outils up -d adminer   # http://127.0.0.1:8081
```

## 11. Entretien

- Sauvegardes : `scripts/db-backup.sh` planifiée par Ansible ; copier les fichiers hors de la machine et tester une restauration (section Sauvegardes).
- Rotation d'un mot de passe : nouvelle valeur par `scripts/secrets-seed.sh`, puis redéploiement.
