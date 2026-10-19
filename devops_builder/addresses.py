# SPDX-License-Identifier: Apache-2.0
"""Adresses saisies dans les briques : adresse IP ou nom d'hôte, registre en HTTP simple."""

from __future__ import annotations

import ipaddress

from .model import Project

HOST_KEYS = ("hostname", "app_hostname", "tools_domain")   # servis par l'entrée : un nom DNS est exigé
SELF_HOSTED_REGISTRIES = ("harbor", "zot", "distribution")


def host_part(address: str) -> str:
    """Nom d'hôte ou IP d'une adresse « hôte[:port] » (schéma et chemin éventuels écartés)."""
    text = str(address or "").strip().split("://")[-1].split("/")[0]
    if text.startswith("["):   # IPv6 entre crochets
        return text[1:].split("]")[0]
    return text.rsplit(":", 1)[0] if text.count(":") == 1 else text


def is_ip(address: str) -> bool:
    try:
        ipaddress.ip_address(host_part(address))
    except ValueError:
        return False
    return True


def plain_http(address: str) -> bool:
    """Registre qu'on suppose sans HTTPS : adresse IP ou « localhost » (aucun certificat public n'est possible)."""
    host = host_part(address)
    return is_ip(host) or host == "localhost"


def ip_addresses(project: Project) -> list[tuple[str, str, str, str]]:
    """(uid, outil, paramètre, valeur) des adresses d'entrée saisies sous forme d'IP, y compris par environnement."""
    found = []
    for _, b in project.all_bricks():
        for key in HOST_KEYS:
            value = (b.params or {}).get(key)
            if value and is_ip(str(value)):
                found.append((b.uid, b.tool, key, str(value)))
        for env in project.environments:
            for key in HOST_KEYS:
                value = (env.overrides.get(b.service_id) or {}).get(key)
                if value and is_ip(str(value)):
                    found.append((b.uid, b.tool, key, f"{value} ({env.display})"))
    return found
