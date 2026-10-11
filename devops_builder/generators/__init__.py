"""Point d'entrée des générateurs : projet → fichiers prêts à committer."""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from ..catalog import Catalog
from ..ir import IR, build_ir
from ..model import Project
from ..rules import Diagnostic, RuleEngine


class BlockingDiagnostics(Exception):
    def __init__(self, diagnostics: list[Diagnostic]):
        self.diagnostics = diagnostics
        super().__init__(f"{len(diagnostics)} erreur(s) bloquante(s)")


@dataclass
class GenerationResult:
    files: dict[str, str]
    ir: IR
    diagnostics: list[Diagnostic] = field(default_factory=list)

    def write(self, directory: str | Path) -> list[Path]:
        root = Path(directory)
        written = []
        for rel, content in self.files.items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            if rel.endswith(".sh"):
                path.chmod(0o755)
            written.append(path)
        return written

    def zip_bytes(self) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for rel, content in sorted(self.files.items()):
                zf.writestr(rel, content)
        return buf.getvalue()


def render(project: Project, catalog: Catalog) -> tuple[dict[str, str], IR]:
    """Produit les fichiers sans évaluer les règles ; renseigne ir.covered et ir.unsupported.

    Utilisé par generate() et par la règle R31 : le rapport et le diagnostic
    disent donc exactement la même chose.
    """
    from . import ci, civars, data, deploy, extras, floci, hosts, iac, localtest, platform

    ir = build_ir(project, catalog)
    files: dict[str, str] = {}
    if ir.ci and ir.ci.id in ci.RENDERERS:
        files.update(ci.RENDERERS[ir.ci.id](ir))
        ir.cover(ir.ci.id, *(st.tool for st in ir.steps))
        for st in ir.steps:
            ir.cover(*st.cloud)
    if ir.forge:
        ir.cover(ir.forge.id)  # brique de contexte : elle oriente CI, registre et GitOps
    if ir.has("docker-compose"):
        files.update(deploy.compose(ir))
    if ir.has("helm"):
        files.update(deploy.helm_chart(ir))
    if ir.has("kustomize") or ((ir.has("argo-cd") or ir.has("flux")) and not ir.has("helm")):
        files.update(deploy.kustomize(ir))
    if ir.has("argo-cd"):
        files.update(deploy.argo_cd(ir))
    if ir.has("flux"):
        files.update(deploy.flux(ir))
    if ir.has("ansible"):
        files.update(deploy.ansible(ir))
    if ir.iac and ir.iac.id in ("terraform", "opentofu") or ir.providers:
        files.update(iac.terraform(ir))
    files.update(platform.platform_files(ir))
    files.update(floci.floci_files(ir))
    files.update(hosts.inventory_script(ir))
    data.notes(ir)
    files.update(extras.renovate(ir))
    files.update(extras.dependabot(ir))
    files.update(extras.clusters(ir))
    files.update(localtest.kind_test(ir, files))
    files.update(civars.ci_variables(ir))
    if ir.registry and files:
        ir.cover(ir.registry.id)  # sa référence d'image est écrite dans la CI ou le déploiement
    seen: set[str] = set()
    for _, b in project.all_bricks():
        tool = catalog.get(b.tool)
        if tool and tool.id not in ir.covered and tool.id not in seen:
            ir.unsupported.append(tool)
            seen.add(tool.id)
    return files, ir


def generate(project: Project, catalog: Catalog, engine: RuleEngine | None = None,
             allow_blocking: bool = False) -> GenerationResult:
    from . import report

    engine = engine or RuleEngine(catalog)
    diagnostics = engine.evaluate(project)
    blocking = RuleEngine.blocking(diagnostics)
    if blocking and not allow_blocking:
        raise BlockingDiagnostics(blocking)
    files, ir = render(project, catalog)
    files.update(report.report(ir, diagnostics, list(files) + ["PIPELINE.md", "devops-builder.yaml"]))
    files["devops-builder.yaml"] = project.to_yaml()
    return GenerationResult(files=files, ir=ir, diagnostics=diagnostics)
