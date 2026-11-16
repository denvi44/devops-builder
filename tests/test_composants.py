# SPDX-License-Identifier: Apache-2.0
"""Plusieurs applications dans un projet : une image par composant, un pipeline, un déploiement."""

from __future__ import annotations

import os

import pytest
import yaml
from test_data import CATALOG, COMPOSE, ENGINE, K3S_HELM, files_of, project

from devops_builder.comparaison import compare
from devops_builder.generators import generate
from devops_builder.model import Component, Project
from devops_builder.ports import port_plan


def multi(target: str, *tools: str, envs: str = "prod") -> Project:
    p = project(target, *tools, envs=envs)
    p.components = [Component(id="api", language="go", port=9000, public=True),
                    Component(id="worker", language="python")]
    return p


def rules(p: Project) -> dict[str, str]:
    return {d.rule_id: d.message for d in ENGINE.evaluate(p)}


def test_format_sans_composant_inchange():
    assert "components" not in project("docker-host", *COMPOSE).to_yaml()


def test_aller_retour_du_fichier_projet():
    p = multi("docker-host", *COMPOSE)
    back = Project.from_yaml(p.to_yaml())
    assert [(c.id, c.language, c.port, c.public) for c in back.components] == [
        ("api", "go", 9000, True), ("worker", "python", 8080, False)]
    assert back.components[0].path == "services/api" and back.components[0].env_name == "IMAGE_API"


def test_une_image_par_composant_dans_la_ci():
    files = files_of(multi("docker-host", *COMPOSE, "unit-tests", "trivy", "cosign"))
    ci = yaml.safe_load(files[".gitlab-ci.yml"])
    for cid, var in (("api", "IMAGE_API"), ("worker", "IMAGE_WORKER")):
        build = "\n".join(ci[f"build-image-{cid}"]["script"])
        assert f'{var}="${{IMAGE%:*}}:{cid}-${{IMAGE##*:}}"' in build
        assert f'docker buildx build --tag "${var}" --push services/{cid}' in build
        assert f'trivy image' in "\n".join(ci[f"trivy-{cid}"]["script"]) and f'"${var}"' in "\n".join(ci[f"trivy-{cid}"]["script"])
        assert f"cosign sign --yes \"${var}\"" in "\n".join(ci[f"cosign-{cid}"]["script"])
        assert "cd services/" + cid in "\n".join(ci[f"unit-tests-{cid}"]["script"])


@pytest.mark.parametrize("builder,expect", [
    ("buildah", "buildah build --tag \"$IMAGE_API\" services/api"),
    ("kaniko", "--context services/api --dockerfile services/api/Dockerfile --destination \"$IMAGE_API\""),
    ("buildpacks", "pack build \"$IMAGE_API\" --builder paketobuildpacks/builder-jammy-base --publish --path services/api"),
])
def test_autres_constructeurs(builder, expect):
    tools = tuple(t for t in COMPOSE if t != "buildkit") + (builder,)
    text = files_of(multi("docker-host", *tools))[".gitlab-ci.yml"]
    assert expect in text


def test_compose_traefik_et_services_internes():
    doc = yaml.safe_load(files_of(multi("docker-host", *COMPOSE))["deploy/docker-compose.yml"])
    api, worker, main = doc["services"]["api"], doc["services"]["worker"], doc["services"]["shop"]
    assert api["image"].startswith("${IMAGE_API:-") and api["image"].endswith(":api-latest}")
    assert any("PathPrefix(`/api`)" in label for label in api["labels"])
    assert "traefik.http.middlewares.shop-api-strip.stripprefix.prefixes=/api" in api["labels"]
    assert "ports" not in worker and "labels" not in worker   # interne : joignable par son nom, non publié
    assert main["environment"]["API_URL"] == "http://api:9000" and main["environment"]["WORKER_URL"] == "http://worker:8080"


def test_compose_sans_traefik_publie_les_composants_exposes():
    tools = tuple(t for t in COMPOSE if t != "traefik")
    doc = yaml.safe_load(files_of(multi("docker-host", *tools))["deploy/docker-compose.yml"])
    assert doc["services"]["api"]["ports"] == ["9000:9000"] and "ports" not in doc["services"]["worker"]


def test_deploiement_ssh_passe_les_images():
    text = files_of(multi("docker-host", *COMPOSE))[".gitlab-ci.yml"]
    assert "IMAGE_API=$IMAGE_API IMAGE_WORKER=$IMAGE_WORKER" in text
    assert 'IMAGE_API="${IMAGE%:*}:api-${IMAGE##*:}"' in text


def test_ansible_passe_les_images():
    files = files_of(multi("vm", *COMPOSE, "ansible"))
    play = yaml.safe_load(files["ansible/deploy.yml"])[0]
    assert play["vars"]["image_api"].endswith(":api-latest")
    start = next(t for t in play["tasks"] if t["name"] == "Démarrer les services")
    assert start["environment"]["IMAGE_API"] == "{{ image_api }}"
    assert '-e "image_api=$IMAGE_API"' in files[".gitlab-ci.yml"]


def test_ansible_sans_compose_definit_les_composants():
    tools = tuple(t for t in COMPOSE if t != "docker-compose") + ("ansible",)
    play = yaml.safe_load(files_of(multi("vm", *tools))["ansible/deploy.yml"])[0]
    start = next(t for t in play["tasks"] if t["name"] == "Démarrer les services")
    services = start["community.docker.docker_compose_v2"]["definition"]["services"]
    assert services["api"]["image"] == "{{ image_api }}" and "ports" not in services["worker"]


def test_helm_un_deployment_et_un_service_par_composant():
    files = files_of(multi("kubernetes", *K3S_HELM))
    values = yaml.safe_load(files["charts/shop/values.yaml"])
    assert values["components"]["api"]["port"] == 9000 and values["components"]["worker"]["image"]["tag"] == "worker-latest"
    tpl = files["charts/shop/templates/component-api.yaml"]
    assert 'index .Values.components "api"' in tpl and "kind: Deployment" in tpl and "kind: Service" in tpl
    assert "templates/component-worker.yaml" in "\n".join(files)
    assert 'components.api.image.tag="${IMAGE_API##*:}"' in files[".github/workflows/pipeline.yml"]
    assert "API_URL" in files["charts/shop/templates/deployment.yaml"]


def test_kind_non_genere_avec_des_composants():
    files = files_of(multi("kubernetes", *K3S_HELM))
    assert not any(f.startswith("scripts/test-kind") for f in files)


def test_plan_des_ports():
    entries = {e.component_id: e for e in port_plan(multi("docker-host", *COMPOSE), CATALOG)}
    assert "Traefik" in entries["api"].exposure and "/api" in entries["api"].exposure
    assert entries["worker"].host_port is None and "interne" in entries["worker"].exposure


def test_r60_cibles_non_prises_en_charge_et_identifiants():
    p = multi("kubernetes", *K3S_HELM, "kustomize")
    assert "Kustomize" in rules(p)["R60"]
    p = multi("docker-host", *COMPOSE)
    assert "R60" not in rules(p)
    p.components.append(Component(id="Api"))
    p.components.append(Component(id="shop"))
    p.components.append(Component(id="api"))
    message = rules(p)["R60"]
    assert "« Api »" in message and "« shop »" in message and "« api »" in message


def test_r60_silencieux_sans_application():
    p = multi("docker-host", *COMPOSE, "kustomize")
    p.app.enabled = False
    assert "R60" not in rules(p)


def test_rapport_et_comparaison():
    p = multi("docker-host", *COMPOSE)
    assert "Composant `api`" in generate(p, CATALOG, ENGINE).files["PIPELINE.md"]
    before = project("docker-host", *COMPOSE, envs="prod")
    cmp = compare(before, p, CATALOG, ENGINE)
    assert any("Application supplémentaire ajoutée : api" in line for line in cmp.settings)


@pytest.fixture(scope="module")
def window(tmp_path_factory):
    home = os.environ.get("HOME")
    os.environ["HOME"] = str(tmp_path_factory.mktemp("home"))
    from devops_builder.ui.app import create_window
    app, win = create_window(["devops-builder"])
    win.show()
    app.processEvents()
    yield win
    win.undo_stack.setClean()
    win.close()
    if home is not None:
        os.environ["HOME"] = home


def test_dialogue_application_edite_les_composants(window):
    from devops_builder.ui.application import ApplicationDialog
    p = multi("docker-host", *COMPOSE)
    dlg = ApplicationDialog(p, CATALOG)
    assert dlg.comp_list.count() == 2 and dlg.comp_id.text() == "api"
    dlg.comp_port.setValue(9100)
    dlg.comp_add.click()
    dlg.comp_id.setText("Front End")
    dlg.comp_public.setChecked(True)
    dlg.comp_list.setCurrentRow(0)          # valide la saisie du composant ajouté
    dlg.comp_list.setCurrentRow(1)
    dlg.comp_remove.click()
    out = Project.from_yaml(p.to_yaml())
    dlg.apply_to(out)
    assert [(c.id, c.port, c.public) for c in out.components] == [("api", 9100, True), ("front-end", 8080 + 2, True)]
