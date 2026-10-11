"""Lot 0.12 : secrets — SOPS, Vault / OpenBao lus par la CI, External Secrets, coffres des clouds."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import minihelm
import pytest
import yaml
from test_data import CATALOG, COMPOSE, ENGINE, K3S_HELM, K3S_KUST, kustomize_build, project

from devops_builder.generators import generate
from devops_builder.ports import port_plan
from devops_builder.rules import RuleEngine
from devops_builder.starter import StarterAnswers, build_starter, validate

AGE = "age1ql3z7hjy54pw3hyww5ayyfg7zqgvc7w3j2elw8zmrj2kg5sfn9aqmcac8p"


def gen(p):
    return generate(p, CATALOG, ENGINE, allow_blocking=True)


def rules(p) -> set[str]:
    return {d.rule_id for d in ENGINE.evaluate(p)}


def ci_var_names(result) -> set[str]:
    return {v.name for v in result.ir.variables}


# ------------------------------------------------------------------ source des valeurs dans la CI
def test_sans_coffre_les_variables_ci_restent_la_source():
    r = gen(project("docker-host", *COMPOSE, "postgresql"))
    assert {"POSTGRESQL_PASSWORD_STAGING", "POSTGRESQL_PASSWORD_PRODUCTION"} <= ci_var_names(r)
    assert "scripts/secrets-fetch.sh" not in r.files and "VAULT_ADDR" not in ci_var_names(r)


def test_openbao_lu_par_la_ci_avant_le_script_de_secrets():
    p = project("docker-host", *COMPOSE, "postgresql", "openbao", openbao={"address": "https://bao.example.com"})
    r = gen(p)
    names = ci_var_names(r)
    assert "POSTGRESQL_PASSWORD_STAGING" not in names and {"VAULT_ADDR", "VAULT_TOKEN"} <= names
    ci = yaml.safe_load(r.files[".gitlab-ci.yml"])
    assert ci["variables"]["VAULT_ADDR"] == "https://bao.example.com"
    job = ci["deploy-staging"]
    assert job["id_tokens"] == {"VAULT_ID_TOKEN": {"aud": "$VAULT_ADDR"}}
    script = job["script"]
    fetch = script.index('SECRETS_ENV="$(bash scripts/secrets-fetch.sh staging)"')
    assert script[fetch + 1] == 'eval "$SECRETS_ENV"'
    assert script[fetch + 2] == "sh deploy/secrets.sh .secrets"  # plus de préfixe VAR="$VAR_STAGING"
    # coffre existant : pas de service Compose, pas de ligne au plan des ports, pas d'avertissement R45
    assert "openbao" not in yaml.safe_load(r.files["deploy/docker-compose.yml"])["services"]
    assert not [e for e in port_plan(p, CATALOG) if e.component_id == "openbao"]
    assert "R45" not in rules(p) and "openbao" in r.ir.covered


def test_coffre_deploye_avec_compose_injoignable_depuis_la_ci():
    p = project("docker-host", *COMPOSE, "postgresql", "vault")
    assert "R45" in rules(p)
    services = yaml.safe_load(gen(p).files["deploy/docker-compose.yml"])["services"]
    assert services["vault"]["command"] == ["server"]
    assert "R45" not in rules(project("docker-host", *COMPOSE, "vault"))  # rien à lire


def test_sops_dans_ansible_et_sur_la_machine_du_runner_github():
    p = project("vm", "github", "github-actions", "buildkit", "ghcr", "docker-compose", "ansible", "postgresql",
                "sops", sops={"age_recipients": AGE}, ansible={"hosts": "a.example.com"})
    r = gen(p)
    assert yaml.safe_load(r.files[".sops.yaml"]) == {
        "creation_rules": [{"path_regex": r"deploy/secrets/.*\.enc\.env$", "age": AGE}]}
    assert "SOPS_AGE_KEY" in ci_var_names(r) and "POSTGRESQL_PASSWORD_STAGING" not in ci_var_names(r)
    run = yaml.safe_load(r.files[".github/workflows/pipeline.yml"])["jobs"]["deploy-staging"]["steps"][-1]["run"]
    assert '"$HOME/.local/bin/sops"' in run and "apk add" not in run
    assert run.index("secrets-fetch.sh staging") < run.index("sh deploy/secrets.sh") < run.index("ansible-playbook")
    assert "R34" not in rules(p)
    assert "R34" in rules(project("vm", "gitlab", "gitlab-ci", "docker-compose", "postgresql", "sops"))


def test_scripts_de_secrets_valides():
    for p in (project("docker-host", *COMPOSE, "postgresql", "redis", "openbao"),
              project("docker-host", *COMPOSE, "postgresql", "sops", sops={"age_recipients": AGE})):
        for path, text in gen(p).files.items():
            if path.startswith("scripts/secrets-"):
                assert subprocess.run(["bash", "-n"], input=text, text=True).returncode == 0, path
                if shutil.which("shellcheck"):
                    sc = subprocess.run(["shellcheck", "-S", "warning", "-"], input=text, text=True,
                                        capture_output=True)
                    assert sc.returncode == 0, sc.stdout


def write(result, root: Path) -> Path:
    result.write(root)
    return root


@pytest.mark.skipif(not (shutil.which("sops") and shutil.which("age-keygen")), reason="sops ou age absents")
def test_sops_chiffre_puis_dechiffre_les_secrets(tmp_path):
    key = tmp_path / "key.txt"
    out = subprocess.run(["age-keygen", "-o", str(key)], capture_output=True, text=True, check=True)
    public = out.stderr.split(":", 1)[1].strip()
    repo = write(gen(project("docker-host", *COMPOSE, "postgresql", "redis", "sops",
                             sops={"age_recipients": public})), tmp_path / "repo")
    env = {**os.environ, "POSTGRESQL_PASSWORD": "Pg-1_a.b~c", "REDIS_PASSWORD": "r3d1s"}
    subprocess.run(["bash", "scripts/secrets-seed.sh", "staging"], cwd=repo, env=env, check=True, capture_output=True)
    encrypted = (repo / "deploy/secrets/staging.enc.env").read_text()
    assert "Pg-1_a.b~c" not in encrypted and "ENC[AES256_GCM" in encrypted
    bad = subprocess.run(["bash", "scripts/secrets-seed.sh", "production"], cwd=repo, capture_output=True, text=True,
                         env={**env, "POSTGRESQL_PASSWORD": "a b"})
    assert bad.returncode == 1 and "caractères autorisés" in bad.stderr
    clean = {k: v for k, v in os.environ.items() if not k.endswith("_PASSWORD")}
    clean["SOPS_AGE_KEY"] = next(line for line in key.read_text().splitlines() if line.startswith("AGE-SECRET-KEY"))
    script = 'SECRETS_ENV="$(bash scripts/secrets-fetch.sh staging)"; eval "$SECRETS_ENV"; sh deploy/secrets.sh .s'
    subprocess.run(["bash", "-ec", script], cwd=repo, env=clean, check=True, capture_output=True)
    assert (repo / ".s/app.env").read_text() == ("DATABASE_URL=postgresql://app:Pg-1_a.b~c@postgresql:5432/app\n"
                                                 "REDIS_URL=redis://:r3d1s@redis:6379/0\n")
    missing = subprocess.run(["bash", "scripts/secrets-fetch.sh", "production"], cwd=repo, env=clean,
                             capture_output=True, text=True)
    assert missing.returncode == 1 and "secrets-seed.sh production" in missing.stderr


class FakeVault(BaseHTTPRequestHandler):
    """Vault réduit : KV v2 sous « apps », auth/jwt/login avec un rôle et un jeton OIDC attendus."""

    store: dict[str, dict] = {}
    logins: list[dict] = []

    def _reply(self, code: int, body: dict | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body or {}).encode())

    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/v1/auth/jwt/login":
            self.logins.append(body)
            if body == {"role": "shop-deploy", "jwt": "oidc-de-la-ci"}:
                return self._reply(200, {"auth": {"client_token": "t-ci"}})
            return self._reply(400, {"errors": ["role or jwt"]})
        if self.headers.get("X-Vault-Token") != "t-root" or not self.path.startswith("/v1/apps/data/"):
            return self._reply(403)
        self.store[self.path.removeprefix("/v1/apps/data/")] = body["data"]
        return self._reply(200)

    def do_GET(self):  # noqa: N802
        if self.headers.get("X-Vault-Token") not in ("t-ci", "t-root"):
            return self._reply(403)
        data = self.store.get(self.path.removeprefix("/v1/apps/data/"))
        return self._reply(200, {"data": {"data": data}}) if data else self._reply(404)

    def log_message(self, *args):
        pass


@pytest.fixture
def fake_vault():
    FakeVault.store, FakeVault.logins = {}, []
    server = HTTPServer(("127.0.0.1", 0), FakeVault)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


@pytest.mark.skipif(not (shutil.which("jq") and shutil.which("curl")), reason="jq ou curl absents")
def test_vault_ecrit_par_le_script_puis_lu_par_jwt(tmp_path, fake_vault):
    p = project("docker-host", *COMPOSE, "postgresql", "redis", "vault",
                vault={"address": "https://vault.example.com", "jwt_role": "shop-deploy", "kv_mount": "apps"})
    repo = write(gen(p), tmp_path)
    base = {k: v for k, v in os.environ.items() if not k.startswith(("VAULT", "ACTIONS_ID"))}
    base["VAULT_ADDR"] = fake_vault
    seed = {**base, "VAULT_TOKEN": "t-root", "POSTGRESQL_PASSWORD": "pg-pass", "REDIS_PASSWORD": "rd-pass"}
    subprocess.run(["bash", "scripts/secrets-seed.sh", "staging"], cwd=repo, env=seed, check=True, capture_output=True)
    assert FakeVault.store == {"shop-staging/postgresql": {"password": "pg-pass"},
                               "shop-staging/redis": {"password": "rd-pass"}}
    out = subprocess.run(["bash", "scripts/secrets-fetch.sh", "staging"], cwd=repo, capture_output=True, text=True,
                         env={**base, "VAULT_ID_TOKEN": "oidc-de-la-ci"}, check=True).stdout
    assert out == "export POSTGRESQL_PASSWORD=pg-pass\nexport REDIS_PASSWORD=rd-pass\n"
    assert FakeVault.logins == [{"role": "shop-deploy", "jwt": "oidc-de-la-ci"}]
    refused = subprocess.run(["bash", "scripts/secrets-fetch.sh", "staging"], cwd=repo, capture_output=True,
                             text=True, env={**base, "VAULT_ID_TOKEN": "autre"})
    assert refused.returncode == 1 and "rôle shop-deploy" in refused.stderr
    absent = subprocess.run(["bash", "scripts/secrets-fetch.sh", "production"], cwd=repo, capture_output=True,
                            text=True, env={**base, "VAULT_TOKEN": "t-root"})
    assert absent.returncode == 1 and "apps/shop/postgresql" in absent.stderr
    nothing = subprocess.run(["bash", "scripts/secrets-fetch.sh", "staging"], cwd=repo, capture_output=True,
                             text=True, env=base)
    assert nothing.returncode == 1 and "Ni VAULT_TOKEN ni jeton OIDC" in nothing.stderr


# ------------------------------------------------------------------ Kubernetes et External Secrets
def chart(files, release="shop-staging"):
    values = yaml.safe_load(files["charts/shop/values.yaml"])
    values = minihelm.merge(values, yaml.safe_load(files["charts/shop/values-staging.yaml"]))
    return minihelm.render_chart(files, "charts/shop", values, release=release, namespace="shop-staging")


def test_helm_et_external_secrets_depuis_openbao():
    r = gen(project("kubernetes", *K3S_HELM, "postgresql", "openbao", "external-secrets"))
    f = r.files
    assert yaml.safe_load(f["charts/shop/values.yaml"])["database"]["postgresql"]["createSecret"] is False
    docs = chart(f)
    assert not [d for d in docs if d["kind"] == "Secret"]
    es = next(d for d in docs if d["kind"] == "ExternalSecret")
    assert es["spec"]["secretStoreRef"] == {"kind": "ClusterSecretStore", "name": "shop"}
    assert es["spec"]["target"]["name"] == "shop-staging-postgresql"
    assert es["spec"]["target"]["template"]["data"] == {
        "password": "{{ .password }}", "url": "postgresql://app:{{ .password }}@shop-staging-postgresql:5432/app"}
    assert es["spec"]["data"] == [{"secretKey": "password",
                                   "remoteRef": {"key": "shop-staging/postgresql", "property": "password"}}]
    # le Secret lu par l'application et la base est bien celui qu'écrit External Secrets
    sts = next(d for d in docs if d["kind"] == "StatefulSet")
    ref = sts["spec"]["template"]["spec"]["containers"][0]["env"][-1]["valueFrom"]["secretKeyRef"]
    assert ref == {"name": "shop-staging-postgresql", "key": "password"}
    ci = f[".github/workflows/pipeline.yml"]
    assert "--set-string" not in ci and "secrets-fetch" not in ci and "VAULT_ADDR" not in ci_var_names(r)
    store = yaml.safe_load(f["platform/external-secrets/cluster-secret-store.yaml"])
    assert store["spec"]["provider"]["vault"]["server"] == "http://openbao.openbao.svc:8200"
    install = f["platform/install.sh"].splitlines()
    eso = next(i for i, line in enumerate(install) if "install external-secrets" in line)
    assert install[eso].endswith("--wait")
    assert install[eso + 1] == 'kubectl apply -f "$(dirname "$0")/external-secrets/cluster-secret-store.yaml"'
    assert "scripts/secrets-seed.sh" in f and "scripts/secrets-fetch.sh" not in f


def test_helm_sans_external_secrets_lit_vault_dans_la_ci():
    r = gen(project("kubernetes", *K3S_HELM, "postgresql", "vault", vault={"address": "https://v.example.com"}))
    ci = yaml.safe_load(r.files[".github/workflows/pipeline.yml"])
    run = ci["jobs"]["deploy-staging"]["steps"][-1]["run"]
    assert run.index("secrets-fetch.sh staging") < run.index("helm upgrade")
    assert '--set-string database.postgresql.password="$POSTGRESQL_PASSWORD"' in run
    assert "vault" not in r.files.get("platform/install.sh", "")  # coffre existant : rien à installer


def test_kustomize_externalsecret_par_overlay(tmp_path):
    p = project("kubernetes", *K3S_KUST, "valkey", "openbao", "external-secrets")
    r = gen(p)
    overlay = yaml.safe_load(r.files["deploy/kustomize/overlays/production/kustomization.yaml"])
    assert overlay["resources"] == ["../../base", "externalsecrets.yaml"]
    ci = r.files[".gitlab-ci.yml"]
    assert "create secret generic" not in ci and "kubectl create namespace shop " in ci
    if shutil.which("kustomize") or shutil.which("kubectl"):
        r.write(tmp_path)
        docs = kustomize_build(tmp_path, "deploy/kustomize/overlays/staging")
        es = next(d for d in docs if d["kind"] == "ExternalSecret")
        assert es["metadata"]["namespace"] == "shop-staging"
        assert es["spec"]["data"][0]["remoteRef"]["key"] == "shop-staging/valkey"
        assert es["spec"]["target"]["template"]["data"]["url"] == "redis://:{{ .password }}@shop-valkey:6379/0"


@pytest.mark.parametrize("store, provider", [("aws-secrets-manager", "aws"), ("gcp-secret-manager", "gcpsm"),
                                             ("azure-key-vault", "azurekv"), ("vault", "vault")])
def test_un_clusterstore_par_coffre(store, provider):
    r = gen(project("kubernetes", *K3S_HELM, store, "external-secrets"))
    doc = yaml.safe_load(r.files["platform/external-secrets/cluster-secret-store.yaml"])
    assert doc["apiVersion"] == "external-secrets.io/v1" and list(doc["spec"]["provider"]) == [provider]
    assert "External Secrets : le ClusterSecretStore « shop »" in r.files["PIPELINE.md"]


def test_gitops_avec_external_secrets_ne_renvoie_plus_vers_sops():
    f = gen(project("kubernetes", *K3S_HELM, "argo-cd", "valkey", "openbao", "external-secrets")).files
    assert "External Secrets ou SOPS" not in f["PIPELINE.md"]
    assert "charts/shop/templates/externalsecrets.yaml" in f


# ------------------------------------------------------------------ Terraform et coffres des clouds
def eks_project(*extra: str, envs: str = "staging-prod"):
    p = project("kubernetes-managed", "gitlab", "gitlab-ci", "buildkit", "aws", "ecr", "eks", "opentofu", "s3",
                "helm", *extra, envs=envs)
    return p


def test_terraform_ecrit_l_url_rds_et_le_mot_de_passe_valkey():
    r = gen(eks_project("aws-rds", "valkey", "aws-secrets-manager", "external-secrets"))
    main = r.files["infra/terraform/main.tf"]
    assert 'resource "aws_secretsmanager_secret" "app"' not in main
    assert 'name                    = "shop-staging/aws-rds"\n  recovery_window_in_days = 0' in main
    assert 'name = "shop/aws-rds"\n}' in main  # production : délai de récupération par défaut
    assert ('data "aws_secretsmanager_secret_version" "db_production_master" {\n'
            '  secret_id = aws_db_instance.db_production.master_user_secret[0].secret_arn') in main
    assert ('jsonencode({ url = "postgresql://app:${urlencode(jsondecode(data.aws_secretsmanager_secret_version'
            '.db_staging_master.secret_string)["password"])}@${aws_db_instance.db_staging.address}:5432/app" })') in main
    assert "jsonencode({ password = random_password.secret_valkey_production.result })" in main
    assert "hashicorp/random" in r.files["infra/terraform/versions.tf"]
    assert "scripts/secrets-seed.sh" not in r.files  # tout est écrit par la pile
    assert "AWS Secrets Manager, clé `<espace de noms>/aws-rds` (External Secrets, écrit par Terraform)" in \
        r.files["PIPELINE.md"]


def test_key_vault_en_rbac_quand_la_pile_y_ecrit():
    p = project("kubernetes-managed", "gitlab", "gitlab-ci", "buildkit", "azure", "acr", "aks", "opentofu",
                "azure-blob", "helm", "azure-database", "azure-key-vault", "external-secrets", envs="prod")
    main = gen(p).files["infra/terraform/main.tf"]
    assert "enable_rbac_authorization = true" in main
    assert 'role_definition_name = "Key Vault Secrets Officer"' in main
    assert 'name         = "shop-azure-database"' in main and "depends_on = [azurerm_role_assignment.kv_terraform]" in main
    alone = project("kubernetes-managed", "gitlab", "gitlab-ci", "azure", "aks", "opentofu", "azure-key-vault")
    assert "enable_rbac_authorization" not in gen(alone).files["infra/terraform/main.tf"]  # inchangé sans base


def test_serverless_valeur_brute_dans_le_coffre():
    a = StarterAnswers(hosting="serverless", cloud="gcp", envs="staging-prod", database="postgresql", secrets="cloud")
    f = gen(build_starter(a, CATALOG)).files
    main = f["infra/terraform/main.tf"]
    assert 'secret_id = "mon-app-staging-cloud-sql"' in main
    assert 'secret_data = "postgresql://app:${random_password.db_staging.result}@' in main
    assert "jsonencode" not in main


def test_coffre_du_cloud_sans_external_secrets_garde_les_variables_ci():
    r = gen(project("docker-host", *COMPOSE, "aws", "postgresql", "aws-secrets-manager"))
    assert "POSTGRESQL_PASSWORD_STAGING" in ci_var_names(r) and "scripts/secrets-seed.sh" not in r.files


# ------------------------------------------------------------------ assistant
@pytest.mark.parametrize("hosting, cloud, secrets, tools", [
    ("docker-host", None, "sops", {"sops"}),
    ("kubernetes", None, "openbao", {"openbao", "external-secrets"}),
    ("kubernetes-managed", "aws", "cloud", {"aws-secrets-manager", "external-secrets"}),
    ("serverless", "azure", "cloud", {"azure-key-vault"}),
])
def test_assistant_propose_la_source_des_secrets(hosting, cloud, secrets, tools):
    a = StarterAnswers(hosting=hosting, cloud=cloud, secrets=secrets, database="postgresql")
    assert not validate(a)
    p = build_starter(a, CATALOG)
    assert tools <= p.tool_ids()
    assert not RuleEngine.blocking(ENGINE.evaluate(p))


def test_assistant_refuse_les_combinaisons_sans_sens():
    assert validate(StarterAnswers(hosting="docker-host", secrets="cloud"))
    assert validate(StarterAnswers(hosting="kubernetes-managed", cloud="scaleway", secrets="cloud"))
    assert validate(StarterAnswers(hosting="serverless", cloud="gcp", secrets="sops"))
    assert "sops" not in build_starter(StarterAnswers(), CATALOG).tool_ids()  # défaut : variables CI
