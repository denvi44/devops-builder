"""Représentation intermédiaire (IR) neutre du pipeline.

Les générateurs CI ne lisent que l'IR : une liste ordonnée d'étapes avec une
image de conteneur et des commandes shell. Ajouter un format de CI revient à
écrire un template qui parcourt `ir.steps`, sans connaître les outils.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .catalog import Catalog
from .model import Environment, Project, Tool
from .params import effective_params

CI_STAGES = ["build", "test", "security", "publish", "deploy", "infra"]


@dataclass
class Service:
    """Conteneur annexe d'un job CI, joignable par son alias."""

    alias: str
    image: str
    port: int
    env: dict[str, str] = field(default_factory=dict)


@dataclass
class Step:
    id: str
    name: str
    stage: str  # un de CI_STAGES
    image: str
    script: list[str]
    tool: str = ""
    docker: bool = False  # a besoin d'un démon Docker (dind / runner hôte)
    cloud: list[str] = field(default_factory=list)  # fournisseurs à authentifier
    main_only: bool = False
    manual: bool = False
    allow_failure: bool = False
    artifacts: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    needs: list[str] = field(default_factory=list)  # dépendances dans la même étape
    environment: str | None = None  # identifiant de l'environnement déployé
    services: list[Service] = field(default_factory=list)  # conteneurs annexes (Floci…)
    lock: str = ""  # groupe d'exclusion : deux jobs du même groupe ne tournent jamais ensemble


@dataclass
class Variable:
    name: str
    description: str
    secret: bool = True
    value: str | None = None  # valeur connue (paramètre de brique) : écrite dans la CI


@dataclass
class IR:
    project: Project
    catalog: Catalog
    forge: Tool | None
    ci: Tool | None
    registry: Tool | None
    image_ref: str
    cluster: Tool | None
    providers: list[Tool]
    iac: Tool | None
    deploy: list[Tool]
    steps: list[Step] = field(default_factory=list)
    variables: list[Variable] = field(default_factory=list)
    unsupported: list[Tool] = field(default_factory=list)
    covered: set[str] = field(default_factory=set)   # briques pour lesquelles un fichier a été produit
    notes: list[str] = field(default_factory=list)    # remarques reprises dans PIPELINE.md

    def cover(self, *tool_ids: str) -> None:
        self.covered.update(t for t in tool_ids if t)

    def has(self, tool_id: str) -> bool:
        return tool_id in self.project.tool_ids()

    def params(self, tool_id: str, env: Environment | None = None) -> dict[str, Any]:
        """Paramètres effectifs : surcharge d'environnement > saisie > défaut > valeur d'exemple."""
        tool = self.catalog.get(tool_id)
        if tool is None:
            return {}
        bricks = self.project.bricks_for(tool_id)
        return effective_params(tool, bricks[0] if bricks else None, self.project, env)

    # ------------------------------------------------------------ environnements
    @property
    def envs(self) -> list[Environment]:
        return self.project.environments

    @property
    def multi_env(self) -> bool:
        return self.project.multi_env

    def cluster_for(self, env: Environment) -> Tool | None:
        """Cluster d'un environnement : le sien, ou l'unique cluster du pipeline."""
        ids = [b.tool for _, b in self.project.all_bricks()
               if (t := self.catalog.get(b.tool)) and "kubernetes-cluster" in t.roles]
        if env.cluster in ids:
            return self.catalog[env.cluster]
        return self.catalog[ids[0]] if len(set(ids)) == 1 else None

    def namespace(self, env: Environment) -> str:
        return self.app + self.project.env_suffix(env)

    def env_var(self, base: str, env: Environment) -> str:
        """Nom de variable propre à l'environnement (inchangé avec un seul environnement)."""
        return base if not self.multi_env else f"{base}_{env.id.upper().replace('-', '_')}"

    def helm_values(self, env: Environment) -> str:
        return f"charts/{self.app}/values-{env.id}.yaml" if self.multi_env else f"charts/{self.app}/values.yaml"

    def overlay(self, env: Environment) -> str:
        return f"deploy/kustomize/overlays/{env.id}"

    def inventory(self, env: Environment) -> str:
        return f"ansible/inventories/{env.id}.ini" if self.multi_env else "ansible/inventory.ini"

    def add_var(self, name: str, description: str, secret: bool = True, value: str | None = None) -> None:
        for v in self.variables:
            if v.name == name:
                if value and not v.value:
                    v.value = value
                return
        self.variables.append(Variable(name, description, secret, value or None))

    @property
    def app(self) -> str:
        return self.project.app.image_name

    @property
    def iac_cmd(self) -> str:
        return "terraform" if self.iac and self.iac.id == "terraform" else "tofu"


# --------------------------------------------------------------------------
TEST_COMMANDS = {
    "python": ["pip install -r requirements.txt", "pytest -q"],
    "node": ["npm ci", "npm test"],
    "java": ["./mvnw -B verify"],
    "go": ["go test ./..."],
    "dotnet": ["dotnet test"],
    "other": ["echo 'Ajouter ici la commande de test du projet'"],
}
TEST_IMAGES = {
    "python": "python:3.12-slim",
    "node": "node:22-alpine",
    "java": "eclipse-temurin:21-jdk",
    "go": "golang:1.23",
    "dotnet": "mcr.microsoft.com/dotnet/sdk:8.0",
    "other": "alpine:3.20",
}
DOCKER_IMAGE = "docker:27"
ALPINE = "alpine:3.20"
TERRAFORM_IMAGE = "hashicorp/terraform:1.16"
TOFU_VERSION = "1.13.1"
# Depuis OpenTofu 1.10, l'image officielle ne sert plus qu'à copier le binaire : la CI l'installe.
TOFU_INSTALL = [
    "apk add --no-cache curl unzip",
    f'curl -fsSLo /tmp/tofu.zip "https://github.com/opentofu/opentofu/releases/download/v{TOFU_VERSION}/'
    f'tofu_{TOFU_VERSION}_linux_amd64.zip"',
    "unzip -o -q /tmp/tofu.zip tofu -d /usr/local/bin",
]
FLOCI_IMAGE = "floci/floci:2.2.0"  # épinglée ; Renovate la tient à jour


FLOCI_CLIENT_ENV = {"AWS_ENDPOINT_URL": "http://floci:4566", "AWS_ACCESS_KEY_ID": "test",
                    "AWS_SECRET_ACCESS_KEY": "test"}


SERVICE_CI = ("gitlab-ci", "github-actions", "gitea-actions", "woodpecker")  # conteneurs annexes par job


def floci_in_ci(ir: IR) -> bool:
    return ir.ci is not None and ir.ci.id in SERVICE_CI


def floci_region(ir: IR) -> str:
    return str(ir.params("aws").get("region", "eu-west-3")) if ir.has("aws") else "us-east-1"


def floci_service(ir: IR) -> Service:
    return Service("floci", FLOCI_IMAGE, 4566, {"FLOCI_HOSTNAME": "floci", "FLOCI_DEFAULT_REGION": floci_region(ir)})


def _first(project: Project, catalog: Catalog, role: str) -> Tool | None:
    for _, b in project.all_bricks():
        t = catalog.get(b.tool)
        if t and t.curated and role in t.roles:
            return t
    return None


def _image_ref(ir: IR) -> str:
    app = ir.app
    reg = ir.registry
    if reg is None:
        if ir.forge and ir.forge.id == "gitlab":
            return "$CI_REGISTRY_IMAGE"
        return f"registry.example.com/{app}"
    p = ir.params(reg.id)
    if reg.id == "ecr":
        region = ir.params("aws").get("region", "eu-west-3")
        account = aws_account_id(ir) or "$AWS_ACCOUNT_ID"
        return f"{account}.dkr.ecr.{region}.amazonaws.com/{p.get('repository', app)}"
    if reg.id in ("artifact-registry", "gcr"):
        g = ir.params("gcp")
        return f"{g.get('region', 'europe-west9')}-docker.pkg.dev/{g.get('project_id', 'mon-projet')}/{p.get('repository', app)}/{app}"
    if reg.id == "acr":
        return f"{p.get('registry_name', 'monappregistry')}.azurecr.io/{app}"
    if reg.id == "ghcr":
        return f"ghcr.io/OWNER/{app}"
    if reg.id == "scaleway-registry":
        region = ir.params("scaleway").get("region", "fr-par")
        return f"rg.{region}.scw.cloud/{p.get('namespace', app)}/{app}"
    url = p.get("url", "registry.example.com")
    return f"{url}/{app}/{app}"


def registry_host(ir: IR) -> str:
    ref = ir.image_ref
    return ref.split("/")[0]


def scanner_credentials(ir: IR, user_var: str, password_var: str) -> dict[str, str]:
    """Identifiants de lecture du registre pour un scanner (Trivy, Grype)."""
    reg = ir.registry
    if reg is None and ir.forge and ir.forge.id == "gitlab":
        return {user_var: "$CI_REGISTRY_USER", password_var: "$CI_REGISTRY_PASSWORD"}
    if reg is None or reg.provider in OIDC_CLOUDS:
        return {}  # registres cloud : le scanner utilise les identifiants du fournisseur
    if reg.id == "scaleway-registry":
        return {user_var: "nologin", password_var: "$SCW_SECRET_KEY"}
    if reg.id == "ghcr":
        return {user_var: "$GITHUB_ACTOR", password_var: "$GITHUB_TOKEN"}
    return {user_var: "$REGISTRY_USER", password_var: "$REGISTRY_PASSWORD"}


def registry_login(ir: IR, cli: str = "docker") -> list[str]:
    reg = ir.registry
    host = registry_host(ir)
    if reg is None and ir.forge and ir.forge.id == "gitlab":
        return [f'echo "$CI_REGISTRY_PASSWORD" | {cli} login "$CI_REGISTRY" -u "$CI_REGISTRY_USER" --password-stdin']
    if reg and reg.id == "ecr":
        region = ir.params("aws").get("region", "eu-west-3")
        ir.add_var("AWS_ACCOUNT_ID", "Identifiant du compte AWS du registre ECR", secret=False,
                   value=aws_account_id(ir))
        return [f'aws ecr get-login-password --region {region} | {cli} login --username AWS --password-stdin "{host}"']
    if reg and reg.id == "ghcr":
        return [f'echo "$GITHUB_TOKEN" | {cli} login ghcr.io -u "$GITHUB_ACTOR" --password-stdin']
    if reg and reg.id == "scaleway-registry":
        ir.add_var("SCW_SECRET_KEY", "Clé secrète d'API Scaleway")
        return [f'echo "$SCW_SECRET_KEY" | {cli} login "{host}" -u nologin --password-stdin']
    ir.add_var("REGISTRY_USER", f"Compte de publication sur {host}")
    ir.add_var("REGISTRY_PASSWORD", f"Mot de passe ou jeton de publication sur {host}")
    return [f'echo "$REGISTRY_PASSWORD" | {cli} login "{host}" -u "$REGISTRY_USER" --password-stdin']


# --------------------------------------------------------------------------
def build_ir(project: Project, catalog: Catalog) -> IR:
    providers = [catalog[t] for t in project.tool_ids() if t in catalog and catalog[t].kind == "provider"]
    providers.sort(key=lambda t: t.id)
    deploy = [t for t in (catalog.get(b.tool) for _, b in project.all_bricks())
              if t and t.curated and t.stage == "deploy"]
    ir = IR(
        project=project,
        catalog=catalog,
        forge=_first(project, catalog, "scm"),
        ci=_first(project, catalog, "ci"),
        registry=_first(project, catalog, "registry"),
        image_ref="",
        cluster=_first(project, catalog, "kubernetes-cluster"),
        providers=providers,
        iac=_first(project, catalog, "iac"),
        deploy=deploy,
    )
    ir.image_ref = _image_ref(ir)
    _add_steps(ir)
    return ir


OIDC_CLOUDS = ("aws", "gcp", "azure")


def _cloud_of_registry(ir: IR) -> list[str]:
    """Fournisseurs dont l'authentification CI sert aussi au registre (OIDC ou statique)."""
    if ir.registry and ir.registry.provider in OIDC_CLOUDS:
        return [ir.registry.provider]
    return []


GET_HELM = "curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash"
GET_KUBECTL = ('curl -fsSLo /usr/local/bin/kubectl "https://dl.k8s.io/release/$(curl -fsSL '
               'https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" && chmod +x /usr/local/bin/kubectl')


@dataclass
class KubeAccess:
    image: str
    script: list[str]
    cloud: list[str]


def _kube_access(ir: IR, need_helm: bool, env: Environment) -> KubeAccess:
    """Image, commandes pour obtenir le kubeconfig de l'environnement, fournisseurs à authentifier."""
    c = ir.cluster_for(env)
    p = ir.params(c.id, env) if c else {}
    name = p.get("cluster_name", "mon-cluster")
    if c and c.id == "eks":
        script = ["yum install -y -q tar gzip openssl >/dev/null"]
        script += [GET_HELM] if need_helm else [GET_KUBECTL]
        script.append(f"aws eks update-kubeconfig --name {name} --region {p.get('region', 'eu-west-3')}")
        return KubeAccess("amazon/aws-cli:latest", script, ["aws"])
    if c and c.id == "gke":
        project_id = ir.params("gcp").get("project_id", "mon-projet")
        script = [GET_HELM] if need_helm else []
        script.append(f"gcloud container clusters get-credentials {name} --region {p.get('region', 'europe-west9')} --project {project_id}")
        return KubeAccess("google/cloud-sdk:latest", script, ["gcp"])
    if c and c.id == "aks":
        rg = ir.params("azure").get("resource_group", "rg-mon-projet")
        script = ["az aks install-cli"] + ([GET_HELM] if need_helm else [])
        script.append(f"az aks get-credentials --name {name} --resource-group {rg}")
        return KubeAccess("mcr.microsoft.com/azure-cli:latest", script, ["azure"])
    label = f"de {c.name}" if c else "du cluster cible"
    var = ir.env_var("KUBECONFIG_DATA", env)
    where = f" ({env.display})" if ir.multi_env else ""
    ir.add_var(var, f"Contenu du kubeconfig {label}{where} (base64)")
    script = ["apk add --no-cache curl bash openssl"]
    script += [GET_HELM] if need_helm else [GET_KUBECTL]
    script += [f'echo "${var}" | base64 -d > /tmp/kubeconfig', "export KUBECONFIG=/tmp/kubeconfig"]
    return KubeAccess(ALPINE, script, [])


def _ports_shifted(ir: IR) -> bool:
    from .ports import parametrized
    return parametrized(ir.project)


SSH_SETUP = 'mkdir -p ~/.ssh && echo "$SSH_PRIVATE_KEY" > ~/.ssh/id_ed25519 && chmod 600 ~/.ssh/id_ed25519'
KNOWN_HOSTS = 'if [ -n "${SSH_KNOWN_HOSTS:-}" ]; then printf \'%s\\n\' "$SSH_KNOWN_HOSTS" > ~/.ssh/known_hosts; fi'
ANSIBLE_INSTALL = [
    "apk add --no-cache openssh-client",
    'pip install --no-cache-dir "ansible-core>=2.21,<2.22" || pipx install "ansible-core>=2.21,<2.22"',
    "ansible-galaxy collection install -r ansible/requirements.yml",
]
ANSIBLE_IMAGE = "python:3.12-alpine"
CLOUD_REGISTRIES = ("ecr", "artifact-registry", "gcr", "acr")


def ssh_variables(ir: IR, what: str) -> None:
    ir.add_var("SSH_PRIVATE_KEY", f"Clé SSH de déploiement vers {what}")
    ir.add_var("SSH_KNOWN_HOSTS", "Facultatif : clés d'hôte attendues (ssh-keyscan) ; sans elle, la clé est "
                                  "acceptée à la première connexion de chaque job", secret=False)


def host_registry(ir: IR) -> tuple[str, str, str] | None:
    """(registre, utilisateur, mot de passe) pour que les hôtes Docker tirent l'image ; None : rien à faire."""
    reg = ir.registry
    if reg is None:
        if ir.forge and ir.forge.id == "gitlab":
            return "$CI_REGISTRY", "$CI_REGISTRY_USER", "$CI_REGISTRY_PASSWORD"
        return None
    if reg.id in CLOUD_REGISTRIES:
        return None  # identité de la machine (rôle IAM, compte de service) : voir PIPELINE.md
    host = registry_host(ir)
    if reg.id == "ghcr":
        return host, "$GITHUB_ACTOR", "$GITHUB_TOKEN"
    if reg.id == "scaleway-registry":
        ir.add_var("SCW_SECRET_KEY", "Clé secrète d'API Scaleway")
        return host, "nologin", "$SCW_SECRET_KEY"
    ir.add_var("REGISTRY_USER", f"Compte de lecture et de publication sur {host}")
    ir.add_var("REGISTRY_PASSWORD", f"Mot de passe ou jeton sur {host}")
    return host, "$REGISTRY_USER", "$REGISTRY_PASSWORD"


def ansible_hosts(ir: IR, env: Environment) -> list[str]:
    from .generators.ansible import lint_hosts
    return lint_hosts(str(ir.params("ansible", env).get("hosts") or "app1.example.com"))


def _registry_note(ir: IR) -> None:
    if ir.registry and ir.registry.id in CLOUD_REGISTRIES:
        note = (f"{ir.registry.name} : les hôtes Docker tirent l'image avec l'identité de la machine (rôle IAM, "
                "compte de service ou identité managée) et l'assistant d'identification du fournisseur "
                "(docker-credential-ecr-login, gcloud auth configure-docker, az acr login).")
        if note not in ir.notes:
            ir.notes.append(note)


def _ansible_step(ir: IR, env: Environment, ns: str, secrets: list[str], name: str) -> Step:
    ssh_variables(ir, "les hôtes")
    reg = host_registry(ir)
    _registry_note(ir)
    login = ([f'export DEPLOY_REGISTRY="{reg[0]}" DEPLOY_REGISTRY_USER="{reg[1]}" DEPLOY_REGISTRY_PASSWORD="{reg[2]}"']
             if reg else [])
    return Step("deploy", name, "deploy", ANSIBLE_IMAGE, [
        *ANSIBLE_INSTALL, SSH_SETUP, KNOWN_HOSTS, *secrets, *login,
        f'ansible-playbook -i {ir.inventory(env)} ansible/deploy.yml -e "image=$IMAGE" -e "project={ns}" '
        f'-e "deploy_env={env.id}"'],
        tool="ansible", env={"ANSIBLE_CONFIG": "ansible/ansible.cfg"})


def _deploy_step(ir: IR, env: Environment) -> Step | None:
    """Étape de déploiement d'un environnement, selon les briques présentes."""
    target = ir.project.target
    app = ir.app
    ns = ir.namespace(env)
    from .generators import data as dbgen
    if ir.has("docker-compose") and target in ("docker-host", "vm"):
        secrets: list[str] = []
        if dbgen.needs_secrets(ir):
            prefix = dbgen.env_prefix(dbgen.secret_bindings(ir, env, dbgen.compose_dbs(ir)))
            secrets = [f"{prefix}sh {dbgen.SECRETS_SCRIPT} .secrets"]
        if ir.has("ansible"):
            return _ansible_step(ir, env, ns, secrets, "Déploiement Ansible + Compose")
        host = ir.env_var("DEPLOY_HOST", env)
        ssh_variables(ir, "l'hôte Docker")
        reg = host_registry(ir)
        _registry_note(ir)
        login = ([f'echo "{reg[2]}" | ssh "${host}" "docker login {reg[0]} -u {reg[1]} --password-stdin"']
                 if reg else [])
        where = f" ({env.display})" if ir.multi_env else ""
        ir.add_var(host, f"Hôte Docker cible{where} (utilisateur@hôte)", secret=False)
        return Step("deploy", "Déploiement Docker Compose (SSH)", "deploy", ALPINE, [
            "apk add --no-cache openssh-client",
            SSH_SETUP,
            KNOWN_HOSTS,
            f'ssh -o StrictHostKeyChecking=accept-new "${host}" "mkdir -p /opt/{ns}"',
            f'scp deploy/docker-compose.yml "${host}:/opt/{ns}/docker-compose.yml"',
            *([f'scp deploy/env/{env.id}.env "${host}:/opt/{ns}/.env"'] if _ports_shifted(ir) else []),
            *([*secrets,
               f'tar -C .secrets -cf - . | ssh "${host}" "mkdir -p /opt/{ns}/secrets && chmod 700 /opt/{ns}/secrets '
               f'&& tar -C /opt/{ns}/secrets -xf - && chmod 600 /opt/{ns}/secrets/*"',
               "rm -rf .secrets"] if secrets else []),
            *([f'scp {dbgen.BACKUP_SCRIPT} "${host}:/opt/{ns}/db-backup.sh"'] if dbgen.backup_script(ir) else []),
            *login,
            f'ssh "${host}" "cd /opt/{ns} && IMAGE=$IMAGE docker compose -p {ns} pull && IMAGE=$IMAGE docker compose -p {ns} up -d"'],
            tool="docker-compose")
    if ir.has("argo-cd") or ir.has("flux"):
        gitops = "Argo CD" if ir.has("argo-cd") else "Flux"
        if ir.has("helm"):
            bump = f"yq -i '.image.tag = strenv(TAG)' {ir.helm_values(env)}"
        else:
            bump = (f"yq -i '(.images[] | select(.name == \"{app}\")).newTag = strenv(TAG)' "
                    f"{ir.overlay(env)}/kustomization.yaml")
        ir.add_var("GITOPS_TOKEN", "Jeton autorisé à pousser sur le dépôt GitOps")
        ir.add_var("GITOPS_REPO", "Dépôt GitOps surveillé, sans schéma (hôte/groupe/depot.git)", secret=False)
        msg = f"deploy({env.id}): {app} $TAG" if ir.multi_env else f"deploy: {app} $TAG"
        return Step("deploy", f"Mise à jour GitOps ({gitops})", "deploy", ALPINE, [
            "apk add --no-cache git yq",
            'git clone "https://oauth2:$GITOPS_TOKEN@$GITOPS_REPO" gitops',
            "cd gitops",
            bump,
            'git config user.email "ci@example.com" && git config user.name "CI"',
            f'git commit -am "{msg}" && git push origin HEAD'],
            tool="argo-cd" if ir.has("argo-cd") else "flux")
    if ir.has("helm"):
        ka = _kube_access(ir, True, env)
        extra = f" -f {ir.helm_values(env)}" if ir.multi_env else ""
        return Step("deploy", "Déploiement Helm", "deploy", ka.image, [
            *ka.script,
            f'helm upgrade --install {app} charts/{app}{extra} --namespace {ns} --create-namespace '
            f'--set image.repository="${{IMAGE%:*}}" --set image.tag="$TAG"{dbgen.helm_set_flags(ir, env)} --wait'],
            tool="helm", cloud=ka.cloud)
    if ir.has("kustomize"):
        ka = _kube_access(ir, False, env)
        return Step("deploy", "Déploiement Kustomize", "deploy", ka.image, [
            *ka.script,
            *dbgen.kubectl_secret_lines(ir, env, ns),
            f"cd {ir.overlay(env)}",
            'sed -i "s|newTag: .*|newTag: \\"$TAG\\"|" kustomization.yaml',
            "kubectl apply -k ."],
            tool="kustomize", cloud=ka.cloud)
    if ir.has("ecs-fargate"):
        p = ir.params("ecs-fargate", env)
        return Step("deploy", "Déploiement ECS", "deploy", "amazon/aws-cli:latest", [
            f"aws ecs update-service --cluster {p.get('cluster')} --service {p.get('service')} --force-new-deployment"],
            tool="ecs-fargate", cloud=["aws"])
    if ir.has("cloud-run"):
        g = ir.params("gcp", env)
        return Step("deploy", "Déploiement Cloud Run", "deploy", "google/cloud-sdk:slim", [
            f'gcloud run deploy {ir.params("cloud-run", env).get("service", app)} --image "$IMAGE" '
            f'--region {g.get("region", "europe-west9")} --project {g.get("project_id", "mon-projet")}'],
            tool="cloud-run", cloud=["gcp"])
    if ir.has("azure-container-apps"):
        a = ir.params("azure", env)
        return Step("deploy", "Déploiement Azure Container Apps", "deploy", "mcr.microsoft.com/azure-cli:latest", [
            f'az containerapp update --name {ir.params("azure-container-apps", env).get("app", app)} '
            f'--resource-group {a.get("resource_group", "rg-mon-projet")} --image "$IMAGE"'],
            tool="azure-container-apps", cloud=["azure"])
    if ir.has("ansible") and target in ("vm", "docker-host"):
        return _ansible_step(ir, env, ns, [], "Déploiement Ansible")
    return None


def _add_steps(ir: IR) -> None:
    project = ir.project
    lang = project.app.language
    s = ir.steps

    # ----------------------------------------------------------------- tests
    if ir.has("unit-tests"):
        unit = Step("unit-tests", "Tests unitaires", "test", TEST_IMAGES.get(lang, ALPINE),
                    TEST_COMMANDS.get(lang, TEST_COMMANDS["other"]), tool="unit-tests")
        if ir.has("floci") and floci_in_ci(ir):  # les tests de l'application appellent AWS sur l'émulateur
            unit.services = [floci_service(ir)]
            unit.env = dict(FLOCI_CLIENT_ENV, AWS_DEFAULT_REGION=floci_region(ir), AWS_REGION=floci_region(ir))
        s.append(unit)
    if ir.has("sonarqube") or ir.has("sonarqube-cloud"):
        host = "https://sonarcloud.io" if ir.has("sonarqube-cloud") else "$SONAR_HOST_URL"
        if ir.has("sonarqube"):
            ir.add_var("SONAR_HOST_URL", "URL du serveur SonarQube", secret=False)
        ir.add_var("SONAR_TOKEN", "Jeton d'analyse SonarQube")
        s.append(Step("sonarqube", "Qualité SonarQube", "test", "sonarsource/sonar-scanner-cli:latest",
                      [f"sonar-scanner -Dsonar.projectKey={ir.app} -Dsonar.host.url={host} -Dsonar.token=$SONAR_TOKEN"],
                      tool="sonarqube"))
    if ir.has("semgrep"):
        s.append(Step("semgrep", "Analyse statique Semgrep", "test", "semgrep/semgrep:latest",
                      ["semgrep scan --config auto --error"], tool="semgrep"))
    if ir.has("gitleaks"):
        s.append(Step("gitleaks", "Recherche de secrets", "security", "zricethezav/gitleaks:latest",
                      ["gitleaks detect --source . --verbose"], tool="gitleaks"))
    iac_dir = "infra/terraform"
    if ir.has("checkov"):
        s.append(Step("checkov", "Analyse IaC Checkov", "security", "bridgecrew/checkov:latest",
                      [f"checkov -d {iac_dir} -d deploy --quiet"], tool="checkov", allow_failure=True))
    if ir.has("kics"):
        s.append(Step("kics", "Analyse IaC KICS", "security", "checkmarx/kics:latest",
                      [f"kics scan -p {iac_dir} -p deploy"], tool="kics", allow_failure=True))

    # ---------------------------------------------------------------- build
    builder = _first(project, ir.catalog, "image-build")
    if builder:
        ref = '"$IMAGE"'
        if builder.id == "buildkit":
            script = registry_login(ir) + [f"docker buildx build --tag {ref} --push ."]
            image, docker = DOCKER_IMAGE, True
        elif builder.id == "buildah":
            script = registry_login(ir, "buildah") + [
                f"buildah build --tag {ref} .", f"buildah push {ref}"]
            image, docker = "quay.io/buildah/stable:latest", False
        elif builder.id == "kaniko":
            script = [
                "# Kaniko est archivé depuis juin 2025 : préférer BuildKit ou Buildah.",
                "# Les identifiants du registre se placent dans /kaniko/.docker/config.json.",
                f"/kaniko/executor --context . --dockerfile Dockerfile --destination {ref}",
            ]
            image, docker = "gcr.io/kaniko-project/executor:debug", False
        else:  # buildpacks
            script = registry_login(ir) + [
                f"pack build {ref} --builder paketobuildpacks/builder-jammy-base --publish"]
            image, docker = "buildpacksio/pack:latest", True
        if ir.registry and ir.registry.id == "ecr":
            script.insert(0, "apk add --no-cache aws-cli || true")
        s.append(Step("build-image", f"Build et publication de l'image ({builder.name})", "build",
                      image, script, tool=builder.id, docker=docker, cloud=_cloud_of_registry(ir)))

    # ------------------------------------------------------- scans d'image
    if builder and ir.has("trivy"):
        s.append(Step("trivy", "Scan de vulnérabilités Trivy", "security", "aquasec/trivy:latest",
                      ['trivy image --exit-code 1 --severity HIGH,CRITICAL "$IMAGE"'], tool="trivy",
                      env=scanner_credentials(ir, "TRIVY_USERNAME", "TRIVY_PASSWORD"),
                      cloud=_cloud_of_registry(ir)))
    elif ir.has("trivy"):
        s.append(Step("trivy", "Scan Trivy du dépôt", "security", "aquasec/trivy:latest",
                      ["trivy fs --exit-code 1 --severity HIGH,CRITICAL ."], tool="trivy"))
    if ir.has("grype"):
        target = '"$IMAGE"' if builder else "dir:."
        s.append(Step("grype", "Scan de vulnérabilités Grype", "security", ALPINE, [
            "apk add --no-cache curl",
            "curl -sSfL https://raw.githubusercontent.com/anchore/grype/main/install.sh | sh -s -- -b /usr/local/bin",
            f"grype {target} --fail-on high"], tool="grype",
            env=scanner_credentials(ir, "GRYPE_REGISTRY_AUTH_USERNAME", "GRYPE_REGISTRY_AUTH_PASSWORD") if builder else {},
            cloud=_cloud_of_registry(ir) if builder else []))
    if ir.has("syft"):
        target = '"$IMAGE"' if builder else "dir:."
        s.append(Step("syft", "SBOM Syft", "security", ALPINE, [
            "apk add --no-cache curl",
            "curl -sSfL https://raw.githubusercontent.com/anchore/syft/main/install.sh | sh -s -- -b /usr/local/bin",
            f"syft {target} -o spdx-json > sbom.spdx.json"], tool="syft", artifacts=["sbom.spdx.json"]))
    if ir.has("snyk"):
        ir.add_var("SNYK_TOKEN", "Jeton d'API Snyk")
        s.append(Step("snyk", "Scan Snyk", "security", "snyk/snyk:alpine",
                      ["snyk test --severity-threshold=high"], tool="snyk", allow_failure=True))
    if builder and ir.has("cosign"):
        pre = ["apk add --no-cache aws-cli"] if ir.registry and ir.registry.id == "ecr" else []
        s.append(Step("cosign", "Signature de l'image (Cosign)", "publish", ALPINE, [
            "apk add --no-cache cosign", *pre, *registry_login(ir, "cosign"),
            'cosign sign --yes "$IMAGE"'], tool="cosign", cloud=_cloud_of_registry(ir), main_only=True))

    # ----------------------------------------------------------- infrastructure
    tf_stack = bool(ir.iac and ir.iac.id in ("terraform", "opentofu"))
    if tf_stack and ir.has("tflint"):
        s.append(Step("tflint", "Analyse TFLint", "test", "ghcr.io/terraform-linters/tflint:latest",
                      [f"tflint --chdir={iac_dir} --init", f"tflint --chdir={iac_dir} --format compact"],
                      tool="tflint"))
    if tf_stack and ir.has("infracost"):
        ir.add_var("INFRACOST_API_KEY", "Clé d'API Infracost (gratuite, infracost auth login)")
        s.append(Step("infracost", "Estimation des coûts Infracost", "test", "infracost/infracost:ci-latest",
                      [f"infracost breakdown --path {iac_dir} --format table"], tool="infracost", allow_failure=True))
    if tf_stack:
        cmd = ir.iac_cmd
        image, install = (TERRAFORM_IMAGE, []) if cmd == "terraform" else (ALPINE, list(TOFU_INSTALL))
        clouds = [p.id for p in ir.providers if p.id in OIDC_CLOUDS]
        for prov in ir.providers:
            for name, desc in PROVIDER_ENV.get(prov.id, []):
                ir.add_var(name, desc)
        from .generators.iac import backend_credentials, required_vars
        for tv in required_vars(ir):
            ir.add_var(f"TF_VAR_{tv.name}", f"{tv.description} (variable Terraform {tv.name}, ex. {tv.example})",
                       secret=False)
        creds = backend_credentials(ir)
        s.append(Step("iac-plan", f"Plan {ir.iac.name}", "infra", image, [
            *install, *creds,
            f"cd {iac_dir}", f"{cmd} fmt -check -recursive", f"{cmd} init -input=false", f"{cmd} validate",
            f"{cmd} plan -input=false -lock-timeout=5m -out=plan.tfplan"], tool=ir.iac.id, cloud=clouds,
            artifacts=[f"{iac_dir}/plan.tfplan"]))
        s.append(Step("iac-apply", f"Application {ir.iac.name}", "infra", image, [
            *install, *creds,
            f"cd {iac_dir}", f"{cmd} init -input=false", f"{cmd} apply -input=false -lock-timeout=5m plan.tfplan"],
            tool=ir.iac.id, cloud=clouds, main_only=True, manual=True, needs=["iac-plan"], lock="terraform"))
        if ir.has("floci") and floci_in_ci(ir) and {p.id for p in ir.providers} == {"aws"}:
            s.append(Step("iac-floci", "Plan de l'IaC sur Floci (émulateur AWS)", "test", ALPINE, [
                *install, "apk add --no-cache bash curl", "bash scripts/tf-floci.sh plan"],
                tool="floci", allow_failure=True, env={"FLOCI_ENDPOINT": "http://floci:4566"},
                services=[floci_service(ir)]))
    elif ir.iac and ir.iac.id == "pulumi":
        ir.add_var("PULUMI_ACCESS_TOKEN", "Jeton Pulumi")
        s.append(Step("iac-preview", "Prévisualisation Pulumi", "infra", "pulumi/pulumi:latest",
                      ["pulumi preview --stack prod"], tool="pulumi"))

    # ------------------------------------------------------------- déploiement
    # Une étape par environnement, dans l'ordre de promotion : la même image est promue.
    previous: str | None = None
    for env in project.environments:
        step = _deploy_step(ir, env)
        if step is None:
            continue
        step.environment = env.id
        step.manual = env.approval
        step.main_only = True
        if ir.multi_env:
            step.id = f"deploy-{env.id}"
            step.name = f"{step.name} — {env.display}"
            if previous:
                step.needs = [previous]
        previous = step.id
        s.append(step)

    # Authentification cloud : variables attendues
    clouds = sorted({c for st in s for c in st.cloud})
    for c in clouds:
        _cloud_variables(ir, c)



PROVIDER_ENV = {
    "scaleway": [("SCW_ACCESS_KEY", "Clé d'accès API Scaleway"), ("SCW_SECRET_KEY", "Clé secrète API Scaleway"),
                 ("SCW_DEFAULT_PROJECT_ID", "Projet Scaleway")],
    "ovhcloud": [("OVH_APPLICATION_KEY", "Clé d'application OVHcloud"),
                 ("OVH_APPLICATION_SECRET", "Secret d'application OVHcloud"),
                 ("OVH_CONSUMER_KEY", "Clé consommateur OVHcloud")],
    "outscale": [("OSC_ACCESS_KEY", "Clé d'accès Outscale"), ("OSC_SECRET_KEY", "Clé secrète Outscale")],
}


def aws_account_id(ir: IR) -> str | None:
    """Compte AWS déduit de l'ARN du rôle de CI, s'il est renseigné."""
    arn = str(ir.params("aws").get("role_arn") or "")
    parts = arn.split(":")
    return parts[4] if len(parts) > 5 and parts[4].isdigit() else None


def _cloud_variables(ir: IR, cloud: str) -> None:
    oidc = ir.project.cloud_auth == "oidc"
    if cloud == "aws":
        a = ir.params("aws")
        if oidc:
            ir.add_var("AWS_ROLE_ARN", "Rôle IAM assumé par la CI via OIDC", secret=False, value=a.get("role_arn"))
        else:
            ir.add_var("AWS_ACCESS_KEY_ID", "Clé d'accès AWS (statique, déconseillé)")
            ir.add_var("AWS_SECRET_ACCESS_KEY", "Secret de la clé d'accès AWS")
        ir.add_var("AWS_REGION", "Région AWS", secret=False, value=a.get("region"))
    elif cloud == "gcp":
        g = ir.params("gcp")
        if oidc:
            ir.add_var("GCP_WORKLOAD_IDENTITY_PROVIDER", "Fournisseur Workload Identity Federation", secret=False,
                       value=g.get("workload_identity_provider"))
            ir.add_var("GCP_SERVICE_ACCOUNT", "Compte de service impersonné par la CI", secret=False,
                       value=g.get("service_account"))
        else:
            ir.add_var("GCP_SA_KEY", "Clé JSON du compte de service (statique, déconseillé)")
    elif cloud == "azure":
        z = ir.params("azure")
        ir.add_var("AZURE_CLIENT_ID", "Identifiant d'application Entra ID", secret=False, value=z.get("client_id"))
        ir.add_var("AZURE_TENANT_ID", "Identifiant du tenant Entra ID", secret=False, value=z.get("tenant_id"))
        ir.add_var("AZURE_SUBSCRIPTION_ID", "Identifiant d'abonnement Azure", secret=False,
                   value=z.get("subscription_id"))
        if not oidc:
            ir.add_var("AZURE_CLIENT_SECRET", "Secret d'application (statique, déconseillé)")
