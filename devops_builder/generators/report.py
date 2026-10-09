"""Rapport PIPELINE.md : briques, licences, variables CI, avertissements restants."""

from __future__ import annotations

from datetime import date

from ..ir import IR
from ..model import ENVIRONMENTS, STAGE_LABELS, TARGETS
from ..rules import Diagnostic


def _ports_section(ir: IR) -> list[str]:
    from ..ports import env_offset, port_plan, shared_hosts
    plan = port_plan(ir.project, ir.catalog)
    if not plan:
        return []
    out = ["## Ports", ""]
    shared = shared_hosts(ir.project)
    if shared:
        for host, envs in shared.items():
            parts = ", ".join(f"{e.display} (+{env_offset(ir.project, e)})" for e in envs)
            out.append(f"Hôte partagé `{host}` : {parts}. Les ports publiés de chaque environnement sont dans "
                       "`deploy/env/<environnement>.env`.")
        out.append("")
    multi = ir.multi_env
    head = ("| Environnement " if multi else "") + "| Composant | Port publié | Port du conteneur | Usage | Exposition |"
    out += [head, "|" + " --- |" * (6 if multi else 5)]
    for e in plan:
        published = str(e.host_port) if e.host_port is not None else "—"
        row = (f"| {e.env} " if multi else "") + f"| {e.component} | {published} | {e.container_port} | {e.usage} | {e.exposure} |"
        out.append(row + (f" ⚠ {e.conflict}" if e.conflict else ""))
    out.append("")
    return out


def report(ir: IR, diagnostics: list[Diagnostic], files: list[str]) -> dict[str, str]:
    p = ir.project
    out = [f"# {p.name} — pipeline généré", "",
           f"Généré par DevOps Builder le {date.today().isoformat()}. "
           f"Cible : {TARGETS.get(p.target)}"
           + (" ; exigence SecNumCloud." if p.secnumcloud else "."), ""]
    out += ["## Environnements", "",
            "Ordre de promotion : la même image est déployée successivement dans chaque environnement.", "",
            "| Environnement | Type | Approbation | Cluster | Espace de noms / projet |", "| --- | --- | --- | --- | --- |"]
    for env in p.environments:
        cluster = ir.cluster_for(env)
        cname = ""
        if cluster is not None:
            name = ir.params(cluster.id, env).get("cluster_name")
            cname = f"{cluster.name}" + (f" `{name}`" if name else "")
        out.append(f"| {env.display} (`{env.id}`) | {ENVIRONMENTS[env.kind]} | {'oui' if env.approval else 'non'} "
                   f"| {cname or '—'} | `{ir.namespace(env)}` |")
    out.append("")
    out += _ports_section(ir)
    out += ["## Briques", "", "| Étape | Brique | Licence | Fiche |", "| --- | --- | --- | --- |"]
    for stage, b in p.all_bricks():
        t = ir.catalog.get(b.tool)
        if not t:
            continue
        fiche = "vérifiée" if t.curated else "non vérifiée (Landscape)"
        out.append(f"| {STAGE_LABELS[stage]} | {t.name} | {t.license} | {fiche} |")
    out += ["", "## Étapes CI", ""]
    if ir.ci is None:
        out.append("Aucun orchestrateur CI dans le pipeline : aucun fichier CI n'a été généré.")
    else:
        out.append(f"Orchestrateur : {ir.ci.name}. Image publiée : `{ir.image_ref}:<commit>`.")
        out.append("")
        for i, st in enumerate(ir.steps, 1):
            flags = []
            if st.main_only:
                flags.append("branche principale")
            if st.manual:
                flags.append("manuel")
            if st.allow_failure:
                flags.append("non bloquant")
            extra = f" ({', '.join(flags)})" if flags else ""
            out.append(f"{i}. {st.name}{extra}")
    if ir.variables:
        out += ["", "## Variables CI", "",
                "Les variables sans valeur sont à déclarer dans la CI ; les autres sont déjà écrites dans les fichiers.", "",
                "| Variable | Secret | Valeur | Rôle |", "| --- | --- | --- | --- |"]
        for v in ir.variables:
            value = f"`{v.value}`" if v.value else "à déclarer"
            out.append(f"| `{v.name}` | {'oui' if v.secret else 'non'} | {value} | {v.description} |")
    remaining = [d for d in diagnostics]
    out += ["", "## Diagnostics restants", ""]
    if not remaining:
        out.append("Aucun.")
    for d in remaining:
        out.append(f"- **{d.severity.label}** ({d.rule_id}) — {d.message}")
    if ir.notes:
        out += ["", "## Notes", ""] + [f"- {n}" for n in ir.notes]
    if ir.unsupported:
        out += ["", "## À configurer à la main", "",
                "Ces briques sont dans le pipeline mais aucun générateur ne les prend en charge :", ""]
        out += [f"- {t.name}" for t in ir.unsupported]
    out += ["", "## Fichiers générés", ""] + [f"- `{f}`" for f in sorted(files)] + [""]
    return {"PIPELINE.md": "\n".join(out)}
