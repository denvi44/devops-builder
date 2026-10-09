"""Modèle de données : fiches outils, projet, pipeline.

Tout est sérialisable en YAML pour que le format `.devops.yaml` reste lisible
et versionnable sans l'application.
"""

from __future__ import annotations

import uuid
from enum import Enum
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

FORMAT_VERSION = 2

# --------------------------------------------------------------------------
# Étapes du pipeline (colonnes de l'interface), dans l'ordre d'exécution.
# --------------------------------------------------------------------------
STAGES: list[tuple[str, str]] = [
    ("source", "Source"),
    ("build", "Build"),
    ("test", "Tests & qualité"),
    ("security", "Sécurité"),
    ("artifacts", "Artefacts"),
    ("infrastructure", "Infrastructure"),
    ("deploy", "Déploiement"),
    ("platform", "Plateforme"),
    ("observability", "Observabilité"),
]
STAGE_IDS = [s for s, _ in STAGES]
STAGE_LABELS = dict(STAGES)

TARGETS: dict[str, str] = {
    "docker-host": "Hôte Docker unique",
    "vm": "Machines virtuelles (Ansible)",
    "kubernetes": "Kubernetes autogéré",
    "kubernetes-managed": "Kubernetes managé (cloud)",
}
ENVIRONMENTS: dict[str, str] = {  # types d'environnement, du moins au plus exposé
    "sandbox": "Bac à sable",
    "dev": "Développement",
    "recette": "Recette",
    "staging": "Préproduction",
    "production": "Production",
}
EnvKind = Literal["sandbox", "dev", "recette", "staging", "production"]
PORT_OFFSET_STEP = 10000  # décalage des ports entre environnements d'un même hôte
ENV_ID_PATTERN = r"[a-z][a-z0-9-]{0,19}"
LANGUAGES: dict[str, str] = {
    "python": "Python",
    "node": "Node.js",
    "java": "Java (Maven)",
    "go": "Go",
    "dotnet": ".NET",
    "other": "Autre",
}

# Licences considérées comme open source (OSI) pour le filtrage.
OSS_LICENSES = {
    "Apache-2.0", "MIT", "BSD-2-Clause", "BSD-3-Clause", "MPL-2.0", "GPL-2.0",
    "GPL-3.0", "LGPL-3.0", "AGPL-3.0", "EPL-2.0", "ISC", "LGPL-2.1",
}


class Severity(str, Enum):
    BLOCKING = "bloquant"
    WARNING = "avertissement"
    INFO = "info"

    @property
    def rank(self) -> int:
        return {"bloquant": 0, "avertissement": 1, "info": 2}[self.value]

    @property
    def label(self) -> str:
        return {"bloquant": "Bloquant", "avertissement": "Avertissement", "info": "Info"}[self.value]


class ParamSpec(BaseModel):
    """Description d'un paramètre de brique, pour le formulaire et la validation."""

    model_config = ConfigDict(extra="forbid")

    label: str
    type: Literal["string", "int", "bool"] = "string"
    description: str = ""
    # Vraie valeur par défaut, légitime en production. « {app} » = nom de l'image du projet.
    default: Any = None
    # Valeur d'exemple écrite dans les fichiers si rien n'est saisi ; signalée par R34.
    example: str | None = None
    required: bool = False
    choices: list[str] = Field(default_factory=list)       # liste fermée
    suggestions: list[str] = Field(default_factory=list)   # liste ouverte
    pattern: str | None = None
    pattern_hint: str = ""
    max_length: int | None = None
    # Cible de déploiement propre à chaque environnement : sans surcharge, la valeur
    # reçoit le suffixe « -<environnement> » (sauf pour l'environnement de production).
    per_env: bool = False


class LandscapeRef(BaseModel):
    category: str | None = None
    subcategory: str | None = None
    maturity: str | None = None  # graduated | incubating | sandbox | archived | None
    repo_url: str | None = None


class Tool(BaseModel):
    """Fiche d'un outil, d'un service managé ou d'un fournisseur cloud."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    kind: Literal["tool", "provider", "service"] = "tool"
    stage: str
    roles: list[str] = Field(default_factory=list)
    description: str = ""
    homepage: str | None = None
    license: str = "Apache-2.0"
    # Dépôt source, s'il n'est pas déjà connu par le Landscape ; "" = brique générique sans dépôt
    repo: str | None = None
    # Où l'outil peut tourner : kubernetes, docker-host, vm, saas, ci, cli
    hosting: list[str] = Field(default_factory=lambda: ["docker-host", "vm", "kubernetes"])
    provides: list[str] = Field(default_factory=list)
    requires: list[str] = Field(default_factory=list)
    # Forges auxquelles un CI est lié (vide = toutes)
    forges: list[str] = Field(default_factory=list)
    # Pour une forge : identifiant de forge et CI compatibles par syntaxe
    forge: str | None = None
    compatible_ci: list[str] = Field(default_factory=list)
    # Service managé : fournisseur cloud requis
    provider: str | None = None
    # Fournisseur : provider Terraform, auth, services par rôle, souveraineté
    terraform_provider: str | None = None
    auth: list[str] = Field(default_factory=list)
    services: dict[str, str] = Field(default_factory=dict)
    secnumcloud: Literal["yes", "no", "partial", "unknown"] | None = None
    # Cycle de vie
    lifecycle: Literal["active", "maintenance-ended", "archived", "discontinued"] = "active"
    lifecycle_note: str = ""
    replacements: list[str] = Field(default_factory=list)
    # Équivalents hors Kubernetes proposés par le résolveur
    alternatives_outside_k8s: list[str] = Field(default_factory=list)
    # Alternatives open source (licences BSL / propriétaires)
    alternatives: list[str] = Field(default_factory=list)
    dev_only: bool = False
    landscape_name: str | None = None
    landscape: LandscapeRef | None = None
    curated: bool = True
    verified: str | None = None  # date de vérification de la fiche
    origin: Literal["livrée", "utilisateur"] = "livrée"  # fiche de l'application ou du catalogue personnel
    corrections: dict[str, Any] = Field(default_factory=dict)  # valeurs d'origine remplacées par une correction
    params: dict[str, Any] = Field(default_factory=dict)  # paramètres par défaut
    param_schema: dict[str, ParamSpec] = Field(default_factory=dict)
    # Étapes où l'outil peut aussi être posé, en plus de `stage` (étape principale).
    extra_stages: list[str] = Field(default_factory=list)

    @property
    def allowed_stages(self) -> list[str]:
        """Étapes autorisées, dans l'ordre du pipeline, étape principale incluse."""
        allowed = {self.stage, *self.extra_stages}
        return [s for s in STAGE_IDS if s in allowed]

    def can_go_in(self, stage: str) -> bool:
        return stage == self.stage or stage in self.extra_stages

    @property
    def is_oss(self) -> bool:
        return self.license in OSS_LICENSES

    @property
    def repo_url(self) -> str | None:
        """Dépôt à surveiller : celui de la fiche, sinon celui du Landscape."""
        if self.repo is not None:
            return self.repo or None
        return self.landscape.repo_url if self.landscape else None

    @property
    def kubernetes_only(self) -> bool:
        return set(self.hosting) == {"kubernetes"}


class BrickInstance(BaseModel):
    """Une brique posée dans une étape du pipeline."""

    uid: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    tool: str
    params: dict[str, Any] = Field(default_factory=dict)


class AppSettings(BaseModel):
    language: str = "python"
    image_name: str = "mon-app"
    port: int = 8000


class Environment(BaseModel):
    """Environnement de déploiement ; l'ordre de la liste est l'ordre de promotion."""

    model_config = ConfigDict(extra="forbid")

    id: str
    label: str = ""
    kind: EnvKind = "production"
    approval: bool = False          # déploiement soumis à une approbation manuelle
    cluster: str | None = None      # brique cluster utilisée (obligatoire s'il y en a plusieurs)
    # Hôte Docker partagé : les environnements qui indiquent le même nom se partagent ses ports
    host: str = ""
    port_offset: int | None = None  # décalage des ports publiés ; None = automatique
    overrides: dict[str, dict[str, Any]] = Field(default_factory=dict)  # outil -> paramètres

    @property
    def display(self) -> str:
        return self.label or ENVIRONMENTS[self.kind]


def env_preset(name: str) -> list[Environment]:
    """Jeux d'environnements proposés par l'assistant et l'éditeur."""
    if name == "prod":
        return [Environment(id="production", kind="production")]
    if name == "staging-prod":
        return [Environment(id="staging", kind="staging"),
                Environment(id="production", kind="production", approval=True)]
    if name == "dev-staging-prod":
        return [Environment(id="dev", kind="dev"), Environment(id="staging", kind="staging"),
                Environment(id="production", kind="production", approval=True)]
    if name == "dev-recette-prod":
        return [Environment(id="dev", kind="dev"), Environment(id="recette", kind="recette"),
                Environment(id="production", kind="production", approval=True)]
    if name == "complet":
        return [Environment(id="sandbox", kind="sandbox"), Environment(id="dev", kind="dev"),
                Environment(id="recette", kind="recette"), Environment(id="staging", kind="staging"),
                Environment(id="production", kind="production", approval=True)]
    raise ValueError(name)


ENV_PRESETS = {
    "prod": "Production seule",
    "staging-prod": "Préproduction → production",
    "dev-staging-prod": "Développement → préproduction → production",
    "dev-recette-prod": "Développement → recette → production",
    "complet": "Bac à sable → développement → recette → préproduction → production",
}


class Project(BaseModel):
    format_version: int = FORMAT_VERSION
    name: str = "Nouveau projet"
    description: str = ""
    target: str = "docker-host"
    environments: list[Environment] = Field(default_factory=lambda: env_preset("prod"))
    secnumcloud: bool = False
    cloud_auth: Literal["oidc", "static"] = "oidc"
    license_policy: Literal["any", "oss-only"] = "any"
    app: AppSettings = Field(default_factory=AppSettings)
    stages: dict[str, list[BrickInstance]] = Field(
        default_factory=lambda: {s: [] for s in STAGE_IDS}
    )

    @model_validator(mode="before")
    @classmethod
    def _migrate(cls, data: Any) -> Any:
        """Format 1 : un seul champ « environment » → liste d'environnements."""
        if isinstance(data, dict) and "environment" in data:
            data = dict(data)
            kind = data.pop("environment") or "production"
            data.setdefault("environments", [{"id": kind, "kind": kind}])
            data["format_version"] = FORMAT_VERSION
        return data

    # ----------------------------------------------------------- environnements
    @property
    def environment(self) -> str:
        """Type d'environnement le plus exposé (compatibilité : règles « en production »)."""
        kinds = {e.kind for e in self.environments}
        for k in reversed(ENVIRONMENTS):
            if k in kinds:
                return k
        return "production"

    def env(self, env_id: str) -> Environment | None:
        return next((e for e in self.environments if e.id == env_id), None)

    @property
    def multi_env(self) -> bool:
        return len(self.environments) > 1

    def env_suffix(self, env: Environment) -> str:
        """Suffixe des cibles de déploiement : aucun pour l'unique environnement de production."""
        if not self.multi_env:
            return ""
        prods = [e for e in self.environments if e.kind == "production"]
        if env.kind == "production" and len(prods) == 1:
            return ""
        return f"-{env.id}"

    # ------------------------------------------------------------------ helpers
    def ensure_stages(self) -> None:
        for s in STAGE_IDS:
            self.stages.setdefault(s, [])

    def all_bricks(self) -> list[tuple[str, BrickInstance]]:
        self.ensure_stages()
        return [(s, b) for s in STAGE_IDS for b in self.stages.get(s, [])]

    def tool_ids(self) -> set[str]:
        return {b.tool for _, b in self.all_bricks()}

    def find(self, uid: str) -> tuple[str, int, BrickInstance] | None:
        for s in STAGE_IDS:
            for i, b in enumerate(self.stages.get(s, [])):
                if b.uid == uid:
                    return s, i, b
        return None

    def bricks_for(self, tool_id: str) -> list[BrickInstance]:
        return [b for _, b in self.all_bricks() if b.tool == tool_id]

    def add(self, tool_id: str, stage: str, index: int | None = None, **params: Any) -> BrickInstance:
        self.ensure_stages()
        brick = BrickInstance(tool=tool_id, params=dict(params))
        lst = self.stages[stage]
        lst.insert(len(lst) if index is None else index, brick)
        return brick

    def remove(self, uid: str) -> BrickInstance | None:
        found = self.find(uid)
        if not found:
            return None
        stage, idx, brick = found
        del self.stages[stage][idx]
        return brick

    def move(self, uid: str, stage: str, index: int | None = None) -> None:
        brick = self.remove(uid)
        if brick is None:
            return
        lst = self.stages[stage]
        lst.insert(len(lst) if index is None else min(index, len(lst)), brick)

    # -------------------------------------------------------------- persistence
    def to_yaml(self) -> str:
        data = self.model_dump(mode="json")
        for env in data.get("environments", []):
            # champs ajoutés en 0.6 : omis quand ils ne servent pas, le fichier reste lisible par la 0.5
            for key, default in (("host", ""), ("port_offset", None)):
                if env.get(key) == default:
                    env.pop(key, None)
        return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)

    @classmethod
    def from_yaml(cls, text: str) -> Project:
        data = yaml.safe_load(text) or {}
        project = cls.model_validate(data)
        project.ensure_stages()
        return project

    def save(self, path: str | Path) -> None:
        Path(path).write_text(self.to_yaml(), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> Project:
        return cls.from_yaml(Path(path).read_text(encoding="utf-8"))

    def clone(self) -> Project:
        return Project.model_validate(self.model_dump())
