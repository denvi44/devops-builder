# Mise en route — Mon projet

<!-- Généré par DevOps Builder — à relire avant usage. -->

Les gestes à faire une fois, dans l'ordre, avant le premier pipeline. Chaque section se vérifie avant de passer à la suivante.

## 1. Premier apply

Le premier passage se fait depuis le poste (ou par le job manuel de la CI) ; les suivants passent par la CI.

```bash
cp infra/terraform/terraform.tfvars.example infra/terraform/terraform.tfvars   # valeurs à renseigner, fichier non versionné
tofu -chdir=infra/terraform init
tofu -chdir=infra/terraform plan -out=plan.tfplan
tofu -chdir=infra/terraform apply plan.tfplan
tofu -chdir=infra/terraform output
```

EKS donne l'administration du cluster à l'identité qui applique la pile : celle du poste au premier apply, puis le rôle d'infrastructure de la CI. Pour garder l'accès, déclarer son rôle IAM dans `cluster_admin_arns` (terraform.tfvars) ; le rôle de déploiement de la CI y entre par `ci_deploy_role_arn`.

## 2. Cluster et plateforme

Avec le kubeconfig du cluster, une fois :

```bash
kubectl config current-context
bash platform/install.sh
kubectl get pods -A | grep -v Running   # rien ne doit rester en attente
```

## 3. Premier déploiement

Pousser sur la branche principale : chaque environnement se déploie dans l'ordre, la production après approbation.

```bash
kubectl -n mon-app rollout status deployment/mon-app
kubectl -n mon-app get pods
```

## 4. Entretien

- Renovate : job planifié (quotidien) avec l'image `renovate/renovate:44.164.5` et `RENOVATE_TOKEN`.
