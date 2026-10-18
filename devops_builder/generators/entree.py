# SPDX-License-Identifier: Apache-2.0
"""Entrée Kubernetes : Ingress (Traefik, ingress-nginx) ou Gateway API (Envoy Gateway) pour l'application et
pour les interfaces web des briques de plateforme.

Sans cela, le contrôleur d'entrée installé ne route rien : les Services restent joignables seulement depuis le
cluster. Le contrôleur est celui de la brique choisie (celui de k3s, Traefik, si le cluster en embarque un).
"""

from __future__ import annotations

from ..ir import IR
from ..ports import INGRESS_TOOLS, KUBE_ROUTED, app_hostname, routed_hostname
from .common import HEADER, dump_yaml, dump_yaml_docs

GATEWAY, GATEWAY_NS, GATEWAY_FILE = "entree", "envoy-gateway-system", "platform/gateway.yaml"
CLASSES = {"traefik": "traefik", "ingress-nginx": "nginx", "envoy-gateway": None}
# Service Kubernetes de l'interface web des charts installés par platform/install.sh : (nom, port)
CHART_SERVICES = {"grafana": ("grafana", 80), "sonarqube": ("sonarqube", 9000), "jenkins": ("jenkins", 8080),
                  "gitea": ("gitea-http", 3000), "zot": ("zot", 5000)}


def controller(ir: IR) -> tuple[str, str | None] | None:
    """(brique, classe d'Ingress) du contrôleur d'entrée ; classe None pour la Gateway API."""
    from .identity import kube_target
    if not kube_target(ir):
        return None
    for tool in INGRESS_TOOLS:
        if ir.has(tool):
            return tool, CLASSES[tool]
    return ("traefik", "traefik") if ir.has("k3s") else None   # contrôleur embarqué de k3s


def gateway_api(ir: IR) -> bool:
    c = controller(ir)
    return bool(c and c[1] is None)


# ------------------------------------------------------------------ application
INGRESS_TEMPLATE = """{{- if .Values.ingress.enabled }}
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {{ .Release.Name }}
spec:
  ingressClassName: {{ .Values.ingress.className }}
  rules:
    - host: {{ .Values.ingress.host | quote }}
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: {{ .Release.Name }}
                port:
                  number: {{ .Values.service.port }}
{{- end }}
"""

HTTPROUTE_TEMPLATE = """{{- if .Values.ingress.enabled }}
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: {{ .Release.Name }}
spec:
  parentRefs:
    - name: GATEWAY_NAME
      namespace: GATEWAY_NAMESPACE
  hostnames:
    - {{ .Values.ingress.host | quote }}
  rules:
    - backendRefs:
        - name: {{ .Release.Name }}
          port: {{ .Values.service.port }}
{{- end }}
""".replace("GATEWAY_NAME", GATEWAY).replace("GATEWAY_NAMESPACE", GATEWAY_NS)


def helm_values(ir: IR) -> dict:
    c = controller(ir)
    if not c:
        return {}
    ingress: dict = {"enabled": True, "host": app_hostname(ir.project)}
    if c[1]:
        ingress = {"enabled": True, "className": c[1], "host": ingress["host"]}
    return {"ingress": ingress}


def helm_env_values(ir: IR, env) -> dict:
    return {"ingress": {"host": app_hostname(ir.project, env)}} if controller(ir) else {}


def helm_templates(ir: IR) -> dict[str, str]:
    c = controller(ir)
    if not c:
        return {}
    return {"templates/httproute.yaml" if c[1] is None else "templates/ingress.yaml":
            HTTPROUTE_TEMPLATE if c[1] is None else INGRESS_TEMPLATE}


def kustomize_resource(ir: IR, env) -> dict | None:
    """Ingress ou HTTPRoute de l'application dans l'overlay d'un environnement."""
    c = controller(ir)
    if not c:
        return None
    host = app_hostname(ir.project, env)
    if c[1] is None:
        return {"apiVersion": "gateway.networking.k8s.io/v1", "kind": "HTTPRoute", "metadata": {"name": ir.app},
                "spec": {"parentRefs": [{"name": GATEWAY, "namespace": GATEWAY_NS}], "hostnames": [host],
                         "rules": [{"backendRefs": [{"name": ir.app, "port": 80}]}]}}
    return {"apiVersion": "networking.k8s.io/v1", "kind": "Ingress", "metadata": {"name": ir.app},
            "spec": {"ingressClassName": c[1],
                     "rules": [{"host": host, "http": {"paths": [{"path": "/", "pathType": "Prefix", "backend": {
                         "service": {"name": ir.app, "port": {"number": 80}}}}]}}]}}


# ------------------------------------------------------------------ briques de plateforme
def chart_args(ir: IR, tool: str) -> str:
    """Options Helm qui placent l'interface web d'une brique derrière le contrôleur (Ingress)."""
    c = controller(ir)
    if not c or not c[1] or tool not in KUBE_ROUTED:
        return ""
    cls, host = c[1], routed_hostname(ir.project, tool)
    if tool == "grafana":
        return f" --set ingress.enabled=true --set ingress.ingressClassName={cls} --set 'ingress.hosts[0]={host}'"
    if tool == "sonarqube":
        return f" --set ingress.enabled=true --set 'ingress.hosts[0].name={host}' --set ingress.ingressClassName={cls}"
    if tool == "jenkins":
        return (f" --set controller.ingress.enabled=true --set controller.ingress.ingressClassName={cls}"
                f" --set controller.ingress.hostName={host}")
    return (f" --set ingress.enabled=true --set ingress.className={cls} --set 'ingress.hosts[0].host={host}'"
            " --set 'ingress.hosts[0].paths[0].path=/'")


def gateway_file(ir: IR, present: list[str]) -> dict[str, str]:
    """Gateway et routes des briques de plateforme avec Envoy Gateway (platform/gateway.yaml)."""
    if not gateway_api(ir):
        return {}
    from .platform import PLATFORM_CHARTS
    docs: list[dict] = [
        {"apiVersion": "gateway.networking.k8s.io/v1", "kind": "GatewayClass", "metadata": {"name": "eg"},
         "spec": {"controllerName": "gateway.envoyproxy.io/gatewayclass-controller"}},
        {"apiVersion": "gateway.networking.k8s.io/v1", "kind": "Gateway",
         "metadata": {"name": GATEWAY, "namespace": GATEWAY_NS},
         "spec": {"gatewayClassName": "eg",
                  "listeners": [{"name": "http", "protocol": "HTTP", "port": 80,
                                 "allowedRoutes": {"namespaces": {"from": "All"}}}]}}]
    for tool in present:
        if tool in KUBE_ROUTED and tool in CHART_SERVICES:
            svc, port = CHART_SERVICES[tool]
            docs.append({"apiVersion": "gateway.networking.k8s.io/v1", "kind": "HTTPRoute",
                         "metadata": {"name": tool, "namespace": PLATFORM_CHARTS[tool].namespace},
                         "spec": {"parentRefs": [{"name": GATEWAY, "namespace": GATEWAY_NS}],
                                  "hostnames": [routed_hostname(ir.project, tool)],
                                  "rules": [{"backendRefs": [{"name": svc, "port": port}]}]}})
    ir.notes.append("Envoy Gateway : platform/gateway.yaml déclare la GatewayClass, la Gateway (HTTP, port 80) et une "
                    "route par interface web ; ajouter un listener HTTPS avec un certificat (cert-manager) pour le TLS, "
                    "et vérifier le nom des Services (kubectl -n <espace> get svc).")
    return {GATEWAY_FILE: dump_yaml_docs(docs)}


__all__ = ["controller", "gateway_api", "helm_values", "helm_env_values", "helm_templates", "kustomize_resource",
           "chart_args", "gateway_file", "dump_yaml", "HEADER"]
