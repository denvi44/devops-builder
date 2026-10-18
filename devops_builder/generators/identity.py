# SPDX-License-Identifier: Apache-2.0
"""Fournisseur d'identité : Keycloak ou Dex — déploiement, realm en code, clients OIDC des outils et de l'application.

L'application reçoit OIDC_ISSUER_URL et OIDC_CLIENT_ID : son client est public, avec PKCE, sans secret
à transporter. Les outils du pipeline (Vault / OpenBao, Argo CD, Grafana, Harbor, SonarQube) ont chacun
un client confidentiel ; le groupe « admins » du fournisseur donne les droits d'administration.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..ir import IR
from .common import HEADER, dump_yaml, dump_yaml_docs

IDPS = ("keycloak", "dex")
KEYCLOAK_IMAGE = "quay.io/keycloak/keycloak"
KEYCLOAK_OPERATOR = "26.8.0"  # keycloak-k8s-resources : CRD et opérateur
KC_RESOURCES = f"https://raw.githubusercontent.com/keycloak/keycloak-k8s-resources/{KEYCLOAK_OPERATOR}/kubernetes"
# Toutes les CRD de la version : l'opérateur surveille chacune et ne démarre pas s'il en manque une
# (les clients OIDC et SAML sont arrivés en 26.8 ; vérifié par le scénario kind-identite-keycloak).
KC_CRDS = ("keycloaks", "keycloakrealmimports", "keycloakoidcclients", "keycloaksamlclients")
DEX_IMAGE = "ghcr.io/dexidp/dex:v2.46.0"
KEYCLOAK_PROVIDER = ("keycloak/keycloak", "~> 5.10")
KC_DIR = "infra/keycloak"
KC_FILE = "platform/keycloak/keycloak.yaml"
DEX_VALUES = "platform/values/dex.yaml"
ADMINS = "admins"
DEVELOPERS = "developpeurs"


@dataclass(frozen=True)
class ToolClient:
    tool: str
    client_id: str
    sub: str                 # sous-domaine attendu (https://<sub>.<domaine>)
    redirects: tuple[str, ...]  # chemins de retour sous l'adresse de l'outil
    var: str                 # variable de la pile Terraform qui porte l'adresse
    saml: bool = False       # client SAML (SonarQube Community ne parle pas OIDC) : Keycloak seulement
    port: int = 0            # port web du conteneur, routé par Traefik sur hôte Docker


TOOL_CLIENTS = (
    ToolClient("vault", "vault", "vault", ("/ui/vault/auth/oidc/oidc/callback",), "vault_url"),
    ToolClient("openbao", "openbao", "openbao", ("/ui/vault/auth/oidc/oidc/callback",), "openbao_url"),
    ToolClient("argo-cd", "argo-cd", "argocd", ("/auth/callback",), "argocd_url"),
    ToolClient("grafana", "grafana", "grafana", ("/login/generic_oauth",), "grafana_url", port=3000),
    ToolClient("harbor", "harbor", "harbor", ("/c/oidc/callback",), "harbor_url"),
    ToolClient("sonarqube", "sonarqube", "sonarqube", ("/oauth2/callback/saml",), "sonarqube_url", saml=True,
               port=9000),
)
CLI_CALLBACK = "http://localhost:8250/oidc/callback"  # connexion « vault login -method=oidc » depuis le poste


@dataclass(frozen=True)
class ComposeSecret:
    """Valeur d'un service de plateforme transmise par deploy/secrets.sh."""

    var: str        # variable CI (ou du coffre) lue par le script
    file: str       # fichier env_file écrit sous secrets/
    key: str        # nom de la variable dans le conteneur
    description: str
    optional: bool = False  # vide au premier déploiement (connu une fois le realm appliqué)
    tool: str = ""          # brique propriétaire (rangement dans le coffre) ; vide : le fournisseur d'identité


def idp(ir: IR) -> str | None:
    return next((t for t in IDPS if ir.has(t)), None)


def params(ir: IR) -> dict:
    tool = idp(ir)
    return ir.params(tool) if tool else {}


def host(ir: IR) -> str:
    return str(params(ir).get("hostname") or "auth.example.com")


def realm(ir: IR) -> str:
    return str(params(ir).get("realm") or ir.app)


def issuer(ir: IR) -> str | None:
    tool = idp(ir)
    if tool == "keycloak":
        return f"https://{host(ir)}/realms/{realm(ir)}"
    if tool == "dex":
        return f"https://{host(ir)}"
    return None


def admin_group(ir: IR) -> str:
    """Groupe qui reçoit les droits d'administration des outils : « admins » de Keycloak, ou le groupe de la forge."""
    if idp(ir) == "dex":
        return str(params(ir).get("org") or ADMINS)
    return ADMINS


def domain(ir: IR) -> str:
    return str(params(ir).get("tools_domain") or "example.com")


def app_url(ir: IR) -> str:
    return str(params(ir).get("app_url") or f"https://{ir.app}.example.com").rstrip("/")


def clients(ir: IR) -> list[ToolClient]:
    """Outils du pipeline branchés sur la connexion unique (Dex ne parle pas SAML : SonarQube passe alors par
    l'authentification GitHub ou GitLab qu'il intègre)."""
    return [c for c in TOOL_CLIENTS if ir.has(c.tool) and (idp(ir) == "keycloak" or not c.saml)]


def oidc_clients(ir: IR) -> list[ToolClient]:
    return [c for c in clients(ir) if not c.saml]


def compose_routes(ir: IR) -> dict[str, list[str]]:
    """Libellés Traefik des outils branchés sur la connexion unique, sur hôte Docker : leur adresse publique
    (https://<outil>.<domaine>) est celle que connaît le fournisseur d'identité."""
    if not idp(ir) or not compose_target(ir) or not ir.has("traefik"):
        return {}
    out = {}
    for c in clients(ir):
        if c.port:
            name = c.client_id
            out[c.tool] = ["traefik.enable=true",
                           f"traefik.http.routers.{name}.rule=Host(`{tool_url(ir, c).split('://', 1)[1]}`)",
                           f"traefik.http.routers.{name}.entrypoints=websecure",
                           f"traefik.http.services.{name}.loadbalancer.server.port={c.port}"]
    return out


def tool_url(ir: IR, c: ToolClient) -> str:
    if c.tool in ("vault", "openbao"):
        addr = str(ir.params(c.tool).get("address") or "")
        if addr:
            return addr.rstrip("/")
    given = str(ir.params(c.tool).get("hostname") or "")
    if given:
        return f"https://{given}"
    return f"https://{c.sub}.{domain(ir)}"


def compose_target(ir: IR) -> bool:
    return ir.project.target in ("docker-host", "vm") and ir.has("docker-compose")


def kube_target(ir: IR) -> bool:
    return ir.project.target in ("kubernetes", "kubernetes-managed") or ir.cluster is not None


def app_env(ir: IR) -> dict[str, str]:
    """Variables de l'application : émetteur et identifiant de son client public."""
    iss = issuer(ir)
    return {"OIDC_ISSUER_URL": iss, "OIDC_CLIENT_ID": ir.app} if iss else {}


def secret_env_name(c: ToolClient) -> str:
    return f"{c.client_id.upper().replace('-', '_')}_OIDC_SECRET"


def compose_secrets(ir: IR) -> list[ComposeSecret]:
    """Secrets des services Compose du fournisseur (vides hors hôte Docker)."""
    tool = idp(ir)
    if not tool or not compose_target(ir):
        return []
    if tool == "keycloak":
        return [ComposeSecret("KEYCLOAK_DB_PASSWORD", "keycloak.env", "KC_DB_PASSWORD",
                              "Mot de passe de la base de Keycloak"),
                ComposeSecret("KEYCLOAK_DB_PASSWORD", "keycloak-db.env", "POSTGRES_PASSWORD",
                              "Mot de passe de la base de Keycloak"),
                ComposeSecret("KEYCLOAK_ADMIN_PASSWORD", "keycloak.env", "KC_BOOTSTRAP_ADMIN_PASSWORD",
                              "Mot de passe de l'administrateur temporaire du premier démarrage de Keycloak")]
    out = [ComposeSecret("DEX_CONNECTOR_ID", "dex.env", "DEX_CONNECTOR_ID",
                         "Identifiant (Client ID) de l'application OAuth créée sur la forge pour Dex"),
           ComposeSecret("DEX_CONNECTOR_SECRET", "dex.env", "DEX_CONNECTOR_SECRET",
                         "Secret de l'application OAuth créée sur la forge pour Dex")]
    out += [ComposeSecret(secret_env_name(c), "dex.env", secret_env_name(c),
                          f"Secret du client OIDC {c.client_id} dans Dex (openssl rand -hex 24)") for c in clients(ir)]
    return out


def grafana_secret(ir: IR) -> list[ComposeSecret]:
    """Secret du client grafana, lu par le service Grafana de Compose."""
    if not idp(ir) or not compose_target(ir) or not ir.has("grafana"):
        return []
    src = "sortie grafana_client_secret de infra/keycloak" if idp(ir) == "keycloak" else "même valeur que dans Dex"
    return [ComposeSecret("GRAFANA_OIDC_SECRET", "grafana.env", "GF_AUTH_GENERIC_OAUTH_CLIENT_SECRET",
                          f"Secret du client OIDC grafana ({src}) ; vide : connexion OIDC inactive",
                          optional=idp(ir) == "keycloak")]


def all_compose_secrets(ir: IR) -> list[ComposeSecret]:
    """Secrets de tous les services de plateforme sur l'hôte Docker : identité, Grafana, Zabbix."""
    from . import zabbix
    return compose_secrets(ir) + grafana_secret(ir) + zabbix.compose_secrets(ir)


# ------------------------------------------------------------------ Compose
def compose_services(ir: IR) -> dict[str, dict]:
    tool = idp(ir)
    if not tool or not compose_target(ir):
        return {}
    traefik = ir.has("traefik")
    if tool == "keycloak":
        version = str(params(ir).get("version") or "26.8")
        kc: dict = {
            "image": f"{KEYCLOAK_IMAGE}:{version}", "restart": "unless-stopped", "command": ["start"],
            "environment": {"KC_DB": "postgres", "KC_DB_URL_HOST": "keycloak-db", "KC_DB_URL_DATABASE": "keycloak",
                            "KC_DB_USERNAME": "keycloak", "KC_HOSTNAME": f"https://{host(ir)}",
                            "KC_HTTP_ENABLED": "true", "KC_PROXY_HEADERS": "xforwarded", "KC_HEALTH_ENABLED": "true",
                            "KC_BOOTSTRAP_ADMIN_USERNAME": "admin-temporaire"},
            "env_file": ["secrets/keycloak.env"],
            "depends_on": {"keycloak-db": {"condition": "service_healthy"}},
        }
        port = 8080
        db = {"image": "postgres:17", "restart": "unless-stopped",
              "environment": {"POSTGRES_USER": "keycloak", "POSTGRES_DB": "keycloak"},
              "env_file": ["secrets/keycloak-db.env"], "volumes": ["keycloak-db-data:/var/lib/postgresql/data"],
              "healthcheck": {"test": ["CMD-SHELL", 'pg_isready -U "$${POSTGRES_USER}" -d "$${POSTGRES_DB}"'],
                              "interval": "10s", "timeout": "5s", "retries": 10}}
        services = {"keycloak": kc, "keycloak-db": db}
        main = kc
    else:
        dex: dict = {"image": DEX_IMAGE, "restart": "unless-stopped",
                     "command": ["dex", "serve", "/etc/dex/config.yaml"], "env_file": ["secrets/dex.env"],
                     "configs": [{"source": "dex-config", "target": "/etc/dex/config.yaml"}],
                     "volumes": ["dex-data:/var/dex"]}
        port = 5556
        services = {"dex": dex}
        main = dex
    if traefik:
        main["labels"] = [
            "traefik.enable=true",
            f"traefik.http.routers.{tool}.rule=Host(`{host(ir)}`)",
            f"traefik.http.routers.{tool}.entrypoints=websecure",
            f"traefik.http.services.{tool}.loadbalancer.server.port={port}",
        ]
    else:
        main["ports"] = [f"{port}:{port}"]
    ir.cover(tool)
    return services


def grafana_compose_env(ir: IR) -> dict[str, str]:
    """Connexion de Grafana (service Compose) au fournisseur."""
    iss = issuer(ir)
    if not iss or not ir.has("grafana"):
        return {}
    kc = idp(ir) == "keycloak"
    base = f"{iss}/protocol/openid-connect" if kc else iss
    return {
        "GF_SERVER_ROOT_URL": f"https://grafana.{domain(ir)}",
        "GF_AUTH_GENERIC_OAUTH_ENABLED": "true",
        "GF_AUTH_GENERIC_OAUTH_NAME": "Keycloak" if kc else "Dex",
        "GF_AUTH_GENERIC_OAUTH_CLIENT_ID": "grafana",
        "GF_AUTH_GENERIC_OAUTH_SCOPES": "openid profile email groups",
        "GF_AUTH_GENERIC_OAUTH_AUTH_URL": f"{base}/auth" if kc else f"{iss}/auth",
        "GF_AUTH_GENERIC_OAUTH_TOKEN_URL": f"{base}/token" if kc else f"{iss}/token",
        "GF_AUTH_GENERIC_OAUTH_API_URL": f"{base}/userinfo" if kc else f"{iss}/userinfo",
        "GF_AUTH_GENERIC_OAUTH_USE_PKCE": "true",
        "GF_AUTH_GENERIC_OAUTH_ROLE_ATTRIBUTE_PATH": f"contains(groups[*], '{admin_group(ir)}') && 'Admin' || 'Viewer'",
    }


def dex_config(ir: IR, kube: bool) -> dict:
    p = params(ir)
    connector = str(p.get("connector") or ("github" if ir.forge and ir.forge.id == "github" else "gitlab"))
    org = str(p.get("org") or "")
    iss = issuer(ir)
    conf: dict = {"clientID": "$DEX_CONNECTOR_ID", "clientSecret": "$DEX_CONNECTOR_SECRET",
                  "redirectURI": f"{iss}/callback"}
    if connector == "gitlab":
        conf["baseURL"] = "https://gitlab.com"
        if org:
            conf["groups"] = [org]
    elif org:
        conf["orgs"] = [{"name": org}]
    static = [{"id": ir.app, "name": ir.app, "public": True,
               "redirectURIs": [f"{app_url(ir)}/callback", f"{app_url(ir)}/oauth2/callback"]}]
    for c in clients(ir):
        url = tool_url(ir, c)
        redirects = [url + r for r in c.redirects]
        if c.tool in ("vault", "openbao"):
            redirects.append(CLI_CALLBACK)
        static.append({"id": c.client_id, "name": c.client_id, "secretEnv": secret_env_name(c),
                       "redirectURIs": redirects})
    return {
        "issuer": iss,
        "storage": {"type": "kubernetes", "config": {"inCluster": True}} if kube else
        {"type": "sqlite3", "config": {"file": "/var/dex/dex.db"}},
        "web": {"http": "0.0.0.0:5556"},
        "oauth2": {"skipApprovalScreen": True},
        "connectors": [{"type": connector, "id": connector, "name": "GitLab" if connector == "gitlab" else "GitHub",
                        "config": conf}],
        "staticClients": static,
    }


def compose_configs(ir: IR) -> dict[str, dict]:
    if idp(ir) != "dex" or not compose_target(ir):
        return {}
    # « $$ » : Compose remplacerait $DEX_… au déploiement par l'environnement du shell (vide sur l'hôte) ; c'est
    # Dex qui doit les lire, dans son propre environnement (secrets/dex.env)
    return {"dex-config": {"content": dump_yaml(dex_config(ir, False), None).replace("$", "$$")}}


# ------------------------------------------------------------------ Kubernetes
def kube_files(ir: IR) -> dict[str, str]:
    tool = idp(ir)
    if not tool or not kube_target(ir):
        return {}
    files: dict[str, str] = {}
    ingress_class = next((c for t, c in (("traefik", "traefik"), ("ingress-nginx", "nginx")) if ir.has(t)), None)
    if ir.has("k3s") and not ingress_class:
        ingress_class = "traefik"  # contrôleur embarqué de k3s
    if tool == "keycloak":
        prod = max((_instances(ir, e) for e in ir.envs), default=1)
        docs: list[dict] = []
        if ir.has("cloudnative-pg"):
            docs.append({"apiVersion": "postgresql.cnpg.io/v1", "kind": "Cluster",
                         "metadata": {"name": "keycloak-pg", "namespace": "keycloak"},
                         "spec": {"instances": 2 if prod > 1 else 1, "storage": {"size": "5Gi"},
                                  "bootstrap": {"initdb": {"database": "keycloak", "owner": "keycloak"}}}})
            secret, db_host = "keycloak-pg-app", "keycloak-pg-rw"
        else:  # base dédiée en StatefulSet ; le Secret est créé par platform/install.sh
            from ..databases import ENGINES, Database
            from .data import statefulset_docs
            db = Database(ir.catalog["postgresql"], ENGINES["postgresql"], "self-hosted",
                          {"database": "keycloak", "user": "keycloak", "version": "17"})
            for doc in statefulset_docs(db, "keycloak-db", "postgres:17", "5Gi", {"app": "keycloak-db"}):
                doc["metadata"]["namespace"] = "keycloak"
                docs.append(doc)
            secret, db_host = "keycloak-db", "keycloak-db"
        spec: dict = {
            "instances": prod,
            "image": f"{KEYCLOAK_IMAGE}:{params(ir).get('version') or '26.8'}",
            # Image officielle, non préconstruite : sans ce réglage l'opérateur la croit « optimisée », la lance
            # avec --optimized et elle s'arrête au premier démarrage (trouvé par kind-identite-keycloak).
            "startOptimized": False,
            "db": {"vendor": "postgres", "host": db_host, "database": "keycloak",
                   "usernameSecret": {"name": secret, "key": "username"},
                   "passwordSecret": {"name": secret, "key": "password"}},
            "http": {"httpEnabled": True},
            "hostname": {"hostname": f"https://{host(ir)}"},
            "proxy": {"headers": "xforwarded"},
            "ingress": {"enabled": bool(ingress_class)},
        }
        if ingress_class:
            spec["ingress"]["className"] = ingress_class
        docs.append({"apiVersion": "k8s.keycloak.org/v2beta1", "kind": "Keycloak",
                     "metadata": {"name": "keycloak", "namespace": "keycloak"}, "spec": spec})
        files[KC_FILE] = dump_yaml_docs(docs)
    else:
        values = {"config": dex_config(ir, True), "envFrom": [{"secretRef": {"name": "dex-secrets"}}],
                  "ingress": {"enabled": bool(ingress_class), "className": ingress_class or "",
                              "hosts": [{"host": host(ir), "paths": [{"path": "/", "pathType": "ImplementationSpecific"}]}]}}
        files[DEX_VALUES] = dump_yaml(values, f"{HEADER} Valeurs du chart dex/dex (platform/install.sh).")
    for name, text in tool_values(ir).items():
        files[name] = text
    ir.cover(tool)
    return files


def _instances(ir: IR, env) -> int:
    return 2 if env.kind == "production" else 1


def install_lines(ir: IR) -> list[str]:
    """Lignes de platform/install.sh : opérateur Keycloak puis ressources (Dex passe par son chart)."""
    if idp(ir) != "keycloak" or not kube_target(ir):
        return []
    db_secret = [] if ir.has("cloudnative-pg") else [
        "if ! kubectl -n keycloak get secret keycloak-db >/dev/null 2>&1; then  # mot de passe tiré une fois",
        '  kubectl -n keycloak create secret generic keycloak-db --from-literal=username=keycloak '
        '--from-literal=password="$(openssl rand -hex 24)"',
        "fi"]
    return ["# Keycloak — opérateur officiel, puis l'instance et sa base",
            "kubectl create namespace keycloak --dry-run=client -o yaml | kubectl apply -f -",
            *db_secret,
            *(f"kubectl apply -f {KC_RESOURCES}/{crd}.k8s.keycloak.org-v1.yml" for crd in KC_CRDS),
            f"kubectl -n keycloak apply -f {KC_RESOURCES}/kubernetes.yml",
            "kubectl -n keycloak rollout status deployment/keycloak-operator --timeout=300s",
            f'kubectl apply -f "$(dirname "$0")/{KC_FILE.split("/", 1)[1]}"', ""]


VALUES_DIR = "platform/values"


def tool_values(ir: IR) -> dict[str, str]:
    """Valeurs Helm d'Argo CD et de Grafana branchés sur le fournisseur (lues par platform/install.sh)."""
    iss = issuer(ir)
    if not iss or not kube_target(ir):
        return {}
    out: dict[str, str] = {}
    kc = idp(ir) == "keycloak"
    name = "Keycloak" if kc else "Dex"
    if ir.has("argo-cd"):
        url = f"https://argocd.{domain(ir)}"
        oidc = {"name": name, "issuer": iss, "clientID": "argo-cd", "clientSecret": "$oidc.clientSecret",
                "requestedScopes": ["openid", "profile", "email", "groups"]}
        values = {"configs": {"cm": {"url": url, "oidc.config": dump_yaml(oidc, None)},
                              "rbac": {"policy.csv": f"g, {admin_group(ir)}, role:admin\n", "policy.default": "role:readonly"}}}
        out[f"{VALUES_DIR}/argo-cd.yaml"] = dump_yaml(values, f"{HEADER} Argo CD : connexion par {name}.")
    if ir.has("grafana"):
        env = grafana_compose_env(ir)
        ini = {"server": {"root_url": env["GF_SERVER_ROOT_URL"]},
               "auth.generic_oauth": {"enabled": True, "name": name, "client_id": "grafana",
                                      "client_secret": "$__env{GRAFANA_OIDC_SECRET}",
                                      "scopes": "openid profile email groups",
                                      "auth_url": env["GF_AUTH_GENERIC_OAUTH_AUTH_URL"],
                                      "token_url": env["GF_AUTH_GENERIC_OAUTH_TOKEN_URL"],
                                      "api_url": env["GF_AUTH_GENERIC_OAUTH_API_URL"], "use_pkce": True,
                                      "role_attribute_path": env["GF_AUTH_GENERIC_OAUTH_ROLE_ATTRIBUTE_PATH"]}}
        values = {"grafana.ini": ini, "envFromSecret": "grafana-oidc"}
        out[f"{VALUES_DIR}/grafana.yaml"] = dump_yaml(values, f"{HEADER} Grafana : connexion par {name}.")
    return out


def chart_args(ir: IR, tool_id: str) -> tuple[list[str], str]:
    """Lignes et options d'installation d'un chart branché sur le fournisseur."""
    if not issuer(ir) or not kube_target(ir):
        return [], ""
    values = f' -f "$(dirname "$0")/values/{tool_id}.yaml"'
    out = f'{ir.iac_cmd} -chdir="$(dirname "$0")/../{KC_DIR}" output -raw' if idp(ir) == "keycloak" else ""
    if tool_id == "dex":
        return [], values
    if tool_id == "argo-cd" and ir.has("argo-cd"):
        lines = _secret_lines("ARGO_CD_OIDC_SECRET", out, "argo_cd_client_secret", "argo-cd")
        return lines, values + ' --set-string "configs.secret.extra.oidc\\.clientSecret=$ARGO_CD_OIDC_SECRET"'
    if tool_id == "harbor" and ir.has("harbor"):
        url = tool_url(ir, next(c for c in TOOL_CLIENTS if c.tool == "harbor"))
        host_ = url.split("://", 1)[1]
        name = "Keycloak" if idp(ir) == "keycloak" else "Dex"
        settings = ('{"auth_mode":"oidc_auth","oidc_name":"' + name + '","oidc_endpoint":"' + str(issuer(ir)) +
                    '","oidc_client_id":"harbor","oidc_client_secret":"%s","oidc_scope":"openid,profile,email,groups,'
                    'offline_access","oidc_groups_claim":"groups","oidc_admin_group":"' + admin_group(ir) +
                    '","oidc_user_claim":"preferred_username","oidc_auto_onboard":"true","oidc_verify_cert":"true"}')
        lines = _secret_lines("HARBOR_OIDC_SECRET", out, "harbor_client_secret", "harbor")
        # réglages OIDC lus par Harbor à chaque démarrage (CONFIG_OVERWRITE_JSON) ; seulement avec le secret du client
        lines += ["HARBOR_OIDC_ARGS=()",
                  'if [ -n "${HARBOR_OIDC_SECRET:-}" ]; then',
                  '  HARBOR_SETTINGS="$(mktemp)"',
                  "  printf '" + settings + "' \"$HARBOR_OIDC_SECRET\" > \"$HARBOR_SETTINGS\"",
                  '  HARBOR_OIDC_ARGS=(--set-file core.configureUserSettings="$HARBOR_SETTINGS")',
                  "fi"]
        cls = " --set expose.ingress.className=traefik" if ir.has("traefik") else ""
        return lines, (f" --set externalURL={url} --set expose.ingress.hosts.core={host_}{cls}"
                       ' "${HARBOR_OIDC_ARGS[@]}"')
    if tool_id == "sonarqube" and ir.has("sonarqube") and idp(ir) == "keycloak":
        url = tool_url(ir, next(c for c in TOOL_CLIENTS if c.tool == "sonarqube"))
        cls = " --set ingress.ingressClassName=traefik" if ir.has("traefik") else ""
        return [], f" --set ingress.enabled=true --set 'ingress.hosts[0].name={url.split('://', 1)[1]}'{cls}"
    if tool_id == "grafana" and ir.has("grafana"):
        lines = _secret_lines("GRAFANA_OIDC_SECRET", out, "grafana_client_secret", "grafana")
        lines += ["kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f -",
                  'kubectl -n monitoring create secret generic grafana-oidc '
                  '--from-literal=GRAFANA_OIDC_SECRET="$GRAFANA_OIDC_SECRET" --dry-run=client -o yaml | kubectl apply -f -']
        return lines, values
    return [], ""


def _secret_lines(var: str, out: str, output: str, client: str) -> list[str]:
    """Secret d'un client : variable, sinon sortie de la pile du realm ; vide au premier passage."""
    if out:
        lines = [f'{var}="${{{var}:-$({out} {output} 2>/dev/null || true)}}"']
        hint = f"relancer ce script après « {KC_DIR} » appliqué (docs/mise-en-route.md)"
    else:  # définie même vide : le script tourne avec « set -u »
        lines = [f'{var}="${{{var}:-}}"']
        hint = f"renseigner {var} (secret du client {client} dans Dex)"
    lines.append(f'[ -n "${{{var}:-}}" ] || echo "{var} vide : connexion OIDC inactive, {hint}" >&2')
    return lines


# ------------------------------------------------------------------ realm en code (Keycloak)
def terraform_stack(ir: IR) -> dict[str, str]:
    if idp(ir) != "keycloak":
        return {}
    src, ver = KEYCLOAK_PROVIDER
    versions = (f"# {HEADER}\n# Realm « {realm(ir)} » : comptes, groupes et clients OIDC. Appliqué à part de l'infrastructure,\n"
                "# une fois Keycloak démarré (docs/mise-en-route.md) ; le provider lit KEYCLOAK_USER et\n"
                "# KEYCLOAK_PASSWORD (administrateur du realm master) dans l'environnement.\n"
                f'terraform {{\n  required_version = ">= 1.10"\n\n  required_providers {{\n    keycloak = {{\n'
                f'      source  = "{src}"\n      version = "{ver}"\n    }}\n  }}\n}}\n\n'
                'provider "keycloak" {\n  url       = var.keycloak_url\n  client_id = "admin-cli"\n}\n')
    variables = [f"# {HEADER}",
                 f'variable "keycloak_url" {{\n  type        = string\n  description = "Adresse de Keycloak"\n'
                 f'  default     = "https://{host(ir)}"\n}}',
                 f'variable "app_url" {{\n  type        = string\n  description = "Adresse publique de '
                 f'l\'application"\n  default     = "{app_url(ir)}"\n}}']
    for c in clients(ir):
        variables.append(f'variable "{c.var}" {{\n  type        = string\n  description = "Adresse de {ir.catalog[c.tool].name}"\n'
                         f'  default     = "{tool_url(ir, c)}"\n}}')
    main = [f"# {HEADER}",
            f'resource "keycloak_realm" "main" {{\n  realm                    = "{realm(ir)}"\n'
            f'  display_name             = "{ir.project.name}"\n  enabled                  = true\n'
            '  login_with_email_allowed = true\n  ssl_required             = "external"\n'
            '  password_policy          = "length(12) and notUsername"\n}',
            *[f'resource "keycloak_group" "{g}" {{\n  realm_id = keycloak_realm.main.id\n  name     = "{g}"\n}}'
              for g in (ADMINS, DEVELOPERS)],
            '# Revendication « groups » : les outils donnent les droits d\'après les groupes',
            'resource "keycloak_openid_client_scope" "groups" {\n  realm_id               = keycloak_realm.main.id\n'
            '  name                   = "groups"\n  include_in_token_scope = true\n}',
            'resource "keycloak_openid_group_membership_protocol_mapper" "groups" {\n'
            '  realm_id        = keycloak_realm.main.id\n  client_scope_id = keycloak_openid_client_scope.groups.id\n'
            '  name            = "groups"\n  claim_name      = "groups"\n  full_path       = false\n}',
            "# Application : client public, PKCE, sans secret\n" + _block("keycloak_openid_client", "app", [
                ("realm_id", "keycloak_realm.main.id"), ("client_id", f'"{ir.app}"'),
                ("name", f'"{ir.project.name}"'), ("access_type", '"PUBLIC"'), ("standard_flow_enabled", "true"),
                ("pkce_code_challenge_method", '"S256"'), ("valid_redirect_uris", '["${var.app_url}/*"]'),
                ("valid_post_logout_redirect_uris", '["${var.app_url}/*"]'), ("web_origins", "[var.app_url]")]),
            _default_scopes("app")]
    outputs = [f"# {HEADER}", f'output "issuer" {{\n  value = "{issuer(ir)}"\n}}']
    for c in [c for c in clients(ir) if c.saml]:
        main += _saml_client(ir, c)
    for c in oidc_clients(ir):
        label = c.client_id.replace("-", "_")
        redirects = ", ".join([f'"${{var.{c.var}}}{r}"' for r in c.redirects]
                              + ([f'"{CLI_CALLBACK}"'] if c.tool in ("vault", "openbao") else []))
        main.append(_block("keycloak_openid_client", label, [
            ("realm_id", "keycloak_realm.main.id"), ("client_id", f'"{c.client_id}"'),
            ("name", f'"{ir.catalog[c.tool].name}"'), ("access_type", '"CONFIDENTIAL"'),
            ("standard_flow_enabled", "true"), ("valid_redirect_uris", f"[{redirects}]"), ("base_url", f"var.{c.var}")]))
        main.append(_default_scopes(label))
        outputs.append(f'output "{label}_client_secret" {{\n  value     = keycloak_openid_client.{label}.client_secret\n'
                       '  sensitive = true\n}')
    return {f"{KC_DIR}/versions.tf": versions, f"{KC_DIR}/main.tf": "\n\n".join(main) + "\n",
            f"{KC_DIR}/variables.tf": "\n\n".join(variables) + "\n", f"{KC_DIR}/outputs.tf": "\n\n".join(outputs) + "\n",
            f"{KC_DIR}/.gitignore": ".terraform/\n*.tfstate\n*.tfstate.*\n*.tfplan\n"}


SAML_ATTRIBUTES = (("login", "username"), ("name", "firstName"), ("email", "email"))


def _saml_client(ir: IR, c: ToolClient) -> list[str]:
    """Client SAML (SonarQube) : assertions signées, identifiant, nom, adresse et groupes en attributs."""
    label = c.client_id.replace("-", "_")
    out = [f"# {ir.catalog[c.tool].name} : SAML (son édition Community ne parle pas OIDC)\n" + _block(
        "keycloak_saml_client", label, [
            ("realm_id", "keycloak_realm.main.id"), ("client_id", f'"{c.client_id}"'),
            ("name", f'"{ir.catalog[c.tool].name}"'), ("sign_documents", "true"), ("sign_assertions", "true"),
            ("client_signature_required", "false"), ("name_id_format", '"username"'),
            ("valid_redirect_uris", f'["${{var.{c.var}}}{c.redirects[0]}"]'), ("base_url", f"var.{c.var}")])]
    for attr, prop in SAML_ATTRIBUTES:
        out.append(_block("keycloak_saml_user_property_protocol_mapper", f"{label}_{attr}", [
            ("realm_id", "keycloak_realm.main.id"), ("client_id", f"keycloak_saml_client.{label}.id"),
            ("name", f'"{attr}"'), ("user_property", f'"{prop}"'), ("saml_attribute_name", f'"{attr}"'),
            ("saml_attribute_name_format", '"Basic"')]))
    groups = _block("keycloak_generic_protocol_mapper", f"{label}_groups", [
        ("realm_id", "keycloak_realm.main.id"), ("client_id", f"keycloak_saml_client.{label}.id"),
        ("name", '"groups"'), ("protocol", '"saml"'), ("protocol_mapper", '"saml-group-membership-mapper"')])
    # attribut sur plusieurs lignes : « tofu fmt » ne l'aligne pas sur les précédents
    out.append(groups.removesuffix("}") + '  config = {\n    "attribute.name"       = "groups"\n'
               '    "attribute.nameformat" = "Basic"\n    "full.path"            = "false"\n'
               '    "single"               = "true"\n  }\n}')
    return out


def _block(kind: str, name: str, rows: list[tuple[str, str]]) -> str:
    """Bloc HCL aligné comme le ferait « tofu fmt »."""
    width = max(len(k) for k, _ in rows)
    return f'resource "{kind}" "{name}" {{\n' + "".join(f"  {k.ljust(width)} = {v}\n" for k, v in rows) + "}"


def _default_scopes(label: str) -> str:
    return _block("keycloak_openid_client_default_scopes", label, [
        ("realm_id", "keycloak_realm.main.id"), ("client_id", f"keycloak_openid_client.{label}.id"),
        ("default_scopes", '["profile", "email", "roles", "web-origins", keycloak_openid_client_scope.groups.name]')])


# ------------------------------------------------------------------ assemblage
def files(ir: IR) -> dict[str, str]:
    out: dict[str, str] = {}
    out.update(kube_files(ir))
    out.update(terraform_stack(ir))
    notes(ir)
    return out


def notes(ir: IR) -> None:
    tool = idp(ir)
    if not tool:
        return
    name = ir.catalog[tool].name
    wired = ", ".join(ir.catalog[c.tool].name for c in clients(ir))
    text = (f"{name} : émetteur OIDC {issuer(ir)} ; l'application reçoit OIDC_ISSUER_URL et OIDC_CLIENT_ID "
            "(client public, PKCE)")
    if wired:
        text += f" ; clients des outils : {wired}, droits d'administration au groupe « {admin_group(ir)} »"
    if tool == "keycloak":
        text += f". Le realm est décrit en Terraform dans {KC_DIR}/ (docs/mise-en-route.md)."
    else:
        text += ". La connexion passe par la forge : créer son application OAuth (docs/mise-en-route.md)."
    ir.notes.append(text)
