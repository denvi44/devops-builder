# Mise en route — Modèle AWS EC2

<!-- Généré par DevOps Builder — à relire avant usage. -->

Les gestes à faire une fois, dans l'ordre, avant le premier pipeline. Chaque section se vérifie avant de passer à la suivante.

## Valeurs à adapter

À poser une fois dans le terminal ; les commandes suivantes les reprennent.

```bash
export REPO="propriétaire/dépôt"   # dépôt de l'application sur la forge
export AWS_ACCOUNT_ID="123456789012"
```

## 1. État Terraform

Le stockage de l'état (Amazon S3) se crée avant le premier `init` : la pile ne le crée pas, elle s'en sert.

```bash
aws s3api create-bucket --bucket mon-projet-tfstate --region eu-west-3 --create-bucket-configuration LocationConstraint=eu-west-3
aws s3api put-bucket-versioning --bucket mon-projet-tfstate --versioning-configuration Status=Enabled
aws s3api put-public-access-block --bucket mon-projet-tfstate --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
```

## 2. Connexion de la CI au cloud

La CI s'authentifie par jeton OIDC (GitHub Actions), sans clé statique, avec deux identités : celle des jobs d'infrastructure (plan, apply), aux droits étendus parce que la pile crée réseaux, clusters et rôles, et celle des autres jobs, limitée à ce qu'ils font. Le jeton de GitHub porte l'environnement du job : seul le plan ou l'apply obtient l'identité d'infrastructure. Une fois par cloud :

**AWS** — fournisseur d'identité OIDC et rôles assumés par la CI ; les ARN affichés vont dans les variables CI. Un refus « AccessDenied » au déploiement nomme l'action manquante, à ajouter à la politique `deploiement`.

```bash
aws iam create-open-id-connect-provider --url https://token.actions.githubusercontent.com --client-id-list sts.amazonaws.com
# déploiement : lire les sorties de l'état Terraform
cat > /tmp/trust-ci.json <<EOF
{"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"Federated": "arn:aws:iam::${AWS_ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com"}, "Action": "sts:AssumeRoleWithWebIdentity", "Condition": {"StringEquals": {"token.actions.githubusercontent.com:aud": "sts.amazonaws.com"}, "StringLike": {"token.actions.githubusercontent.com:sub": ["repo:${REPO}:ref:refs/heads/main", "repo:${REPO}:environment:staging", "repo:${REPO}:environment:production"]}}}]}
EOF
cat > /tmp/policy-ci.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "EtatLecture",
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::mon-projet-tfstate/mon-app/terraform.tfstate"
    },
    {
      "Sid": "EtatListe",
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::mon-projet-tfstate"
    }
  ]
}
EOF
aws iam create-role --role-name mon-app-ci --assume-role-policy-document file:///tmp/trust-ci.json
aws iam put-role-policy --role-name mon-app-ci --policy-name deploiement --policy-document file:///tmp/policy-ci.json
echo "AWS_ROLE_ARN=arn:aws:iam::$AWS_ACCOUNT_ID:role/mon-app-ci"
# infrastructure : la pile crée des rôles IAM (EKS, External Secrets) et des réseaux
cat > /tmp/trust-infra.json <<EOF
{"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"Federated": "arn:aws:iam::${AWS_ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com"}, "Action": "sts:AssumeRoleWithWebIdentity", "Condition": {"StringEquals": {"token.actions.githubusercontent.com:aud": "sts.amazonaws.com"}, "StringLike": {"token.actions.githubusercontent.com:sub": ["repo:${REPO}:ref:refs/heads/main", "repo:${REPO}:pull_request", "repo:${REPO}:environment:production"]}}}]}
EOF
aws iam create-role --role-name mon-app-ci-infra --assume-role-policy-document file:///tmp/trust-infra.json
aws iam attach-role-policy --role-name mon-app-ci-infra --policy-arn arn:aws:iam::aws:policy/AdministratorAccess
echo "AWS_INFRA_ROLE_ARN=arn:aws:iam::$AWS_ACCOUNT_ID:role/mon-app-ci-infra"
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

6 variable(s) à déclarer (liste dans `PIPELINE.md`). Le script les déclare avec l'outil de la forge, sans écrire les valeurs dans le dépôt :

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
