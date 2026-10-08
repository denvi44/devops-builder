"""Représentation intermédiaire (IR) neutre du pipeline.

Les générateurs CI ne lisent que l'IR : une liste ordonnée d'étapes avec une
image de conteneur et des commandes shell. Ajouter un format de CI revient à
écrire un template qui parcourt `ir.steps`, sans connaître les outils.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .catalog import Catalog
from .model import Project, Tool

CI_STAGES = ["build", "test", "security", "publish", "deploy", "infra"]


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


@dataclass
class Variable:
    name: str
    description: str
    secret: bool = True


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

    def has(self, tool_id: str) -> bool:
        return tool_id in self.project.tool_ids()

    def params(self, tool_id: str) -> dict[str, Any]:
        tool = self.catalog.get(tool_id)
        merged = dict(tool.params) if tool else {}
        for b in self.project.bricks_for(tool_id):
            merged.update(b.params)
        return merged

    def add_var(self, name: str, description: str, secret: bool = True) -> None:
        if all(v.name != name for v in self.variables):
            self.variables.append(Variable(name, description, secret))

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
        return f"$AWS_ACCOUNT_ID.dkr.ecr.{region}.amazonaws.com/{p.get('repository', app)}"
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
        ir.add_var("AWS_ACCOUNT_ID", "Identifiant du compte AWS du registre ECR", secret=False)
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


def _kube_access(ir: IR, need_helm: bool) -> KubeAccess:
    """Image, commandes pour obtenir un kubeconfig, et fournisseurs à authentifier."""
    c = ir.cluster
    p = ir.params(c.id) if c else {}
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
    ir.add_var("KUBECONFIG_DATA", f"Contenu du kubeconfig {label} (base64)")
    script = ["apk add --no-cache curl bash openssl"]
    script += [GET_HELM] if need_helm else [GET_KUBECTL]
    script += ['echo "$KUBECONFIG_DATA" | base64 -d > /tmp/kubeconfig', "export KUBECONFIG=/tmp/kubeconfig"]
    return KubeAccess(ALPINE, script, [])


def _add_steps(ir: IR) -> None:
    project = ir.project
    lang = project.app.language
    s = ir.steps

    # ----------------------------------------------------------------- tests
    if ir.has("unit-tests"):
        s.append(Step("unit-tests", "Tests unitaires", "test", TEST_IMAGES.get(lang, ALPINE),
                      TEST_COMMANDS.get(lang, TEST_COMMANDS["other"]), tool="unit-tests"))
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
    if ir.iac and ir.iac.id in ("terraform", "opentofu"):
        cmd = ir.iac_cmd
        image = "hashicorp/terraform:1.9" if cmd == "terraform" else "ghcr.io/opentofu/opentofu:1.10"
        clouds = [p.id for p in ir.providers if p.id in OIDC_CLOUDS]
        for prov in ir.providers:
            for name, desc in PROVIDER_ENV.get(prov.id, []):
                ir.add_var(name, desc)
        s.append(Step("iac-plan", f"Plan {ir.iac.name}", "infra", image, [
            f"cd {iac_dir}", f"{cmd} init -input=false", f"{cmd} validate",
            f"{cmd} plan -input=false -out=plan.tfplan"], tool=ir.iac.id, cloud=clouds,
            artifacts=[f"{iac_dir}/plan.tfplan"]))
        s.append(Step("iac-apply", f"Application {ir.iac.name}", "infra", image, [
            f"cd {iac_dir}", f"{cmd} init -input=false", f"{cmd} apply -input=false plan.tfplan"],
            tool=ir.iac.id, cloud=clouds, main_only=True, manual=True, needs=["iac-plan"]))
    elif ir.iac and ir.iac.id == "pulumi":
        ir.add_var("PULUMI_ACCESS_TOKEN", "Jeton Pulumi")
        s.append(Step("iac-preview", "Prévisualisation Pulumi", "infra", "pulumi/pulumi:latest",
                      ["pulumi preview --stack prod"], tool="pulumi"))

    # ------------------------------------------------------------- déploiement
    target = project.target
    if ir.has("docker-compose") and target in ("docker-host", "vm"):
        if ir.has("ansible"):
            ir.add_var("SSH_PRIVATE_KEY", "Clé SSH de déploiement vers les hôtes")
            s.append(Step("deploy", "Déploiement Ansible + Compose", "deploy", "alpine/ansible:latest", [
                "mkdir -p ~/.ssh && echo \"$SSH_PRIVATE_KEY\" > ~/.ssh/id_ed25519 && chmod 600 ~/.ssh/id_ed25519",
                "ansible-galaxy collection install community.docker",
                'ansible-playbook -i ansible/inventory.ini ansible/deploy.yml -e "image=$IMAGE"'],
                tool="ansible", main_only=True))
        else:
            ir.add_var("SSH_PRIVATE_KEY", "Clé SSH de déploiement vers l'hôte Docker")
            ir.add_var("DEPLOY_HOST", "Hôte Docker cible (utilisateur@hôte)", secret=False)
            s.append(Step("deploy", "Déploiement Docker Compose (SSH)", "deploy", ALPINE, [
                "apk add --no-cache openssh-client",
                "mkdir -p ~/.ssh && echo \"$SSH_PRIVATE_KEY\" > ~/.ssh/id_ed25519 && chmod 600 ~/.ssh/id_ed25519",
                'scp -o StrictHostKeyChecking=accept-new deploy/docker-compose.yml "$DEPLOY_HOST:/opt/app/docker-compose.yml"',
                'ssh "$DEPLOY_HOST" "cd /opt/app && IMAGE=$IMAGE docker compose pull && IMAGE=$IMAGE docker compose up -d"'],
                tool="docker-compose", main_only=True))
    elif ir.has("argo-cd") or ir.has("flux"):
        gitops = "Argo CD" if ir.has("argo-cd") else "Flux"
        values = f"charts/{ir.app}/values.yaml" if ir.has("helm") else "deploy/kustomize/overlays/production/kustomization.yaml"
        if ir.has("helm"):
            bump = f"yq -i '.image.tag = strenv(TAG)' {values}"
        else:
            bump = f"yq -i '(.images[] | select(.name == \"{ir.app}\")).newTag = strenv(TAG)' {values}"
        ir.add_var("GITOPS_TOKEN", "Jeton autorisé à pousser sur le dépôt GitOps")
        ir.add_var("GITOPS_REPO", "Dépôt GitOps surveillé, sans schéma (hôte/groupe/depot.git)", secret=False)
        s.append(Step("deploy", f"Mise à jour GitOps ({gitops})", "deploy", ALPINE, [
            "apk add --no-cache git yq",
            'git clone "https://oauth2:$GITOPS_TOKEN@$GITOPS_REPO" gitops',
            "cd gitops",
            bump,
            'git config user.email "ci@example.com" && git config user.name "CI"',
            f'git commit -am "deploy: {ir.app} $TAG" && git push origin HEAD'],
            tool="argo-cd" if ir.has("argo-cd") else "flux", main_only=True))
    elif ir.has("helm"):
        ka = _kube_access(ir, need_helm=True)
        s.append(Step("deploy", "Déploiement Helm", "deploy", ka.image, [
            *ka.script,
            f'helm upgrade --install {ir.app} charts/{ir.app} --namespace {ir.app} --create-namespace '
            f'--set image.repository="${{IMAGE%:*}}" --set image.tag="$TAG" --wait'],
            tool="helm", cloud=ka.cloud, main_only=True))
    elif ir.has("kustomize"):
        ka = _kube_access(ir, need_helm=False)
        s.append(Step("deploy", "Déploiement Kustomize", "deploy", ka.image, [
            *ka.script,
            "cd deploy/kustomize/overlays/production",
            'sed -i "s|newTag: .*|newTag: \\"$TAG\\"|" kustomization.yaml',
            "kubectl apply -k ."],
            tool="kustomize", cloud=ka.cloud, main_only=True))
    elif ir.has("ecs-fargate"):
        p = ir.params("ecs-fargate")
        s.append(Step("deploy", "Déploiement ECS", "deploy", "amazon/aws-cli:latest", [
            f"aws ecs update-service --cluster {p.get('cluster')} --service {p.get('service')} --force-new-deployment"],
            tool="ecs-fargate", cloud=["aws"], main_only=True))
    elif ir.has("cloud-run"):
        g = ir.params("gcp")
        s.append(Step("deploy", "Déploiement Cloud Run", "deploy", "google/cloud-sdk:slim", [
            f'gcloud run deploy {ir.params("cloud-run").get("service", ir.app)} --image "$IMAGE" '
            f'--region {g.get("region", "europe-west9")} --project {g.get("project_id", "mon-projet")}'],
            tool="cloud-run", cloud=["gcp"], main_only=True))
    elif ir.has("azure-container-apps"):
        a = ir.params("azure")
        s.append(Step("deploy", "Déploiement Azure Container Apps", "deploy", "mcr.microsoft.com/azure-cli:latest", [
            f'az containerapp update --name {ir.params("azure-container-apps").get("app", ir.app)} '
            f'--resource-group {a.get("resource_group", "rg-mon-projet")} --image "$IMAGE"'],
            tool="azure-container-apps", cloud=["azure"], main_only=True))
    elif ir.has("ansible") and target in ("vm", "docker-host"):
        ir.add_var("SSH_PRIVATE_KEY", "Clé SSH de déploiement vers les hôtes")
        s.append(Step("deploy", "Déploiement Ansible", "deploy", "alpine/ansible:latest", [
            "mkdir -p ~/.ssh && echo \"$SSH_PRIVATE_KEY\" > ~/.ssh/id_ed25519 && chmod 600 ~/.ssh/id_ed25519",
            'ansible-playbook -i ansible/inventory.ini ansible/deploy.yml -e "image=$IMAGE"'],
            tool="ansible", main_only=True))

    # Authentification cloud : variables attendues
    clouds = sorted({c for st in s for c in st.cloud})
    for c in clouds:
        _cloud_variables(ir, c)

    # Outils sans prise en charge par les générateurs
    handled = {st.tool for st in s} | {
        "github", "gitlab", "gitea", "bitbucket", "azure-repos", "codecommit", "secure-source-manager",
        "github-actions", "gitlab-ci", "gitea-actions", "jenkins", "woodpecker", "tekton",
        "azure-pipelines", "aws-codebuild", "google-cloud-build", "harbor", "zot", "distribution", "ghcr",
        "nexus", "artifactory", "ecr", "artifact-registry", "gcr", "acr", "ovh-registry",
        "scaleway-registry", "opentofu", "terraform", "helm", "kustomize", "argo-cd", "flux",
        "docker-compose", "ansible",
    }
    from .generators.iac import IAC_RESOURCES
    from .generators.platform import COMPOSE_SERVICES, PLATFORM_CHARTS  # import local : évite un cycle
    handled |= set(PLATFORM_CHARTS) | set(COMPOSE_SERVICES) | set(IAC_RESOURCES)
    handled |= {p.id for p in ir.providers}
    for _, b in project.all_bricks():
        t = ir.catalog.get(b.tool)
        if t and t.id not in handled and t not in ir.unsupported:
            ir.unsupported.append(t)


PROVIDER_ENV = {
    "scaleway": [("SCW_ACCESS_KEY", "Clé d'accès API Scaleway"), ("SCW_SECRET_KEY", "Clé secrète API Scaleway"),
                 ("SCW_DEFAULT_PROJECT_ID", "Projet Scaleway")],
    "ovhcloud": [("OVH_APPLICATION_KEY", "Clé d'application OVHcloud"),
                 ("OVH_APPLICATION_SECRET", "Secret d'application OVHcloud"),
                 ("OVH_CONSUMER_KEY", "Clé consommateur OVHcloud")],
    "outscale": [("OSC_ACCESS_KEY", "Clé d'accès Outscale"), ("OSC_SECRET_KEY", "Clé secrète Outscale")],
}


def _cloud_variables(ir: IR, cloud: str) -> None:
    oidc = ir.project.cloud_auth == "oidc"
    if cloud == "aws":
        if oidc:
            ir.add_var("AWS_ROLE_ARN", "Rôle IAM assumé par la CI via OIDC", secret=False)
        else:
            ir.add_var("AWS_ACCESS_KEY_ID", "Clé d'accès AWS (statique, déconseillé)")
            ir.add_var("AWS_SECRET_ACCESS_KEY", "Secret de la clé d'accès AWS")
        ir.add_var("AWS_REGION", "Région AWS", secret=False)
    elif cloud == "gcp":
        if oidc:
            ir.add_var("GCP_WORKLOAD_IDENTITY_PROVIDER", "Fournisseur Workload Identity Federation", secret=False)
            ir.add_var("GCP_SERVICE_ACCOUNT", "Compte de service impersonné par la CI", secret=False)
        else:
            ir.add_var("GCP_SA_KEY", "Clé JSON du compte de service (statique, déconseillé)")
    elif cloud == "azure":
        ir.add_var("AZURE_CLIENT_ID", "Identifiant d'application Entra ID", secret=False)
        ir.add_var("AZURE_TENANT_ID", "Identifiant du tenant Entra ID", secret=False)
        ir.add_var("AZURE_SUBSCRIPTION_ID", "Identifiant d'abonnement Azure", secret=False)
        if not oidc:
            ir.add_var("AZURE_CLIENT_SECRET", "Secret d'application (statique, déconseillé)")
