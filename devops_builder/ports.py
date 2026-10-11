"""Ports de l'application et des briques, par environnement.

Sur un hôte Docker, chaque service Compose publie des ports. Des environnements qui
partagent le même hôte (champ « host » de l'environnement) ne peuvent pas publier les
mêmes : leurs ports sont décalés de 10 000 par environnement, production d'abord, sauf
décalage choisi à la main. Sur Kubernetes, les ports sont ceux des Services, isolés par
espace de noms : ils sont listés pour information et ne peuvent pas entrer en conflit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from .catalog import Catalog
from .databases import DATABASE_TOOLS, databases
from .model import PORT_OFFSET_STEP, Environment, Project

PORTS_FILE = Path(__file__).parent / "data" / "ports.yaml"
MAX_PORT = 65535
KUBERNETES_TARGETS = ("kubernetes", "kubernetes-managed")
SERVERLESS = {"cloud-run": "Cloud Run", "ecs-fargate": "ECS Fargate", "azure-container-apps": "Azure Container Apps"}


@lru_cache(maxsize=1)
def known_ports() -> dict[str, dict[int, str]]:
    data = yaml.safe_load(PORTS_FILE.read_text(encoding="utf-8")) or {}
    return {tid: {int(p): str(u) for p, u in ports.items()} for tid, ports in data.items()}


@dataclass
class PortEntry:
    env_id: str
    env: str                    # libellé de l'environnement
    component_id: str           # « app » ou identifiant de brique
    component: str
    container_port: int
    host_port: int | None       # port publié sur l'hôte ; None si non publié (Service, Traefik…)
    usage: str
    exposure: str
    host_group: str             # hôte Docker partagé, ou l'environnement lui-même
    variable: str = ""          # variable Compose quand les ports sont décalés
    conflict: str = ""


# ------------------------------------------------------------------ décalages
def shared_hosts(project: Project) -> dict[str, list[Environment]]:
    groups: dict[str, list[Environment]] = {}
    for env in project.environments:
        if env.host.strip():
            groups.setdefault(env.host.strip(), []).append(env)
    return {h: envs for h, envs in groups.items() if len(envs) > 1}


def env_offset(project: Project, env: Environment) -> int:
    """Décalage des ports publiés : choisi à la main, sinon rang sur l'hôte partagé × 10 000."""
    if env.port_offset is not None:
        return env.port_offset
    group = shared_hosts(project).get(env.host.strip())
    if not group:
        return 0
    ordered = [e for e in group if e.kind == "production"] + [e for e in group if e.kind != "production"]
    return PORT_OFFSET_STEP * ordered.index(env)


def compose_publishes(project: Project) -> bool:
    return project.target in ("docker-host", "vm") and any(b.tool == "docker-compose" for _, b in project.all_bricks())


def parametrized(project: Project) -> bool:
    """Les ports Compose deviennent des variables quand un environnement est décalé."""
    return compose_publishes(project) and any(env_offset(project, e) for e in project.environments)


def port_variable(component_id: str, container_port: int) -> str:
    if component_id == "app":
        return "PORT_APP"
    return f"PORT_{re.sub(r'[^A-Z0-9]+', '_', component_id.upper())}_{container_port}"


def _compose_ports(spec: list[str]) -> list[tuple[int, int]]:
    out = []
    for p in spec:
        host, _, container = str(p).partition(":")
        out.append((int(host), int(container or host)))
    return out


# ------------------------------------------------------------------ plan
def port_plan(project: Project, catalog: Catalog) -> list[PortEntry]:
    from .generators.platform import COMPOSE_SERVICES, PLATFORM_CHARTS

    ports = known_ports()
    # Vault / OpenBao avec une adresse : coffre existant, pas déployé avec l'application
    present = [b.tool for _, b in project.all_bricks()
               if not (b.tool in ("vault", "openbao") and (b.params or {}).get("address"))]
    app_port = project.app.port
    name = project.app.image_name
    entries: list[PortEntry] = []
    for env in project.environments:
        suffix = project.env_suffix(env)
        group = env.host.strip() or f"(hôte de {env.display})"
        offset = env_offset(project, env)

        def add(cid: str, label: str, container: int, host: int | None, usage: str, exposure: str) -> None:
            var = port_variable(cid, container) if host is not None and parametrized(project) else ""
            entries.append(PortEntry(env.id, env.display, cid, label, container, host, usage, exposure, group, var))

        def add_databases(kube: bool, compose: bool = True) -> None:
            for db in databases(project, catalog):
                if db.mode == "managed":
                    add(db.id, db.tool.name, db.engine.port, None, db.engine.label,
                        "service managé, une instance par environnement")
                elif kube:
                    host = f"{name}-pg-rw" if db.mode == "operator" else f"{name}-{db.id}"
                    add(db.id, db.tool.name, db.engine.port, None, db.engine.label,
                        f"Service {host}, espace de noms {name}{suffix}, interne au cluster")
                elif db.mode == "self-hosted" and compose:
                    add(db.id, db.tool.name, db.engine.port, None, db.engine.label,
                        f"réseau interne Compose (hôte « {db.id} »), non publié")

        if compose_publishes(project):
            if "traefik" in present:
                add("app", name, app_port, None, "application",
                    f"via Traefik, hôte {app_hostname(project, env)}")
            else:
                add("app", name, app_port, app_port + offset, "application", "publié sur l'hôte Docker")
            for tid in COMPOSE_SERVICES:
                if tid not in present:
                    continue
                tool = catalog.get(tid)
                for host, container in _compose_ports(COMPOSE_SERVICES[tid].get("ports", [])):
                    add(tid, tool.name if tool else tid, container, host + offset,
                        ports.get(tid, {}).get(container, ""), "publié sur l'hôte Docker")
            add_databases(False)
        elif project.target in KUBERNETES_TARGETS or any(
                (t := catalog.get(tid)) and "kubernetes-cluster" in t.roles for tid in present):
            ingress = next((catalog[t].name for t in ("traefik", "ingress-nginx", "envoy-gateway") if t in present), None)
            exposure = f"Service {name} port 80, espace de noms {name}{suffix}"
            if ingress:
                exposure += f", exposé par {ingress}"
            add("app", name, app_port, None, "application", exposure)
            add_databases(True)
            for tid in present:
                if tid in PLATFORM_CHARTS and tid in ports and tid not in DATABASE_TOOLS:
                    tool = catalog.get(tid)
                    for container, usage in ports[tid].items():
                        add(tid, tool.name if tool else tid, container, None, usage,
                            f"Service Kubernetes, espace de noms {PLATFORM_CHARTS[tid].namespace}")
        else:
            service = next((SERVERLESS[t] for t in present if t in SERVERLESS), None)
            add("app", name, app_port, None, "application",
                f"{service} : URL HTTPS gérée par le service" if service else "port du conteneur")
            add_databases(False, compose=False)
    _mark_conflicts(entries)
    return entries


def _mark_conflicts(entries: list[PortEntry]) -> None:
    by_key: dict[tuple[str, int], list[PortEntry]] = {}
    for e in entries:
        if e.host_port is None:
            continue
        if e.host_port > MAX_PORT or e.host_port < 1:
            e.conflict = f"port {e.host_port} hors de la plage 1–{MAX_PORT}"
            continue
        by_key.setdefault((e.host_group, e.host_port), []).append(e)
    for (_group, port), same in by_key.items():
        owners = {(e.env_id, e.component_id) for e in same}
        if len(owners) < 2:
            continue
        for e in same:
            others = [f"{o.component} ({o.env})" for o in same if o is not e]
            e.conflict = f"port {port} déjà publié par " + ", ".join(others)


def conflicts(entries: list[PortEntry]) -> list[PortEntry]:
    return [e for e in entries if e.conflict]


def free_port(entries: list[PortEntry], start: int) -> int:
    """Premier port libre à partir de `start`, en laissant la place aux décalages d'environnements."""
    used = {e.host_port for e in entries if e.host_port is not None} | {e.container_port for e in entries}
    limit = MAX_PORT - PORT_OFFSET_STEP * 4
    port = start
    while port in used or port > limit:
        port = 1024 if port > limit else port + 1
    return port


def app_hostname(project: Project, env: Environment) -> str:
    """Nom d'hôte routé par Traefik : propre à chaque environnement quand les ports sont décalés."""
    name = project.app.image_name
    return f"{name}{project.env_suffix(env)}.example.com" if parametrized(project) else f"{name}.example.com"


def env_file(project: Project, env: Environment, entries: list[PortEntry]) -> str:
    """Contenu de deploy/env/<env>.env : ports publiés de cet environnement."""
    lines = [f"# Ports publiés par l'environnement « {env.display} » (décalage {env_offset(project, env)})."]
    if compose_publishes(project) and any(b.tool == "traefik" for _, b in project.all_bricks()):
        lines.append(f"APP_HOST={app_hostname(project, env)}")
    for e in entries:
        if e.env_id == env.id and e.variable:
            lines.append(f"{e.variable}={e.host_port}")
    return "\n".join(lines) + "\n"
