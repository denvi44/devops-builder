# SPDX-License-Identifier: Apache-2.0
"""Analyse dynamique (DAST) par ZAP : un job de CI après le déploiement de l'environnement analysé.

Le job tourne dans l'image officielle de ZAP, comme n'importe quelle étape : les scripts « paquetés »
(zap-baseline.py, zap-full-scan.py, zap-api-scan.py) écrivent dans /zap/wrk, le rapport est recopié dans le
dossier du dépôt et publié comme artefact. `.zap/rules.tsv` règle ce qui fait échouer le job ; le job ne
bloque la suite du pipeline que si la brique le demande.
"""

from __future__ import annotations

from ..ir import IR, Step
from ..model import Environment

IMAGE = "ghcr.io/zaproxy/zaproxy"
DEFAULT_VERSION = "2.17.0"
RULES_FILE = ".zap/rules.tsv"
REPORTS = ["zap-report.html", "zap-report.json"]
SCRIPTS = {"baseline": "zap-baseline.py", "full": "zap-full-scan.py", "api": "zap-api-scan.py"}

# (identifiant de la règle ZAP, action, intitulé) : en-têtes et cookies, faciles à corriger et sans faux positif.
FAIL_RULES = [
    ("10010", "Cookie sans l'attribut HttpOnly"),
    ("10011", "Cookie sans l'attribut Secure"),
    ("10054", "Cookie sans l'attribut SameSite"),
    ("10020", "En-tête anti-clickjacking absent (X-Frame-Options ou CSP frame-ancestors)"),
    ("10021", "En-tête X-Content-Type-Options absent"),
]


def enabled(ir: IR) -> bool:
    return ir.has("zap")


def scanned_env(ir: IR) -> Environment | None:
    """Environnement analysé : celui de la brique, sinon le dernier avant la production, sinon l'unique."""
    envs = ir.envs
    wanted = str(ir.params("zap").get("environment") or "")
    for env in envs:
        if env.id == wanted:
            return env
    before_prod = [e for e in envs if e.kind != "production"]
    return before_prod[-1] if before_prod else (envs[-1] if envs else None)


def params(ir: IR) -> dict:
    return ir.params("zap", scanned_env(ir))


def mode(ir: IR) -> str:
    value = str(params(ir).get("scan") or "baseline")
    return value if value in SCRIPTS else "baseline"


def target_url(ir: IR) -> str:
    from ..ports import app_hostname
    url = str(params(ir).get("target_url") or "")
    if url:
        return url
    env = scanned_env(ir)
    return f"https://{app_hostname(ir.project, env)}" if env else ""


def blocking(ir: IR) -> bool:
    return params(ir).get("blocking") is True


def script(ir: IR) -> list[str]:
    extra = " -f openapi" if mode(ir) == "api" else ""
    return [
        # /zap/wrk : seul dossier où les scripts de ZAP lisent la configuration et écrivent les rapports
        f"mkdir -p /zap/wrk && cp {RULES_FILE} /zap/wrk/rules.tsv",
        f'code=0; {SCRIPTS[mode(ir)]} -t "$ZAP_TARGET_URL"{extra} -c rules.tsv -r {REPORTS[0]} -J {REPORTS[1]} -I '
        "|| code=$?",
        "cp " + " ".join(f"/zap/wrk/{r}" for r in REPORTS) + " . || true",
        'if [ "$code" -eq 3 ]; then echo "ZAP n\'a pas pu analyser $ZAP_TARGET_URL (adresse injoignable depuis la CI ?)" >&2; fi',
        'exit "$code"',
    ]


def add_step(ir: IR) -> None:
    """Insère le job ZAP juste après le déploiement de l'environnement analysé."""
    if not enabled(ir):
        return
    env = scanned_env(ir)
    url = target_url(ir)
    ir.add_var("ZAP_TARGET_URL", "Adresse analysée par ZAP (" + ("définition OpenAPI de l'API" if mode(ir) == "api"
               else "application déployée") + ")", secret=False, value=url)
    version = str(params(ir).get("version") or DEFAULT_VERSION)
    label = {"baseline": "scan de base", "full": "scan complet", "api": "scan d'API"}[mode(ir)]
    step = Step("dast", f"Analyse dynamique ZAP ({label})", "deploy", f"{IMAGE}:{version}", script(ir),
                tool="zap", main_only=True, allow_failure=not blocking(ir), artifacts=list(REPORTS),
                user="root", always_artifacts=True)
    deploy = next((s for s in ir.steps if s.stage == "deploy" and env is not None and s.environment == env.id), None)
    if ir.multi_env and env is not None:
        step.id = f"dast-{env.id}"
        step.name = f"{step.name} — {env.display}"
    if deploy is None:
        ir.steps.append(step)
        return
    step.needs = [deploy.id]
    index = ir.steps.index(deploy)
    ir.steps.insert(index + 1, step)
    following = next((s for s in ir.steps[index + 2:] if s.stage == "deploy" and s.environment), None)
    if following is not None and deploy.id in following.needs:
        following.needs = following.needs + [step.id]  # l'environnement suivant attend le résultat de l'analyse


def rules_tsv(ir: IR) -> str:
    lines = [
        "# Généré par DevOps Builder — à relire avant usage.",
        "# Règles de ZAP : identifiant<TAB>action<TAB>(intitulé). Actions : IGNORE, INFO, WARN, FAIL, OUTOFSCOPE.",
        "# Une règle absente reste à WARN (signalée, sans échec). FAIL fait échouer le job ; "
        + ("le pipeline s'arrête alors." if blocking(ir) else "le pipeline continue (brique non bloquante)."),
        "# Liste complète des règles : https://www.zaproxy.org/docs/alerts/",
        "# Faux positif : passer la règle à IGNORE ici, avec la raison en commentaire.",
    ]
    lines += [f"{rid}\tFAIL\t({title})" for rid, title in FAIL_RULES]
    return "\n".join(lines) + "\n"


def files(ir: IR) -> dict[str, str]:
    if not enabled(ir):
        return {}
    return {RULES_FILE: rules_tsv(ir)}


def notes(ir: IR) -> None:
    if not enabled(ir):
        return
    env = scanned_env(ir)
    where = f"l'environnement « {env.display} »" if env else "l'application"
    ir.notes.append(
        f"ZAP analyse {where} à l'adresse ZAP_TARGET_URL ({target_url(ir)}) après son déploiement ; rapport en "
        f"artefact du job ({REPORTS[0]}). L'adresse doit être joignable depuis les machines de la CI. "
        + ("Le job bloque la suite du pipeline quand une règle FAIL de .zap/rules.tsv est déclenchée."
           if blocking(ir) else "Le job signale sans bloquer ; paramètre « Bloquant » pour arrêter le pipeline."))
    if mode(ir) == "full" and env is not None and env.kind == "production":
        ir.notes.append("ZAP : le scan complet attaque l'application (injections, formulaires soumis) ; le lancer sur "
                        "la production peut altérer ses données. Analyser plutôt une préproduction.")
    if ".example.com" in target_url(ir):
        ir.notes.append("ZAP : adresse d'exemple en place ; renseigner « Adresse analysée » sur la brique ou par "
                        "environnement.")
