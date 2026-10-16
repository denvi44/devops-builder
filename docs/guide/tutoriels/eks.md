# Plateforme sur Amazon EKS

**Objectif** : une application Java déployée par Helm sur un cluster Amazon EKS créé par OpenTofu, avec une
base PostgreSQL managée (Amazon RDS), ses mots de passe dans AWS Secrets Manager lus par External Secrets, et
une CI GitLab qui se connecte à AWS par OIDC, sans clé d'accès stockée.

**Il faut** : un compte AWS et le droit d'y créer des rôles IAM ; un VPC avec des sous-réseaux privés (la pile
s'en sert, elle ne les crée pas) ; un projet GitLab ; sur le poste, `aws`, `tofu` (ou `terraform`) et
`kubectl`. Durée : deux heures environ, dont une demi-heure de création du cluster.

![Le pipeline créé par l'assistant : GitLab, GitLab CI, BuildKit, Renovate, tests, Gitleaks, Trivy, Cosign,
Amazon ECR, AWS, Amazon EKS, OpenTofu, état dans S3, Amazon RDS, Helm, cert-manager, AWS Secrets Manager,
External Secrets, Prometheus et Grafana](../captures/eks.png)

## 1. Décrire le projet

Ctrl+N ouvre l'assistant :

1. **Application** : *Plateforme*, *Java (Maven)*, image *plateforme*, port *8080*.
2. **Code et intégration continue** : *GitLab*.
3. **Hébergement** : *Kubernetes managé d'un cloud*, cloud *AWS*.
4. **Environnements et options** : *Préproduction → production* ; infrastructure *OpenTofu* ; base
   *PostgreSQL* ; secrets *Coffre du cloud*.
5. **Récapitulatif** : « Créer le projet ».

L'assistant choisit les services d'AWS qui vont ensemble : ECR pour les images, EKS pour le cluster, RDS pour
la base, S3 pour l'état OpenTofu, Secrets Manager pour les secrets, et External Secrets pour les amener dans le
cluster.

## 2. Renseigner les paramètres

Deux avertissements R34 restent ; chacun se règle dans le panneau Propriétés de la brique :

- **Amazon EKS** › « Nom du cluster » (par exemple `plateforme`) ;
- **Amazon S3** › « Bucket de l'état Terraform » : un nom unique dans tout AWS (par exemple
  `plateforme-tfstate-123456789012`).

La région (`eu-west-3` par défaut) se règle sur la brique AWS. Paramètres du projet (F2) › « Authentification
cloud en CI » reste sur *Fédération d'identité OIDC (recommandé)*.

## 3. Générer

| Fichier | Rôle |
| --- | --- |
| `.gitlab-ci.yml` | tests et analyses, image poussée dans ECR, plan puis apply OpenTofu (job manuel), déploiement Helm par environnement |
| `infra/terraform/` | la pile : cluster EKS (module officiel), instances RDS, identité d'External Secrets, secrets écrits dans Secrets Manager, backend S3 chiffré et verrouillé ; `terraform.tfvars.example` à copier |
| `charts/plateforme/` | le chart de l'application, avec les `ExternalSecret` qui lisent ses secrets dans le coffre |
| `platform/external-secrets/cluster-secret-store.yaml` | le `ClusterSecretStore` qui relie External Secrets à Secrets Manager |
| `platform/install.sh` | cert-manager, External Secrets, Prometheus et Grafana depuis leurs charts officiels |
| `dev/db/` | la même version de PostgreSQL sur le poste |

## 4. Mettre en route

`docs/mise-en-route.md` donne chaque commande, à exécuter dans l'ordre :

1. **État OpenTofu** : créer le bucket S3 (versionné, accès public bloqué) avant le premier `init`.
2. **Connexion de la CI à AWS** : le fournisseur OIDC de GitLab et deux rôles IAM. Le rôle de déploiement
   n'a que ce qu'il faut (pousser l'image dans le dépôt ECR, lire le cluster) ; le rôle d'infrastructure, aux
   droits étendus, ne sert qu'aux jobs plan et apply. Leurs ARN vont dans `AWS_ROLE_ARN` et
   `AWS_INFRA_ROLE_ARN`. Protéger ces variables (branche principale seulement) : GitLab ne distingue pas les
   jobs dans son jeton.
3. **Premier apply**, depuis le poste : `cp infra/terraform/terraform.tfvars.example infra/terraform/terraform.tfvars`,
   renseigner le VPC, les sous-réseaux et les groupes de la base, puis `tofu init`, `plan`, `apply`. Déclarer son propre rôle IAM dans
   `cluster_admin_arns` pour garder l'administration du cluster quand la CI prendra le relais.
4. **Plateforme** : `bash platform/install.sh` avec le kubeconfig du cluster.
5. **Secrets et External Secrets** : la pile a écrit les mots de passe de RDS dans le coffre ; vérifier le
   `ClusterSecretStore` (READY True) puis, après le premier déploiement, les `ExternalSecret` (SecretSynced).
6. **Variables de la CI** : `bash scripts/ci-variables.sh` (outil `glab`) ; `PIPELINE.md` décrit chaque
   variable, dont le VPC et les sous-réseaux passés à OpenTofu (`TF_VAR_vpc_id`, `TF_VAR_subnet_ids`…).
7. **Premier déploiement** : pousser sur la branche principale.

## 5. Vérifier

- Projet › Valider passe la pile à `tofu fmt` et `tofu validate`, le chart à `helm lint` et à son rendu par
  environnement, les manifestes à kubeconform et la CI au schéma de GitLab, quand ces outils sont installés.
- Sans compte AWS, l'émulateur [Floci](https://floci.io/) peut jouer le plan : ajouter la
  brique Floci, puis `bash scripts/tf-floci.sh plan`. EKS et RDS n'y sont pas créés pour de vrai.
- Sur le cluster : `kubectl -n plateforme rollout status deployment/plateforme`.

## Limites à connaître

Les droits réduits du rôle de déploiement et la création des machines n'ont été vérifiés que par
`tofu validate`, sans apply sur un vrai compte (voir la section « Limites connues » du README). Un seul état
OpenTofu porte tous les environnements.
