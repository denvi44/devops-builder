# SPDX-License-Identifier: Apache-2.0
"""Briques de plateforme : charts Helm (Kubernetes) et services Compose (hôte Docker)."""

from __future__ import annotations

from dataclasses import dataclass

from ..ir import IR
from .common import HEADER, dump_yaml


@dataclass
class Chart:
    repo: str
    url: str
    chart: str
    namespace: str
    args: str = ""
    note: str = ""


PLATFORM_CHARTS: dict[str, Chart] = {
    "cert-manager": Chart("jetstack", "https://charts.jetstack.io", "jetstack/cert-manager", "cert-manager", "--set crds.enabled=true"),
    "kyverno": Chart("kyverno", "https://kyverno.github.io/kyverno/", "kyverno/kyverno", "kyverno"),
    "gatekeeper": Chart("gatekeeper", "https://open-policy-agent.github.io/gatekeeper/charts", "gatekeeper/gatekeeper", "gatekeeper-system"),
    "prometheus": Chart("prometheus-community", "https://prometheus-community.github.io/helm-charts", "prometheus-community/kube-prometheus-stack", "monitoring"),
    # grafana et tempo : charts repris par grafana-community, ceux de grafana/helm-charts sont dépréciés
    "grafana": Chart("grafana-community", "https://grafana-community.github.io/helm-charts", "grafana-community/grafana", "monitoring", note="Déjà inclus si kube-prometheus-stack est installé."),
    "loki": Chart("grafana", "https://grafana.github.io/helm-charts", "grafana/loki", "monitoring",
                  # un seul binaire, stockage sur disque : le chart refuse de s'installer sans stockage ni schéma
                  "--set deploymentMode=SingleBinary --set singleBinary.replicas=1 --set loki.auth_enabled=false "
                  "--set loki.commonConfig.replication_factor=1 --set loki.storage.type=filesystem "
                  "--set loki.useTestSchema=true --set chunksCache.enabled=false --set resultsCache.enabled=false "
                  "--set backend.replicas=0 --set read.replicas=0 --set write.replicas=0",
                  note="Stockage sur disque du pod : en production, stockage objet (loki.storage) et schéma daté."),
    "tempo": Chart("grafana-community", "https://grafana-community.github.io/helm-charts", "grafana-community/tempo", "monitoring"),
    "argo-cd": Chart("argo", "https://argoproj.github.io/argo-helm", "argo/argo-cd", "argocd"),
    "argo-rollouts": Chart("argo", "https://argoproj.github.io/argo-helm", "argo/argo-rollouts", "argo-rollouts"),
    "argo-workflows": Chart("argo", "https://argoproj.github.io/argo-helm", "argo/argo-workflows", "argo"),
    "argo-events": Chart("argo", "https://argoproj.github.io/argo-helm", "argo/argo-events", "argo-events"),
    "flux": Chart("fluxcd-community", "https://fluxcd-community.github.io/helm-charts", "fluxcd-community/flux2", "flux-system"),
    "traefik": Chart("traefik", "https://traefik.github.io/charts", "traefik/traefik", "traefik"),
    "envoy-gateway": Chart("", "", "oci://docker.io/envoyproxy/gateway-helm", "envoy-gateway-system"),
    "ingress-nginx": Chart("ingress-nginx", "https://kubernetes.github.io/ingress-nginx", "ingress-nginx/ingress-nginx", "ingress-nginx", note="Fin de maintenance en mars 2026 : migrer vers Gateway API."),
    "cilium": Chart("cilium", "https://helm.cilium.io/", "cilium/cilium", "kube-system", note="À installer avant toute charge applicative (CNI)."),
    "calico": Chart("projectcalico", "https://docs.tigera.io/calico/charts", "projectcalico/tigera-operator", "tigera-operator", note="À installer avant toute charge applicative (CNI)."),
    "istio": Chart("istio", "https://istio-release.storage.googleapis.com/charts", "istio/istiod", "istio-system", note="Installer d'abord le chart istio/base."),
    "linkerd": Chart("linkerd-edge", "https://helm.linkerd.io/edge", "linkerd-edge/linkerd-control-plane", "linkerd", note="Installer d'abord linkerd-crds ; certificats d'identité requis."),
    "longhorn": Chart("longhorn", "https://charts.longhorn.io", "longhorn/longhorn", "longhorn-system"),
    "rook": Chart("rook-release", "https://charts.rook.io/release", "rook-release/rook-ceph", "rook-ceph"),
    "velero": Chart("vmware-tanzu", "https://vmware-tanzu.github.io/helm-charts", "vmware-tanzu/velero", "velero", note="Configurer le bucket et le plugin du fournisseur."),
    "keda": Chart("kedacore", "https://kedacore.github.io/charts", "kedacore/keda", "keda"),
    "falco": Chart("falcosecurity", "https://falcosecurity.github.io/charts", "falcosecurity/falco", "falco"),
    "external-secrets": Chart("external-secrets", "https://charts.external-secrets.io", "external-secrets/external-secrets", "external-secrets"),
    "vault": Chart("hashicorp", "https://helm.releases.hashicorp.com", "hashicorp/vault", "vault"),
    "openbao": Chart("openbao", "https://openbao.github.io/openbao-helm", "openbao/openbao", "openbao"),
    "opencost": Chart("opencost", "https://opencost.github.io/opencost-helm-chart", "opencost/opencost", "opencost"),
    "jaeger": Chart("jaegertracing", "https://jaegertracing.github.io/helm-charts", "jaegertracing/jaeger", "observability"),
    "opensearch": Chart("opensearch", "https://opensearch-project.github.io/helm-charts", "opensearch/opensearch", "observability"),
    "fluent-bit": Chart("fluent", "https://fluent.github.io/helm-charts", "fluent/fluent-bit", "logging"),
    "fluentd": Chart("fluent", "https://fluent.github.io/helm-charts", "fluent/fluentd", "logging"),
    "otel-collector": Chart("open-telemetry", "https://open-telemetry.github.io/opentelemetry-helm-charts", "open-telemetry/opentelemetry-collector", "observability", "--set mode=deployment --set image.repository=otel/opentelemetry-collector-k8s"),
    "litmus": Chart("litmuschaos", "https://litmuschaos.github.io/litmus-helm/", "litmuschaos/litmus", "litmus"),
    "chaos-mesh": Chart("chaos-mesh", "https://charts.chaos-mesh.org", "chaos-mesh/chaos-mesh", "chaos-mesh"),
    "harbor": Chart("harbor", "https://helm.goharbor.io", "harbor/harbor", "harbor"),
    "zot": Chart("project-zot", "https://zotregistry.dev/helm-charts", "project-zot/zot", "zot"),
    "sonarqube": Chart("sonarqube", "https://SonarSource.github.io/helm-chart-sonarqube", "sonarqube/sonarqube", "sonarqube", note="PostgreSQL externe requis en production."),
    "gitea": Chart("gitea-charts", "https://dl.gitea.com/charts/", "gitea-charts/gitea", "gitea"),
    "jenkins": Chart("jenkins", "https://charts.jenkins.io", "jenkins/jenkins", "jenkins"),
    "crossplane": Chart("crossplane-stable", "https://charts.crossplane.io/stable", "crossplane-stable/crossplane", "crossplane-system"),
    "cloudnative-pg": Chart("cnpg", "https://cloudnative-pg.github.io/charts", "cnpg/cloudnative-pg", "cnpg-system",
                            note="Opérateur seulement : le Cluster PostgreSQL est livré avec l'application."),
    "dex": Chart("dex", "https://charts.dexidp.io", "dex/dex", "dex"),
    "kubescape": Chart("kubescape", "https://kubescape.github.io/helm-charts/", "kubescape/kubescape-operator", "kubescape"),
}

# Ordre d'installation : réseau, puis socle, puis le reste.
FIRST = ["cilium", "calico", "cert-manager", "istio", "linkerd", "cloudnative-pg"]

# Services Compose pour une cible hôte Docker / VM.
COMPOSE_SERVICES: dict[str, dict] = {
    # HTTPS pour de vrai : TLS sur l'entrée websecure (donc sur chaque route qui la vise), certificat Let's Encrypt
    # par challenge TLS sur le port 443, redirection du port 80. Sans DNS public, Traefik sert son certificat
    # par défaut (auto-signé). Trouvé par les tests de bout en bout : avant, le port 443 répondait en HTTP clair.
    "traefik": {
        "image": "traefik:v3.1",
        "command": ["--providers.docker=true", "--providers.docker.exposedbydefault=false",
                    "--entrypoints.web.address=:80",
                    "--entrypoints.web.http.redirections.entrypoint.to=websecure",
                    "--entrypoints.web.http.redirections.entrypoint.scheme=https",
                    "--entrypoints.websecure.address=:443",
                    "--entrypoints.websecure.http.tls=true",
                    "--entrypoints.websecure.http.tls.certresolver=letsencrypt",
                    "--certificatesresolvers.letsencrypt.acme.tlschallenge=true",
                    "--certificatesresolvers.letsencrypt.acme.storage=/letsencrypt/acme.json"],
        "ports": ["80:80", "443:443"],
        "volumes": ["/var/run/docker.sock:/var/run/docker.sock:ro", "traefik-letsencrypt:/letsencrypt"],
    },
    "prometheus": {"image": "prom/prometheus:latest", "ports": ["9090:9090"],
                   "volumes": ["prometheus-data:/prometheus"]},
    "grafana": {"image": "grafana/grafana:latest", "ports": ["3000:3000"],
                "volumes": ["grafana-data:/var/lib/grafana"]},
    "loki": {"image": "grafana/loki:latest", "ports": ["3100:3100"]},
    "tempo": {"image": "grafana/tempo:latest", "command": ["-config.file=/etc/tempo.yaml"]},
    "jaeger": {"image": "jaegertracing/jaeger:latest", "ports": ["16686:16686", "4317:4317", "4318:4318"]},
    "otel-collector": {"image": "otel/opentelemetry-collector-contrib:latest", "ports": ["4317:4317", "4318:4318"]},
    "opensearch": {"image": "opensearchproject/opensearch:latest",
                   "environment": {"discovery.type": "single-node",
                                   "OPENSEARCH_INITIAL_ADMIN_PASSWORD": "${OPENSEARCH_ADMIN_PASSWORD}"}},
    "fluent-bit": {"image": "fluent/fluent-bit:latest"},
    "fluentd": {"image": "fluent/fluentd:edge"},
    "minio": {"image": "minio/minio:latest", "command": ["server", "/data", "--console-address", ":9001"],
              "ports": ["9000:9000", "9001:9001"], "volumes": ["minio-data:/data"],
              "environment": {"MINIO_ROOT_USER": "${MINIO_ROOT_USER}", "MINIO_ROOT_PASSWORD": "${MINIO_ROOT_PASSWORD}"}},
    "zot": {"image": "ghcr.io/project-zot/zot-linux-amd64:latest", "ports": ["5000:5000"]},
    "distribution": {"image": "registry:2", "ports": ["5000:5000"], "volumes": ["registry-data:/var/lib/registry"]},
    "gitea": {"image": "gitea/gitea:latest", "ports": ["3001:3000", "2222:22"], "volumes": ["gitea-data:/data"]},
    "jenkins": {"image": "jenkins/jenkins:lts", "ports": ["8080:8080"], "volumes": ["jenkins-home:/var/jenkins_home"]},
    # mmap désactivé pour l'Elasticsearch embarqué : pas de vm.max_map_count à régler sur l'hôte
    "sonarqube": {"image": "sonarqube:community", "ports": ["9002:9000"], "volumes": ["sonarqube-data:/opt/sonarqube/data"],
                  "environment": {"SONAR_SEARCH_JAVAADDITIONALOPTS": "-Dnode.store.allow_mmap=false"}},
    # Vrai serveur (stockage intégré Raft), non publié sur l'hôte : à initialiser puis desceller (PIPELINE.md)
    "vault": {"image": "hashicorp/vault:latest", "command": ["server"],
              "environment": {"VAULT_ADDR": "http://127.0.0.1:8200"},
              "volumes": ["vault-data:/vault/file"],
              "configs": [{"source": "vault-config", "target": "/vault/config/vault.hcl"}]},
    "openbao": {"image": "quay.io/openbao/openbao:latest", "command": ["server"],
                "environment": {"BAO_ADDR": "http://127.0.0.1:8200"},
                "volumes": ["openbao-data:/openbao/file"],
                "configs": [{"source": "openbao-config", "target": "/openbao/config/openbao.hcl"}]},
    "falco": {"image": "falcosecurity/falco:latest", "privileged": True,
              "volumes": ["/var/run/docker.sock:/host/var/run/docker.sock", "/proc:/host/proc:ro"]},
}


def install_script(ir: IR) -> dict[str, str]:
    from . import identity, secrets
    from .data import cnpg_backup
    from .extras import embedded_components

    embedded = embedded_components(ir)
    for tid, note in embedded.items():
        ir.notes.append(note)
        ir.cover(tid)
    present = [t for t in PLATFORM_CHARTS if ir.has(t) and t not in embedded and not external_vault(ir, t)]
    ir.cover(*(t for t in ("vault", "openbao") if external_vault(ir, t)))
    idp_lines = identity.install_lines(ir)
    after_cnpg = bool(idp_lines) and "cloudnative-pg" in present
    if after_cnpg:  # le Cluster de la base de Keycloak attend l'opérateur
        idp_lines.insert(1, "kubectl -n cnpg-system rollout status deployment/cloudnative-pg --timeout=180s")
    if not present and not idp_lines:
        return {}
    ir.cover(*present)
    present.sort(key=lambda t: (FIRST.index(t) if t in FIRST else len(FIRST), t))
    repos: dict[str, str] = {}
    lines = ["#!/usr/bin/env bash", f"# {HEADER}",
             "# Installe les briques de plateforme sur le cluster courant (kubectl config current-context).",
             "set -euo pipefail", ""]
    for t in present:
        c = PLATFORM_CHARTS[t]
        if c.repo and c.repo not in repos:
            repos[c.repo] = c.url
    for name, url in repos.items():
        lines.append(f"helm repo add {name} {url}")
    if repos:
        lines += ["helm repo update", ""]
    if idp_lines and not after_cnpg:  # le fournisseur d'identité avant les outils qui s'y branchent
        lines += idp_lines
        idp_lines = []
    for t in present:
        c = PLATFORM_CHARTS[t]
        tool = ir.catalog[t]
        lines.append(f"# {tool.name}" + (f" — {c.note}" if c.note else ""))
        if t == "istio":
            lines.append("helm upgrade --install istio-base istio/base --namespace istio-system --create-namespace")
        if t == "linkerd":
            lines.append("helm upgrade --install linkerd-crds linkerd-edge/linkerd-crds --namespace linkerd --create-namespace")
        args = f" {c.args}" if c.args else ""
        if t == "sonarqube":  # le chart exige l'édition et un code de sonde (sinon il refuse de s'installer)
            lines += ["kubectl create namespace sonarqube --dry-run=client -o yaml | kubectl apply -f -",
                      "kubectl -n sonarqube get secret sonarqube-monitoring >/dev/null 2>&1 || kubectl -n sonarqube "
                      'create secret generic sonarqube-monitoring --from-literal=passcode="$(openssl rand -hex 16)"']
            args += (" --set community.enabled=true --set monitoringPasscodeSecretName=sonarqube-monitoring"
                     " --set monitoringPasscodeSecretKey=passcode")
        pre_idp, idp_args = identity.chart_args(ir, t)
        lines += pre_idp
        args += idp_args
        store_file = t == "external-secrets" and secrets.eso(ir)
        if store_file:
            pre, extra = secrets.eso_helm_args(ir)
            lines += pre
            args += extra + " --wait"  # CRD et webhook prêts avant le ClusterSecretStore
        lines.append(f"helm upgrade --install {t} {c.chart} --namespace {c.namespace} --create-namespace{args}")
        if store_file:
            lines.append(f'kubectl apply -f "$(dirname "$0")/{secrets.STORE_FILE.split("/", 1)[1]}"')
        if t == "cloudnative-pg" and after_cnpg:
            lines.append("")
            lines += idp_lines
            idp_lines = []
        if t == "cloudnative-pg" and cnpg_backup(ir):
            lines.append("# Plugin Barman Cloud : sauvegardes et archivage des WAL (demande cert-manager)")
            lines.append("helm upgrade --install plugin-barman-cloud cnpg/plugin-barman-cloud --namespace cnpg-system "
                         "--wait")
        lines.append("")
    lines += idp_lines
    return {"platform/install.sh": "\n".join(lines)}


VAULT_CONFIG = """ui            = true
disable_mlock = true
api_addr      = "http://{name}:8200"
cluster_addr  = "http://{name}:8201"

storage "raft" {{
  path    = "/{name}/file"
  node_id = "{name}-1"
}}

# Réseau interne Compose, sans TLS : ne jamais publier ce port sur l'hôte tel quel.
listener "tcp" {{
  address     = "0.0.0.0:8200"
  tls_disable = true
}}
"""


def compose_configs(ir: IR) -> dict[str, dict]:
    """Configurations Compose (contenu en ligne) des services de plateforme."""
    out = {}
    for name in ("vault", "openbao"):
        if ir.has(name) and name in COMPOSE_SERVICES and not external_vault(ir, name):
            out[f"{name}-config"] = {"content": VAULT_CONFIG.format(name=name)}
    if out:
        cli = "vault" if ir.has("vault") else "bao"
        svc = "vault" if ir.has("vault") else "openbao"
        ir.notes.append(f"{ir.catalog[svc].name} : serveur à stockage intégré, joignable seulement sur le réseau "
                        f"Compose. Une fois : `docker compose exec {svc} {cli} operator init` (clés de descellement "
                        f"et jeton racine à ranger hors de l'hôte), puis `{cli} operator unseal` après chaque "
                        "redémarrage, ou un descellement automatique (transit, KMS du cloud).")
    return out


def external_vault(ir: IR, tool_id: str) -> bool:
    """Vault / OpenBao avec une adresse : coffre existant, que le pipeline ne déploie pas."""
    return tool_id in ("vault", "openbao") and ir.has(tool_id) and bool(ir.params(tool_id).get("address"))


def compose_platform_services(ir: IR) -> dict[str, dict]:
    services = {t: COMPOSE_SERVICES[t] for t in COMPOSE_SERVICES if ir.has(t) and not external_vault(ir, t)}
    # seulement une adresse saisie : la valeur d'exemple (example.com) ferait refuser le compte par Let's Encrypt
    email = next((str(b.params.get("acme_email") or "") for b in ir.project.bricks_for("traefik")), "")
    if email and "traefik" in services:  # adresse de contact du compte Let's Encrypt (facultative)
        services["traefik"] = {**services["traefik"], "command": [
            *services["traefik"]["command"], f"--certificatesresolvers.letsencrypt.acme.email={email}"]}
    for t in ("vault", "openbao"):
        if external_vault(ir, t):
            ir.cover(t)  # coffre existant : lu par la CI (scripts/secrets-fetch.sh)
    ir.cover(*services)
    return services


def platform_files(ir: IR) -> dict[str, str]:
    files: dict[str, str] = {}
    if ir.project.target in ("kubernetes", "kubernetes-managed") or ir.cluster is not None:
        files.update(install_script(ir))
    return files


__all__ = ["PLATFORM_CHARTS", "COMPOSE_SERVICES", "platform_files", "compose_platform_services", "dump_yaml"]
