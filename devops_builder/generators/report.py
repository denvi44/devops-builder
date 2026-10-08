"""Rapport PIPELINE.md : briques, licences, variables CI, avertissements restants."""

from __future__ import annotations

from datetime import date

from ..ir import IR
from ..model import ENVIRONMENTS, STAGE_LABELS, TARGETS
from ..rules import Diagnostic


def report(ir: IR, diagnostics: list[Diagnostic], files: list[str]) -> dict[str, str]:
    p = ir.project
    out = [f"# {p.name} — pipeline généré", "",
           f"Généré par DevOps Builder le {date.today().isoformat()}. "
           f"Cible : {TARGETS.get(p.target)} ; environnement : {ENVIRONMENTS.get(p.environment)}"
           + (" ; exigence SecNumCloud." if p.secnumcloud else "."), ""]
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
        out += ["", "## Variables CI à déclarer", "", "| Variable | Secret | Rôle |", "| --- | --- | --- |"]
        for v in ir.variables:
            out.append(f"| `{v.name}` | {'oui' if v.secret else 'non'} | {v.description} |")
    remaining = [d for d in diagnostics]
    out += ["", "## Diagnostics restants", ""]
    if not remaining:
        out.append("Aucun.")
    for d in remaining:
        out.append(f"- **{d.severity.label}** ({d.rule_id}) — {d.message}")
    if ir.unsupported:
        out += ["", "## À configurer à la main", "",
                "Ces briques sont dans le pipeline mais aucun générateur ne les prend en charge :", ""]
        out += [f"- {t.name}" for t in ir.unsupported]
    out += ["", "## Fichiers générés", ""] + [f"- `{f}`" for f in sorted(files)] + [""]
    return {"PIPELINE.md": "\n".join(out)}
