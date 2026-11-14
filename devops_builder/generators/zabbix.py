# SPDX-License-Identifier: Apache-2.0
"""Zabbix sur un hôte Docker (ou des VM qui reçoivent le Compose) : images officielles, base PostgreSQL dédiée.

Les images créent elles-mêmes le schéma au premier démarrage ; le mot de passe de la base passe par le circuit
habituel (variables CI, SOPS ou coffre) via deploy/secrets.sh. L'agent 2 partage le réseau du serveur : l'hôte
« Zabbix server » créé par défaut (interface 127.0.0.1) est supervisé sans réglage.

Un second agent (paramètre « Superviser l'hôte Docker », activé par défaut) tourne sur le réseau de l'hôte : il voit
la machine elle-même (processeur, mémoire, disques sous /hostfs) et ses conteneurs par le socket Docker. Le port
10051 du serveur est publié : les agents d'autres machines s'y annoncent. Essai réel sur un Unraid (0.26.2) : sans
cet agent, ni l'hôte ni ses conteneurs n'étaient supervisés, et les agents actifs étaient refusés.
"""

from __future__ import annotations

from ..ir import IR
from .identity import ComposeSecret, compose_target

IMAGES = ("zabbix/zabbix-server-pgsql", "zabbix/zabbix-web-nginx-pgsql", "zabbix/zabbix-agent2")
DEFAULT_VERSION = "7.4"
DB_IMAGE = "postgres:17"
WEB_PORT = 8080   # nginx de l'image web (non privilégié)
TRAPPER_PORT = 10051   # agents actifs et zabbix_sender
AGENT_PORT = 10050
HOST_AGENT_SERVICE = "zabbix-agent-host"
HOST_AGENT_NAME = "Docker host"       # nom de l'hôte dans Zabbix (ZBX_HOSTNAME de l'agent)
HOST_GATEWAY = "host.docker.internal"  # l'hôte Docker vu depuis le conteneur du serveur
DOCKER_NETWORKS = "172.16.0.0/12"      # réseaux ponts de Docker : c'est de là que le serveur interroge l'agent


def enabled(ir: IR) -> bool:
    return ir.has("zabbix") and compose_target(ir)


def params(ir: IR) -> dict:
    return ir.params("zabbix")


def host(ir: IR) -> str:
    return str(params(ir).get("hostname") or "zabbix.example.com")


def version(ir: IR) -> str:
    return str(params(ir).get("version") or DEFAULT_VERSION)


def host_agent(ir: IR) -> bool:
    """Agent de l'hôte Docker et de ses conteneurs (réseau de l'hôte, socket Docker)."""
    return enabled(ir) and params(ir).get("supervise_host", True) is not False


def compose_secrets(ir: IR) -> list[ComposeSecret]:
    if not enabled(ir):
        return []
    return [ComposeSecret("ZABBIX_DB_PASSWORD", "zabbix.env", "POSTGRES_PASSWORD",
                          "Mot de passe de la base de Zabbix (serveur, interface web et base le partagent)",
                          tool="zabbix")]


def compose_services(ir: IR) -> dict[str, dict]:
    if not enabled(ir):
        return {}
    tag = f"alpine-{version(ir)}-latest"
    db_env = {"DB_SERVER_HOST": "zabbix-db", "POSTGRES_USER": "zabbix", "POSTGRES_DB": "zabbix"}
    healthy_db = {"zabbix-db": {"condition": "service_healthy"}}
    server: dict = {
        "image": f"{IMAGES[0]}:{tag}", "restart": "unless-stopped",
        "environment": dict(db_env), "env_file": ["secrets/zabbix.env"], "depends_on": healthy_db,
    }
    web: dict = {
        "image": f"{IMAGES[1]}:{tag}", "restart": "unless-stopped",
        "environment": {**db_env, "ZBX_SERVER_HOST": "zabbix-server",
                        "PHP_TZ": str(params(ir).get("timezone") or "Europe/Paris")},
        "env_file": ["secrets/zabbix.env"],
        "depends_on": {**healthy_db, "zabbix-server": {"condition": "service_started"}},
        "healthcheck": {"test": ["CMD-SHELL", f"wget -q -O /dev/null http://localhost:{WEB_PORT}/ || exit 1"],
                        "interval": "15s", "timeout": "5s", "retries": 10, "start_period": "30s"},
    }
    agent: dict = {
        "image": f"{IMAGES[2]}:{tag}", "restart": "unless-stopped",
        "environment": {"ZBX_HOSTNAME": "Zabbix server", "ZBX_SERVER_HOST": "127.0.0.1"},
        # même réseau que le serveur : l'interface 127.0.0.1 de l'hôte par défaut joint l'agent
        "network_mode": "service:zabbix-server", "depends_on": {"zabbix-server": {"condition": "service_started"}},
    }
    db: dict = {
        "image": DB_IMAGE, "restart": "unless-stopped",
        "environment": {"POSTGRES_USER": "zabbix", "POSTGRES_DB": "zabbix"},
        "env_file": ["secrets/zabbix.env"], "volumes": ["zabbix-db-data:/var/lib/postgresql/data"],
        "healthcheck": {"test": ["CMD-SHELL", 'pg_isready -U "$${POSTGRES_USER}" -d "$${POSTGRES_DB}"'],
                        "interval": "10s", "timeout": "5s", "retries": 10},
    }
    if ir.has("traefik"):
        web["labels"] = [
            "traefik.enable=true",
            f"traefik.http.routers.zabbix.rule=Host(`{host(ir)}`)",
            "traefik.http.routers.zabbix.entrypoints=websecure",
            f"traefik.http.services.zabbix.loadbalancer.server.port={WEB_PORT}",
        ]
    else:
        web["ports"] = [f"{WEB_PORT}:{WEB_PORT}"]
    # agents actifs et zabbix_sender des autres machines : sans ce port, le serveur les refuse
    server["ports"] = [f"{TRAPPER_PORT}:{TRAPPER_PORT}"]
    services = {"zabbix-server": server, "zabbix-web": web, "zabbix-agent": agent, "zabbix-db": db}
    if host_agent(ir):
        server["extra_hosts"] = [f"{HOST_GATEWAY}:host-gateway"]
        services[HOST_AGENT_SERVICE] = {
            "image": f"{IMAGES[2]}:{tag}", "restart": "unless-stopped",
            # réseau et processus de l'hôte : c'est la machine qui est mesurée, pas le conteneur
            "network_mode": "host", "pid": "host", "user": "0:0",
            "environment": {"ZBX_HOSTNAME": HOST_AGENT_NAME, "ZBX_SERVER_HOST": "127.0.0.1",
                            "ZBX_PASSIVESERVERS": DOCKER_NETWORKS, "ZBX_TIMEOUT": "30"},
            "volumes": ["/:/hostfs:ro,rslave", "/var/run/docker.sock:/var/run/docker.sock:ro"],
            "depends_on": {"zabbix-server": {"condition": "service_started"}},
        }
    ir.cover("zabbix")
    return services


def web_url(ir: IR) -> str:
    return f"https://{host(ir)}" if ir.has("traefik") else f"http://<hôte>:{WEB_PORT}"


def notes(ir: IR) -> None:
    if enabled(ir):
        ir.notes.append(f"Zabbix : interface sur {web_url(ir)} ; compte Admin / zabbix au premier accès, à changer "
                        "aussitôt (docs/mise-en-route.md). "
                        + ("Un agent supervise le serveur Zabbix, un second l'hôte Docker et ses conteneurs (à "
                           "déclarer une fois, docs/mise-en-route.md) : ce second agent lit le socket Docker, ce qui "
                           "lui donne des droits étendus sur l'hôte. " if host_agent(ir) else
                           "L'agent fourni supervise le serveur Zabbix lui-même. ")
                        + f"Les autres machines reçoivent chacune un agent, qui s'annonce sur le port {TRAPPER_PORT}.")
