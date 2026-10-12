"""Assistant de démarrage : quelques réponses → un pipeline complet et cohérent.

La fonction `build_starter` ne dépend pas de l'interface ; les tests vérifient que
toutes les combinaisons de réponses donnent un pipeline sans erreur bloquante.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .catalog import Catalog
from .generators.iac import REMOTE_BACKENDS
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
DATABASES = {"none": "Aucune", "postgresql": "PostgreSQL", "mysql": "MySQL", "mariadb": "MariaDB",
             "mongodb": "MongoDB"}
SECRETS = {"ci": "Variables de la CI", "sops": "Chiffrés dans le dépôt (SOPS + age)",
           "openbao": "Coffre OpenBao", "cloud": "Coffre du cloud"}
SECRET_CLOUDS = ("aws", "gcp", "azure")
IDENTITY = {"none": "Aucune", "keycloak": "Keycloak (comptes et groupes)", "dex": "Dex (comptes de la forge)"}  # fournisseurs dont la fiche porte un coffre de secrets
# Valeur du paramètre « engine » d'une base managée, selon le moteur demandé
MANAGED_ENGINE_PARAM = {
    "aws-rds": {"postgresql": "postgres", "mysql": "mysql", "mariadb": "mariadb"},
    "cloud-sql": {"postgresql": "postgres", "mysql": "mysql", "mariadb": "mysql"},
    "azure-database": {"postgresql": "postgres", "mysql": "mysql", "mariadb": "mysql"},
    "scaleway-rdb": {"postgresql": "PostgreSQL-16", "mysql": "MySQL-8", "mariadb": "MySQL-8"},
    "ovh-databases": {"postgresql": "postgresql", "mysql": "mysql", "mariadb": "mysql"},
}
SERVERLESS_TOOLS = ("cloud-run", "ecs-fargate", "azure-container-apps")


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
    shared_host: bool = False         # hôte Docker : environnements hors production sur une même machine
    dockerfile: bool = True           # sans Dockerfile, l'image est construite par Buildpacks
    k8s_deploy: str = "helm"          # « helm » ou « kustomize » (déjà présent dans l'application)
    dependency_tool: str | None = None  # outil déjà configuré dans l'application
    source: str = ""                  # dossier de l'application analysée
    database: str = "none"            # moteur de la base principale (DATABASES)
    cache: bool = False               # stockage clé-valeur Valkey (cache, sessions)
    migrations: str = ""              # commande de migration de schéma, détectée dans l'application
    secrets: str = "ci"               # source des secrets de l'application (SECRETS)
    connections: dict = field(default_factory=dict)  # variable et format de connexion détectés, par famille
    identity: str = "none"            # connexion unique des outils et de l'application (IDENTITY)


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


def host_clouds(hosting: str, secnumcloud: bool) -> list[str]:
    """Clouds où créer les machines d'un hôte Docker ou de VM (facultatif : sinon, serveurs existants)."""
    if hosting not in ("docker-host", "vm"):
        return []
    return [c for c in CLOUDS if not secnumcloud or c in SECNUMCLOUD_CLOUDS]


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
    elif a.hosting in ("docker-host", "vm") and a.cloud is not None and a.cloud not in host_clouds(a.hosting, a.secnumcloud):
        problems.append("Ce cloud ne convient pas (SecNumCloud) : choisir Outscale, OVHcloud ou des serveurs existants.")
    if a.hosting == "serverless" and a.identity != "none":
        problems.append("Serverless : pas de fournisseur d'identité déployé avec l'application ; utiliser celui "
                        "du cloud (Cognito, Identity Platform, Entra ID).")
    if a.hosting == "serverless" and a.secrets in ("sops", "openbao"):
        problems.append("Serverless : le service lit ses secrets dans le coffre du cloud ; choisir ce coffre ou "
                        "les variables de la CI.")
    if a.secrets == "cloud" and (a.hosting not in ("kubernetes-managed", "serverless") or a.cloud not in SECRET_CLOUDS):
        problems.append("Coffre du cloud : avec Kubernetes managé ou serverless chez AWS, Google Cloud ou Azure ; "
                        "sinon choisir OpenBao ou SOPS.")
    return problems


def database_brick(engine: str, project: Project, catalog: Catalog) -> tuple[str, dict]:
    """Brique qui porte ce moteur dans ce projet : service managé du cloud, opérateur ou conteneur."""
    from .databases import ENGINES
    ids = project.tool_ids()
    cluster = any((t := catalog.get(i)) and "kubernetes-cluster" in t.roles for i in ids)
    kube = project.target in ("kubernetes", "kubernetes-managed") or cluster
    serverless = any(i in SERVERLESS_TOOLS for i in ids)
    if engine == "redis":
        engine = "valkey"
    if ENGINES[engine].family == "sql" and (project.target == "kubernetes-managed" or serverless):
        for pid in sorted(ids):
            prov = catalog.get(pid)
            svc = prov.services.get("database") if prov and prov.kind == "provider" else None
            if svc and svc in catalog:
                value = MANAGED_ENGINE_PARAM.get(svc, {}).get(engine)
                default = catalog[svc].param_schema.get("engine")
                params = {"engine": value} if value and default and value != default.default else {}
                return svc, params
    if engine == "postgresql" and kube:
        return "cloudnative-pg", {}
    return engine, {}


def build_starter(a: StarterAnswers, catalog: Catalog) -> Project:
    problems = validate(a)
    if problems:
        raise ValueError(" ".join(problems))
    p = Project(name=a.name.strip() or "Mon projet", environments=env_preset(a.envs), secnumcloud=a.secnumcloud)
    if a.shared_host and a.hosting in ("docker-host", "vm"):
        for env in p.environments:
            if env.kind != "production":
                env.host = "hors-production"  # une machine pour tous les environnements hors production
    p.app.language = a.language
    p.app.image_name = a.image_name.strip() or "mon-app"
    p.app.port = a.port
    p.app.source = a.source
    p.target = {"serverless": "docker-host"}.get(a.hosting, a.hosting)

    def add(tool_id: str, **params) -> None:
        if tool_id in catalog and not p.bricks_for(tool_id):
            p.add(tool_id, catalog[tool_id].stage, **params)

    vm_cloud = a.hosting in ("docker-host", "vm") and a.cloud is not None  # machines créées par Terraform
    cloud = a.cloud if a.hosting in ("kubernetes-managed", "serverless") or vm_cloud else None
    provider = catalog.get(cloud) if cloud else None

    # Code, CI, build
    add(a.forge)
    ci = a.ci or NATIVE_CI[a.forge]
    add(ci)
    add("buildah" if ci == "tekton" else "buildkit" if a.dockerfile else "buildpacks")
    add("unit-tests")
    if a.quality:
        add("sonarqube")
    if a.dependencies:
        tool = a.dependency_tool if a.dependency_tool in ("renovate", "dependabot") else None
        if tool == "dependabot" and a.forge != "github":
            tool = None
        add(tool or ("dependabot" if a.forge == "github" else "renovate"))

    # Registre (sur des machines, celui de la forge : les hôtes s'y connectent avec les identifiants de la CI)
    if provider and provider.services.get("registry") and not vm_cloud:
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
        add("kustomize" if a.k8s_deploy == "kustomize" else "helm")
        add("traefik")
        add("cert-manager")
    elif a.hosting == "kubernetes-managed" and provider:
        add(provider.services["k8s.managed"])
        add("kustomize" if a.k8s_deploy == "kustomize" else "helm")
        add("cert-manager")
    elif a.hosting == "serverless" and provider:
        add(provider.services["containers"])
    if a.gitops and a.hosting in ("kubernetes", "kubernetes-managed"):
        add("argo-cd")

    # Machines créées par Terraform / OpenTofu (hôte Docker ou VM sur un cloud)
    if vm_cloud and provider and provider.services.get("compute"):
        add(provider.services["compute"])

    # Infrastructure as code pour un cloud (indispensable pour créer les machines)
    if provider and (a.iac != "none" or vm_cloud):
        add(a.iac if a.iac != "none" else "opentofu")
        storage = provider.services.get("object-storage")
        if storage in REMOTE_BACKENDS:  # état partagé entre les jobs (R44)
            add(storage)

    # Données
    if a.database in DATABASES and a.database != "none":
        from .databases import ENGINES
        tool, params = database_brick(a.database, p, catalog)
        add(tool, **params, **a.connections.get(ENGINES[a.database].family, {}))
    if a.cache:
        add("valkey", **a.connections.get("key-value", {}))
    if a.migrations and (a.database != "none" or a.cache):
        add("db-migrations", command=a.migrations)

    # Secrets de l'application
    k8s = a.hosting in ("kubernetes", "kubernetes-managed")
    if a.secrets == "sops":
        add("sops")
    elif a.secrets == "openbao":
        add("openbao")
    elif a.secrets == "cloud" and provider and provider.services.get("secrets"):
        add(provider.services["secrets"])
    if a.secrets in ("openbao", "cloud") and k8s:
        add("external-secrets")  # écrit les Secrets Kubernetes à partir du coffre

    # Connexion unique
    if a.identity in ("keycloak", "dex") and a.hosting != "serverless":
        add(a.identity)  # sur Kubernetes, sa base : Cluster CloudNativePG s'il est là, sinon StatefulSet dédié

    # Observabilité
    if (a.observability == "prometheus" and a.hosting != "serverless") or (a.observability == "cloud" and vm_cloud):
        # sur des machines, les agents des services d'observabilité du cloud ne sont pas générés
        add("prometheus")
        add("grafana")
    elif a.observability == "cloud" and provider and provider.services.get("observability"):
        add(provider.services["observability"])
    return p


def answers_from_profile(profile, catalog: Catalog, base: StarterAnswers | None = None) -> tuple[StarterAnswers, list[str]]:
    """Réponses de l'assistant déduites de l'analyse de l'application, et ce qui a été repris."""
    from dataclasses import replace
    a = replace(base) if base else StarterAnswers()
    taken: list[str] = []
    a.name = profile.name or a.name
    a.image_name = profile.image_name or a.image_name
    a.source = str(profile.path)
    if profile.language in ("python", "node", "java", "go", "dotnet", "other"):
        a.language = profile.language
    if profile.port:
        a.port = profile.port
    a.dockerfile = profile.dockerfile
    taken.append("nom, langage et port de l'application")
    if profile.forge in FORGES:
        a.forge = profile.forge
        taken.append(f"forge {FORGES[profile.forge]} (dépôt distant)")
    if profile.ci and profile.ci != NATIVE_CI.get(a.forge):
        ci, forge_tool = catalog.get(profile.ci), catalog.get(a.forge)
        if ci and forge_tool and (not ci.forges or forge_tool.forge in ci.forges):
            a.ci = profile.ci
            taken.append(f"CI existante {ci.name}")
    hint = profile.hosting_hint
    if hint == "kubernetes" and a.hosting not in ("kubernetes", "kubernetes-managed"):
        a.hosting = "kubernetes"
        taken.append("hébergement Kubernetes (manifestes ou chart présents)")
    elif hint == "docker-host" and a.hosting not in ("docker-host", "vm"):
        a.hosting = "docker-host"
        taken.append("hébergement sur hôte Docker (fichier Compose présent)")
    if profile.kustomize and not profile.helm:
        a.k8s_deploy = "kustomize"
    if profile.iac:
        a.iac = profile.iac
    if profile.dependencies:
        a.dependencies = True
        a.dependency_tool = profile.dependencies
    if not profile.dockerfile:
        taken.append("construction par Buildpacks (pas de Dockerfile)")
    main = next((e for e in profile.databases if e in DATABASES), None)
    if main:
        a.database = main
        taken.append(f"base {DATABASES[main]} (pilote dans les dépendances)")
    if any(e in ("valkey", "redis") for e in profile.databases):
        a.cache = True
        taken.append("cache Valkey (client Redis dans les dépendances)")
    if profile.connections:
        a.connections = dict(profile.connections)
    if profile.migrations:
        a.migrations = profile.migrations
        taken.append(f"migrations « {profile.migrations} »")
    return a, taken

