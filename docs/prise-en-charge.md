# Prise en charge des briques

Fichier produit par `python -m devops_builder.support` ; un test vérifie qu'il est à jour, et un autre que chaque niveau correspond à ce que les générateurs produisent.

## Niveaux

- **Pris en charge** (140) : les fichiers sont générés et passent l'outil de référence dans les tests (linter, schéma, `tofu validate`, ShellCheck) ; aucune limite connue n'empêche le premier déploiement en suivant `docs/mise-en-route.md`.
- **Expérimental** (8) : les fichiers sont générés, mais une limite connue demande une intervention ou n'a pas été vérifiée ; la règle R50 la rappelle dans le projet.
- **À configurer à la main** (10) : aucun générateur ne produit de fichier ; la brique sert aux règles et à la documentation, elle est listée dans « À configurer à la main » de `PIPELINE.md` (règle R31).

Une entrée du CNCF Landscape sans fiche, ou une fiche personnelle, est toujours à configurer à la main.

## Expérimental

| Brique | Étape | Raison |
| --- | --- | --- |
| AWS CodeBuild | Build | Pas de porte d'approbation native : la production part d'un déclenchement manuel ; secrets de la CI à déclarer à la main. |
| Google Cloud Build | Build | Pas de porte d'approbation native : la production part d'un déclenchement manuel ; secrets de la CI à déclarer à la main. |
| Tekton | Build | Pas de porte d'approbation native : la production part d'un déclenchement manuel ; secrets de la CI à déclarer à la main. |
| Woodpecker CI | Build | Pas de porte d'approbation native : la production part d'un déclenchement manuel ; secrets de la CI à déclarer à la main. |
| Floci | Tests & qualité | Dans la CI, le plan passe ; EKS, RDS et Lambda ne se créent qu'en local, et un apply échoue sur les réseaux existants. |
| RKE2 | Infrastructure | Le contrôleur d'entrée embarqué dépend de la version : à désactiver à la main si un autre contrôleur est posé. |
| Azure Container Apps | Déploiement | Aucune ressource Terraform générée : l'application Container Apps se crée à la main, la CI la met ensuite à jour. |
| Dex | Plateforme | Configuration vérifiée, pas encore exécutée de bout en bout. |

## À configurer à la main

| Brique | Étape | Raison |
| --- | --- | --- |
| Secure Source Manager | Source | Dépôt à créer à la main ; aucune CI générée ne s'y branche. |
| Packer | Build | Modèle d'image à écrire à la main. |
| ansible-lint | Tests & qualité | Aucune étape de CI générée ; les playbooks générés passent ansible-lint dans les tests de l'application. |
| SonarQube Cloud | Tests & qualité | Analyse à brancher à la main dans la CI. |
| AWS CloudFormation | Infrastructure | L'infrastructure générée est écrite en Terraform ou OpenTofu. |
| Azure Bicep | Infrastructure | L'infrastructure générée est écrite en Terraform ou OpenTofu. |
| Outscale Kubernetes as a Service (OKS) | Infrastructure | Aucune ressource Terraform générée ; la prise en charge d'OKS par le provider outscale/outscale reste à vérifier. |
| AWS App Mesh | Plateforme | Service arrêté par AWS, sans générateur. |
| Knative | Plateforme | Installation et services Knative à écrire à la main. |
| Thanos | Observabilité | Installation à écrire à la main, à côté de Prometheus. |

## Pris en charge

- **Source** : AWS CodeCommit, Azure Repos, Bitbucket Cloud, Gitea, GitHub, GitLab
- **Build** : Argo Workflows, Azure Pipelines, Buildah, BuildKit (docker buildx), Cloud Native Buildpacks, Dependabot, Gitea Actions, GitHub Actions, GitLab CI, Jenkins, Kaniko, Renovate
- **Tests & qualité** : Chaos Mesh, Infracost, LitmusChaos, Semgrep CE, SonarQube, Tests unitaires, TFLint
- **Sécurité** : Checkov, Cosign, Gitleaks, Grype, KICS, Kubescape, Snyk, Syft, Trivy
- **Artefacts** : Amazon ECR, Azure Container Registry, Distribution (registry), GitHub Container Registry, Google Artifact Registry, Google Container Registry, Harbor, JFrog Artifactory, Nexus Repository, OVHcloud Managed Private Registry, Scaleway Container Registry, zot
- **Infrastructure** : Amazon EC2, Amazon EKS, Amazon S3, Amazon Web Services, Ansible, Azure Blob Storage, Azure Kubernetes Service, Azure Virtual Machines, Crossplane, Google Cloud, Google Cloud Storage, Google Compute Engine, Google Kubernetes Engine, k3s, kind, kubeadm, MicroK8s, Microsoft Azure, minikube, MinIO, OpenTofu, Outscale, Outscale Object Storage (OOS), Outscale VM, OVHcloud, OVHcloud Managed Kubernetes, OVHcloud Object Storage, OVHcloud Public Cloud Instances, Pulumi, Scaleway, Scaleway Instances, Scaleway Kapsule, Scaleway Object Storage, Terraform
- **Données** : Amazon RDS, Azure Database (serveur flexible), CloudNativePG, Google Cloud SQL, MariaDB, Migrations de schéma, MongoDB, MySQL, OVHcloud Public Cloud Databases, PostgreSQL, Redis, Scaleway Managed Database, Valkey
- **Déploiement** : Amazon ECS (Fargate), Argo CD, Argo Events, Argo Rollouts, Docker Compose, Flux, Google Cloud Run, Helm, Kustomize
- **Plateforme** : AWS Secrets Manager, Azure Key Vault, Calico, cert-manager, Cilium, Envoy Gateway, External Secrets Operator, Falco, Flannel, Google Secret Manager, ingress-nginx, Istio, KEDA, Keycloak, Kyverno, Linkerd, Longhorn, OPA Gatekeeper, OpenBao, Rook (Ceph), SOPS, Traefik, Vault, Velero
- **Observabilité** : Amazon CloudWatch, Azure Monitor, Fluent Bit, Fluentd, Google Cloud Monitoring et Logging, Grafana, Grafana Loki, Grafana Tempo, Jaeger, OpenCost, OpenSearch, OpenTelemetry Collector, Prometheus, Zabbix
