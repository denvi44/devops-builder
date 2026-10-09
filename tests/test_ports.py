"""Environnements Bac à sable et Recette, ports par environnement, hôte partagé."""

from __future__ import annotations

import shutil
import subprocess

import pytest
import yaml

from devops_builder.catalog import default_catalog
from devops_builder.generators import generate
from devops_builder.model import ENV_PRESETS, ENVIRONMENTS, Project, env_preset
from devops_builder.ports import conflicts, env_offset, known_ports, parametrized, port_plan
from devops_builder.rules import RuleEngine, apply_action

CATALOG = default_catalog()
ENGINE = RuleEngine(CATALOG)


def docker(*tools: str, preset: str = "prod", port: int = 8000) -> Project:
    p = Project(name="ports", target="docker-host", environments=env_preset(preset))
    for t in ("gitlab", "gitlab-ci", "buildkit", "harbor", "docker-compose", *tools):
        p.add(t, CATALOG[t].stage)
    p.app.port = port
    return p


def r39(p: Project):
    return [d for d in ENGINE.evaluate(p) if d.rule_id == "R39"]


# ------------------------------------------------------------------ environnements
def test_types_bac_a_sable_et_recette():
    assert list(ENVIRONMENTS) == ["sandbox", "dev", "recette", "staging", "production"]
    full = env_preset("complet")
    assert [e.kind for e in full] == list(ENVIRONMENTS) and full[-1].approval
    assert [e.id for e in env_preset("dev-recette-prod")] == ["dev", "recette", "production"]
    assert set(ENV_PRESETS) >= {"dev-recette-prod", "complet"}


@pytest.mark.parametrize("hosting", ["docker-host", "kubernetes", "kubernetes-managed"])
def test_chaine_complete_generee(hosting):
    from devops_builder.starter import StarterAnswers, build_starter
    cloud = "aws" if hosting == "kubernetes-managed" else None
    p = build_starter(StarterAnswers(hosting=hosting, cloud=cloud, envs="complet"), CATALOG)
    result = generate(p, CATALOG)
    ci = yaml.safe_load(result.files[".gitlab-ci.yml"])
    deploys = [k for k in ci if k.startswith("deploy-")]
    assert deploys == ["deploy-sandbox", "deploy-dev", "deploy-recette", "deploy-staging", "deploy-production"]
    assert ci["deploy-production"]["rules"][0]["when"] == "manual"
    if hosting != "docker-host":
        values = result.files.get("charts/mon-app/values-recette.yaml") or \
            result.files["deploy/kustomize/overlays/recette/kustomization.yaml"]
        assert "1" in values


def test_projet_sans_les_nouveaux_champs_inchange():
    p = docker()
    text = p.to_yaml()
    assert "host:" not in text and "port_offset" not in text      # lisible par la 0.5
    p.environments[0].host = "vm1"
    assert "host: vm1" in p.to_yaml()
    assert Project.from_yaml(p.to_yaml()).environments[0].host == "vm1"


# ------------------------------------------------------------------ plan des ports
def test_ports_visibles_sur_hote_docker():
    plan = port_plan(docker("prometheus", "grafana", "minio"), CATALOG)
    rows = {(e.component_id, e.container_port): e for e in plan}
    assert rows[("app", 8000)].host_port == 8000
    assert rows[("grafana", 3000)].usage == "interface web"
    assert rows[("minio", 9001)].usage == "console web"
    assert conflicts(plan) == []


def test_ports_avec_traefik_et_kubernetes():
    plan = port_plan(docker("traefik"), CATALOG)
    app = next(e for e in plan if e.component_id == "app")
    assert app.host_port is None and "Traefik" in app.exposure
    k = Project(name="k", target="kubernetes", environments=env_preset("dev-recette-prod"))
    for t in ("gitlab", "gitlab-ci", "buildkit", "harbor", "k3s", "helm", "grafana", "traefik"):
        k.add(t, CATALOG[t].stage)
    plan = port_plan(k, CATALOG)
    app = next(e for e in plan if e.component_id == "app" and e.env_id == "recette")
    assert "mon-app-recette" in app.exposure and "Traefik" in app.exposure
    assert any(e.component_id == "grafana" and "monitoring" in e.exposure for e in plan) or \
        any(e.component_id == "grafana" for e in plan)
    assert all(e.host_port is None for e in plan) and conflicts(plan) == []


def test_ports_connus_pour_des_fiches_existantes():
    assert set(known_ports()) <= set(CATALOG.tools)


# ------------------------------------------------------------------ conflits
def test_conflit_application_et_brique():
    p = docker("grafana", port=3000)
    (d,) = r39(p)
    assert "3000" in d.message and "Grafana" in d.message
    apply_action(p, d.actions[0], CATALOG)
    assert p.app.port == 3001 and r39(p) == []


def test_conflit_entre_deux_briques():
    p = docker("jaeger", "otel-collector")
    diags = r39(p)
    assert {d.message.split()[1] for d in diags} == {"4317", "4318"}
    apply_action(p, diags[0].actions[-1], CATALOG)
    assert "otel-collector" not in p.tool_ids() and r39(p) == []


def test_hote_partage_decale_les_ports():
    p = docker("traefik", "prometheus", preset="complet")
    for e in p.environments:
        e.host = "vm-hors-prod" if e.kind != "production" else ""
    assert [env_offset(p, e) for e in p.environments] == [0, 10000, 20000, 30000, 0]
    assert parametrized(p) and r39(p) == []
    p.environments[4].host = "vm-hors-prod"               # production rejoint l'hôte : elle garde 80/443
    assert env_offset(p, p.environments[4]) == 0 and env_offset(p, p.environments[0]) == 10000


def test_decalage_manuel_en_conflit():
    p = docker("prometheus", preset="dev-recette-prod")
    for e in p.environments:
        e.host = "vm"
    p.environments[1].port_offset = 0
    diags = r39(p)
    assert diags and any(a.op == "set_env" for a in diags[0].actions)
    fix = next(a for a in diags[0].actions if a.op == "set_env")
    apply_action(p, fix, CATALOG)
    assert r39(p) == []


def test_decalage_hors_plage():
    p = docker("jaeger", preset="dev-recette-prod")
    p.environments[0].host = p.environments[1].host = "vm"
    p.environments[1].port_offset = 60000
    assert any("au-delà" in d.message for d in r39(p))


def test_pas_de_conflit_entre_hotes_dedies():
    p = docker("grafana", preset="complet")      # chaque environnement sur son hôte
    assert r39(p) == [] and not parametrized(p)


# ------------------------------------------------------------------ génération
def test_fichiers_avec_hote_partage(tmp_path):
    p = docker("traefik", "grafana", preset="dev-recette-prod")
    p.environments[0].host = p.environments[1].host = "vm-hors-prod"
    result = generate(p, CATALOG)
    compose = yaml.safe_load(result.files["deploy/docker-compose.yml"])
    assert compose["services"]["grafana"]["ports"] == ["${PORT_GRAFANA_3000:-3000}:3000"]
    assert "${APP_HOST:-mon-app.example.com}" in compose["services"]["mon-app"]["labels"][1]
    recette = result.files["deploy/env/recette.env"]
    assert "PORT_GRAFANA_3000=13000" in recette and "PORT_TRAEFIK_443=10443" in recette
    assert "APP_HOST=mon-app-recette.example.com" in recette
    ci = result.files[".gitlab-ci.yml"]
    assert 'scp deploy/env/recette.env "$DEPLOY_HOST_RECETTE:/opt/mon-app-recette/.env"' in ci
    assert "## Ports" in result.files["PIPELINE.md"] and "13000" in result.files["PIPELINE.md"]
    if shutil.which("docker") and subprocess.run(["docker", "compose", "version"], capture_output=True).returncode == 0:
        result.write(tmp_path)
        (tmp_path / "deploy" / ".env").write_text(recette)
        out = subprocess.run(["docker", "compose", "-f", "deploy/docker-compose.yml", "config"], cwd=tmp_path,
                             capture_output=True, text=True)
        assert out.returncode == 0, out.stderr
        assert "published: \"13000\"" in out.stdout or "13000" in out.stdout


def test_ansible_copie_le_fichier_de_ports():
    p = docker("ansible", "grafana", preset="dev-recette-prod")
    p.target = "vm"
    p.environments[0].host = p.environments[1].host = "vm-hors-prod"
    result = generate(p, CATALOG)
    play = result.files["ansible/deploy.yml"]
    assert "deploy/env/{{ deploy_env }}.env" in play
    assert '-e "deploy_env=recette"' in result.files[".gitlab-ci.yml"]


def test_sans_hote_partage_fichiers_identiques_a_la_05():
    p = docker("grafana", preset="dev-recette-prod")
    files = generate(p, CATALOG).files
    assert not any(f.startswith("deploy/env/") for f in files)
    assert "- 3000:3000" in files["deploy/docker-compose.yml"]


def test_assistant_hote_partage():
    from devops_builder.starter import StarterAnswers, build_starter
    p = build_starter(StarterAnswers(hosting="docker-host", envs="complet", shared_host=True), CATALOG)
    assert [e.host for e in p.environments] == ["hors-production"] * 4 + [""]
    assert parametrized(p) and r39(p) == []
    k = build_starter(StarterAnswers(hosting="kubernetes", envs="complet", shared_host=True), CATALOG)
    assert all(not e.host for e in k.environments)
