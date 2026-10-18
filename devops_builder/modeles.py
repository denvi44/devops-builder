# SPDX-License-Identifier: Apache-2.0
"""Pipelines types par fournisseur cloud : les services du fournisseur qui vont ensemble, prêts à ajuster.

Chaque modèle est construit par l'assistant à partir de réponses fixées, avec le catalogue du moment : il suit
donc les fiches et les règles, sans fichier figé à entretenir. Il ne garde aucune erreur bloquante ; seules
restent les valeurs propres au projet (nom du cluster, bucket de l'état…), signalées par R34.
"""

from __future__ import annotations

from dataclasses import dataclass

from .catalog import Catalog
from .model import Project
from .starter import StarterAnswers, build_starter


@dataclass(frozen=True)
class Modele:
    slug: str
    title: str
    description: str
    answers: StarterAnswers
    fix: tuple[str, ...] = ()  # règles dont la première correction est appliquée d'office


def _a(name: str, **kw) -> StarterAnswers:
    base = {"name": name, "envs": "staging-prod", "database": "postgresql", "iac": "opentofu"}
    return StarterAnswers(**{**base, **kw})


MODELES: dict[str, Modele] = {m.slug: m for m in (
    Modele("aws", "AWS",
           "Amazon EKS, ECR, RDS PostgreSQL, Secrets Manager lu par External Secrets, CloudWatch ; état OpenTofu "
           "dans S3 ; GitHub Actions connecté à AWS par OIDC, sans clé stockée.",
           _a("Modèle AWS", forge="github", hosting="kubernetes-managed", cloud="aws", secrets="cloud",
              observability="cloud")),
    Modele("gcp", "Google Cloud",
           "GKE, Artifact Registry, Cloud SQL PostgreSQL, Secret Manager lu par External Secrets, Cloud Monitoring ; "
           "état OpenTofu dans Cloud Storage ; GitLab CI par Workload Identity Federation, sans clé stockée.",
           _a("Modèle Google Cloud", forge="gitlab", hosting="kubernetes-managed", cloud="gcp", secrets="cloud",
              observability="cloud")),
    Modele("azure", "Azure",
           "AKS, Azure Container Registry, Azure Database pour PostgreSQL (serveur flexible), Key Vault lu par "
           "External Secrets, Azure Monitor ; état OpenTofu dans Blob Storage ; GitHub Actions par fédération "
           "d'identité Entra ID, sans secret stocké.",
           _a("Modèle Azure", forge="github", hosting="kubernetes-managed", cloud="azure", secrets="cloud",
              observability="cloud")),
    Modele("ovhcloud", "OVHcloud",
           "Managed Kubernetes, Managed Private Registry, Public Cloud Databases PostgreSQL ; état OpenTofu dans "
           "Object Storage ; secrets chiffrés dans le dépôt (SOPS et age) ; Prometheus et Grafana ; GitLab CI avec "
           "les clés d'API d'OVHcloud.",
           _a("Modèle OVHcloud", forge="gitlab", hosting="kubernetes-managed", cloud="ovhcloud", secrets="sops")),
    Modele("scaleway", "Scaleway",
           "Kapsule, Container Registry, Managed Database PostgreSQL ; état OpenTofu dans Object Storage ; secrets "
           "chiffrés dans le dépôt (SOPS et age) ; Prometheus et Grafana ; GitLab CI avec les clés d'API de "
           "Scaleway.",
           _a("Modèle Scaleway", forge="gitlab", hosting="kubernetes-managed", cloud="scaleway", secrets="sops")),
    Modele("outscale", "Outscale (SecNumCloud)",
           "Exigence SecNumCloud : machines virtuelles créées par OpenTofu et configurées par Ansible, Docker Compose "
           "et Traefik, PostgreSQL sur chaque machine ; état dans le stockage objet d'Outscale ; secrets chiffrés "
           "dans le dépôt (SOPS et age) ; GitLab CI avec les clés d'accès d'Outscale. Le Kubernetes managé d'Outscale "
           "(OKS) n'a pas encore de ressource OpenTofu générée.",
           _a("Modèle Outscale (SecNumCloud)", forge="gitlab", hosting="vm", cloud="outscale", secnumcloud=True,
              secrets="sops")),
    Modele("aws-ecs", "AWS — ECS Fargate",
           "Conteneurs serverless sur ECS Fargate, ECR, RDS PostgreSQL, Secrets Manager ; sans cluster à administrer ; "
           "journaux dans CloudWatch ; GitHub Actions connecté à AWS par OIDC.",
           _a("Modèle AWS ECS", forge="github", hosting="serverless", cloud="aws", secrets="cloud")),
    Modele("aws-ec2", "AWS — machines EC2",
           "Une instance EC2 par environnement, Ansible, Docker Compose et Traefik, PostgreSQL sur la machine ; "
           "secrets chiffrés dans le dépôt (SOPS et age).",
           _a("Modèle AWS EC2", forge="github", hosting="vm", cloud="aws", secrets="sops"), fix=("R52",)),
    Modele("gcp-cloud-run", "Google Cloud — Cloud Run",
           "Cloud Run, Artifact Registry, Cloud SQL PostgreSQL, Secret Manager ; GitLab CI par Workload Identity "
           "Federation.",
           _a("Modèle Google Cloud Run", forge="gitlab", hosting="serverless", cloud="gcp", secrets="cloud")),
    Modele("azure-vm", "Azure — machines virtuelles",
           "Une machine virtuelle Azure par environnement, Ansible, Docker Compose et Traefik ; secrets chiffrés dans "
           "le dépôt (SOPS et age).",
           _a("Modèle Azure VM", forge="github", hosting="vm", cloud="azure", secrets="sops"), fix=("R52",)),
    Modele("ovhcloud-vm", "OVHcloud — instances",
           "Une instance Public Cloud par environnement, Ansible, Docker Compose et Traefik ; secrets chiffrés dans "
           "le dépôt (SOPS et age). Pas de pare-feu généré : à poser à la main.",
           _a("Modèle OVHcloud instances", forge="gitlab", hosting="vm", cloud="ovhcloud", secrets="sops"), fix=("R52",)),
    Modele("scaleway-instance", "Scaleway — instance Docker",
           "Une instance Scaleway par environnement, Docker Compose déployé par SSH derrière Traefik ; secrets "
           "chiffrés dans le dépôt (SOPS et age). Le plus simple, pour une petite application.",
           _a("Modèle Scaleway instance", forge="gitlab", hosting="docker-host", cloud="scaleway", secrets="sops"), fix=("R52",)),
)}


def build(slug: str, catalog: Catalog) -> Project:
    """Projet du modèle ; KeyError si le modèle n'existe pas."""
    modele = MODELES[slug]
    project = build_starter(modele.answers, catalog)
    project.description = modele.description
    if modele.fix:
        from .rules import RuleEngine, apply_action
        for rule_id in modele.fix:
            for diag in [d for d in RuleEngine(catalog).evaluate(project) if d.rule_id == rule_id and d.actions]:
                apply_action(project, diag.actions[0], catalog)
    return project
