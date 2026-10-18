# Pipelines types par fournisseur cloud

Douze modèles donnent, pour chaque fournisseur du catalogue, un pipeline complet avec les services du fournisseur
qui vont ensemble : un Kubernetes managé par fournisseur, et des variantes plus simples (conteneurs serverless
ou machines). On les ouvre par **Fichier › Nouveau depuis un modèle de fournisseur**, ou en ligne de
commande ; on ajuste ensuite comme n'importe quel projet (briques, paramètres, environnements).

```bash
devops-builder template
devops-builder template aws -o mon-projet.devops.yaml
```

Chaque modèle compte deux environnements (préproduction, puis production après approbation), une application
avec sa base PostgreSQL, l'infrastructure en OpenTofu et les contrôles de sécurité (Gitleaks, Trivy, Cosign). Il
ne garde aucune erreur bloquante ; restent seulement les valeurs propres au projet — nom du cluster, bucket de
l'état OpenTofu, identifiant du projet cloud… —, signalées en avertissement (R34) jusqu'à ce qu'on les renseigne
dans le panneau Propriétés. Les modèles sont construits avec le catalogue du moment : ils suivent les fiches et
les règles de la version installée.

| Modèle | Commande | Cluster et registre | Base | Secrets | Supervision | CI et connexion au cloud |
| --- | --- | --- | --- | --- | --- | --- |
| AWS | `devops-builder template aws` | Amazon EKS, ECR | Amazon RDS | Secrets Manager, lu par External Secrets | CloudWatch | GitHub Actions, OIDC |
| Google Cloud | `devops-builder template gcp` | GKE, Artifact Registry | Cloud SQL | Secret Manager, lu par External Secrets | Cloud Monitoring | GitLab CI, Workload Identity Federation |
| Azure | `devops-builder template azure` | AKS, Azure Container Registry | Azure Database (serveur flexible) | Key Vault, lu par External Secrets | Azure Monitor | GitHub Actions, fédération Entra ID |
| OVHcloud | `devops-builder template ovhcloud` | Managed Kubernetes, Managed Private Registry | Public Cloud Databases | SOPS et age, dans le dépôt | Prometheus, Grafana | GitLab CI, clés d'API |
| Scaleway | `devops-builder template scaleway` | Kapsule, Container Registry | Managed Database | SOPS et age, dans le dépôt | Prometheus, Grafana | GitLab CI, clés d'API |
| Outscale (SecNumCloud) | `devops-builder template outscale` | machines virtuelles, Ansible, Docker Compose et Traefik | PostgreSQL sur chaque machine | SOPS et age, dans le dépôt | Prometheus, Grafana | GitLab CI, clés d'accès |

## Variantes sans Kubernetes

| Commande | Hébergement | Ce qui change |
| --- | --- | --- |
| `devops-builder template aws-ecs` | ECS Fargate | pas de cluster à administrer ; RDS, Secrets Manager, journaux CloudWatch |
| `devops-builder template aws-ec2` | une instance EC2 par environnement | Ansible, Docker Compose, Traefik ; secrets SOPS ; type de machine choisi d'après les services |
| `devops-builder template gcp-cloud-run` | Cloud Run | Cloud SQL, Secret Manager |
| `devops-builder template azure-vm` | une machine virtuelle par environnement | Ansible, Docker Compose, Traefik ; secrets SOPS |
| `devops-builder template ovhcloud-vm` | une instance Public Cloud par environnement | idem ; pas de pare-feu généré, à poser à la main |
| `devops-builder template scaleway-instance` | une instance par environnement | Docker Compose par SSH, le plus simple |

L'état OpenTofu va dans le stockage objet du fournisseur (S3, Cloud Storage, Blob Storage, Object Storage
d'OVHcloud et de Scaleway, OOS d'Outscale), chiffré et verrouillé, sauf chez Outscale dont le stockage objet n'offre
pas de verrou d'état.

## Choix faits par les modèles

- **Connexion de la CI** : OIDC chez AWS, Google Cloud et Azure, sans clé stockée ; deux identités, l'une pour les
  jobs d'infrastructure, l'autre limitée au déploiement. OVHcloud, Scaleway et Outscale n'offrent pas de
  fédération d'identité pour la CI : leurs clés sont des variables protégées, à renouveler.
- **Secrets** : le coffre du fournisseur quand il en a un, lu dans le cluster par External Secrets ; sinon SOPS
  et age, les valeurs chiffrées dans le dépôt.
- **Supervision** : le service du fournisseur quand il en a un, Prometheus et Grafana sinon.
- **Outscale** : l'exigence SecNumCloud est activée, et le déploiement passe par des machines virtuelles, le
  Kubernetes managé d'Outscale (OKS) n'ayant pas encore de ressource OpenTofu générée. Le tutoriel
  [souverain](tutoriels/souverain.md) déroule ce modèle de bout en bout.

## Après l'ouverture

1. Renseigner les valeurs signalées dans les diagnostics, puis enregistrer (Ctrl+S).
2. Adapter l'application : Projet › Application (Ctrl+Maj+A) pour désigner son dossier, le langage et le port.
3. Générer (Ctrl+G) et suivre `docs/mise-en-route.md` : création du stockage de l'état, connexion de la CI au
   cloud, premier apply, plateforme, variables de la CI, premier déploiement. Le tutoriel
   [Amazon EKS](tutoriels/eks.md) en détaille chaque étape pour AWS ; elles sont les mêmes ailleurs, avec les
   services du fournisseur.
