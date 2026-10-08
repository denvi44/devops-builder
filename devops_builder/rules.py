"""Moteur de règles de compatibilité et résolveur de corrections.

Chaque règle est un fichier YAML de `data/rules/` qui choisit un *type*
(handler Python générique) et ses paramètres. Ajouter une incohérence =
ajouter un fichier YAML et son test, sans toucher au code tant qu'un type
existant convient.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .catalog import DATA_DIR, Catalog
from .model import ENVIRONMENTS, TARGETS, BrickInstance, Project, Severity, Tool

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


@handler("environment")
def h_environment(rule: Rule, ctx: Context) -> list[Diagnostic]:
    if ctx.project.environment not in rule.params.get("environments", ["production"]):
        return []
    out = []
    for p in ctx.placed:
        if not p.tool.dev_only:
            continue
        actions = _replace_actions(ctx, p, rule.params.get("suggest", ["k3s", "rke2"]))
        out.append(_diag(rule, _fmt(rule.message, tool=p.tool.name,
                                    env=ENVIRONMENTS.get(ctx.project.environment)),
                         [p.brick.uid], actions))
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
    elif action.op == "set_project":
        setattr(project, args["field"], args["value"])
    else:
        raise ValueError(f"Action inconnue : {action.op}")
