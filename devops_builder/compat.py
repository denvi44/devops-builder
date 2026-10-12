# SPDX-License-Identifier: Apache-2.0
"""Briques adaptées au projet : ce que la palette propose par défaut.

Une brique est écartée quand les règles la refuseraient ou la signaleraient aussitôt posée :
cible d'hébergement, forge, politique de licence, SecNumCloud, fournisseur cloud différent,
rôle déjà tenu (une forge, une CI, un GitOps, un CNI…), outils incompatibles entre eux.
La raison est donnée en clair pour l'afficher quand l'utilisateur demande à tout voir.
"""

from __future__ import annotations

from functools import lru_cache

from .catalog import Catalog
from .model import TARGETS, Project, Tool

# Rôles tenus par une seule brique dans un pipeline, en plus des règles d'exclusivité
SINGLE_ROLES = {"ci": "orchestrateur CI", "scm": "forge"}
ROLE_LABELS = {"gitops": "outil GitOps", "service-mesh": "maillage de services", "cni": "CNI",
               "admission-policy": "contrôleur d'admission", "sql-database": "base relationnelle",
               "key-value-store": "stockage clé-valeur"}
FEMININE = {"forge", "base relationnelle"}  # accord de « déjà choisi »


@lru_cache(maxsize=1)
def _rule_constraints() -> tuple[dict[str, str], list[tuple[str, str]], dict[str, list[str]]]:
    from .rules import load_rules
    exclusive: dict[str, str] = dict(SINGLE_ROLES)
    pairs: list[tuple[str, str]] = []
    target_mismatch: dict[str, list[str]] = {}
    for r in load_rules():
        if r.type == "exclusive_role":
            exclusive.setdefault(r.params["role"], ROLE_LABELS.get(r.params["role"], r.params["role"]))
        elif r.type == "conflict_pair" and r.severity.value != "info":
            a, b = r.params["tools"]
            pairs.append((a, b))
        elif r.type == "target_mismatch":
            target_mismatch[r.params["tool"]] = list(r.params["targets"])
    return exclusive, pairs, target_mismatch


def _has_cluster(project: Project, catalog: Catalog) -> bool:
    return any((t := catalog.get(b.tool)) and "kubernetes-cluster" in t.roles for _, b in project.all_bricks())


def incompatibility(tool: Tool, project: Project, catalog: Catalog) -> str | None:
    """Pourquoi cette brique ne convient pas au projet, ou None si elle convient."""
    present = [catalog.get(b.tool) for _, b in project.all_bricks()]
    present = [t for t in present if t is not None]
    ids = {t.id for t in present}
    if tool.id in ids:
        return "déjà dans le pipeline"
    exclusive, pairs, mismatch = _rule_constraints()
    target = project.target
    if tool.kubernetes_only and target in ("docker-host", "vm") and not _has_cluster(project, catalog):
        return f"nécessite Kubernetes (cible : {TARGETS.get(target, target)})"
    if target in mismatch.get(tool.id, []):
        return f"inadapté à la cible {TARGETS.get(target, target)}"
    if project.license_policy == "oss-only" and not tool.is_oss:
        return f"licence {tool.license} : le projet n'accepte que l'open source"
    if project.secnumcloud:
        provider = catalog.get(tool.provider) if tool.provider else (tool if tool.kind == "provider" else None)
        if provider is not None and provider.secnumcloud == "no":
            return f"{provider.name} n'est pas qualifié SecNumCloud"
    forge = next((t for t in present if t.forge), None)
    if forge is not None and tool.forges and forge.forge not in tool.forges:
        return f"ne fonctionne pas avec {forge.name}"
    providers = {t.id for t in present if t.kind == "provider"}
    if tool.provider and providers and tool.provider not in providers:
        prov = catalog.get(tool.provider)
        names = ", ".join(sorted(catalog[p].name for p in providers))
        return f"service {prov.name if prov else tool.provider}, alors que le projet utilise {names}"
    for role, label in exclusive.items():
        if role in tool.roles:
            holder = next((t for t in present if role in t.roles), None)
            if holder is not None:
                return f"{label} déjà {'choisie' if label in FEMININE else 'choisi'} : {holder.name}"
    for a, b in pairs:
        other = b if tool.id == a else a if tool.id == b else None
        if other in ids:
            return f"incompatible avec {catalog[other].name}, déjà dans le pipeline"
    return None


def adapted(tools: list[Tool], project: Project, catalog: Catalog) -> tuple[list[Tool], dict[str, str]]:
    """Briques adaptées, et la raison de chaque brique écartée."""
    keep: list[Tool] = []
    reasons: dict[str, str] = {}
    for t in tools:
        why = incompatibility(t, project, catalog)
        if why is None:
            keep.append(t)
        else:
            reasons[t.id] = why
    return keep, reasons
