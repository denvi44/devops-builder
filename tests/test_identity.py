# SPDX-License-Identifier: Apache-2.0
"""Lot 0.15 : fournisseur d'identité — Keycloak et Dex, realm en code, connexion unique des outils."""

from __future__ import annotations

import itertools
import json
import os
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
import yaml
from test_data import CATALOG, COMPOSE, ENGINE, K3S_HELM, project

from devops_builder.generators import generate
from devops_builder.rules import RuleEngine
from devops_builder.starter import StarterAnswers, build_starter, validate

KC = {"hostname": "auth.boutique.fr", "tools_domain": "boutique.fr", "app_url": "https://boutique.fr"}


def gen(p):
    return generate(p, CATALOG, ENGINE, allow_blocking=True)


def rule_ids(p) -> set[str]:
    return {d.rule_id for d in ENGINE.evaluate(p)}


# ------------------------------------------------------------------ hôte Docker
def test_keycloak_sur_hote_docker_avec_sa_base_et_traefik():
    r = gen(project("docker-host", *COMPOSE, "postgresql", "keycloak", "grafana", keycloak=KC))
    services = yaml.safe_load(r.files["deploy/docker-compose.yml"])["services"]
    kc = services["keycloak"]
    assert kc["image"] == "quay.io/keycloak/keycloak:26.8" and kc["command"] == ["start"]
    assert kc["environment"]["KC_HOSTNAME"] == "https://auth.boutique.fr"
    assert kc["environment"]["KC_PROXY_HEADERS"] == "xforwarded"
    assert "traefik.http.routers.keycloak.rule=Host(`auth.boutique.fr`)" in kc["labels"]
    assert services["keycloak-db"]["env_file"] == ["secrets/keycloak-db.env"]
    app = services["shop"]["environment"]
    assert app["OIDC_ISSUER_URL"] == "https://auth.boutique.fr/realms/shop" and app["OIDC_CLIENT_ID"] == "shop"
    graf = services["grafana"]["environment"]
    assert graf["GF_AUTH_GENERIC_OAUTH_AUTH_URL"] == "https://auth.boutique.fr/realms/shop/protocol/openid-connect/auth"
    script = r.files["deploy/secrets.sh"]
    assert 'cat > "$dir/keycloak.env" <<EOF\nKC_DB_PASSWORD=$KEYCLOAK_DB_PASSWORD\n' in script
    assert ': "${GRAFANA_OIDC_SECRET:=}"' in script  # connu une fois le realm appliqué
    names = {v.name for v in r.ir.variables}
    assert {"KEYCLOAK_DB_PASSWORD_STAGING", "KEYCLOAK_ADMIN_PASSWORD_PRODUCTION"} <= names
    ci = r.files[".gitlab-ci.yml"]
    assert 'KEYCLOAK_DB_PASSWORD="$KEYCLOAK_DB_PASSWORD_STAGING"' in ci
    assert subprocess.run(["sh", "-n"], input=script, text=True).returncode == 0


def test_keycloak_lu_dans_le_coffre_par_la_ci():
    p = project("docker-host", *COMPOSE, "keycloak", "openbao", keycloak=KC,
                openbao={"address": "https://coffre.boutique.fr"})
    r = gen(p)
    assert "KEYCLOAK_DB_PASSWORD_STAGING" not in {v.name for v in r.ir.variables}
    fetch = r.files["scripts/secrets-fetch.sh"]
    assert 'read_secret KEYCLOAK_DB_PASSWORD "$NS/keycloak" keycloak_db_password' in fetch


def test_prerequis_signales():
    assert "R49" in rule_ids(project("docker-host", "gitlab", "gitlab-ci", "docker-compose", "keycloak"))
    assert "R49" not in rule_ids(project("kubernetes", *K3S_HELM, "keycloak"))
    assert "R48" in rule_ids(project("kubernetes", *K3S_HELM, "keycloak", "dex", "cloudnative-pg"))


# ------------------------------------------------------------------ Kubernetes
def test_keycloak_operateur_base_cloudnativepg_et_ingress():
    f = gen(project("kubernetes", *K3S_HELM, "cloudnative-pg", "keycloak", "argo-cd", "grafana", keycloak=KC)).files
    docs = list(yaml.safe_load_all(f["platform/keycloak/keycloak.yaml"]))
    cluster, kc = docs
    assert cluster["kind"] == "Cluster" and cluster["spec"]["bootstrap"]["initdb"] == {"database": "keycloak",
                                                                                     "owner": "keycloak"}
    assert kc["apiVersion"] == "k8s.keycloak.org/v2beta1" and kc["spec"]["instances"] == 2
    assert kc["spec"]["db"]["passwordSecret"] == {"name": "keycloak-pg-app", "key": "password"}
    assert kc["spec"]["ingress"] == {"enabled": True, "className": "traefik"}  # contrôleur embarqué de k3s
    install = f["platform/install.sh"]
    order = [install.index(x) for x in ("cnpg/cloudnative-pg", "keycloak-operator", "argo/argo-cd", "grafana-community/grafana")]
    assert order == sorted(order)  # base, puis Keycloak, puis les outils qui s'y branchent
    kc = next(d for d in yaml.safe_load_all(f["platform/keycloak/keycloak.yaml"]) if d and d["kind"] == "Keycloak")
    assert kc["spec"]["startOptimized"] is False  # image officielle : pas de --optimized au premier démarrage
    # toutes les CRD de la 26.8, sinon l'opérateur ne démarre pas (trouvé par le scénario kind-identite-keycloak)
    for crd in ("keycloaks", "keycloakrealmimports", "keycloakoidcclients", "keycloaksamlclients"):
        assert f"/26.8.0/kubernetes/{crd}.k8s.keycloak.org-v1.yml" in install
    argo = yaml.safe_load(f["platform/values/argo-cd.yaml"])
    oidc = yaml.safe_load(argo["configs"]["cm"]["oidc.config"])
    assert oidc["issuer"] == "https://auth.boutique.fr/realms/shop" and oidc["clientID"] == "argo-cd"
    assert argo["configs"]["rbac"]["policy.csv"] == "g, admins, role:admin\n"
    dep = f["charts/shop/templates/deployment.yaml"]
    assert "name: OIDC_ISSUER_URL" in dep and "value: https://auth.boutique.fr/realms/shop" in dep
    assert subprocess.run(["bash", "-n"], input=install, text=True).returncode == 0


def test_dex_delegue_a_la_forge():
    f = gen(project("kubernetes", "gitlab", "gitlab-ci", "buildkit", "k3s", "kustomize", "dex", "argo-cd", "grafana",
                    dex={"hostname": "dex.boutique.fr", "org": "boutique"})).files
    values = yaml.safe_load(f["platform/values/dex.yaml"])
    conf = values["config"]
    assert conf["issuer"] == "https://dex.boutique.fr"
    assert conf["connectors"][0]["type"] == "gitlab" and conf["connectors"][0]["config"]["groups"] == ["boutique"]
    clients = {c["id"]: c for c in conf["staticClients"]}
    assert clients["shop"]["public"] is True and clients["argo-cd"]["secretEnv"] == "ARGO_CD_OIDC_SECRET"
    assert values["envFrom"] == [{"secretRef": {"name": "dex-secrets"}}]
    assert "dex/dex --namespace dex" in f["platform/install.sh"]
    argo = yaml.safe_load(f["platform/values/argo-cd.yaml"])
    assert argo["configs"]["rbac"]["policy.csv"] == "g, boutique, role:admin\n"  # groupe de la forge
    assert "kubectl -n dex create secret generic dex-secrets" in f["docs/mise-en-route.md"]
    deployment = yaml.safe_load(f["deploy/kustomize/base/deployment.yaml"])
    env = {e["name"]: e.get("value") for e in deployment["spec"]["template"]["spec"]["containers"][0]["env"]}
    assert env["OIDC_ISSUER_URL"] == "https://dex.boutique.fr"


def test_dex_sur_hote_docker_github():
    r = gen(project("docker-host", "github", "github-actions", "buildkit", "ghcr", "docker-compose", "traefik", "dex",
                    dex={"hostname": "dex.boutique.fr"}))
    doc = yaml.safe_load(r.files["deploy/docker-compose.yml"])
    assert doc["services"]["dex"]["configs"] == [{"source": "dex-config", "target": "/etc/dex/config.yaml"}]
    config = yaml.safe_load(doc["configs"]["dex-config"]["content"])
    assert config["connectors"][0]["type"] == "github" and config["storage"]["type"] == "sqlite3"
    # « $$ » : Compose laisse $DEX_CONNECTOR_ID à Dex, qui le lit dans secrets/dex.env (trouvé par compose-dex)
    assert config["connectors"][0]["config"]["clientID"] == "$$DEX_CONNECTOR_ID"
    secrets_sh = r.files["deploy/secrets.sh"]
    assert "DEX_CONNECTOR_ID" in secrets_sh and "DEX_CONNECTOR_SECRET" in secrets_sh


# ------------------------------------------------------------------ realm en code et coffre
def test_realm_terraform_clients_des_outils():
    f = gen(project("kubernetes", *K3S_HELM, "cloudnative-pg", "keycloak", "argo-cd", "grafana", "vault",
                    keycloak=KC)).files
    main = f["infra/keycloak/main.tf"]
    assert 'realm                    = "shop"' in main
    assert 'access_type                     = "PUBLIC"' in main and 'pkce_code_challenge_method      = "S256"' in main
    for client in ("vault", "argo_cd", "grafana"):
        assert f'resource "keycloak_openid_client" "{client}"' in main
        assert f'output "{client}_client_secret"' in f["infra/keycloak/outputs.tf"]
    assert '"http://localhost:8250/oidc/callback"' in main  # vault login -method=oidc depuis le poste
    assert 'default     = "https://argocd.boutique.fr"' in f["infra/keycloak/variables.tf"]
    assert 'source  = "keycloak/keycloak"' in f["infra/keycloak/versions.tf"]


TOFU = shutil.which("tofu") or os.environ.get("DEVOPS_BUILDER_TOFU")


@pytest.mark.skipif(not (TOFU and os.environ.get("DEVOPS_BUILDER_TOFU_MIRROR")), reason="tofu et miroir absents")
def test_realm_terraform_valide(tmp_path):
    gen(project("docker-host", *COMPOSE, "keycloak", "grafana", "openbao", keycloak=KC)).write(tmp_path)
    # même sens que dans test_iac : DEVOPS_BUILDER_TOFU_MIRROR est le dossier d'un filesystem_mirror
    rc = tmp_path / "tofurc"
    rc.write_text('provider_installation {\n  filesystem_mirror {\n'
                  f'    path = "{os.environ["DEVOPS_BUILDER_TOFU_MIRROR"]}"\n  }}\n}}\n')
    env = {**os.environ, "TF_CLI_CONFIG_FILE": str(rc)}
    stack = tmp_path / "infra/keycloak"
    assert subprocess.run([TOFU, "init", "-backend=false", "-input=false"], cwd=stack, env=env,
                          capture_output=True).returncode == 0
    assert subprocess.run([TOFU, "validate"], cwd=stack, env=env, capture_output=True).returncode == 0
    assert subprocess.run([TOFU, "fmt", "-check"], cwd=stack, env=env, capture_output=True).returncode == 0


class RecordingVault(BaseHTTPRequestHandler):
    state: dict = {}

    def _reply(self, code: int, body: dict | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body or {}).encode())

    def do_GET(self):  # noqa: N802
        path = self.path.removeprefix("/v1/")
        if path == "auth/token/lookup-self":
            return self._reply(200, {"data": {}})
        if path in ("sys/mounts", "sys/auth"):
            return self._reply(200, {"data": {f"{k}/": {} for k in self.state[path]}})
        return self._reply(404)

    def do_POST(self):  # noqa: N802
        path = self.path.removeprefix("/v1/")
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        if path.startswith("sys/auth/"):
            self.state["sys/auth"].append(path.removeprefix("sys/auth/"))
        elif path.startswith("sys/mounts/"):
            self.state["sys/mounts"].append(path.removeprefix("sys/mounts/"))
        else:
            self.state["objects"][path] = body
        return self._reply(204)

    do_PUT = do_POST  # noqa: N815

    def log_message(self, *args):
        pass


@pytest.mark.skipif(not (shutil.which("jq") and shutil.which("curl")), reason="jq ou curl absents")
def test_coffre_connexion_oidc_des_personnes(tmp_path):
    RecordingVault.state = {"sys/mounts": ["secret"], "sys/auth": ["token"], "objects": {}}
    server = HTTPServer(("127.0.0.1", 0), RecordingVault)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        gen(project("docker-host", *COMPOSE, "postgresql", "keycloak", "openbao", keycloak=KC,
                    openbao={"address": "https://coffre.boutique.fr"})).write(tmp_path)
        env = {k: v for k, v in os.environ.items() if not k.startswith(("VAULT", "OIDC", "CI_"))}
        env.update(VAULT_ADDR=f"http://127.0.0.1:{server.server_port}", VAULT_TOKEN="t", CI_REPO="g/shop",
                   OIDC_CLIENT_SECRET="s3cret")
        r = subprocess.run(["bash", "scripts/vault-setup.sh"], cwd=tmp_path, env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        obj = RecordingVault.state["objects"]
        assert obj["auth/oidc/config"] == {"oidc_discovery_url": "https://auth.boutique.fr/realms/shop",
                                           "oidc_client_id": "openbao", "oidc_client_secret": "s3cret",
                                           "default_role": "admin"}
        role = obj["auth/oidc/role/admin"]
        assert role["bound_claims"] == {"groups": ["admins"]} and role["token_policies"] == ["admin"]
        assert role["allowed_redirect_uris"][0] == "https://coffre.boutique.fr/ui/vault/auth/oidc/oidc/callback"
        assert 'path \\"*\\"' in json.dumps(obj["sys/policies/acl/admin"])
    finally:
        server.shutdown()


# ------------------------------------------------------------------ assistant et mode d'emploi
@pytest.mark.parametrize("hosting, identity, tools", [
    ("kubernetes", "keycloak", {"keycloak"}),
    ("docker-host", "keycloak", {"keycloak", "traefik"}),
    ("kubernetes-managed", "dex", {"dex"}),
])
def test_assistant_connexion_unique(hosting, identity, tools):
    a = StarterAnswers(hosting=hosting, cloud="aws" if hosting == "kubernetes-managed" else None, identity=identity)
    assert not validate(a)
    p = build_starter(a, CATALOG)
    assert tools <= p.tool_ids()
    assert not RuleEngine.blocking(ENGINE.evaluate(p))
    assert validate(StarterAnswers(hosting="serverless", cloud="gcp", identity="keycloak"))


def test_toutes_les_combinaisons_identite_de_l_assistant():
    """Chaque fournisseur × forge × hébergement × GitOps × secrets : rien de bloquant, et le pipeline se génère."""
    from devops_builder.starter import FORGES, HOSTINGS, IDENTITY, SECRETS, clouds_for

    count = 0
    for forge, hosting, identity, gitops, secrets in itertools.product(
            FORGES, HOSTINGS, [i for i in IDENTITY if i != "none"], [False, True], SECRETS):
        for cloud in (clouds_for(hosting, False) or [None])[:2]:
            a = StarterAnswers(forge=forge, hosting=hosting, cloud=cloud, identity=identity, gitops=gitops,
                               secrets=secrets)
            if validate(a):
                continue
            p = build_starter(a, CATALOG)
            blocking = RuleEngine.blocking(ENGINE.evaluate(p))
            assert not blocking, (a, [d.message for d in blocking])
            count += 1
            if count % 25 == 0:  # génération complète sur un échantillon régulier
                files = generate(p, CATALOG, ENGINE).files
                assert any(k.startswith(("infra/keycloak/", "platform/", "deploy/")) for k in files)
    assert count > 50


def test_keycloak_sans_cloudnativepg_base_dediee():
    f = gen(project("kubernetes", *K3S_HELM, "keycloak", keycloak=KC)).files
    docs = list(yaml.safe_load_all(f["platform/keycloak/keycloak.yaml"]))
    assert [d["kind"] for d in docs] == ["Service", "StatefulSet", "Keycloak"]
    assert all(d["metadata"]["namespace"] == "keycloak" for d in docs)
    assert "DATABASE_URL" not in f["charts/shop/templates/deployment.yaml"]  # l'application n'en hérite pas
    assert 'kubectl -n keycloak create secret generic keycloak-db --from-literal=username=keycloak' in \
        f["platform/install.sh"]


def test_mode_d_emploi_keycloak():
    guide = gen(project("kubernetes", *K3S_HELM, "cloudnative-pg", "keycloak", keycloak=KC)).files[
        "docs/mise-en-route.md"]
    assert "kubectl -n keycloak get secret keycloak-initial-admin" in guide
    assert "tofu -chdir=infra/keycloak apply" in guide
    assert guide.index("## 2. Keycloak") < guide.index("Premier déploiement")


def test_install_sh_avec_dex_sans_secrets_ne_plante_pas(tmp_path):
    """« set -u » : avec Dex, les secrets des clients non encore renseignés ne doivent pas arrêter le script
    (trouvé par le scénario kind-plateforme)."""
    p = project("kubernetes", *K3S_HELM, "dex", "argo-cd", "grafana", "harbor",
                dex={"hostname": "dex.boutique.fr", "tools_domain": "boutique.fr"})
    gen(p).write(tmp_path)
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    for name in ("helm", "kubectl"):
        (stubs / name).write_text("#!/bin/sh\nexit 0\n")
        (stubs / name).chmod(0o755)
    env = {k: v for k, v in os.environ.items() if not k.endswith("_OIDC_SECRET")}
    env["PATH"] = f"{stubs}:{env['PATH']}"
    r = subprocess.run(["bash", "platform/install.sh"], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "ARGO_CD_OIDC_SECRET vide" in r.stderr
