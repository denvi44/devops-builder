# SPDX-License-Identifier: Apache-2.0
"""Dimensionnement : besoin calculé à partir des services Compose, type proposé, règle R52 et sa correction."""

from __future__ import annotations

from test_rules import CATALOG

from devops_builder.generators import generate, render
from devops_builder.model import Severity
from devops_builder.rules import RuleEngine, apply_action
from devops_builder.sizing import Capacity, HostNeed, capacity, compose_needs, host_needs, service_need, suggest, table
from devops_builder.starter import StarterAnswers, build_starter

ENGINE = RuleEngine(CATALOG)


def _vm(envs="prod", **answers):
    return build_starter(StarterAnswers(forge="github", hosting="docker-host", cloud="aws", envs=envs, **answers),
                         CATALOG)


def _r52(p):
    return [d for d in ENGINE.evaluate(p) if d.rule_id == "R52"]


def test_besoin_des_services():
    assert service_need("boutique", "${IMAGE:-ghcr.io/x/boutique:1}", "boutique").memory == table()["app"]["memory"]
    kc = service_need("keycloak", "quay.io/keycloak/keycloak:26.4", "app")
    assert kc.memory == 1250 and kc.sourced
    assert service_need("db", "postgres:17", "app").memory == 512
    assert service_need("zbx", "zabbix/zabbix-server-pgsql:alpine-7.4-latest", "app").memory == 512
    inconnu = service_need("x", "example.org/inconnu:1", "app")
    assert (inconnu.cpu, inconnu.memory) == (table()["unknown"]["cpu"], table()["unknown"]["memory"])


def test_taches_ponctuelles_et_profils_ignores():
    text = """services:
  app: {image: "${IMAGE}"}
  migrate: {image: "${IMAGE}", restart: "no"}
  adminer: {image: adminer, profiles: [outils]}
  postgresql: {image: "postgres:17"}
"""
    assert [s.name for s in compose_needs(text, "app")] == ["app", "postgresql"]


def test_un_hote_partage_porte_chaque_environnement():
    seul = HostNeed("p", ["production"], compose_needs("services:\n  db: {image: postgres:17}\n", "app"))
    deux = HostNeed("h", ["dev", "recette"], seul.services)
    system = table()["system"]["memory"]
    assert deux.memory - system == 2 * (seul.memory - system)


def test_capacites_connues_et_deduites():
    assert capacity("aws-ec2", "t3.medium") == Capacity("t3.medium", 2, 4)
    assert capacity("scaleway-instance", "POP2-2C-8G").memory == 8
    assert capacity("outscale-vm", "tinav7.c4r8p1") == Capacity("tinav7.c4r8p1", 4, 8)
    assert capacity("aws-ec2", "x9.inconnu") is None


def test_proposition_la_plus_petite_qui_suffit():
    need = HostNeed("p", ["production"], compose_needs("services:\n  kc: {image: quay.io/keycloak/keycloak:26}\n", "a"))
    for tool, rows in table()["instances"].items():
        caps = [Capacity(*r) for r in rows]
        assert caps == sorted(caps, key=lambda c: (c.memory, c.vcpu)), tool   # tableau ordonné
        best = suggest(tool, need)
        assert best is not None and best.memory * 1024 >= need.memory
        smaller = [c for c in caps if c.memory < best.memory]
        assert all(c.memory * 1024 < need.memory or c.vcpu * 1000 < need.cpu for c in smaller)


def test_regle_et_correction_en_un_clic():
    p = _vm()
    diags = _r52(p)
    assert len(diags) == 1 and diags[0].severity == Severity.WARNING and "t3.small" in diags[0].message
    action = diags[0].actions[0]
    assert action.op == "set_param" and action.args["value"] == "t3.medium"
    apply_action(p, action, CATALOG)
    assert p.bricks_for("aws-ec2")[0].params["instance_type"] == "t3.medium"
    assert not _r52(p)
    files, _ = render(p, CATALOG)
    assert 'instance_type          = "t3.medium"' in files["infra/terraform/main.tf"]


def test_correction_par_environnement_quand_les_machines_different():
    p = _vm(envs="staging-prod")
    diags = _r52(p)
    assert len(diags) == 2
    action = diags[0].actions[0]
    assert action.op == "set_override" and len(action.args["envs"]) == 1
    apply_action(p, action, CATALOG)
    env = p.env(action.args["envs"][0])
    assert env.overrides["aws-ec2"]["instance_type"] == action.args["value"]
    assert len(_r52(p)) == 1


def test_type_suffisant_sans_diagnostic_et_rapport():
    p = _vm()
    p.bricks_for("aws-ec2")[0].params["instance_type"] = "t3.large"
    assert not _r52(p)
    report = generate(p, CATALOG, ENGINE, allow_blocking=True).files["PIPELINE.md"]
    assert "## Dimensionnement" in report and "`t3.large` (2 vCPU, 8 Gio) | suffisant" in report


def test_hote_existant_besoin_seulement():
    p = build_starter(StarterAnswers(forge="gitlab", hosting="docker-host", envs="prod"), CATALOG)
    files, ir = render(p, CATALOG)
    needs = host_needs(ir, files)
    assert len(needs) == 1 and needs[0].tool is None and needs[0].chosen is None and not _r52(p)


def test_hors_hote_docker_rien():
    p = build_starter(StarterAnswers(forge="gitlab", hosting="kubernetes", envs="prod"), CATALOG)
    files, ir = render(p, CATALOG)
    assert host_needs(ir, files) == []
