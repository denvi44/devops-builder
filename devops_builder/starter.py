"""Assistant de démarrage : quelques réponses → un pipeline complet et cohérent.

La fonction `build_starter` ne dépend pas de l'interface ; les tests vérifient que
toutes les combinaisons de réponses donnent un pipeline sans erreur bloquante.
"""

from __future__ import annotations

from dataclasses import dataclass

from .catalog import Catalog
from .model import Project, env_preset

FORGES = {
    "gitlab": "GitLab",
    "github": "GitHub",
    "gitea": "Gitea",
    "bitbucket": "Bitbucket Cloud",
    "azure-repos": "Azure Repos",
}
NATIVE_CI = {
    "gitlab": "gitlab-ci",
    "github": "github-actions",
    "gitea": "gitea-actions",
    "bitbucket": "woodpecker",
    "azure-repos": "azure-pipelines",
}
HOSTINGS = {
    "docker-host": "Un serveur avec Docker",
    "vm": "Des machines virtuelles (Ansible)",
    "kubernetes": "Kubernetes autogéré (k3s)",
    "kubernetes-managed": "Kubernetes managé d'un cloud",
    "serverless": "Conteneurs serverless d'un cloud",
}
CLOUDS = {
    "aws": "AWS", "gcp": "Google Cloud", "azure": "Azure",
    "ovhcloud": "OVHcloud", "scaleway": "Scaleway", "outscale": "Outscale",
}
SERVERLESS_CLOUDS = ("aws", "gcp", "azure")
SECNUMCLOUD_CLOUDS = ("outscale", "ovhcloud")
OBSERVABILITY = {"prometheus": "Prometheus et Grafana", "cloud": "Service du cloud", "none": "Aucune"}
IAC = {"opentofu": "OpenTofu", "terraform": "Terraform", "none": "Aucune"}


@dataclass
class StarterAnswers:
    name: str = "Mon projet"
    language: str = "python"
    image_name: str = "mon-app"
    port: int = 8000
    forge: str = "gitlab"
    ci: str | None = None             # None : CI native de la forge
    hosting: str = "docker-host"
    cloud: str | None = None          # pour « kubernetes-managed » et « serverless »
    secnumcloud: bool = False
    envs: str = "staging-prod"
    gitops: bool = False              # Kubernetes seulement
    security: bool = True             # Gitleaks, Trivy, Cosign
    quality: bool = False             # SonarQube
    observability: str = "prometheus"
    dependencies: bool = True         # Renovate ou Dependabot
    iac: str = "opentofu"             # pour un cloud


def clouds_for(hosting: str, secnumcloud: bool) -> list[str]:
    """Clouds proposés selon l'hébergement et l'exigence SecNumCloud."""
    if hosting == "serverless":
        options = list(SERVERLESS_CLOUDS)
    elif hosting == "kubernetes-managed":
        options = list(CLOUDS)
    else:
        return []
    if secnumcloud:
        options = [c for c in options if c in SECNUMCLOUD_CLOUDS]
    return options


def validate(a: StarterAnswers) -> list[str]:
    """Problèmes bloquants dans les réponses (affichés par l'assistant avant de créer)."""
    problems = []
    if a.forge not in FORGES:
        problems.append("Forge inconnue.")
    if a.hosting in ("kubernetes-managed", "serverless"):
        allowed = clouds_for(a.hosting, a.secnumcloud)
        if not allowed:
            problems.append("Aucun cloud qualifié SecNumCloud ne propose de conteneurs serverless ici : "
                            "choisir Kubernetes managé ou un hébergement autogéré.")
        elif a.cloud not in allowed:
            problems.append("Choisir un cloud compatible avec cet hébergement.")
    return problems


def build_starter(a: StarterAnswers, catalog: Catalog) -> Project:
    problems = validate(a)
    if problems:
        raise ValueError(" ".join(problems))
    p = Project(name=a.name.strip() or "Mon projet", environments=env_preset(a.envs), secnumcloud=a.secnumcloud)
    p.app.language = a.language
    p.app.image_name = a.image_name.strip() or "mon-app"
    p.app.port = a.port
    p.target = {"serverless": "docker-host"}.get(a.hosting, a.hosting)

    def add(tool_id: str, **params) -> None:
        if tool_id in catalog and not p.bricks_for(tool_id):
            p.add(tool_id, catalog[tool_id].stage, **params)

    cloud = a.cloud if a.hosting in ("kubernetes-managed", "serverless") else None
    provider = catalog.get(cloud) if cloud else None

    # Code, CI, build
    add(a.forge)
    ci = a.ci or NATIVE_CI[a.forge]
    add(ci)
    add("buildah" if ci == "tekton" else "buildkit")
    add("unit-tests")
    if a.quality:
        add("sonarqube")
    if a.dependencies:
        add("dependabot" if a.forge == "github" else "renovate")

    # Registre
    if provider and provider.services.get("registry"):
        add(provider.services["registry"])
    elif a.forge == "github":
        add("ghcr")
    elif a.forge != "gitlab":  # GitLab fournit son registre
        add("harbor")

    # Sécurité
    if a.security:
        add("gitleaks")
        add("trivy")
        add("cosign")

    # Hébergement
    if provider:
        add(provider.id)
    if a.hosting == "docker-host":
        add("docker-compose")
        add("traefik")
    elif a.hosting == "vm":
        add("ansible")
        add("docker-compose")
        add("traefik")
    elif a.hosting == "kubernetes":
        add("k3s")
        add("helm")
        add("traefik")
        add("cert-manager")
    elif a.hosting == "kubernetes-managed" and provider:
        add(provider.services["k8s.managed"])
        add("helm")
        add("cert-manager")
    elif a.hosting == "serverless" and provider:
        add(provider.services["containers"])
    if a.gitops and a.hosting in ("kubernetes", "kubernetes-managed"):
        add("argo-cd")

    # Infrastructure as code pour un cloud
    if provider and a.iac != "none":
        add(a.iac)
        storage = provider.services.get("object-storage")
        if storage in ("s3", "gcs", "azure-blob"):
            add(storage)

    # Observabilité
    if a.observability == "prometheus" and a.hosting != "serverless":
        add("prometheus")
        add("grafana")
    elif a.observability == "cloud" and provider and provider.services.get("observability"):
        add(provider.services["observability"])
    return p
