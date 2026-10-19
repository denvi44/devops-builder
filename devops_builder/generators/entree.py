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
INGRESS_FILE = "platform/ingress.yaml"
ISSUER, ISSUER_FILE = "letsencrypt", "platform/cluster-issuer.yaml"
CLASSES = {"traefik": "traefik", "ingress-nginx": "nginx", "envoy-gateway": None}
# Service Kubernetes de l'interface web des charts installés par platform/install.sh : (nom, port)
CHART_SERVICES = {"grafana": ("grafana", 80), "sonarqube": ("sonarqube", 9000), "jenkins": ("jenkins", 8080),
                  "gitea": ("gitea-http", 3000), "zot": ("zot", 5000), "harbor": ("harbor", 80),
                  "argo-cd": ("argo-cd-server", 80), "argo-workflows": ("argo-workflows-server", 2746),
                  "chaos-mesh": ("chaos-dashboard", 2333), "jaeger": ("jaeger", 16686)}
# Charts dont les valeurs d'Ingress ne sont pas fiables : l'Ingress est écrit dans platform/ingress.yaml
MANIFEST_ROUTED = ("jaeger",)


def instances_of(ir: IR, tool: str) -> list:
    """Briques à installer pour un outil : toutes celles d'un outil « multi », la première sinon."""
    bricks = ir.project.bricks_for(tool)
    return bricks if ir.catalog[tool].multi else bricks[:1]


def service_name(tool: str, brick) -> str:
    """Nom du Service Kubernetes : celui du chart, dont le préfixe est le nom de la release."""
    svc = CHART_SERVICES[tool][0]
    return svc.replace(tool, brick.service_id, 1) if brick is not None and svc.startswith(tool) else svc


def namespace_of(tool: str, brick) -> str:
    from ..instances import chart_namespace
    from .platform import PLATFORM_CHARTS
    return chart_namespace(tool, brick) if brick is not None else PLATFORM_CHARTS[tool].namespace


def controller(ir: IR) -> tuple[str, str | None] | None:
    """(brique, classe d'Ingress) du contrôleur d'entrée ; classe None pour la Gateway API."""
    from .identity import kube_target
    if not kube_target(ir):
        return None
    for tool in INGRESS_TOOLS:
        if ir.has(tool):
            return tool, CLASSES[tool]
    return ("traefik", "traefik") if ir.has("k3s") else None   # contrôleur embarqué de k3s


def https(ir: IR) -> bool:
    """HTTPS à l'entrée : certificats Let's Encrypt obtenus par cert-manager (ClusterIssuer « letsencrypt »)."""
    return controller(ir) is not None and ir.has("cert-manager")


def acme_email(ir: IR) -> str:
    return next((str(b.params.get("acme_email")) for t in INGRESS_TOOLS for b in ir.project.bricks_for(t)
                 if b.params.get("acme_email")), "")


def gateway_api(ir: IR) -> bool:
    c = controller(ir)
    return bool(c and c[1] is None)


# ------------------------------------------------------------------ application
INGRESS_TEMPLATE = """{{- if .Values.ingress.enabled }}
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {{ .Release.Name }}
  {{- if .Values.ingress.clusterIssuer }}
  annotations:
    cert-manager.io/cluster-issuer: {{ .Values.ingress.clusterIssuer }}
  {{- end }}
spec:
  ingressClassName: {{ .Values.ingress.className }}
  {{- if .Values.ingress.clusterIssuer }}
  tls:
    - hosts:
        - {{ .Values.ingress.host | quote }}
      secretName: {{ .Release.Name }}-tls
  {{- end }}
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
        if https(ir):
            ingress["clusterIssuer"] = ISSUER
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
    ingress: dict = {"apiVersion": "networking.k8s.io/v1", "kind": "Ingress", "metadata": {"name": ir.app},
                     "spec": {"ingressClassName": c[1],
                              "rules": [{"host": host, "http": {"paths": [{"path": "/", "pathType": "Prefix", "backend": {
                                  "service": {"name": ir.app, "port": {"number": 80}}}}]}}]}}
    if https(ir):
        ingress["metadata"]["annotations"] = {"cert-manager.io/cluster-issuer": ISSUER}
        ingress["spec"]["tls"] = [{"hosts": [host], "secretName": f"{ir.app}-tls"}]
    return ingress


# ------------------------------------------------------------------ briques de plateforme
ANNOTATION = "cert-manager\\.io/cluster-issuer=" + ISSUER   # point échappé : clé Helm --set


def _tls_args(tool: str, host: str, release: str = "") -> str:
    """Options Helm qui demandent un certificat à cert-manager pour l'Ingress d'une brique."""
    release = release or tool
    prefix = {"jenkins": "controller.ingress", "argo-workflows": "server.ingress"}.get(tool, "ingress")
    if tool == "argo-cd":
        return f" --set server.ingress.tls=true --set 'server.ingress.annotations.{ANNOTATION}'"
    if tool == "chaos-mesh":
        return (f" --set 'dashboard.ingress.annotations.{ANNOTATION}' --set 'dashboard.ingress.hosts[0].tls=true'"
                " --set 'dashboard.ingress.hosts[0].tlsSecret=chaos-mesh-tls'")
    if tool == "harbor":
        return (f" --set 'expose.ingress.annotations.{ANNOTATION}' --set expose.tls.certSource=secret"
                " --set expose.tls.secret.secretName=harbor-tls")
    return (f" --set '{prefix}.annotations.{ANNOTATION}' --set '{prefix}.tls[0].secretName={release}-tls'"
            f" --set '{prefix}.tls[0].hosts[0]={host}'")


def chart_args(ir: IR, tool: str, brick=None) -> str:
    """Options Helm qui placent l'interface web d'une brique derrière le contrôleur."""
    args = _routing_args(ir, tool, brick)
    c = controller(ir)
    if args and c and c[1] and https(ir):
        args += _tls_args(tool, routed_hostname(ir.project, tool, brick), brick.service_id if brick else "")
    return args


def _routing_args(ir: IR, tool: str, brick=None) -> str:
    c = controller(ir)
    if not c or tool not in KUBE_ROUTED or tool in MANIFEST_ROUTED:
        return ""
    cls, host = c[1], routed_hostname(ir.project, tool, brick)
    if cls is None:   # Gateway API : la route est dans platform/gateway.yaml ; réglages du chart pour être derrière elle
        return {"argo-cd": " --set configs.params.server.insecure=true",
                "harbor": f" --set expose.type=clusterIP --set expose.tls.enabled=false --set externalURL=https://{host}"
                }.get(tool, "")
    if tool == "grafana":
        return f" --set ingress.enabled=true --set ingress.ingressClassName={cls} --set 'ingress.hosts[0]={host}'"
    if tool == "sonarqube":
        return f" --set ingress.enabled=true --set 'ingress.hosts[0].name={host}' --set ingress.ingressClassName={cls}"
    if tool == "jenkins":
        return (f" --set controller.ingress.enabled=true --set controller.ingress.ingressClassName={cls}"
                f" --set controller.ingress.hostName={host}")
    if tool == "argo-cd":   # TLS terminé à l'entrée : le serveur parle en clair
        return (f" --set server.ingress.enabled=true --set server.ingress.ingressClassName={cls}"
                f" --set server.ingress.hostname={host} --set configs.params.server.insecure=true")
    if tool == "argo-workflows":
        return (f" --set server.ingress.enabled=true --set server.ingress.ingressClassName={cls}"
                f" --set 'server.ingress.hosts[0]={host}'")
    if tool == "chaos-mesh":
        return (f" --set dashboard.ingress.enabled=true --set dashboard.ingress.ingressClassName={cls}"
                f" --set 'dashboard.ingress.hosts[0].name={host}'")
    if tool == "harbor":   # avec la connexion unique, l'adresse externe est déjà posée par identity.py
        from .identity import issuer
        base = "" if issuer(ir) else f" --set externalURL=https://{host} --set expose.ingress.hosts.core={host}"
        return base + f" --set expose.ingress.className={cls}"
    return (f" --set ingress.enabled=true --set ingress.className={cls} --set 'ingress.hosts[0].host={host}'"
            " --set 'ingress.hosts[0].paths[0].path=/'")


def issuer_file(ir: IR) -> dict[str, str]:
    """ClusterIssuer Let's Encrypt (challenge HTTP-01 par le contrôleur d'entrée) quand cert-manager est là."""
    c = controller(ir)
    if not c or not https(ir):
        return {}
    solver = ({"http01": {"ingress": {"ingressClassName": c[1]}}} if c[1] else
              {"http01": {"gatewayHTTPRoute": {"parentRefs": [{"kind": "Gateway", "name": GATEWAY,
                                                                 "namespace": GATEWAY_NS}]}}})
    spec: dict = {"server": "https://acme-v02.api.letsencrypt.org/directory",
                  "privateKeySecretRef": {"name": "letsencrypt-account"}, "solvers": [solver]}
    if acme_email(ir):
        spec["email"] = acme_email(ir)
    ir.notes.append("HTTPS Kubernetes : platform/cluster-issuer.yaml (Let's Encrypt, challenge HTTP-01) ; chaque nom "
                    "d'hôte doit pointer vers l'adresse publique du contrôleur d'entrée avant l'émission du certificat."
                    + (" Envoy Gateway : cert-manager est installé avec la Gateway API activée."
                       if c[1] is None else ""))
    return {ISSUER_FILE: dump_yaml_docs([{"apiVersion": "cert-manager.io/v1", "kind": "ClusterIssuer",
                                          "metadata": {"name": ISSUER}, "spec": {"acme": spec}}])}


def cert_manager_args(ir: IR) -> str:
    """cert-manager prêt (webhook) avant le ClusterIssuer ; Envoy Gateway : Gateway API activée sur demande."""
    if not https(ir):
        return ""
    gateway = (" --set config.apiVersion=controller.config.cert-manager.io/v1alpha1"
               " --set config.kind=ControllerConfiguration --set config.enableGatewayAPI=true"
               if gateway_api(ir) else "")
    return gateway + " --wait"


def ingress_file(ir: IR, present: list[str]) -> dict[str, str]:
    """Ingress des briques dont le chart n'en porte pas de façon fiable (platform/ingress.yaml)."""
    c = controller(ir)
    if not c or not c[1]:
        return {}
    docs = []
    for tool, brick in ((t, b) for t in present for b in instances_of(ir, t)):
        if tool in MANIFEST_ROUTED and tool in CHART_SERVICES:
            port = CHART_SERVICES[tool][1]
            svc, name = service_name(tool, brick), brick.service_id
            host = routed_hostname(ir.project, tool, brick)
            ingress: dict = {"apiVersion": "networking.k8s.io/v1", "kind": "Ingress",
                             "metadata": {"name": name, "namespace": namespace_of(tool, brick)},
                             "spec": {"ingressClassName": c[1],
                                      "rules": [{"host": host, "http": {"paths": [{
                                          "path": "/", "pathType": "Prefix",
                                          "backend": {"service": {"name": svc, "port": {"number": port}}}}]}}]}}
            if https(ir):
                ingress["metadata"]["annotations"] = {"cert-manager.io/cluster-issuer": ISSUER}
                ingress["spec"]["tls"] = [{"hosts": [host], "secretName": f"{name}-tls"}]
            docs.append(ingress)
    if not docs:
        return {}
    ir.notes.append("platform/ingress.yaml : Ingress des briques dont le chart n'en gère pas de façon fiable "
                    "(Jaeger) ; vérifier le nom du Service (kubectl -n observability get svc).")
    return {INGRESS_FILE: dump_yaml_docs(docs)}


def gateway_file(ir: IR, present: list[str]) -> dict[str, str]:
    """Gateway et routes des briques de plateforme avec Envoy Gateway (platform/gateway.yaml)."""
    if not gateway_api(ir):
        return {}
    listeners: list[dict] = [{"name": "http", "protocol": "HTTP", "port": 80,
                              "allowedRoutes": {"namespaces": {"from": "All"}}}]
    gateway: dict = {"apiVersion": "gateway.networking.k8s.io/v1", "kind": "Gateway",
                     "metadata": {"name": GATEWAY, "namespace": GATEWAY_NS},
                     "spec": {"gatewayClassName": "eg", "listeners": listeners}}
    if https(ir):   # un listener HTTPS par nom d'hôte ; cert-manager (Gateway API activée) y dépose le certificat
        gateway["metadata"]["annotations"] = {"cert-manager.io/cluster-issuer": ISSUER}
        hosts = [(f"app-{e.id}", app_hostname(ir.project, e)) for e in ir.envs]
        hosts += [(b.service_id, routed_hostname(ir.project, t, b)) for t in present
                  if t in KUBE_ROUTED and t in CHART_SERVICES for b in instances_of(ir, t)]
        for name, host in dict.fromkeys(hosts):
            listeners.append({"name": f"https-{name}", "protocol": "HTTPS", "port": 443, "hostname": host,
                              "tls": {"mode": "Terminate", "certificateRefs": [{"name": f"{name}-tls"}]},
                              "allowedRoutes": {"namespaces": {"from": "All"}}})
    docs: list[dict] = [
        {"apiVersion": "gateway.networking.k8s.io/v1", "kind": "GatewayClass", "metadata": {"name": "eg"},
         "spec": {"controllerName": "gateway.envoyproxy.io/gatewayclass-controller"}}, gateway]
    for tool, brick in ((t, b) for t in present for b in instances_of(ir, t)):
        if tool in KUBE_ROUTED and tool in CHART_SERVICES:
            svc, port = service_name(tool, brick), CHART_SERVICES[tool][1]
            docs.append({"apiVersion": "gateway.networking.k8s.io/v1", "kind": "HTTPRoute",
                         "metadata": {"name": brick.service_id, "namespace": namespace_of(tool, brick)},
                         "spec": {"parentRefs": [{"name": GATEWAY, "namespace": GATEWAY_NS}],
                                  "hostnames": [routed_hostname(ir.project, tool, brick)],
                                  "rules": [{"backendRefs": [{"name": svc, "port": port}]}]}})
    ir.notes.append("Envoy Gateway : platform/gateway.yaml déclare la GatewayClass, la Gateway (HTTP, port 80"
                    + (", un listener HTTPS par nom d'hôte, certificats cert-manager" if https(ir) else
                       " ; ajouter cert-manager au pipeline pour le HTTPS") +
                    ") et une route par interface web ; vérifier le nom des Services (kubectl -n <espace> get svc).")
    return {GATEWAY_FILE: dump_yaml_docs(docs)}


__all__ = ["controller", "gateway_api", "helm_values", "helm_env_values", "helm_templates", "kustomize_resource",
           "chart_args", "gateway_file", "ingress_file", "issuer_file", "cert_manager_args", "https", "dump_yaml", "HEADER"]
