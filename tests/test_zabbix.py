# SPDX-License-Identifier: Apache-2.0
"""Zabbix sur hôte Docker et VM : images officielles, base dédiée, secrets par le circuit habituel."""

from __future__ import annotations

import yaml
from test_data import CATALOG, COMPOSE, ENGINE, project

from devops_builder.generators import generate
from devops_builder.generators.secrets import values
from devops_builder.ports import port_plan


def gen(p):
    return generate(p, CATALOG, ENGINE, allow_blocking=True)


def compose(files):
    return yaml.safe_load(files["deploy/docker-compose.yml"])


def test_services_officiels_et_base_dediee():
    r = gen(project("docker-host", *COMPOSE, "zabbix", zabbix={"hostname": "zabbix.boutique.fr"}))
    svc = compose(r.files)["services"]
    assert {"zabbix-server", "zabbix-web", "zabbix-agent", "zabbix-db"} <= set(svc)
    assert svc["zabbix-server"]["image"] == "zabbix/zabbix-server-pgsql:alpine-7.4-latest"
    assert svc["zabbix-server"]["depends_on"]["zabbix-db"]["condition"] == "service_healthy"
    assert svc["zabbix-agent"]["network_mode"] == "service:zabbix-server"
    for name in ("zabbix-server", "zabbix-web", "zabbix-db"):
        assert svc[name]["env_file"] == ["secrets/zabbix.env"]
        assert "POSTGRES_PASSWORD" not in svc[name].get("environment", {})   # jamais en clair
    web = svc["zabbix-web"]
    assert "ports" not in web and "traefik.http.routers.zabbix.rule=Host(`zabbix.boutique.fr`)" in web["labels"]
    assert "zabbix-db-data" in compose(r.files)["volumes"]
    secrets_sh = r.files["deploy/secrets.sh"]
    assert ': "${ZABBIX_DB_PASSWORD:?' in secrets_sh and 'cat > "$dir/zabbix.env"' in secrets_sh
    assert "zabbix" not in [t.id for t in r.ir.unsupported]


def test_sans_traefik_port_publie():
    r = gen(project("docker-host", "gitlab", "gitlab-ci", "buildkit", "docker-compose", "zabbix"))
    assert compose(r.files)["services"]["zabbix-web"]["ports"] == ["8080:8080"]


def test_secret_range_sous_zabbix_dans_le_coffre():
    r = gen(project("docker-host", *COMPOSE, "zabbix"))
    assert ("ZABBIX_DB_PASSWORD", "zabbix", "zabbix_db_password") in values(r.ir, [])


def test_mode_d_emploi_mot_de_passe_admin():
    r = gen(project("docker-host", *COMPOSE, "zabbix", zabbix={"hostname": "zabbix.boutique.fr"}))
    guide = r.files["docs/mise-en-route.md"]
    assert "## " in guide and "Zabbix" in guide and "Admin / zabbix" in guide
    assert 'ZBX="https://zabbix.boutique.fr/api_jsonrpc.php"' in guide and 'user.update' in guide


def test_ports_declares_et_conflit_sans_traefik():
    with_traefik = port_plan(project("docker-host", *COMPOSE, "zabbix", zabbix={"hostname": "zabbix.boutique.fr"}),
                             CATALOG)
    zbx = [e for e in with_traefik if e.component_id == "zabbix"]
    assert zbx and all(e.host_port is None and "zabbix.boutique.fr" in e.exposure for e in zbx)
    # sans Traefik, Keycloak et l'interface Zabbix publient tous deux 8080 : le conflit est signalé (R39)
    bare = project("docker-host", "gitlab", "gitlab-ci", "buildkit", "docker-compose", "zabbix", "keycloak")
    clash = [e for e in port_plan(bare, CATALOG) if e.host_port == 8080]
    assert {e.component_id for e in clash} == {"zabbix", "keycloak"} and all(e.conflict for e in clash)
    assert "R39" in {d.rule_id for d in ENGINE.evaluate(bare)}


def test_hors_hote_docker_rien_genere():
    r = gen(project("kubernetes", "github", "github-actions", "buildkit", "ghcr", "k3s", "helm", "zabbix"))
    assert not any("zabbix" in f for f in r.files.get("charts/boutique/values.yaml", ""))
    assert "zabbix" in [t.id for t in r.ir.unsupported]


def test_traefik_https_reel_sur_l_hote_docker():
    """Défaut trouvé par les tests de bout en bout : le port 443 répondait en HTTP clair."""
    svc = compose(gen(project("docker-host", *COMPOSE)).files)["services"]["traefik"]
    cmd = svc["command"]
    assert "--entrypoints.websecure.http.tls=true" in cmd
    assert "--entrypoints.web.http.redirections.entrypoint.scheme=https" in cmd
    assert "--certificatesresolvers.letsencrypt.acme.tlschallenge=true" in cmd
    assert not any("acme.email" in c for c in cmd)            # jamais l'adresse d'exemple
    with_mail = compose(gen(project("docker-host", *COMPOSE, traefik={"acme_email": "ops@boutique.fr"})).files)
    assert "--certificatesresolvers.letsencrypt.acme.email=ops@boutique.fr" in with_mail["services"]["traefik"]["command"]
