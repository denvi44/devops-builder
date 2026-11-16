# SPDX-License-Identifier: Apache-2.0
"""Accès privé aux hôtes : VPN (Tailscale, WireGuard) et bastion SSH.

Le déploiement par SSH (Compose ou Ansible) passe par ces accès quand les hôtes ne sont pas joignables depuis Internet :
la CI ouvre le tunnel (ou saute par le bastion) avant la première connexion. Les playbooks installent Tailscale ou
WireGuard sur les hôtes ; aucune clé privée n'est écrite dans le dépôt.
"""

from __future__ import annotations

from ..ir import IR
from .common import dump_yaml

TOOLS = ("tailscale", "wireguard", "ssh-bastion")
SSH_CONFIG = "~/.ssh/config"


def present(ir: IR) -> list[str]:
    return [t for t in TOOLS if ir.has(t)]


def ci_lines(ir: IR) -> list[str]:
    """Lignes à lancer dans le job de déploiement, une fois la clé SSH posée et avant la première connexion."""
    lines: list[str] = []
    if ir.has("tailscale"):
        ir.add_var("TAILSCALE_AUTHKEY", "Clé d'authentification Tailscale (éphémère, réutilisable, étiquetée) du job de "
                                        "déploiement")
        lines += [
            "apk add --no-cache tailscale netcat-openbsd",
            "tailscaled --tun=userspace-networking --state=mem: --socks5-server=localhost:1055 >/tmp/tailscaled.log 2>&1 &",
            'for i in 1 2 3 4 5; do tailscale up --authkey="$TAILSCALE_AUTHKEY" --hostname="ci-$(hostname)" '
            "--accept-dns=false && break; sleep 2; done",
            f"printf 'Host *\\n  ProxyCommand nc -X 5 -x localhost:1055 %%h %%p\\n' >> {SSH_CONFIG}",
        ]
    if ir.has("wireguard"):
        ir.add_var("WG_CONFIG", "Configuration WireGuard du job de déploiement (contenu de wg0.conf : clé privée du "
                                "client et pair de la passerelle)")
        lines += [
            "apk add --no-cache wireguard-tools iproute2",
            "mkdir -p /etc/wireguard",
            'printf \'%s\\n\' "$WG_CONFIG" > /etc/wireguard/wg0.conf && chmod 600 /etc/wireguard/wg0.conf',
            "wg-quick up wg0",
        ]
    if ir.has("ssh-bastion"):
        ir.add_var("BASTION_HOST", "Bastion SSH par lequel passer pour joindre les hôtes (utilisateur@hôte)", secret=False)
        lines += [
            'BASTION="${BASTION_HOST#*@}"',
            f"printf 'Host %s\\n  ProxyJump none\\nHost *\\n  ProxyJump %s\\n' \"$BASTION\" \"$BASTION_HOST\" >> {SSH_CONFIG}",
        ]
    return lines


def _tailscale_playbook() -> list[dict]:
    return [{
        "name": "Installer Tailscale sur les hôtes",
        "hosts": "app",
        "become": True,
        "tasks": [
            {"name": "Tailscale déjà installé ?", "ansible.builtin.stat": {"path": "/usr/bin/tailscale"},
             "register": "tailscale_bin"},
            {"name": "Installer Tailscale (script officiel)",
             "ansible.builtin.shell": "set -o pipefail && curl -fsSL https://tailscale.com/install.sh | sh",
             "args": {"executable": "/bin/bash"}, "when": "not tailscale_bin.stat.exists", "changed_when": True},
            {"name": "Rejoindre le réseau Tailscale",
             "ansible.builtin.command": {"argv": ["tailscale", "up", "--authkey",
                                                  "{{ lookup('ansible.builtin.env', 'TAILSCALE_AUTHKEY') }}",
                                                  "--hostname", "{{ inventory_hostname_short }}"]},
             "no_log": True, "changed_when": False},
        ],
    }]


_WG_CONF = """[Interface]
Address = {{ wg_address }}
ListenPort = {{ wg_port }}
PrivateKey = {{ wg_private_key.content | b64decode | trim }}
{% for peer in wg_peers %}

[Peer]
PublicKey = {{ peer.public_key }}
AllowedIPs = {{ peer.allowed_ips }}
{% endfor %}
"""


def _wireguard_playbook() -> list[dict]:
    return [{
        "name": "Installer WireGuard sur les hôtes",
        "hosts": "app",
        "become": True,
        "vars": {"wg_address": "10.66.0.1/24", "wg_port": 51820, "wg_peers": []},
        "tasks": [
            {"name": "Paquet WireGuard", "ansible.builtin.package": {"name": "wireguard", "state": "present"}},
            {"name": "Générer la paire de clés de l'hôte (une seule fois)",
             "ansible.builtin.shell": "set -o pipefail && umask 077 && wg genkey | tee /etc/wireguard/private.key "
                                      "| wg pubkey > /etc/wireguard/public.key",
             "args": {"creates": "/etc/wireguard/private.key", "executable": "/bin/bash"}},
            {"name": "Lire la clé privée", "ansible.builtin.slurp": {"src": "/etc/wireguard/private.key"},
             "register": "wg_private_key", "no_log": True},
            {"name": "Écrire wg0.conf",
             "ansible.builtin.copy": {"content": _WG_CONF, "dest": "/etc/wireguard/wg0.conf", "mode": "0600"},
             "no_log": True, "notify": "Redémarrer WireGuard"},
            {"name": "Activer WireGuard au démarrage",
             "ansible.builtin.service": {"name": "wg-quick@wg0", "state": "started", "enabled": True}},
        ],
        "handlers": [{"name": "Redémarrer WireGuard",
                      "ansible.builtin.service": {"name": "wg-quick@wg0", "state": "restarted"}}],
    }]


def files(ir: IR) -> dict[str, str]:
    out: dict[str, str] = {}
    if present(ir) and not ir.has("ansible"):
        ir.notes.append("VPN / bastion : la CI ouvre l'accès avant le déploiement ; sans brique Ansible, aucun playbook "
                        "n'installe Tailscale ou WireGuard sur les hôtes (à faire à la main).")
    if ir.has("tailscale"):
        if ir.has("ansible"):
            out["ansible/tailscale.yml"] = dump_yaml(_tailscale_playbook(), indent_lists=True)
        ir.notes.append("Tailscale : le job de déploiement rejoint le réseau en mode utilisateur (sans privilèges), "
                        "puis SSH passe par le proxy SOCKS de Tailscale ; adresser les hôtes par leur nom Tailscale "
                        "(MagicDNS) ou leur adresse 100.x. Clé : réutilisable, éphémère, étiquetée (tag:ci).")
        ir.cover("tailscale")
    if ir.has("wireguard"):
        if ir.has("ansible"):
            out["ansible/wireguard.yml"] = dump_yaml(_wireguard_playbook(), indent_lists=True)
        ir.notes.append("WireGuard : `wg-quick up` demande un runner autorisé à créer une interface réseau (conteneur "
                        "privilégié ou runner sur machine dédiée) ; WG_CONFIG contient le wg0.conf du client, dont le pair "
                        "est la passerelle (paramètre wg_peers du playbook pour l'autre sens).")
        ir.cover("wireguard")
    if ir.has("ssh-bastion"):
        ir.notes.append("Bastion SSH : toutes les connexions de la CI sautent par BASTION_HOST (ProxyJump), avec la "
                        "même clé SSH_PRIVATE_KEY ; le bastion doit accepter cette clé et joindre les hôtes.")
        ir.cover("ssh-bastion")
    return out
