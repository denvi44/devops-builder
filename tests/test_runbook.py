# SPDX-License-Identifier: Apache-2.0
"""Lot 0.13 : mode d'emploi généré, configuration du coffre par script, identité d'External Secrets par Terraform."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
import yaml
from test_data import CATALOG, COMPOSE, ENGINE, K3S_HELM, K3S_KUST, project

from devops_builder.generators import generate
from devops_builder.starter import StarterAnswers, build_starter

GUIDE = "docs/mise-en-route.md"


def files_of(p):
    return generate(p, CATALOG, ENGINE, allow_blocking=True).files


def sections(text: str) -> list[str]:
    return re.findall(r"^## (?:\d+\. )?(.+)$", text, re.M)


def bash_blocks(text: str) -> list[str]:
    return re.findall(r"```bash\n(.*?)```", text, re.S)


# ------------------------------------------------------------------ mode d'emploi
def test_mode_d_emploi_dans_l_ordre_et_annonce_dans_le_rapport():
    a = StarterAnswers(hosting="kubernetes-managed", cloud="aws", envs="staging-prod", database="postgresql",
                       secrets="cloud")
    f = files_of(build_starter(a, CATALOG))
    guide = f[GUIDE]
    assert sections(guide) == ["Valeurs à adapter", "État Terraform", "Connexion de la CI au cloud", "Premier apply",
                               "Cluster et plateforme", "Secrets de l'application", "External Secrets",
                               "Variables CI", "Premier déploiement", "Poste de développement", "Entretien"]
    assert "aws s3api create-bucket --bucket mon-projet-tfstate" in guide
    assert "tofu -chdir=infra/terraform apply plan.tfplan" in guide
    assert "aws secretsmanager get-secret-value --secret-id mon-app-staging/aws-rds" in guide
    assert "après le premier apply (le script lit les sorties de la pile)" in guide
    assert "docs/mise-en-route.md" in f["PIPELINE.md"]


def test_valeurs_a_adapter_seulement_si_employees():
    guide = files_of(project("docker-host", *COMPOSE))[GUIDE]
    assert "Valeurs à adapter" not in guide and "$REPO" not in guide
    assert sections(guide)[0] == "Hôtes"


def test_coffre_dans_le_cluster_init_port_forward_et_script():
    guide = files_of(project("kubernetes", *K3S_HELM, "postgresql", "openbao", "external-secrets"))[GUIDE]
    assert "kubectl -n openbao exec -ti openbao-0 -- bao operator init -key-shares=5 -key-threshold=3" in guide
    assert "kubectl -n openbao port-forward svc/openbao 8200:8200 &" in guide
    assert 'export VAULT_ADDR="http://127.0.0.1:8200"' in guide
    assert "bash scripts/vault-setup.sh" in guide and "revoke-self" in guide
    assert "kubectl -n shop get externalsecret" in guide


def test_coffre_existant_sans_init():
    guide = files_of(project("docker-host", *COMPOSE, "postgresql", "vault",
                             vault={"address": "https://vault.example.com"}))[GUIDE]
    assert "operator init" not in guide and 'export VAULT_ADDR="https://vault.example.com"' in guide
    assert 'CI_REPO="$REPO" bash scripts/vault-setup.sh' in guide
    assert 'POSTGRESQL_PASSWORD="$(openssl rand -hex 24)" bash scripts/secrets-seed.sh staging' in guide


def test_sops_cle_puis_brique_puis_chiffrement():
    guide = files_of(project("docker-host", *COMPOSE, "postgresql", "sops"))[GUIDE]
    keygen, seed = guide.index("age-keygen"), guide.index("secrets-seed.sh staging")
    assert keygen < guide.index("Puis, avec `.sops.yaml` à jour") < seed
    assert "sops updatekeys" in guide


def test_hotes_ansible_et_gitops():
    guide = files_of(project("vm", "gitlab", "gitlab-ci", "buildkit", "docker-compose", "ansible"))[GUIDE]
    assert "echo 'deploy ALL=(ALL) NOPASSWD:ALL' | sudo tee /etc/sudoers.d/deploy" in guide
    assert "ansible-playbook -i ansible/inventories/staging.ini ansible/site.yml" in guide
    argo = files_of(project("kubernetes", *K3S_KUST, "argo-cd"))[GUIDE]
    assert "kubectl apply -f deploy/argocd/application.yaml" in argo
    assert 'url="https://git.example.com/groupe/gitops.git"' in argo            # dépôt de la brique
    assert "argocd.argoproj.io/secret-type=repository" in argo and "$GITOPS_READ_TOKEN" in argo
    assert 'read -rsp "Jeton de lecture du dépôt GitOps : " GITOPS_READ_TOKEN' in argo   # sans écho


def test_depot_gitops_saisi_sur_la_brique():
    p = project("kubernetes", *K3S_KUST, "argo-cd")
    p.bricks_for("argo-cd")[0].params["repo_url"] = "https://gitlab.com/boutique/gitops.git"
    files = files_of(p)
    assert "repoURL: https://gitlab.com/boutique/gitops.git" in files["deploy/argocd/application.yaml"]
    ci = files[".gitlab-ci.yml"]
    assert "GITOPS_REPO: gitlab.com/boutique/gitops.git" in ci
    assert "apk add --no-cache git yq-go" in ci and "[skip ci]" in ci and "strenv(IMAGE_NAME)" in ci


@pytest.mark.parametrize("forge, ci, issuer", [("gitlab", "gitlab-ci", "https://gitlab.com"),
                                               ("github", "github-actions", "https://token.actions.githubusercontent.com")])
def test_connexion_oidc_de_la_ci_par_cloud(forge, ci, issuer):
    for cloud, marker in (("aws", "create-open-id-connect-provider"), ("gcp", "workload-identity-pools create"),
                          ("azure", "az ad app federated-credential create")):
        p = build_starter(StarterAnswers(forge=forge, hosting="kubernetes-managed", cloud=cloud, envs="staging-prod"),
                          CATALOG)
        guide = files_of(p)[GUIDE]
        assert marker in guide and issuer in guide, cloud
    github_azure = files_of(build_starter(StarterAnswers(forge="github", hosting="kubernetes-managed",
                                                         cloud="azure", envs="staging-prod"), CATALOG))[GUIDE]
    if forge == "github":  # un identifiant fédéré par environnement GitHub, plus la branche
        assert "repo:${REPO}:environment:production" in github_azure


def test_commandes_du_mode_d_emploi_valides():
    cases = [build_starter(StarterAnswers(forge=f, hosting=h, cloud=c, envs="staging-prod", database="postgresql",
                                          secrets=s), CATALOG)
             for f, h, c, s in (("gitlab", "kubernetes-managed", "aws", "cloud"), ("github", "kubernetes", None,
                                                                                    "openbao"),
                                ("gitlab", "vm", "scaleway", "sops"), ("github", "serverless", "gcp", "cloud"),
                                ("gitlab", "kubernetes-managed", "azure", "cloud"))]
    for p in cases:
        for block in bash_blocks(files_of(p)[GUIDE]):
            assert subprocess.run(["bash", "-n"], input=block, text=True).returncode == 0, block
            if shutil.which("shellcheck"):
                sc = subprocess.run(["shellcheck", "-s", "bash", "-S", "warning", "-"], input=block, text=True,
                                    capture_output=True)
                assert sc.returncode == 0, sc.stdout


# ------------------------------------------------------------------ scripts/vault-setup.sh
class RecordingVault(BaseHTTPRequestHandler):
    """Coffre minimal : montages, méthodes d'authentification, politiques et rôles enregistrés."""

    state: dict = {}

    def _reply(self, code: int, body: dict | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body or {}).encode())

    def _ok(self) -> bool:
        if self.headers.get("X-Vault-Token") != "root":
            self._reply(403, {"errors": ["permission denied"]})
            return False
        return True

    def do_GET(self):  # noqa: N802
        if not self._ok():
            return None
        path = self.path.removeprefix("/v1/")
        if path == "auth/token/lookup-self":
            return self._reply(200, {"data": {"id": "root"}})
        if path in ("sys/mounts", "sys/auth"):
            return self._reply(200, {"data": {f"{k}/": {} for k in self.state[path]}})
        return self._reply(404)

    def do_POST(self):  # noqa: N802
        if not self._ok():
            return None
        path = self.path.removeprefix("/v1/")
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        self.state["calls"].append((self.command, path))
        if path.startswith("sys/mounts/"):
            self.state["sys/mounts"].append(path.removeprefix("sys/mounts/"))
        elif path.startswith("sys/auth/"):
            self.state["sys/auth"].append(path.removeprefix("sys/auth/"))
        else:
            self.state["objects"][path] = body
        return self._reply(204)

    do_PUT = do_POST  # noqa: N815

    def log_message(self, *args):
        pass


@pytest.fixture
def vault():
    RecordingVault.state = {"sys/mounts": ["secret", "sys"], "sys/auth": ["token"], "objects": {}, "calls": []}
    server = HTTPServer(("127.0.0.1", 0), RecordingVault)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}", RecordingVault.state
    server.shutdown()


def run_setup(tmp_path, p, env: dict) -> subprocess.CompletedProcess:
    generate(p, CATALOG, ENGINE, allow_blocking=True).write(tmp_path)
    base = {k: v for k, v in os.environ.items() if not k.startswith(("VAULT", "CI_", "KUBE_"))}
    return subprocess.run(["bash", "scripts/vault-setup.sh"], cwd=tmp_path, env={**base, **env},
                          capture_output=True, text=True)


needs_tools = pytest.mark.skipif(not (shutil.which("jq") and shutil.which("curl")), reason="jq ou curl absents")


@needs_tools
def test_setup_gitlab_kv_politique_et_role_jwt(tmp_path, vault):
    addr, state = vault
    p = project("docker-host", *COMPOSE, "postgresql", "openbao",
                openbao={"address": "https://bao.example.com", "kv_mount": "apps", "jwt_role": "shop-deploy"})
    r = run_setup(tmp_path, p, {"VAULT_ADDR": addr, "VAULT_TOKEN": "root", "CI_REPO": "groupe/shop"})
    assert r.returncode == 0, r.stderr
    assert "apps" in state["sys/mounts"] and "jwt" in state["sys/auth"]
    obj = state["objects"]
    assert obj["sys/policies/acl/shop-ci-read"]["policy"] == (
        'path "apps/data/shop/*" { capabilities = ["read"] }\n'
        'path "apps/data/shop-staging/*" { capabilities = ["read"] }\n')
    assert obj["auth/jwt/config"] == {"oidc_discovery_url": "https://gitlab.com", "bound_issuer": "https://gitlab.com"}
    role = obj["auth/jwt/role/shop-deploy"]
    assert role["bound_audiences"] == [addr] and role["token_policies"] == ["shop-ci-read"]
    assert role["bound_claims"] == {"project_path": "groupe/shop", "ref_type": "branch", "ref": "main",
                                    "ref_protected": "true"}
    calls = len(state["calls"])
    again = run_setup(tmp_path, p, {"VAULT_ADDR": addr, "VAULT_TOKEN": "root", "CI_REPO": "groupe/shop",
                                    "CI_ISSUER": "https://gitlab.example.fr"})
    assert again.returncode == 0 and "Moteur apps déjà activé" in again.stdout
    new = state["calls"][calls:]
    assert ("POST", "sys/mounts/apps") not in new and ("POST", "sys/auth/jwt") not in new  # rien n'est réactivé
    assert obj["auth/jwt/config"]["bound_issuer"] == "https://gitlab.example.fr"


@needs_tools
def test_setup_github_et_external_secrets(tmp_path, vault):
    addr, state = vault
    p = project("kubernetes", *K3S_HELM, "postgresql", "vault")  # la CI lit le coffre (pas d'External Secrets)
    r = run_setup(tmp_path, p, {"VAULT_ADDR": addr, "VAULT_TOKEN": "root", "CI_REPO": "moi/shop"})
    assert r.returncode == 0, r.stderr
    role = state["objects"]["auth/jwt/role/shop-ci"]
    assert role["bound_claims"] == {"repository": "moi/shop", "ref": "refs/heads/main"}
    assert state["objects"]["auth/jwt/config"]["oidc_discovery_url"] == "https://token.actions.githubusercontent.com"

    eso = project("kubernetes", *K3S_KUST, "valkey", "openbao", "external-secrets")
    r = run_setup(tmp_path / "eso", eso, {"VAULT_ADDR": addr, "VAULT_TOKEN": "root"})
    assert r.returncode == 0, r.stderr
    assert state["objects"]["auth/kubernetes/config"] == {"kubernetes_host": "https://kubernetes.default.svc"}
    assert state["objects"]["auth/kubernetes/role/external-secrets"] == {
        "bound_service_account_names": ["external-secrets"], "bound_service_account_namespaces": ["external-secrets"],
        "token_policies": ["shop-eso-read"], "token_ttl": "1h"}
    assert "jwt" not in [c[1] for c in state["calls"][-6:]]


@needs_tools
def test_setup_refuse_sans_jeton_ni_depot(tmp_path, vault):
    addr, _ = vault
    p = project("docker-host", *COMPOSE, "postgresql", "openbao", openbao={"address": "https://b.example.com"})
    bad = run_setup(tmp_path, p, {"VAULT_ADDR": addr, "VAULT_TOKEN": "autre", "CI_REPO": "g/p"})
    assert bad.returncode == 1 and "VAULT_TOKEN refusé" in bad.stderr
    missing = run_setup(tmp_path, p, {"VAULT_ADDR": addr, "VAULT_TOKEN": "root"})
    assert missing.returncode == 1 and "CI_REPO manquant" in missing.stderr


def test_pas_de_script_sans_usage_du_coffre():
    assert "scripts/vault-setup.sh" not in files_of(project("docker-host", *COMPOSE, "openbao"))
    jenkins = files_of(project("docker-host", "gitlab", "jenkins", "buildkit", "docker-compose", "postgresql",
                               "openbao", openbao={"address": "https://b.example.com"}))
    assert "auth/jwt" not in jenkins["scripts/vault-setup.sh"]  # Jenkins : un jeton limité, pas de JWT
    assert "auth/token/create" in jenkins["scripts/vault-setup.sh"]


# ------------------------------------------------------------------ identité d'External Secrets
def managed(cloud: str):
    return build_starter(StarterAnswers(hosting="kubernetes-managed", cloud=cloud, envs="staging-prod",
                                        secrets="cloud", database="postgresql"), CATALOG)


def test_eks_pod_identity_pour_external_secrets():
    f = files_of(managed("aws"))
    main = f["infra/terraform/main.tf"]
    assert 'Principal = { Service = "pods.eks.amazonaws.com" }' in main
    assert '"arn:aws:secretsmanager:*:*:secret:mon-app/*", "arn:aws:secretsmanager:*:*:secret:mon-app-staging/*"' in main
    assert 'resource "aws_eks_pod_identity_association" "external_secrets"' in main
    assert 'addon_name   = "eks-pod-identity-agent"' in main
    store = yaml.safe_load(f["platform/external-secrets/cluster-secret-store.yaml"])
    assert "auth" not in store["spec"]["provider"]["aws"]  # identité du contrôleur
    assert 'output "eso_role_arn"' in f["infra/terraform/outputs.tf"]


def test_gke_workload_identity_pour_external_secrets():
    main = files_of(managed("gcp"))["infra/terraform/main.tf"]
    assert ("member  = \"principal://iam.googleapis.com/projects/${data.google_project.current.number}/locations/"
            "global/workloadIdentityPools/${var.gcp_project_id}.svc.id.goog/subject/ns/external-secrets/sa/"
            "external-secrets\"") in main
    assert 'role    = "roles/secretmanager.secretAccessor"' in main


def test_aks_workload_identity_pour_external_secrets():
    f = files_of(managed("azure"))
    main = f["infra/terraform/main.tf"]
    assert "oidc_issuer_enabled       = true\n  workload_identity_enabled = true" in main
    assert 'subject             = "system:serviceaccount:external-secrets:external-secrets"' in main
    assert 'role_definition_name = "Key Vault Secrets User"' in main
    assert "enable_rbac_authorization = true" in main
    install = f["platform/install.sh"]
    assert 'ESO_CLIENT_ID="${ESO_CLIENT_ID:-$(tofu -chdir="$(dirname "$0")/../infra/terraform" output -raw ' \
           'eso_client_id)}"' in install
    assert "serviceAccount.annotations.azure\\.workload\\.identity/client-id=$ESO_CLIENT_ID" in install
    assert subprocess.run(["bash", "-n"], input=install, text=True).returncode == 0
    without = files_of(project("kubernetes-managed", "gitlab", "gitlab-ci", "azure", "aks", "opentofu",
                               "azure-key-vault"))["infra/terraform/main.tf"]
    assert "workload_identity_enabled" not in without  # sans External Secrets, le cluster ne change pas


def test_cluster_hors_cloud_garde_la_connexion_par_jeton():
    store = yaml.safe_load(files_of(project("kubernetes", *K3S_HELM, "aws", "aws-secrets-manager",
                                            "external-secrets"))["platform/external-secrets/cluster-secret-store.yaml"])
    assert store["spec"]["provider"]["aws"]["auth"] == {
        "jwt": {"serviceAccountRef": {"name": "external-secrets", "namespace": "external-secrets"}}}
