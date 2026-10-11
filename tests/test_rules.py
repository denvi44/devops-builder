"""Un test par règle de la matrice (R00 à R24), plus les corrections."""

from __future__ import annotations

import pytest

from devops_builder.catalog import default_catalog
from devops_builder.model import Project, Severity
from devops_builder.rules import RuleEngine, apply_action, load_rules

CATALOG = default_catalog()
ENGINE = RuleEngine(CATALOG)


def make(target: str = "kubernetes", env: str = "production", **flags) -> Project:
    p = Project(name="test", target=target, environment=env)
    for k, v in flags.items():
        setattr(p, k, v)
    return p


def put(p: Project, *tool_ids: str) -> Project:
    for tid in tool_ids:
        p.add(tid, CATALOG[tid].stage)
    return p


def ids(p: Project) -> dict[str, Severity]:
    return {d.rule_id: d.severity for d in ENGINE.evaluate(p)}


# (règle, projet qui la déclenche, gravité attendue)
CASES = [
    ("R00", lambda: put(make(), "lsc-backstage" if "lsc-backstage" in CATALOG else next(
        t.id for t in CATALOG.tools.values() if not t.curated)), Severity.INFO),
    ("R01", lambda: put(make("docker-host"), "argo-cd"), Severity.BLOCKING),
    ("R02", lambda: put(make(), "argo-cd", "flux"), Severity.BLOCKING),
    ("R03", lambda: put(make(), "istio", "linkerd"), Severity.BLOCKING),
    ("R04", lambda: put(make(), "cilium", "calico"), Severity.BLOCKING),
    ("R05", lambda: put(make("kubernetes-managed"), "aws", "eks", "k3s"), Severity.BLOCKING),
    ("R06", lambda: put(make(), "gitlab", "github-actions"), Severity.BLOCKING),
    ("R07", lambda: put(make(), "thanos"), Severity.BLOCKING),
    ("R08", lambda: put(make(), "velero"), Severity.BLOCKING),
    ("R09", lambda: put(make(), "ecr"), Severity.BLOCKING),
    ("R10", lambda: put(make(), "aws", "app-mesh"), Severity.BLOCKING),
    ("R11", lambda: put(make(), "gcp", "gcr"), Severity.BLOCKING),
    ("R12", lambda: put(make(secnumcloud=True), "aws", "eks"), Severity.BLOCKING),
    ("R13", lambda: put(make(), "ingress-nginx"), Severity.WARNING),
    ("R14", lambda: put(make(), "kaniko"), Severity.WARNING),
    ("R15", lambda: put(make(), "kyverno", "gatekeeper"), Severity.WARNING),
    ("R16", lambda: put(make(), "terraform", "opentofu"), Severity.WARNING),
    ("R17", lambda: put(make("kubernetes"), "docker-compose"), Severity.WARNING),
    ("R18", lambda: put(make("kubernetes", "production"), "kind"), Severity.WARNING),
    ("R19", lambda: put(make(env="production"), "jaeger"), Severity.WARNING),
    ("R20", lambda: put(make("kubernetes-managed"), "aws", "gcp", "eks", "artifact-registry"),
     Severity.WARNING),
    ("R21", lambda: put(make(cloud_auth="static"), "azure"), Severity.WARNING),
    ("R22", lambda: put(make(), "gitea", "github-actions"), Severity.WARNING),
    ("R23", lambda: put(make(), "harbor", "trivy"), Severity.INFO),
    ("R24", lambda: put(make(), "terraform"), Severity.INFO),
    ("R25", lambda: _misplaced("traefik", "test"), Severity.BLOCKING),
    ("R26", lambda: put(make("docker-host"), "github", "github-actions", "buildkit"), Severity.BLOCKING),
    ("R27", lambda: put(make("docker-host"), "gitlab", "gitlab-ci", "docker-compose"), Severity.WARNING),
    ("R28", lambda: put(make("docker-host"), "docker-compose"), Severity.BLOCKING),
    ("R29", lambda: put(make(), "kubeadm"), Severity.BLOCKING),
    ("R30", lambda: put(make("kubernetes-managed"), "helm"), Severity.WARNING),
    ("R31", lambda: put(make(), "packer"), Severity.INFO),
    ("R32", lambda: _with_params("eks", region="Paris"), Severity.BLOCKING),
    ("R33", lambda: _with_params("eks", clustr_name="prod"), Severity.WARNING),
    ("R34", lambda: _with_params("eks"), Severity.WARNING),
    ("R35", lambda: _envs("staging-prod", approval=False), Severity.WARNING),
    ("R36", lambda: put(_envs("dev-staging-prod"), "aws", "eks", "kind"), Severity.BLOCKING),
    ("R37", lambda: _envs(None), Severity.BLOCKING),
    ("R38", lambda: _ecs_collision(), Severity.BLOCKING),
    ("R39", lambda: _port_clash(), Severity.BLOCKING),
    ("R40", lambda: put(make(), "k3s", "helm", "cloudnative-pg"), Severity.WARNING),
    ("R41", lambda: put(make(), "k3s", "helm", "postgresql"), Severity.WARNING),
    ("R42", lambda: put(make("docker-host"), "docker-compose", "postgresql", "mariadb"), Severity.WARNING),
    ("R43", lambda: put(make("docker-host"), "docker-compose", "valkey", "redis"), Severity.WARNING),
    ("R44", lambda: put(make("kubernetes-managed"), "gitlab", "gitlab-ci", "scaleway", "kapsule", "opentofu"),
     Severity.WARNING),
]


def _port_clash() -> Project:
    p = put(make("docker-host"), "gitlab", "gitlab-ci", "buildkit", "harbor", "docker-compose", "grafana")
    p.app.port = 3000
    return p


def _envs(preset: str | None, approval: bool = True, target: str = "kubernetes-managed") -> Project:
    from devops_builder.model import env_preset
    p = make(target)
    p.environments = env_preset(preset) if preset else []
    for e in p.environments:
        if e.kind == "production":
            e.approval = approval
    return p


def _ecs_collision() -> Project:
    p = put(_envs("staging-prod", target="docker-host"), "aws", "ecs-fargate")
    p.environments[0].overrides = {"ecs-fargate": {"service": "commandes"}}
    p.environments[1].overrides = {"ecs-fargate": {"service": "commandes"}}
    return p


def _with_params(tool_id: str, **params) -> Project:
    p = put(make("kubernetes-managed"), "aws", tool_id)
    p.bricks_for(tool_id)[0].params = dict(params)
    return p


def _misplaced(tool_id: str, stage: str) -> Project:
    p = make()
    p.add(tool_id, stage)  # contourne l'interface, comme un fichier édité à la main
    return p


def test_toutes_les_regles_ont_un_cas():
    assert {r.id for r in load_rules()} == {c[0] for c in CASES}


@pytest.mark.parametrize("rule_id,build,severity", CASES, ids=[c[0] for c in CASES])
def test_regle_declenchee(rule_id, build, severity):
    found = ids(build())
    assert rule_id in found, f"{rule_id} attendu, obtenu {sorted(found)}"
    assert found[rule_id] is severity


@pytest.mark.parametrize("rule_id,build,severity", CASES, ids=[c[0] for c in CASES])
def test_chaque_correction_est_applicable(rule_id, build, severity):
    project = build()
    for diag in ENGINE.evaluate(project):
        for action in diag.actions:
            copy = project.clone()
            apply_action(copy, action, CATALOG)  # ne doit pas lever


def test_pipeline_propre_sans_diagnostic():
    p = put(make("docker-host"), "gitlab", "gitlab-ci", "buildkit", "unit-tests", "trivy",
            "harbor", "opentofu", "ansible", "docker-compose", "traefik", "prometheus", "grafana")
    blocking = [d for d in ENGINE.evaluate(p) if d.severity is Severity.BLOCKING]
    assert blocking == []


def test_r22_ne_bloque_pas_gitea():
    found = ids(put(make(), "gitea", "github-actions"))
    assert "R06" not in found and "R22" in found


def test_r01_resolu_en_ajoutant_k3s():
    p = put(make("vm"), "argo-cd")
    diag = next(d for d in ENGINE.evaluate(p) if d.rule_id == "R01")
    add_k3s = next(a for a in diag.actions if a.op == "add_brick")
    apply_action(p, add_k3s, CATALOG)
    assert "R01" not in ids(p)


def test_r01_resolu_par_remplacement():
    p = put(make("docker-host"), "argo-cd")
    diag = next(d for d in ENGINE.evaluate(p) if d.rule_id == "R01")
    swap = next(a for a in diag.actions if a.op == "replace_brick" and a.args["tool"] == "docker-compose")
    apply_action(p, swap, CATALOG)
    assert "argo-cd" not in p.tool_ids() and "docker-compose" in p.tool_ids()
    assert "R01" not in ids(p)


def test_r09_resolu_en_ajoutant_le_fournisseur():
    p = put(make(), "ecr")
    diag = next(d for d in ENGINE.evaluate(p) if d.rule_id == "R09")
    apply_action(p, diag.actions[0], CATALOG)
    assert "aws" in p.tool_ids() and "R09" not in ids(p)


def test_licence_politique_oss_only_devient_avertissement():
    p = put(make(license_policy="oss-only"), "snyk")
    assert ids(p).get("R24") is Severity.WARNING


def test_ovhcloud_partiel_non_bloque_en_secnumcloud():
    p = put(make("kubernetes-managed", secnumcloud=True), "ovhcloud", "ovh-mks")
    assert "R12" not in ids(p)


def test_r25_correction_deplace_vers_une_etape_autorisee():
    p = _misplaced("argo-cd", "source")
    diag = next(d for d in ENGINE.evaluate(p) if d.rule_id == "R25")
    move = next(a for a in diag.actions if a.op == "move_brick")
    apply_action(p, move, CATALOG)
    assert p.stages["deploy"][0].tool == "argo-cd"
    assert "R25" not in ids(p)


def test_etapes_secondaires_acceptees():
    p = make("vm")
    p.add("ansible", "deploy")
    p.add("trivy", "test")
    p.add("cosign", "artifacts")
    assert "R25" not in ids(p)


def test_toutes_les_fiches_ont_des_etapes_valides():
    for t in CATALOG.tools.values():
        assert t.stage in t.allowed_stages
        assert t.can_go_in(t.stage)


def test_exemples_bien_places():
    from pathlib import Path
    for path in (Path(__file__).parents[1] / "devops_builder" / "data" / "examples").glob("*.yaml"):
        assert "R25" not in ids(Project.load(path)), path.name


# ---------------------------------------------------------------- complétude
def _diag(p, rule_id):
    return next(d for d in ENGINE.evaluate(p) if d.rule_id == rule_id)


def test_r26_registre_integre_de_gitlab():
    assert "R26" not in ids(put(make("docker-host"), "gitlab", "gitlab-ci", "buildkit"))


def test_r26_propose_le_registre_du_cloud_present():
    d = _diag(put(make("kubernetes-managed"), "github", "github-actions", "buildkit", "gcp"), "R26")
    assert d.actions[0].args["tool"] == "artifact-registry"


def test_r28_propose_la_ci_native_de_la_forge():
    d = _diag(put(make("docker-host"), "gitea", "docker-compose"), "R28")
    assert d.actions[0].args["tool"] == "gitea-actions"
    apply_action(p := put(make("docker-host"), "gitea", "docker-compose"), _diag(p, "R28").actions[0], CATALOG)
    assert "R28" not in ids(p)


def test_r29_propose_la_forge_compatible_avec_la_ci():
    d = _diag(put(make(), "gitlab-ci"), "R29")
    assert d.actions[0].args["tool"] == "gitlab"


def test_r29_ne_double_pas_les_regles_dediees():
    found = [d.rule_id for d in ENGINE.evaluate(put(make(), "thanos"))]
    assert found.count("R07") == 1
    assert "R29" in found  # Thanos exige aussi un stockage objet, non couvert par R07


def test_r30_cluster_manage_et_cible_autogeree():
    d = _diag(put(make("kubernetes"), "aws", "eks"), "R30")
    apply_action(p := put(make("kubernetes"), "aws", "eks"), d.actions[0], CATALOG)
    assert p.target == "kubernetes-managed"


def test_r31_disparait_quand_un_fichier_est_produit():
    sans_eks = put(make("kubernetes-managed"), "gitlab", "gitlab-ci", "aws", "opentofu", "cloudwatch")
    assert ids(sans_eks).get("R31") is Severity.INFO
    avec_eks = put(make("kubernetes-managed"), "gitlab", "gitlab-ci", "aws", "opentofu", "eks", "cloudwatch")
    assert "R31" not in ids(avec_eks)  # module complémentaire EKS généré


# ---------------------------------------------------------------- paramètres
def test_r33_renommer_la_cle():
    p = _with_params("eks", clustr_name="prod")
    d = _diag(p, "R33")
    apply_action(p, d.actions[0], CATALOG)
    assert p.bricks_for("eks")[0].params == {"cluster_name": "prod"}
    assert "R33" not in ids(p)


def test_r32_valeur_deduite_du_projet():
    p = put(make("kubernetes-managed"), "gcp", "artifact-registry")
    p.app.image_name = "Mon_App"
    assert ids(p).get("R32") is Severity.BLOCKING


def test_r32_url_avec_schema_refusee():
    p = put(make(), "harbor")
    p.bricks_for("harbor")[0].params = {"url": "https://registry.example.com"}
    assert "nom d'hôte" in _diag(p, "R32").message


def test_r34_disparait_quand_renseigne():
    p = _with_params("eks", cluster_name="prod")
    assert "R34" not in ids(p) and "R32" not in ids(p)


# ------------------------------------------------------------- environnements
def test_cluster_de_dev_et_cluster_de_prod_rattaches():
    p = put(_envs("dev-staging-prod"), "aws", "eks", "kind")
    for e in p.environments:
        e.cluster = "kind" if e.kind == "dev" else "eks"
    found = ids(p)
    assert not {"R05", "R18", "R30", "R36"} & set(found), found


def test_r18_kind_servant_la_production():
    p = put(_envs("dev-staging-prod", target="kubernetes"), "kind")
    assert ids(p).get("R18") is Severity.WARNING


def test_r05_propose_de_creer_des_environnements():
    p = put(make("kubernetes-managed"), "aws", "eks", "kind")
    d = next(d for d in ENGINE.evaluate(p) if d.rule_id == "R05")
    preset = next(a for a in d.actions if a.op == "set_project")
    apply_action(p, preset, CATALOG)
    assert [e.id for e in p.environments] == ["dev", "staging", "production"]
    found = ids(p)
    assert "R05" not in found and "R36" in found  # reste à rattacher chaque environnement


def test_r36_correction_rattache_le_cluster():
    p = put(_envs("staging-prod"), "aws", "eks", "kind")
    for d in [d for d in ENGINE.evaluate(p) if d.rule_id == "R36"]:
        apply_action(p, d.actions[0], CATALOG)
    assert all(e.cluster for e in p.environments)


def test_r35_correction_active_l_approbation():
    p = _envs("staging-prod", approval=False)
    d = next(d for d in ENGINE.evaluate(p) if d.rule_id == "R35")
    apply_action(p, d.actions[0], CATALOG)
    assert p.env("production").approval is True


def test_surcharge_inconnue_par_environnement():
    p = put(_envs("staging-prod"), "aws", "eks")
    p.env("staging").overrides = {"eks": {"clustr_name": "preprod"}}
    d = next(d for d in ENGINE.evaluate(p) if d.rule_id == "R33")
    assert "Préproduction" in d.message
    apply_action(p, d.actions[0], CATALOG)
    assert p.env("staging").overrides == {"eks": {"cluster_name": "preprod"}}


def test_suffixe_automatique_evite_les_collisions():
    p = put(_envs("dev-staging-prod", target="docker-host"), "aws", "ecs-fargate")
    assert "R38" not in ids(p)


def test_identifiants_d_environnement():
    from devops_builder.model import Environment
    p = make()
    p.environments = [Environment(id="Prod", kind="production"), Environment(id="Prod", kind="production")]
    msgs = [d.message for d in ENGINE.evaluate(p) if d.rule_id == "R37"]
    assert any("invalide" in m for m in msgs) and any("deux fois" in m for m in msgs)
