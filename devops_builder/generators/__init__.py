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


def generate(project: Project, catalog: Catalog, engine: RuleEngine | None = None,
             allow_blocking: bool = False) -> GenerationResult:
    from . import ci, deploy, iac, platform, report

    engine = engine or RuleEngine(catalog)
    diagnostics = engine.evaluate(project)
    blocking = RuleEngine.blocking(diagnostics)
    if blocking and not allow_blocking:
        raise BlockingDiagnostics(blocking)

    ir = build_ir(project, catalog)
    files: dict[str, str] = {}
    if ir.ci and ir.ci.id in ci.RENDERERS:
        files.update(ci.RENDERERS[ir.ci.id](ir))
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
    files.update(report.report(ir, diagnostics, list(files) + ["PIPELINE.md", "devops-builder.yaml"]))
    files["devops-builder.yaml"] = project.to_yaml()
    return GenerationResult(files=files, ir=ir, diagnostics=diagnostics)
