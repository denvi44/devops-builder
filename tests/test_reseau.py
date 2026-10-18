# SPDX-License-Identifier: Apache-2.0
"""0.21 : schéma réseau par environnement (2D, 3D isométrique), avec les erreurs posées sur les composants."""

from __future__ import annotations

import os

import pytest

from devops_builder.catalog import DATA_DIR, default_catalog
from devops_builder.model import Project, Severity
from devops_builder.modeles import MODELES, build
from devops_builder.network import LAYERS, build_graph
from devops_builder.rules import RuleEngine

CATALOG = default_catalog()
ENGINE = RuleEngine(CATALOG)
EXAMPLES = sorted((DATA_DIR / "examples").glob("*.yaml"))


def projects():
    for slug in MODELES:
        yield slug, build(slug, CATALOG)
    for path in EXAMPLES:
        yield path.stem, Project.load(path)


@pytest.mark.parametrize("name,project", list(projects()), ids=[n for n, _ in projects()])
def test_graphe_coherent_pour_chaque_environnement(name, project):
    for env in project.environments:
        g = build_graph(project, CATALOG, ENGINE, env.id)
        ids = {n.id for n in g.nodes}
        assert {"internet", "app"} <= ids and len(ids) == len(g.nodes), "chaque composant une seule fois"
        assert all(n.layer in LAYERS for n in g.nodes)
        assert all(e.src in ids and e.dst in ids for e in g.edges), "aucune flèche vers un composant absent"
        assert all(n in ids for f in g.findings for n in f.nodes)
        # chaque composant est atteint par un flux, sauf l'application d'un cluster sans entrée (constat d'information)
        reached = {e.dst for e in g.edges}
        orphans = {n.id for n in g.nodes if n.id not in reached and n.id != "internet" and n.kind != "hosting"}
        assert not orphans or any(f.severity is Severity.INFO for f in g.findings), (name, orphans)


def test_une_erreur_de_regle_est_posee_sur_le_composant_de_sa_brique():
    p = build("outscale", CATALOG)
    g = build_graph(p, CATALOG, ENGINE)
    traefik = [f for f in g.findings_of("traefik") if f.rule_id == "R34"]
    assert traefik and traefik[0].severity is Severity.WARNING and g.worst("traefik") is Severity.WARNING
    assert g.elsewhere >= 0 and g.worst("postgresql") is None


def _docker(*tools):
    from devops_builder.model import env_preset
    p = Project(name="ports", target="docker-host", environments=env_preset("prod"))
    for t in ("gitlab", "gitlab-ci", "buildkit", "harbor", "docker-compose", *tools):
        p.add(t, CATALOG[t].stage)
    return p


def test_service_publie_sans_passer_par_l_entree():
    # sans Traefik, Grafana est publié sur l'hôte : constat, mais sans « entrée » à contourner pour Prometheus
    g = build_graph(_docker("grafana", "prometheus"), CATALOG, ENGINE)
    reseau = [f for f in g.findings if f.source == "réseau"]
    assert {n for f in reseau for n in f.nodes} >= {"grafana", "prometheus"}
    assert any(e.public and not e.secure and e.dst == "grafana" for e in g.edges)


def test_interfaces_derriere_traefik_et_services_internes():
    g = build_graph(_docker("traefik", "grafana", "prometheus", "jaeger"), CATALOG, ENGINE)
    assert any(e.src == "traefik" and e.dst == "grafana" for e in g.edges)
    assert not any(e.public and e.dst in ("grafana", "prometheus") for e in g.edges)
    assert not any(f.nodes == ["grafana"] for f in g.findings if f.source == "réseau")
    # Jaeger : interface derrière Traefik, ports OTLP encore publiés (protocole machine, pas de constat)
    assert any(e.src == "traefik" and e.dst == "jaeger" for e in g.edges)
    assert any(e.public and e.dst == "jaeger" for e in g.edges)
    assert not any(f.nodes == ["jaeger"] for f in g.findings if f.source == "réseau")


def test_conflit_de_port_bloquant():
    from devops_builder.model import env_preset
    p = Project.load(DATA_DIR / "examples" / "01-web-hote-docker.devops.yaml")
    p.environments = env_preset("staging-prod")
    prod, staging = p.environments[-1], p.environments[0]
    prod.host = staging.host = "hote-commun"
    prod.port_offset = staging.port_offset = 0
    g = build_graph(p, CATALOG, ENGINE, prod.id)
    blocking = [f for f in g.findings if f.severity is Severity.BLOCKING]
    assert blocking and all(f.rule_id == "R39" for f in blocking), "les conflits viennent de la règle R39"
    assert any("traefik" in f.nodes for f in blocking) and g.worst("traefik") is Severity.BLOCKING


def test_cluster_sans_entree_est_signale():
    g = build_graph(build("aws", CATALOG), CATALOG, ENGINE)
    assert any("aucun point d'entrée" in f.message for f in g.findings_of("app"))
    serverless = build_graph(build("aws-ecs", CATALOG), CATALOG, ENGINE)
    assert any(e.src == "internet" and e.dst == "app" and e.secure for e in serverless.edges)


def test_projet_sans_environnement_ni_brique():
    g = build_graph(Project(environments=[]), CATALOG, ENGINE)
    assert g.nodes == []
    assert {"internet", "app"} <= {n.id for n in build_graph(Project(), CATALOG, ENGINE).nodes}


# ------------------------------------------------------------------ interface
@pytest.fixture()
def win(tmp_path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    home = os.environ.get("HOME")
    os.environ["HOME"] = str(tmp_path)
    from devops_builder.ui.app import create_window
    app, window = create_window(["devops-builder"])
    window.show()
    window._load(build("outscale", window.catalog), None)
    app.processEvents()
    yield window
    window.undo_stack.setClean()
    window.close()
    if home is not None:
        os.environ["HOME"] = home


def test_menu_et_raccourci(win):
    assert win.a_network.shortcut().toString() == "Ctrl+Shift+R"
    assert win.a_network in win.views_btn.menu().actions()


@pytest.mark.parametrize("mode", ["2d", "3d"])
def test_dessin_les_deux_vues(win, mode):
    from devops_builder.ui.reseau import NetworkDialog
    dialog = NetworkDialog(win.project, win.catalog, win.engine, win)
    dialog.show()
    dialog.mode.setCurrentIndex(1 if mode == "3d" else 0)
    assert dialog.view.mode == mode
    image = dialog.view.grab().toImage()
    assert image.width() >= dialog.view.sizeHint().width() and len({image.pixel(x, y) for x in range(0, 700, 9) for y in range(0, 500, 11)}) > 3
    for node in dialog.graph.nodes:   # chaque composant a une zone cliquable dans le dessin
        assert any(i == node.id for i, _ in dialog.view._hits)
    box = dialog.view.sizeHint()
    for rect in dialog.view._pills.values():
        assert 0 <= rect.left() and rect.right() <= box.width() and 0 <= rect.top() and rect.bottom() <= box.height()
    dialog.close()


def test_selection_synchronisee_et_erreurs_dans_la_liste(win):
    from PySide6.QtCore import Qt

    from devops_builder.ui.reseau import NetworkDialog
    dialog = NetworkDialog(win.project, win.catalog, win.engine, win)
    dialog.show()
    dialog.view.select("traefik")
    assert dialog.tree.currentItem().data(0, Qt.ItemDataRole.UserRole) == ("node", "traefik")
    assert "avertissement" in dialog.detail.text()
    texts = [dialog.tree.topLevelItem(i).text(0) for i in range(dialog.tree.topLevelItemCount())]
    assert any("Traefik" in t and "avertissement" in t for t in texts), "l'erreur est écrite, pas seulement colorée"
    grafana = next(dialog.tree.topLevelItem(i) for i in range(dialog.tree.topLevelItemCount())
                   if "Traefik" in dialog.tree.topLevelItem(i).text(0))
    dialog.tree.setCurrentItem(grafana.child(0))
    assert dialog.view.selected == "traefik"
    dialog.close()


def test_clavier_dans_le_dessin(win):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from devops_builder.ui.reseau import NetworkDialog
    dialog = NetworkDialog(win.project, win.catalog, win.engine, win)
    dialog.show()
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QFocusEvent
    from PySide6.QtWidgets import QApplication
    QApplication.sendEvent(dialog.view, QFocusEvent(QEvent.Type.FocusIn))   # l'écran virtuel n'active pas la fenêtre
    first = dialog.view.selected
    assert first == dialog.graph.nodes[0].id
    QTest.keyClick(dialog.view, Qt.Key.Key_Right)
    assert dialog.view.selected == dialog.graph.nodes[1].id
    QTest.keyClick(dialog.view, Qt.Key.Key_Left)
    assert dialog.view.selected == first
    dialog.close()


def test_voir_la_brique_ferme_et_selectionne(win):
    from devops_builder.ui.reseau import NetworkDialog
    seen = []
    dialog = NetworkDialog(win.project, win.catalog, win.engine, win, focus_brick=seen.append)
    dialog.show()
    dialog.view.select("traefik")
    dialog.open_btn.click()
    assert seen == [win.project.bricks_for("traefik")[0].uid] and not dialog.isVisible()


def test_corriger_depuis_le_schema(win):
    """R52 (machine trop petite) tombe sur l'hébergement, avec sa correction applicable depuis le schéma."""
    from devops_builder.modeles import MODELES
    from devops_builder.rules import apply_action
    from devops_builder.starter import build_starter
    from devops_builder.ui.reseau import NetworkDialog
    project = build_starter(MODELES["aws-ec2"].answers, win.catalog)
    graph = build_graph(project, win.catalog, win.engine)
    fixable = [f for f in graph.findings if f.rule_id == "R52"]
    assert fixable and fixable[0].actions and fixable[0].nodes[0].startswith("host:")
    state = {"project": project}

    def fix(action):
        apply_action(state["project"], action, win.catalog)
        return state["project"]
    dialog = NetworkDialog(project, win.catalog, win.engine, win, apply_fix=fix)
    dialog.show()
    node_id = fixable[0].nodes[0]
    dialog.view.select(node_id)
    finding_item = next(dialog.tree.topLevelItem(i) for i in range(dialog.tree.topLevelItemCount())
                        if dialog.tree.topLevelItem(i).text(0).startswith(dialog.graph.node(node_id).label))
    dialog.tree.setCurrentItem(next(finding_item.child(i) for i in range(finding_item.childCount())
                                    if "R52" in dialog.graph.findings[finding_item.child(i).data(
                                        0, 0x100)[1]].rule_id))
    assert dialog.actions_box.count() >= 1
    dialog.actions_box.itemAt(0).widget().click()
    assert not [f for f in dialog.graph.findings if f.rule_id == "R52"], "la correction a effacé l'erreur du schéma"
    dialog.close()


def test_taille_du_schema_agrandit_textes_et_espaces(win):
    from devops_builder.ui.reseau import NetworkDialog
    dialog = NetworkDialog(win.project, win.catalog, win.engine, win)
    dialog.show()
    sizes = {}
    for zoom in (1.0, 2.0):
        dialog.view.set_zoom(zoom)
        for mode in ("2d", "3d"):
            dialog.view.set_mode(mode)
            sizes[(zoom, mode)] = (dialog.view.sizeHint(), dialog.view._metrics()[0].pointSizeF())
    for mode in ("2d", "3d"):
        small, big = sizes[(1.0, mode)], sizes[(2.0, mode)]
        assert big[0].width() > small[0].width() * 1.5 and big[1] > small[1] * 1.8
    dialog.close()
