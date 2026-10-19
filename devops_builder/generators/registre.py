# SPDX-License-Identifier: Apache-2.0
"""Registre d'images auto-hébergé en HTTP simple (adresse IP, localhost) : déclaration sur les clients.

Docker, containerd et k3s refusent par défaut un registre sans HTTPS. Les hôtes Docker déployés par Ansible reçoivent
`insecure-registries` ; k3s reçoit `deploy/registries.yaml` à copier sur chaque nœud. La CI, qui construit et pousse
l'image, doit être réglée de la même façon : une note le dit.
"""

from __future__ import annotations

from ..addresses import SELF_HOSTED_REGISTRIES, plain_http
from ..ir import IR, registry_host
from .common import dump_yaml

K3S_FILE = "deploy/registries.yaml"

# Fusionne `insecure-registries` dans /etc/docker/daemon.json sans perdre le reste ; affiche « changed » si modifié
DAEMON_SNIPPET = (
    "import json, os, sys\n"
    "p = '/etc/docker/daemon.json'\n"
    "d = json.load(open(p)) if os.path.exists(p) and os.path.getsize(p) else {}\n"
    "r = d.setdefault('insecure-registries', [])\n"
    "if sys.argv[1] not in r:\n"
    "    r.append(sys.argv[1]); json.dump(d, open(p, 'w'), indent=2); print('changed')\n")


def insecure_host(ir: IR) -> str | None:
    """Adresse du registre à déclarer, si le pipeline pousse vers un registre auto-hébergé sans HTTPS."""
    reg = ir.registry
    if reg is None or reg.id not in SELF_HOSTED_REGISTRIES:
        return None
    host = registry_host(ir)
    return host if plain_http(host) else None


def ansible_tasks(ir: IR) -> list[dict]:
    host = insecure_host(ir)
    if not host:
        return []
    return [
        {"name": f"Autoriser le registre {host} en HTTP simple (insecure-registries)",
         "ansible.builtin.command": {"argv": ["python3", "-c", DAEMON_SNIPPET, host]},
         "register": "daemon_json",
         "changed_when": "'changed' in daemon_json.stdout"},
        {"name": "Redémarrer Docker pour prendre en compte le registre",
         "ansible.builtin.service": {"name": "docker", "state": "restarted"},
         "when": "daemon_json.changed"},
    ]


def files(ir: IR) -> dict[str, str]:
    host = insecure_host(ir)
    if not host:
        return {}
    ir.notes.append(
        f"Registre {host} en HTTP simple : la CI qui pousse l'image doit l'autoriser (Docker : insecure-registries "
        "dans /etc/docker/daemon.json ; BuildKit : [registry.\"" + host + "\"] http = true, insecure = true dans "
        "buildkitd.toml ; Kaniko : --insecure-registry ; podman : registries.conf, insecure = true). Prévoir un "
        "certificat et un nom DNS pour la production.")
    if ir.has("ansible"):
        ir.notes.append(f"Ansible : les hôtes Docker reçoivent {host} dans insecure-registries (Docker redémarré si "
                        "le fichier change).")
    if not ir.has("k3s"):
        return {}
    data = {"mirrors": {host: {"endpoint": [f"http://{host}"]}}}
    ir.notes.append(f"k3s : copier {K3S_FILE} dans /etc/rancher/k3s/registries.yaml sur chaque nœud puis redémarrer "
                    "k3s (systemctl restart k3s ou k3s-agent) pour tirer les images de " + host + " en HTTP.")
    return {K3S_FILE: dump_yaml(data)}
