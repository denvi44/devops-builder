# SPDX-License-Identifier: Apache-2.0
"""Ce que deviennent les bases d'un projet : mode, emplacement, connexion, secret, sauvegarde.

Une seule source pour la carte du canevas, le panneau des propriétés, la vue « Données » et la
section Données de PIPELINE.md : ce que l'interface annonce est ce que les générateurs écrivent.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .catalog import Catalog
from .databases import Database, databases, env_params
from .model import Project

MODES = {"self-hosted": "autogérée", "operator": "opérateur Kubernetes", "managed": "service managé"}


@dataclass
class DbInfo:
    db: Database
    badge: str        # mode en quelques mots, pour la carte : « Conteneur Compose », « Service managé »…
    where: str
    secret: str       # d'où viennent le mot de passe ou l'URL
    backup: str
    connection: str   # variable lue par l'application et son format


@dataclass
class DbRow:
    """Une base dans un environnement (vue « Données »)."""

    env_id: str
    env: str
    db_id: str
    name: str
    badge: str
    version: str
    size: str
    instance: str
    connection: str
    secret: str
    backup: str
    warnings: list[str] = field(default_factory=list)


def _kube(ir) -> bool:
    return ir.project.target in ("kubernetes", "kubernetes-managed") or ir.cluster is not None


def connection_label(db: Database, code: bool = True) -> str:
    """Variable lue par l'application, avec son format quand ce n'est pas une URL simple."""
    q = "`" if code else ""
    label = f"{q}{db.url_var}{q}"
    if db.fmt == "jdbc":
        label += " (JDBC)"
    elif db.fmt == "parts":
        p = db.parts_prefix
        label += f" et {q}{p}_HOST{q}, {q}_PORT{q}, {q}_NAME{q}, {q}_USER{q}, {q}_PASSWORD{q}"
    return label


def describe(ir, db: Database, code: bool = True) -> DbInfo:
    from .generators.data import BACKUP_SCRIPT, DUMPS, cnpg_backup, gitops, secret_name
    from .generators.secrets import origin
    kube = _kube(ir)
    q = "`" if code else ""
    if db.mode == "managed":
        badge = "Service managé"
        where = f"{db.tool.name}, une instance par environnement (Terraform)"
        secret = f"variable CI {q}{db.url_ci_var}" + ("_<ENV>" if ir.multi_env else "") + q
        backup = ("cache : données reconstructibles, pas de sauvegarde planifiée" if db.engine.family == "key-value"
                  else "service du fournisseur (rétention configurée)")
    elif db.mode == "operator":
        badge = "CloudNativePG"
        where = "Cluster CloudNativePG dans l'espace de noms de l'application"
        secret = f"Secret {q}{secret_name(ir, db)}{q} créé par l'opérateur"
        target = cnpg_backup(ir)
        backup = (f"Barman Cloud vers {target[1]}, rétention 30 jours" if target else
                  "plugin Barman Cloud ou instantanés de volumes, à configurer")
    else:
        if kube and not ir.has("docker-compose"):
            badge = "StatefulSet"
            where = "StatefulSet dans l'espace de noms de l'application"
            backup = "Velero ou instantanés de volumes" if ir.has("velero") else "à prévoir (Velero, instantanés)"
        else:
            badge = "Conteneur Compose"
            where = "service Compose, volume nommé, réseau interne"
            backup = f"{q}{BACKUP_SCRIPT}{q} à planifier" if db.id in DUMPS else "persistance AOF du volume"
        secret = f"variable CI {q}{db.password_var}" + ("_<ENV>" if ir.multi_env else "") + q
        if kube and gitops(ir):
            secret = f"Secret {q}{secret_name(ir, db)}{q} (GitOps : External Secrets ou SOPS)"
    if db.mode != "operator":
        found = origin(ir, db, kube)
        if found:
            secret = found if code else found.replace("`", "")
    return DbInfo(db, badge, where, secret, backup, connection_label(db, code))


def infos(project: Project, catalog: Catalog) -> dict[str, DbInfo]:
    """Description de chaque base du projet, par identifiant de brique."""
    from .ir import build_ir
    dbs = databases(project, catalog)
    if not dbs:
        return {}
    ir = build_ir(project, catalog)
    return {db.id: describe(ir, db, code=False) for db in dbs}


SIZE_KEYS = ("memory_gb", "capacity", "storage", "instance_class", "tier", "sku", "node_type", "flavor", "plan", "storage_gb")


def rows(project: Project, catalog: Catalog, diagnostics=None) -> list[DbRow]:
    """Une ligne par base et par environnement ; les avertissements des règles de données y sont rattachés."""
    from .generators.data import instances_for
    from .ir import build_ir
    dbs = databases(project, catalog)
    if not dbs:
        return []
    ir = build_ir(project, catalog)
    by_brick: dict[str, list[str]] = {}
    for d in diagnostics or []:
        for uid in d.bricks:
            by_brick.setdefault(uid, []).append(f"{d.rule_id} — {d.message}")
    out = []
    for db in dbs:
        info = describe(ir, db, code=False)
        uid = next((b.uid for _, b in project.all_bricks() if b.tool == db.id), "")
        warnings = by_brick.get(uid, [])
        for env in project.environments:
            p = env_params(db, project, env)
            if db.mode == "operator":
                size = f"{instances_for(env.kind)} instance(s), {p.get('storage') or '10Gi'}"
            else:
                size = ", ".join(str(p[k]) + (" Go" if k in ("storage_gb", "memory_gb") else "") for k in SIZE_KEYS if p.get(k))
            version = str(p.get("version") or (db.version if db.mode != "managed" else ""))
            engine = p.get("engine")
            if db.mode == "managed" and engine:
                version = f"{engine} {version}".strip()
            mentioned = [w for w in warnings if env.display in w or not any(e.display in w for e in project.environments)]
            out.append(DbRow(env.id, env.display, db.id, db.tool.name, info.badge, version, size,
                             str(p.get("instance") or ""), info.connection, info.secret, info.backup, mentioned))
    return out
