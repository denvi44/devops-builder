"""Moteur de règles de compatibilité et résolveur de corrections.

Chaque règle est un fichier YAML de `data/rules/` qui choisit un *type*
(handler Python générique) et ses paramètres. Ajouter une incohérence =
ajouter un fichier YAML et son test, sans toucher au code tant qu'un type
existant convient.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .catalog import DATA_DIR, Catalog
from .model import ENV_ID_PATTERN, STAGE_LABELS, TARGETS, BrickInstance, Project, Severity, Tool, env_preset
from .params import check_overrides

RULES_DIR = DATA_DIR / "rules"

FAMILIES = {
    "cible": "Cible d'hébergement",
    "exclusivite": "Exclusivité de rôle",
    "dependance": "Dépendance fonctionnelle",
    "contrat": "Contrat entre étapes",
    "plateforme": "Plateforme de code",
    "cycle-de-vie": "Cycle de vie",
    "conformite": "Licence et conformité",
    "redondance": "Redondance",
    "catalogue": "Catalogue",
    "placement": "Placement dans le pipeline",
    "completude": "Complétude du pipeline",
    "parametres": "Paramètres des briques",
    "environnements": "Environnements",
    "donnees": "Données",
}


# --------------------------------------------------------------------------
# Structures
# --------------------------------------------------------------------------
@dataclass
class Action:
    op: str  # add_brick | remove_bricks | replace_brick | set_project
    label: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass
class Diagnostic:
    rule_id: str
    family: str
    severity: Severity
    message: str
    bricks: list[str] = field(default_factory=list)
    actions: list[Action] = field(default_factory=list)

    @property
    def family_label(self) -> str:
        return FAMILIES.get(self.family, self.family)


@dataclass
class Rule:
    id: str
    title: str
    family: str
    severity: Severity
    type: str
    message: str
    params: dict[str, Any] = field(default_factory=dict)
    source: str = ""


@dataclass
class Placed:
    stage: str
    brick: BrickInstance
    tool: Tool


class Context:
    def __init__(self, project: Project, catalog: Catalog):
        self.project = project
        self.catalog = catalog
        self.placed: list[Placed] = []
        for stage, brick in project.all_bricks():
            tool = catalog.get(brick.tool)
            if tool is not None:
                self.placed.append(Placed(stage, brick, tool))

    def with_tool(self, tool_id: str) -> list[Placed]:
        return [p for p in self.placed if p.tool.id == tool_id]

    def with_role(self, role: str) -> list[Placed]:
        return [p for p in self.placed if role in p.tool.roles]

    def provides(self, capability: str) -> bool:
        return any(capability in p.tool.provides for p in self.placed)

    def has(self, tool_id: str) -> bool:
        return any(p.tool.id == tool_id for p in self.placed)

    def name(self, tool_id: str) -> str:
        t = self.catalog.get(tool_id)
        return t.name if t else tool_id


def _fmt(template: str, **values: Any) -> str:
    try:
        return template.format(**values)
    except (KeyError, IndexError):
        return template


def _names(placed: list[Placed]) -> str:
    seen: list[str] = []
    for p in placed:
        if p.tool.name not in seen:
            seen.append(p.tool.name)
    return ", ".join(seen)


def _replace_actions(ctx: Context, p: Placed, candidates: list[str]) -> list[Action]:
    actions = []
    for tid in candidates:
        if tid in ctx.catalog and tid != p.tool.id:
            actions.append(Action("replace_brick", f"Remplacer {p.tool.name} par {ctx.name(tid)}",
                                  {"uid": p.brick.uid, "tool": tid}))
    return actions


def _keep_only_actions(group: list[Placed]) -> list[Action]:
    actions = []
    tools: dict[str, list[Placed]] = {}
    for p in group:
        tools.setdefault(p.tool.id, []).append(p)
    for tid, keep in tools.items():
        others = [q.brick.uid for q in group if q.tool.id != tid]
        actions.append(Action("remove_bricks", f"Garder seulement {keep[0].tool.name}", {"uids": others}))
    return actions


# --------------------------------------------------------------------------
# Handlers : (rule, ctx) -> list[Diagnostic]
# --------------------------------------------------------------------------
Handler = Callable[[Rule, Context], list[Diagnostic]]
HANDLERS: dict[str, Handler] = {}


def handler(name: str) -> Callable[[Handler], Handler]:
    def deco(fn: Handler) -> Handler:
        HANDLERS[name] = fn
        return fn
    return deco


def _diag(rule: Rule, message: str, bricks: list[str], actions: list[Action],
          severity: Severity | None = None) -> Diagnostic:
    return Diagnostic(rule.id, rule.family, severity or rule.severity, message, bricks, actions)


@handler("hosting_kubernetes")
def h_hosting_kubernetes(rule: Rule, ctx: Context) -> list[Diagnostic]:
    if ctx.project.target not in ("docker-host", "vm"):
        return []
    if ctx.provides("kubernetes-cluster"):
        return []
    out = []
    cluster = rule.params.get("cluster_suggestion", "k3s")
    for p in ctx.placed:
        if not p.tool.kubernetes_only:
            continue
        actions = [
            Action("add_brick", f"Ajouter un cluster {ctx.name(cluster)}",
                   {"tool": cluster, "stage": "infrastructure"}),
            Action("set_project", "Passer la cible en Kubernetes autogéré",
                   {"field": "target", "value": "kubernetes"}),
        ]
        actions += _replace_actions(ctx, p, p.tool.alternatives_outside_k8s)
        actions.append(Action("remove_bricks", f"Retirer {p.tool.name}", {"uids": [p.brick.uid]}))
        out.append(_diag(rule, _fmt(rule.message, tool=p.tool.name,
                                    target=TARGETS.get(ctx.project.target, ctx.project.target)),
                         [p.brick.uid], actions))
    return out


@handler("exclusive_role")
def h_exclusive_role(rule: Rule, ctx: Context) -> list[Diagnostic]:
    role = rule.params["role"]
    group = ctx.with_role(role)
    if len({p.tool.id for p in group}) < 2:
        return []
    return [_diag(rule, _fmt(rule.message, tools=_names(group), role=role),
                  [p.brick.uid for p in group], _keep_only_actions(group))]


@handler("conflict_pair")
def h_conflict_pair(rule: Rule, ctx: Context) -> list[Diagnostic]:
    tools: list[str] = rule.params["tools"]
    group = [p for t in tools for p in ctx.with_tool(t)]
    if not all(ctx.has(t) for t in tools):
        return []
    if rule.params.get("suggest_remove"):
        rm = rule.params["suggest_remove"]
        actions = [Action("remove_bricks", f"Retirer {ctx.name(rm)}",
                          {"uids": [p.brick.uid for p in ctx.with_tool(rm)]})]
    else:
        actions = _keep_only_actions(group)
    return [_diag(rule, _fmt(rule.message, tools=_names(group)), [p.brick.uid for p in group], actions)]


def _project_forges(ctx: Context) -> set[str]:
    return {p.tool.forge for p in ctx.with_role("scm") if p.tool.forge}


@handler("forge")
def h_forge(rule: Rule, ctx: Context) -> list[Diagnostic]:
    forges = _project_forges(ctx)
    if not forges:
        return []
    mode = rule.params.get("mode", "strict")
    out = []
    for p in ctx.placed:
        if not p.tool.forges or forges & set(p.tool.forges):
            continue
        compatible = any(p.tool.id in s.tool.compatible_ci for s in ctx.with_role("scm"))
        if (mode == "strict" and compatible) or (mode == "compatible" and not compatible):
            continue
        role = p.tool.roles[0] if p.tool.roles else None
        natives = [
            t.id for t in ctx.catalog.curated()
            if role in t.roles and t.id != p.tool.id and (not t.forges or forges & set(t.forges))
            and t.kind == "tool"
        ]
        natives.sort(key=lambda tid: (not ctx.catalog[tid].forges, tid))
        actions = _replace_actions(ctx, p, natives[:3])
        forge_names = ", ".join(sorted(forges))
        out.append(_diag(rule, _fmt(rule.message, tool=p.tool.name, forge=forge_names,
                                    forges=", ".join(p.tool.forges)),
                         [p.brick.uid], actions))
    return out


@handler("requires")
def h_requires(rule: Rule, ctx: Context) -> list[Diagnostic]:
    envs = rule.params.get("environments")
    if envs and ctx.project.environment not in envs:
        return []
    capability = rule.params["capability"]
    out = []
    for p in ctx.with_tool(rule.params["tool"]):
        if ctx.provides(capability):
            continue
        actions = [Action("add_brick", f"Ajouter {ctx.name(t)}", {"tool": t})
                   for t in rule.params.get("add", []) if t in ctx.catalog]
        out.append(_diag(rule, _fmt(rule.message, tool=p.tool.name, capability=capability),
                         [p.brick.uid], actions))
    return out


@handler("requires_provider")
def h_requires_provider(rule: Rule, ctx: Context) -> list[Diagnostic]:
    out = []
    present = {p.tool.id for p in ctx.placed}
    for p in ctx.placed:
        prov = p.tool.provider
        if not prov or prov in present:
            continue
        actions = [Action("add_brick", f"Ajouter le fournisseur {ctx.name(prov)}",
                          {"tool": prov, "stage": "infrastructure"})]
        out.append(_diag(rule, _fmt(rule.message, tool=p.tool.name, provider=ctx.name(prov)),
                         [p.brick.uid], actions))
    return out


@handler("lifecycle")
def h_lifecycle(rule: Rule, ctx: Context) -> list[Diagnostic]:
    out = []
    for p in ctx.with_tool(rule.params["tool"]):
        actions = _replace_actions(ctx, p, p.tool.replacements)
        out.append(_diag(rule, _fmt(rule.message, tool=p.tool.name, note=p.tool.lifecycle_note),
                         [p.brick.uid], actions))
    return out


@handler("sovereignty")
def h_sovereignty(rule: Rule, ctx: Context) -> list[Diagnostic]:
    if not ctx.project.secnumcloud:
        return []
    out = []
    refused = {p.tool.id for p in ctx.placed if p.tool.kind == "provider" and p.tool.secnumcloud == "no"}
    for p in ctx.placed:
        prov = p.tool.id if p.tool.kind == "provider" else p.tool.provider
        if prov not in refused:
            continue
        actions = []
        if p.tool.kind == "provider":
            actions += _replace_actions(ctx, p, rule.params.get("suggest", ["outscale"]))
        actions.append(Action("set_project", "Lever l'exigence SecNumCloud",
                              {"field": "secnumcloud", "value": False}))
        out.append(_diag(rule, _fmt(rule.message, tool=p.tool.name, provider=ctx.name(prov)),
                         [p.brick.uid], actions))
    return out


@handler("target_mismatch")
def h_target_mismatch(rule: Rule, ctx: Context) -> list[Diagnostic]:
    if ctx.project.target not in rule.params["targets"]:
        return []
    out = []
    for p in ctx.with_tool(rule.params["tool"]):
        actions = _replace_actions(ctx, p, p.tool.replacements)
        out.append(_diag(rule, _fmt(rule.message, tool=p.tool.name,
                                    target=TARGETS.get(ctx.project.target)),
                         [p.brick.uid], actions))
    return out


def env_cluster(ctx: Context, env) -> Placed | None:
    """Brique cluster utilisée par un environnement : la sienne, ou l'unique cluster du pipeline."""
    clusters = ctx.with_role("kubernetes-cluster")
    if env.cluster:
        return next((c for c in clusters if c.tool.id == env.cluster), None)
    return clusters[0] if len({c.tool.id for c in clusters}) == 1 else None


@handler("environment")
def h_environment(rule: Rule, ctx: Context) -> list[Diagnostic]:
    kinds = rule.params.get("environments", ["production"])
    out = []
    seen: set[str] = set()
    for env in ctx.project.environments:
        if env.kind not in kinds:
            continue
        p = env_cluster(ctx, env)
        if p is None or not p.tool.dev_only or p.brick.uid in seen:
            continue
        seen.add(p.brick.uid)
        actions = _replace_actions(ctx, p, rule.params.get("suggest", ["k3s", "rke2"]))
        out.append(_diag(rule, _fmt(rule.message, tool=p.tool.name, env=env.display), [p.brick.uid], actions))
    return out


@handler("cross_cloud")
def h_cross_cloud(rule: Rule, ctx: Context) -> list[Diagnostic]:
    clusters = [p for p in ctx.placed if "kubernetes-managed" in p.tool.provides and p.tool.provider]
    registries = [p for p in ctx.with_role("registry") if p.tool.provider]
    out = []
    for c in clusters:
        for r in registries:
            if r.tool.provider == c.tool.provider:
                continue
            prov = ctx.catalog.get(c.tool.provider)
            actions = []
            if prov and prov.services.get("registry"):
                actions = _replace_actions(ctx, r, [prov.services["registry"]])
            out.append(_diag(rule, _fmt(rule.message, cluster=c.tool.name, registry=r.tool.name),
                             [c.brick.uid, r.brick.uid], actions))
    return out


@handler("static_credentials")
def h_static_credentials(rule: Rule, ctx: Context) -> list[Diagnostic]:
    if ctx.project.cloud_auth != "static":
        return []
    providers = [p for p in ctx.placed if p.tool.kind == "provider" and "oidc" in p.tool.auth]
    if not providers:
        return []
    return [_diag(rule, _fmt(rule.message, tools=_names(providers)),
                  [p.brick.uid for p in providers],
                  [Action("set_project", "Utiliser la fédération d'identité OIDC",
                          {"field": "cloud_auth", "value": "oidc"})])]


@handler("license")
def h_license(rule: Rule, ctx: Context) -> list[Diagnostic]:
    licenses = set(rule.params.get("licenses", []))
    out = []
    for p in ctx.placed:
        if not p.tool.curated:
            continue
        flagged = p.tool.license in licenses
        policy = ctx.project.license_policy == "oss-only" and not p.tool.is_oss
        if not (flagged or policy):
            continue
        severity = Severity.WARNING if policy else None
        actions = _replace_actions(ctx, p, p.tool.alternatives)
        out.append(_diag(rule, _fmt(rule.message, tool=p.tool.name, license=p.tool.license),
                         [p.brick.uid], actions, severity))
    return out


@handler("placement")
def h_placement(rule: Rule, ctx: Context) -> list[Diagnostic]:
    out = []
    for p in ctx.placed:
        if p.tool.can_go_in(p.stage):
            continue
        allowed = p.tool.allowed_stages
        actions = [Action("move_brick", f"Déplacer vers « {STAGE_LABELS[s]} »", {"uid": p.brick.uid, "stage": s})
                   for s in allowed]
        actions.append(Action("remove_bricks", f"Retirer {p.tool.name}", {"uids": [p.brick.uid]}))
        out.append(_diag(rule, _fmt(rule.message, tool=p.tool.name, stage=STAGE_LABELS[p.stage],
                                    allowed=", ".join(STAGE_LABELS[s] for s in allowed)),
                         [p.brick.uid], actions))
    return out


# --------------------------------------------------------------------------
# Complétude
# --------------------------------------------------------------------------
CI_ROLES = {"image-build", "unit-tests", "code-quality", "sast", "vuln-scan", "iac-scan", "secret-scan",
            "sbom", "signing", "deploy", "gitops", "iac"}
CAP_LABELS = {  # complément de « a besoin … »
    "git-server": "d'une forge Git",
    "registry-oci": "d'un registre d'images OCI",
    "secret-store": "d'un coffre de secrets",
    "object-storage": "d'un stockage objet",
    "metrics-prometheus": "de Prometheus",
    "trace-storage": "d'un stockage de traces",
    "cni": "d'un plugin réseau (CNI)",
    "kubernetes-cluster": "d'un cluster Kubernetes",
    "database": "d'une base de données",
    "config-mgmt": "de playbooks Ansible",
    "iac-hcl": "de Terraform ou OpenTofu pour créer les machines",
}
MANAGED_TARGETS = ("kubernetes", "kubernetes-managed")


def _needs_ci(tool: Tool) -> bool:
    if tool.kind == "provider" or not tool.curated:
        return False
    if tool.kubernetes_only and "iac" in tool.roles:
        return False  # Crossplane : réconcilié dans le cluster, pas en CI
    return bool(CI_ROLES & set(tool.roles))


def _add_actions(ctx: Context, tool_ids: list[str], limit: int = 4) -> list[Action]:
    seen: list[str] = []
    for tid in tool_ids:
        if tid in ctx.catalog and tid not in seen and not ctx.has(tid):
            seen.append(tid)
    return [Action("add_brick", f"Ajouter {ctx.name(t)}", {"tool": t}) for t in seen[:limit]]


def _present_providers(ctx: Context) -> list[Tool]:
    return [p.tool for p in ctx.placed if p.tool.kind == "provider"]


@handler("missing_ci")
def h_missing_ci(rule: Rule, ctx: Context) -> list[Diagnostic]:
    if ctx.with_role("ci"):
        return []
    needing = [p for p in ctx.placed if _needs_ci(p.tool)]
    if not needing:
        return []
    forges = _project_forges(ctx)
    natives = [t.id for t in ctx.catalog.curated() if "ci" in t.roles and t.forges and forges & set(t.forges)]
    natives.sort(key=lambda tid: (ctx.catalog[tid].kind != "tool", len(ctx.catalog[tid].forges), tid))
    generic = ["jenkins", "woodpecker"] if forges else ["gitlab-ci", "github-actions", "jenkins"]
    return [_diag(rule, _fmt(rule.message, tools=_names(needing)), [p.brick.uid for p in needing],
                  _add_actions(ctx, natives + generic, 3))]


@handler("build_without_registry")
def h_build_without_registry(rule: Rule, ctx: Context) -> list[Diagnostic]:
    builders = ctx.with_role("image-build")
    if not builders or ctx.with_role("registry"):
        return []
    forges = _project_forges(ctx)
    if "gitlab" in forges:
        return []  # registre intégré de GitLab ($CI_REGISTRY_IMAGE)
    suggestions = [p.services["registry"] for p in _present_providers(ctx) if p.services.get("registry")]
    if "github" in forges:
        suggestions.append("ghcr")
    suggestions += ["harbor", "zot"]
    return [_diag(rule, _fmt(rule.message, tools=_names(builders)), [p.brick.uid for p in builders],
                  _add_actions(ctx, suggestions))]


@handler("deploy_without_build")
def h_deploy_without_build(rule: Rule, ctx: Context) -> list[Diagnostic]:
    if ctx.with_role("image-build"):
        return []
    deployers = [p for p in ctx.placed if p.tool.curated and {"deploy", "gitops"} & set(p.tool.roles)
                 and p.tool.id != "ansible"]
    if not deployers:
        return []
    return [_diag(rule, _fmt(rule.message, tools=_names(deployers), app=ctx.project.app.image_name),
                  [p.brick.uid for p in deployers], _add_actions(ctx, ["buildkit", "buildpacks", "buildah"], 3))]


@handler("requires_generic")
def h_requires_generic(rule: Rule, ctx: Context) -> list[Diagnostic]:
    skip = {tuple(x) for x in rule.params.get("skip", [])}
    provider_ids = {t.id for t in _present_providers(ctx)}
    target = ctx.project.target
    no_cluster = not ctx.provides("kubernetes-cluster") and target in ("docker-host", "vm")
    out = []
    for p in ctx.placed:
        for cap in p.tool.requires:
            if (p.tool.id, cap) in skip or ctx.provides(cap):
                continue
            candidates = [t for t in ctx.catalog.providing(cap) if not (no_cluster and t.kubernetes_only)]
            wanted_forges = set(p.tool.forges)
            candidates.sort(key=lambda t, wf=wanted_forges: (
                bool(wf) and t.forge not in wf,                                # forge compatible d'abord
                t.provider not in provider_ids if t.provider else True,        # cloud déjà présent
                t.kind != "tool", t.id))
            out.append(_diag(rule, _fmt(rule.message, tool=p.tool.name, capability=CAP_LABELS.get(cap, cap)),
                             [p.brick.uid], _add_actions(ctx, [t.id for t in candidates], 3)))
    return out


@handler("target_cluster")
def h_target_cluster(rule: Rule, ctx: Context) -> list[Diagnostic]:
    target = ctx.project.target
    clusters = ctx.with_role("kubernetes-cluster")
    # La cible décrit l'hébergement de la production : un cluster kind de développement
    # à côté d'un EKS de production n'est pas une incohérence.
    prod = [c for e in ctx.project.environments if e.kind == "production" if (c := env_cluster(ctx, e))]
    if prod:
        clusters = list({c.brick.uid: c for c in prod}.values())
    managed = [p for p in clusters if "kubernetes-managed" in p.tool.provides]
    self_managed = [p for p in clusters if p not in managed]
    tname = TARGETS.get(target, target)
    out = []
    if target in MANAGED_TARGETS and not clusters:
        if target == "kubernetes-managed":
            sugg = [p.services["k8s.managed"] for p in _present_providers(ctx) if p.services.get("k8s.managed")]
            sugg = sugg or ["eks", "gke", "aks"]
        else:
            sugg = ["k3s", "rke2"]
        msg = _fmt(rule.message, target=tname) + " Les déploiements utiliseront un kubeconfig fourni par la variable KUBECONFIG_DATA."
        out.append(_diag(rule, msg, [], _add_actions(ctx, sugg, 3)))
    if target == "kubernetes-managed" and self_managed:
        out.append(_diag(rule, f"{_names(self_managed)} n'est pas un Kubernetes managé, or la cible est « {tname} ».",
                         [p.brick.uid for p in self_managed],
                         [Action("set_project", "Passer la cible en Kubernetes autogéré",
                                 {"field": "target", "value": "kubernetes"})]))
    if target in ("kubernetes", "docker-host") and managed:
        out.append(_diag(rule, f"{_names(managed)} est un Kubernetes managé, or la cible est « {tname} ».",
                         [p.brick.uid for p in managed],
                         [Action("set_project", "Passer la cible en Kubernetes managé",
                                 {"field": "target", "value": "kubernetes-managed"})]))
    return out


@handler("no_generator")
def h_no_generator(rule: Rule, ctx: Context) -> list[Diagnostic]:
    from .generators import render  # import tardif : les générateurs dépendent des règles

    try:
        unsupported = render(ctx.project, ctx.catalog)[1].unsupported
    except Exception:  # un projet bancal ne doit pas faire tomber l'évaluation
        return []
    out = []
    for tool in unsupported:
        if not tool.curated:
            continue  # déjà signalé par R00
        uids = [b.uid for b in ctx.project.bricks_for(tool.id)]
        out.append(_diag(rule, _fmt(rule.message, tool=tool.name), uids, []))
    return out


# --------------------------------------------------------------------------
# Paramètres
# --------------------------------------------------------------------------
@handler("params")
def h_params(rule: Rule, ctx: Context) -> list[Diagnostic]:
    from .params import check_brick

    kinds = set(rule.params["kinds"])
    out = []
    for p in ctx.placed:
        for issue in check_brick(p.tool, p.brick, ctx.project):
            if issue.kind not in kinds:
                continue
            spec = p.tool.param_schema.get(issue.key)
            if issue.kind == "example" and spec and spec.provided_by and ctx.provides(spec.provided_by):
                continue
            actions: list[Action] = []
            if issue.kind == "unknown":
                if issue.suggestion:
                    actions.append(Action("rename_param", f"Renommer en « {issue.suggestion} »",
                                          {"uid": p.brick.uid, "old": issue.key, "new": issue.suggestion}))
                actions.append(Action("remove_param", f"Supprimer « {issue.key} »",
                                      {"uid": p.brick.uid, "key": issue.key}))
            elif issue.kind == "invalid" and issue.key in p.brick.params:
                spec = p.tool.param_schema[issue.key]
                if spec.default is not None or spec.example is not None:
                    actions.append(Action("remove_param", "Revenir à la valeur par défaut",
                                          {"uid": p.brick.uid, "key": issue.key}))
            out.append(_diag(rule, f"{p.tool.name} : {issue.message}.", [p.brick.uid], actions))
        for env in ctx.project.environments:
            for issue in check_overrides(p.tool, env):
                if issue.kind not in kinds:
                    continue
                args = {"env": env.id, "tool": p.tool.id, "key": issue.key}
                actions = []
                if issue.kind == "unknown" and issue.suggestion:
                    actions.append(Action("rename_override", f"Renommer en « {issue.suggestion} »",
                                          {**args, "new": issue.suggestion}))
                actions.append(Action("remove_override", f"Supprimer la surcharge « {issue.key} »", args))
                out.append(_diag(rule, f"{p.tool.name} : {issue.message}.", [p.brick.uid], actions))
    return out


# --------------------------------------------------------------------------
# Environnements
# --------------------------------------------------------------------------
@handler("single_cluster")
def h_single_cluster(rule: Rule, ctx: Context) -> list[Diagnostic]:
    group = ctx.with_role("kubernetes-cluster")
    if len({p.tool.id for p in group}) < 2 or ctx.project.multi_env:
        return []  # avec plusieurs environnements, chacun désigne son cluster (R36)
    actions = _keep_only_actions(group)
    actions.append(Action("set_project", "Créer des environnements (dev → préprod → production)",
                          {"field": "environments", "value": "preset:dev-staging-prod"}))
    return [_diag(rule, _fmt(rule.message, tools=_names(group)), [p.brick.uid for p in group], actions)]


@handler("env_definition")
def h_env_definition(rule: Rule, ctx: Context) -> list[Diagnostic]:
    envs = ctx.project.environments
    if not envs:
        return [_diag(rule, "Le projet n'a aucun environnement de déploiement.", [],
                      [Action("set_project", "Ajouter un environnement de production",
                              {"field": "environments", "value": "preset:prod"})])]
    out = []
    seen: set[str] = set()
    for env in envs:
        if not re.fullmatch(ENV_ID_PATTERN, env.id):
            out.append(_diag(rule, f"L'identifiant d'environnement « {env.id} » est invalide : minuscules, chiffres "
                                   "et tirets, 20 caractères au plus, commence par une lettre.", [], []))
        if env.id in seen:
            out.append(_diag(rule, f"L'identifiant d'environnement « {env.id} » est utilisé deux fois.", [], []))
        seen.add(env.id)
    return out


@handler("env_cluster")
def h_env_cluster(rule: Rule, ctx: Context) -> list[Diagnostic]:
    clusters = ctx.with_role("kubernetes-cluster")
    ids = [c.tool.id for c in clusters]
    out = []
    for env in ctx.project.environments:
        if env.cluster and env.cluster not in ids:
            out.append(_diag(rule, f"L'environnement « {env.display} » désigne le cluster « {ctx.name(env.cluster)} », "
                                   "absent du pipeline.", [],
                             [Action("set_env", "Retirer ce rattachement", {"env": env.id, "field": "cluster", "value": None})]))
        elif not env.cluster and len(set(ids)) > 1:
            out.append(_diag(rule, f"Plusieurs clusters sont décrits : préciser celui de l'environnement « {env.display} ».",
                             [c.brick.uid for c in clusters],
                             [Action("set_env", f"Utiliser {c.tool.name} pour « {env.display} »",
                                     {"env": env.id, "field": "cluster", "value": c.tool.id}) for c in clusters]))
    if len(set(ids)) > 1 and ctx.project.multi_env:
        used = {e.cluster for e in ctx.project.environments}
        for c in clusters:
            if c.tool.id not in used and all(e.cluster for e in ctx.project.environments):
                out.append(_diag(rule, f"{c.tool.name} n'est rattaché à aucun environnement.", [c.brick.uid],
                                 [Action("remove_bricks", f"Retirer {c.tool.name}", {"uids": [c.brick.uid]})],
                                 Severity.WARNING))
    return out


@handler("prod_approval")
def h_prod_approval(rule: Rule, ctx: Context) -> list[Diagnostic]:
    if not ctx.project.multi_env:
        return []
    return [_diag(rule, _fmt(rule.message, env=e.display), [],
                  [Action("set_env", f"Exiger une approbation pour « {e.display} »",
                          {"env": e.id, "field": "approval", "value": True})])
            for e in ctx.project.environments if e.kind == "production" and not e.approval]


@handler("env_collision")
def h_env_collision(rule: Rule, ctx: Context) -> list[Diagnostic]:
    from .params import effective_params

    if not ctx.project.multi_env:
        return []
    out = []
    for p in ctx.placed:
        for key, spec in p.tool.param_schema.items():
            if not spec.per_env:
                continue
            seen: dict[str, str] = {}
            for env in ctx.project.environments:
                value = str(effective_params(p.tool, p.brick, ctx.project, env).get(key))
                if value in seen:
                    out.append(_diag(rule, _fmt(rule.message, tool=p.tool.name, label=spec.label, value=value,
                                                a=seen[value], b=env.display), [p.brick.uid],
                                     [Action("remove_override", f"Supprimer la surcharge de « {env.display} »",
                                             {"env": env.id, "tool": p.tool.id, "key": key})]
                                     if key in env.overrides.get(p.tool.id, {}) else []))
                seen[value] = env.display
    return out


@handler("unverified")
def h_unverified(rule: Rule, ctx: Context) -> list[Diagnostic]:
    return [
        _diag(rule, _fmt(rule.message, tool=p.tool.name), [p.brick.uid], [])
        for p in ctx.placed if not p.tool.curated
    ]


# --------------------------------------------------------------------------
# Chargement et évaluation
# --------------------------------------------------------------------------
def load_rules(directory: Path = RULES_DIR) -> list[Rule]:
    rules: list[Rule] = []
    for path in sorted(directory.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if data["type"] not in HANDLERS:
            raise ValueError(f"{path.name}: type de règle inconnu {data['type']}")
        rules.append(Rule(
            id=data["id"], title=data["title"], family=data["family"],
            severity=Severity(data["severity"]), type=data["type"],
            message=data["message"], params=data.get("params", {}), source=path.name,
        ))
    ids = [r.id for r in rules]
    if len(ids) != len(set(ids)):
        raise ValueError("Identifiants de règles en double")
    return rules


class RuleEngine:
    def __init__(self, catalog: Catalog, rules: list[Rule] | None = None):
        self.catalog = catalog
        self.rules = rules if rules is not None else load_rules()

    def evaluate(self, project: Project) -> list[Diagnostic]:
        ctx = Context(project, self.catalog)
        out: list[Diagnostic] = []
        for rule in self.rules:
            out.extend(HANDLERS[rule.type](rule, ctx))
        out.sort(key=lambda d: (d.severity.rank, d.rule_id))
        return out

    @staticmethod
    def blocking(diagnostics: list[Diagnostic]) -> list[Diagnostic]:
        return [d for d in diagnostics if d.severity is Severity.BLOCKING]


@handler("port_conflict")
def h_port_conflict(rule: Rule, ctx: Context) -> list[Diagnostic]:
    from .ports import MAX_PORT, conflicts, free_port, port_plan
    plan = port_plan(ctx.project, ctx.catalog)
    out = []
    groups: dict[tuple[str, int], list] = {}
    for e in conflicts(plan):
        groups.setdefault((e.host_group, e.host_port or 0), []).append(e)
    for (group, port), same in groups.items():
        host = "l'" + group[1:-1] if group.startswith("(") else f"l'hôte « {group} »"
        if port > MAX_PORT:
            message = f"{same[0].component} ({same[0].env}) : port {port} au-delà de {MAX_PORT} après décalage."
        else:
            owners = ", ".join(dict.fromkeys(f"{x.component} ({x.env})" for x in same))
            message = _fmt(rule.message, port=port, host=host, owners=owners)
        actions: list[Action] = []
        if any(x.component_id == "app" for x in same):
            new = free_port(plan, ctx.project.app.port + 1)
            actions.append(Action("set_app_port", f"Publier l'application sur le port {new}", {"port": new}))
        for env in ctx.project.environments:
            if env.port_offset is not None and any(x.env_id == env.id for x in same):
                actions.append(Action("set_env", f"Décalage automatique des ports pour « {env.display} »",
                                      {"env": env.id, "field": "port_offset", "value": None}))
        tools = list(dict.fromkeys(x.component_id for x in same if x.component_id != "app"))
        for tid in tools[1:]:
            actions.append(Action("remove_bricks", f"Retirer {ctx.name(tid)}",
                                  {"uids": [b.uid for b in ctx.project.bricks_for(tid)]}))
        bricks = [b.uid for tid in tools for b in ctx.project.bricks_for(tid)]
        out.append(_diag(rule, message, bricks, actions))
    return out


def _kube_databases(ctx: Context) -> list[Placed]:
    """Bases autogérées ou opérateur qui tournent dans un cluster (pas de Compose pour les porter)."""
    from .databases import ENGINES, OPERATORS
    on_cluster = ctx.project.target in MANAGED_TARGETS or bool(ctx.with_role("kubernetes-cluster"))
    if not on_cluster or ctx.has("docker-compose"):
        return []
    return [p for p in ctx.placed if p.tool.id in ENGINES or p.tool.id in OPERATORS]


def _prod_envs(ctx: Context) -> list:
    return [e for e in ctx.project.environments if e.kind == "production"]


@handler("database_backup")
def h_database_backup(rule: Rule, ctx: Context) -> list[Diagnostic]:
    from .databases import ENGINES
    prod = _prod_envs(ctx)
    if not prod or ctx.has("velero"):
        return []
    out = []
    for p in _kube_databases(ctx):
        if p.tool.id in ENGINES and ENGINES[p.tool.id].family == "key-value":
            continue  # cache : la persistance du volume suffit en général
        if p.tool.id == "cloudnative-pg":
            from .generators.data import cnpg_backup
            from .ir import build_ir
            if cnpg_backup(build_ir(ctx.project, ctx.catalog)):
                continue  # plugin Barman Cloud vers le stockage objet
        actions = _add_actions(ctx, ["velero"], 1)
        out.append(_diag(rule, _fmt(rule.message, tool=p.tool.name, env=prod[0].display), [p.brick.uid], actions))
    return out


@handler("database_statefulset")
def h_database_statefulset(rule: Rule, ctx: Context) -> list[Diagnostic]:
    from .databases import ENGINES
    prod = _prod_envs(ctx)
    if not prod:
        return []
    out = []
    managed = [prov.services.get("database") for prov in _present_providers(ctx)]
    for p in _kube_databases(ctx):
        engine = ENGINES.get(p.tool.id)
        if engine is None or engine.family == "key-value":
            continue
        candidates = (["cloudnative-pg"] if p.tool.id == "postgresql" else []) + [m for m in managed if m]
        actions = _replace_actions(ctx, p, [c for c in candidates if not ctx.has(c)])
        out.append(_diag(rule, _fmt(rule.message, tool=p.tool.name, env=prod[0].display), [p.brick.uid], actions))
    return out


@handler("local_state")
def h_local_state(rule: Rule, ctx: Context) -> list[Diagnostic]:
    from .generators.iac import REMOTE_BACKENDS
    stacks = [p for p in ctx.placed if p.tool.id in ("terraform", "opentofu")]
    if not stacks or not ctx.with_role("ci") or any(ctx.has(t) for t in REMOTE_BACKENDS):
        return []
    storages = [prov.services["object-storage"] for prov in _present_providers(ctx)
                if prov.services.get("object-storage") in REMOTE_BACKENDS]
    return [_diag(rule, _fmt(rule.message, tool=stacks[0].tool.name), [p.brick.uid for p in stacks],
                  _add_actions(ctx, storages, 3))]


@handler("connection_format")
def h_connection_format(rule: Rule, ctx: Context) -> list[Diagnostic]:
    from .databases import databases
    out = []
    seen: dict[str, str] = {}
    for db in databases(ctx.project, ctx.catalog):
        uid = next((p.brick.uid for p in ctx.placed if p.tool.id == db.id), None)
        if db.mode == "managed" and str(db.params.get("url_format") or "") == "parts":
            out.append(_diag(rule, _fmt(rule.message, tool=db.tool.name,
                                        detail="une base managée transmet une seule URL : les variables séparées "
                                               "ne sont pas générées, l'application reçoit l'URL"),
                             [uid] if uid else [], []))
        if db.url_var in seen:
            out.append(_diag(rule, _fmt(rule.message, tool=db.tool.name,
                                        detail=f"la variable {db.url_var} est déjà celle de {seen[db.url_var]} : "
                                               "l'une écraserait l'autre"), [uid] if uid else [], []))
        seen.setdefault(db.url_var, db.tool.name)
    return out


@handler("backup_plugin")
def h_backup_plugin(rule: Rule, ctx: Context) -> list[Diagnostic]:
    """Sauvegardes CloudNativePG générées : le plugin Barman Cloud demande cert-manager."""
    from .generators.data import cnpg_backup
    from .ir import build_ir
    placed = [p for p in ctx.placed if p.tool.id == "cloudnative-pg"]
    if not placed or ctx.has("cert-manager"):
        return []
    if not cnpg_backup(build_ir(ctx.project, ctx.catalog)):
        return []
    return [_diag(rule, rule.message, [placed[0].brick.uid], _add_actions(ctx, ["cert-manager"]))]


@handler("identity_prereq")
def h_identity_prereq(rule: Rule, ctx: Context) -> list[Diagnostic]:
    """Keycloak et Dex sur un hôte Docker : terminaison HTTPS par Traefik."""
    out = []
    for p in ctx.placed:
        if p.tool.id not in ("keycloak", "dex"):
            continue
        if ctx.project.target in ("docker-host", "vm") and ctx.has("docker-compose") and not ctx.has("traefik"):
            out.append(_diag(rule, _fmt(rule.message, tool=p.tool.name,
                                        detail="un fournisseur d'identité se sert en HTTPS : ajouter Traefik, qui "
                                               "termine TLS devant lui sur l'hôte Docker"),
                             [p.brick.uid], _add_actions(ctx, ["traefik"])))
    return out


@handler("vault_unreachable")
def h_vault_unreachable(rule: Rule, ctx: Context) -> list[Diagnostic]:
    from .databases import DATABASE_TOOLS
    from .params import effective_params
    if ctx.project.target not in ("docker-host", "vm") or not ctx.has("docker-compose") or ctx.has("sops"):
        return []
    if not any(p.tool.id in DATABASE_TOOLS for p in ctx.placed):
        return []
    out = []
    for p in ctx.placed:
        if p.tool.id in ("vault", "openbao") and not effective_params(p.tool, p.brick, ctx.project).get("address"):
            out.append(_diag(rule, _fmt(rule.message, tool=p.tool.name), [p.brick.uid], []))
            break  # Vault l'emporte sur OpenBao comme source : un seul message
    return out


def apply_action(project: Project, action: Action, catalog: Catalog) -> None:
    """Applique une correction proposée au projet (en place)."""
    args = action.args
    if action.op == "add_brick":
        tool = catalog[args["tool"]]
        if not project.bricks_for(tool.id):
            project.add(tool.id, args.get("stage") or tool.stage)
    elif action.op == "remove_bricks":
        for uid in args["uids"]:
            project.remove(uid)
    elif action.op == "replace_brick":
        found = project.find(args["uid"])
        if not found:
            return
        stage, idx, brick = found
        new_tool = catalog[args["tool"]]
        if project.bricks_for(new_tool.id):
            project.remove(brick.uid)
            return
        if new_tool.stage == stage:
            brick.tool = new_tool.id
            brick.params = {}
        else:
            project.remove(brick.uid)
            project.add(new_tool.id, new_tool.stage)
    elif action.op in ("rename_param", "remove_param"):
        found = project.find(args["uid"])
        if found:
            params = dict(found[2].params)
            key = args["old"] if action.op == "rename_param" else args["key"]
            value = params.pop(key, None)
            if action.op == "rename_param" and value is not None:
                params[args["new"]] = value
            found[2].params = params
    elif action.op in ("rename_override", "remove_override"):
        env = project.env(args["env"])
        if env is not None:
            values = dict(env.overrides.get(args["tool"], {}))
            value = values.pop(args["key"], None)
            if action.op == "rename_override" and value is not None:
                values[args["new"]] = value
            if values:
                env.overrides[args["tool"]] = values
            else:
                env.overrides.pop(args["tool"], None)
    elif action.op == "set_env":
        env = project.env(args["env"])
        if env is not None:
            setattr(env, args["field"], args["value"])
    elif action.op == "set_app_port":
        project.app.port = int(args["port"])
    elif action.op == "move_brick":
        project.move(args["uid"], args["stage"])
    elif action.op == "set_project":
        value = args["value"]
        if args["field"] == "environments" and isinstance(value, str) and value.startswith("preset:"):
            value = env_preset(value.split(":", 1)[1])
        setattr(project, args["field"], value)
    else:
        raise ValueError(f"Action inconnue : {action.op}")
