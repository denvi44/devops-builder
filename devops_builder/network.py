# SPDX-License-Identifier: Apache-2.0
"""Schéma réseau d'un environnement : qui parle à qui, ce qui est exposé, et les constats qui s'y rattachent.

Le graphe est tiré du plan de ports (`ports.port_plan`) et des diagnostics des règles : chaque composant est
rattaché aux briques qui le portent, de sorte qu'une erreur d'une règle s'affiche sur le composant concerné. Deux
contrôles propres au réseau s'y ajoutent (service publié sans passer par l'entrée, application exposée sans TLS) ;
les conflits de ports viennent de la règle R39.

Cinq plans, de haut en bas : Internet, entrée (reverse proxy, Ingress), application et services, données, et
l'hébergement (fournisseur cloud, cluster) qui porte le tout.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .catalog import Catalog
from .databases import databases
from .model import TARGETS, Project, Severity
from .ports import KUBERNETES_TARGETS, PortEntry, compose_publishes, port_plan
from .rules import Action, Diagnostic, RuleEngine

LAYERS = ("internet", "entree", "application", "donnees", "hebergement")
LAYER_LABELS = {"internet": "Internet", "entree": "Entrée", "application": "Application et services",
                "donnees": "Données",
                "hebergement": "Hébergement"}
INGRESS_TOOLS = ("traefik", "ingress-nginx", "envoy-gateway")
# Services d'administration : les publier directement sur l'hôte est un risque, pas un usage normal
ADMIN_PORT_HINT = {"grafana": "tableau de bord", "prometheus": "métriques", "keycloak": "console d'administration"}


@dataclass
class NetNode:
    id: str
    label: str
    layer: str
    kind: str                       # internet | ingress | app | service | database
    detail: str = ""
    ports: list[str] = field(default_factory=list)
    bricks: list[str] = field(default_factory=list)   # uid des briques qui portent ce composant


@dataclass
class NetEdge:
    src: str
    dst: str
    label: str = ""
    public: bool = False            # flux venant d'Internet
    secure: bool = True             # chiffré de bout en bout jusqu'à l'entrée


@dataclass
class Finding:
    severity: Severity
    message: str
    source: str                     # « règle R12 » ou « réseau »
    nodes: list[str] = field(default_factory=list)
    actions: list[Action] = field(default_factory=list)
    rule_id: str = ""


@dataclass
class NetGraph:
    env_id: str
    env_label: str
    hosting: str
    nodes: list[NetNode] = field(default_factory=list)
    edges: list[NetEdge] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    elsewhere: int = 0              # diagnostics qui ne concernent aucun composant du schéma (CI, sécurité…)

    def node(self, node_id: str) -> NetNode | None:
        return next((n for n in self.nodes if n.id == node_id), None)

    def layer(self, layer: str) -> list[NetNode]:
        return [n for n in self.nodes if n.layer == layer]

    def findings_of(self, node_id: str) -> list[Finding]:
        return [f for f in self.findings if node_id in f.nodes]

    def worst(self, node_id: str) -> Severity | None:
        found = self.findings_of(node_id)
        return min((f.severity for f in found), key=lambda s: s.rank) if found else None


def _hosting(project: Project, present: set[str], catalog: Catalog) -> str:
    label = TARGETS.get(project.target, project.target)
    cloud = next((catalog[t].name for t in present if (tool := catalog.get(t)) and tool.kind == "provider"), "")
    return f"{label} · {cloud}" if cloud else label


def build_graph(project: Project, catalog: Catalog, engine: RuleEngine, env_id: str | None = None,
                diags: list[Diagnostic] | None = None) -> NetGraph:
    env = project.env(env_id) if env_id else None
    env = env or (project.environments[-1] if project.environments else None)
    if env is None:
        return NetGraph("", "", TARGETS.get(project.target, project.target))
    diags = engine.evaluate(project) if diags is None else diags
    present = project.tool_ids()
    graph = NetGraph(env.id, env.display, _hosting(project, present, catalog))
    entries = [e for e in port_plan(project, catalog) if e.env_id == env.id]
    ingress = next((t for t in INGRESS_TOOLS if t in present), None)
    kube = project.target in KUBERNETES_TARGETS
    db_ids = {d.id for d in databases(project, catalog)}

    def bricks_of(service_id: str) -> list[str]:
        return [b.uid for _, b in project.all_bricks() if b.service_id == service_id]

    graph.nodes.append(NetNode("internet", "Internet", "internet", "internet", "utilisateurs, navigateurs"))
    name = project.app.image_name or "app"
    app_entries = [e for e in entries if e.component_id == "app"]
    graph.nodes.append(NetNode("app", name, "application", "app", "application",
                               [f"{e.container_port}" for e in app_entries[:1]]))
    if ingress:
        tool = catalog[ingress]
        graph.nodes.append(NetNode(ingress, tool.name, "entree", "ingress", "reverse proxy, HTTPS",
                                   ["80", "443"] if not kube else ["80", "443"], bricks_of(ingress)))
        graph.edges.append(NetEdge("internet", ingress, "HTTPS 443", public=True))
        graph.edges.append(NetEdge(ingress, "app", f":{project.app.port}"))
    elif app_entries and "URL HTTPS gérée" in app_entries[0].exposure:   # serverless : l'URL vient du service
        graph.edges.append(NetEdge("internet", "app", "HTTPS (URL gérée)", public=True))
    elif app_entries and app_entries[0].host_port is not None:
        graph.edges.append(NetEdge("internet", "app", f":{app_entries[0].host_port}", public=True, secure=False))
    elif kube:
        graph.findings.append(Finding(
            Severity.INFO, f"{name} : aucun point d'entrée (Ingress, reverse proxy) : l'application n'est joignable "
            "que depuis le cluster. Ajouter Traefik, ingress-nginx ou Envoy Gateway.", "réseau", ["app"]))

    by_component: dict[str, list[PortEntry]] = {}
    for e in entries:
        if e.component_id != "app" and e.component_id != ingress:   # l'entrée a son propre plan
            by_component.setdefault(e.component_id, []).append(e)
    for cid, comp in by_component.items():
        base = comp[0].tool_id or cid   # l'identifiant d'une instance nommée n'est pas celui de l'outil
        tool = catalog.get(base)
        is_db = cid in db_ids
        node = NetNode(cid, comp[0].component if comp[0].tool_id else (tool.name if tool else cid),
                       "donnees" if is_db else "application",
                       "database" if is_db else "service", comp[0].usage,
                       sorted({str(e.container_port) for e in comp}), bricks_of(cid))
        graph.nodes.append(node)
        if is_db:
            graph.edges.append(NetEdge("app", cid, f":{comp[0].container_port}"))
            continue
        published = [e for e in comp if e.host_port is not None]
        via_ingress = ingress and any("via Traefik" in e.exposure or "exposé par" in e.exposure for e in comp)
        if via_ingress:   # interface web derrière l'entrée ; ports restants (OTLP, SSH, S3…) : protocoles machine
            graph.edges.append(NetEdge(ingress, cid, f":{next(e for e in comp if e.host_port is None).container_port}"))
        if published:
            graph.edges.append(NetEdge("internet", cid, ":" + ", ".join(str(e.host_port) for e in published),
                                       public=True, secure=False))
            hint = ADMIN_PORT_HINT.get(base)
            if not via_ingress and (hint or ingress):
                e = published[0]
                graph.findings.append(Finding(
                    Severity.WARNING,
                    f"{node.label} : port {e.host_port} publié sur l'hôte"
                    + (f" ({hint})" if hint else "") + ", sans passer par "
                    + (catalog[ingress].name if ingress else "un reverse proxy")
                    + " : le placer derrière l'entrée ou le fermer au pare-feu.",
                    "réseau", [cid]))
        elif not via_ingress:
            graph.edges.append(NetEdge("app", cid, f":{comp[0].container_port}"))

    for tid in sorted(present):   # hébergement : fournisseur cloud et cluster, porteurs des erreurs de dimensionnement
        tool = catalog.get(tid)
        roles = set(tool.roles) if tool else set()
        if tool and (tool.kind == "provider" or roles & {"kubernetes-cluster", "compute", "serverless"}):
            detail = ("fournisseur cloud" if tool.kind == "provider" else "cluster Kubernetes"
                      if "kubernetes-cluster" in roles else "machine virtuelle" if "compute" in roles else "serverless")
            graph.nodes.append(NetNode(f"host:{tid}", tool.name, "hebergement", "hosting", detail, [], bricks_of(tid)))

    if compose_publishes(project) and not ingress and app_entries and app_entries[0].host_port is not None:
        graph.findings.append(Finding(
            Severity.WARNING,
            f"{name} : publié sur l'hôte en HTTP simple (port {app_entries[0].host_port}), sans terminaison TLS : "
            "ajouter Traefik ou un reverse proxy.", "réseau", ["app"]))
    # diagnostics des règles, posés sur le composant qui porte la brique concernée
    owner = {uid: n.id for n in graph.nodes for uid in n.bricks}
    for d in diags:
        scoped = {e for a in d.actions for e in a.args.get("envs", [])}
        if scoped and env.id not in scoped:   # diagnostic d'un autre environnement (dimensionnement, surcharge…)
            continue
        nodes = sorted({owner[u] for u in d.bricks if u in owner})
        if not nodes:
            graph.elsewhere += 1
            continue
        graph.findings.append(Finding(d.severity, d.message, f"règle {d.rule_id}", nodes, list(d.actions), d.rule_id))
    graph.findings.sort(key=lambda f: f.severity.rank)
    return graph
