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
    zbx = [e for e in with_traefik if e.component_id == "zabbix-web"]
    assert zbx and all(e.host_port is None and "zabbix.boutique.fr" in e.exposure for e in zbx)
    # sans Traefik, Keycloak et l'interface Zabbix publient tous deux 8080 : le conflit est signalé (R39)
    bare = project("docker-host", "gitlab", "gitlab-ci", "buildkit", "docker-compose", "zabbix", "keycloak")
    clash = [e for e in port_plan(bare, CATALOG) if e.host_port == 8080]
    assert {e.component_id for e in clash} == {"zabbix-web", "keycloak"} and all(e.conflict for e in clash)
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


def test_bases_de_plateforme_sauvegardees():
    """Zabbix et Keycloak portent configuration et comptes : leurs bases passent par db-backup.sh et db-restore.sh."""
    f = gen(project("docker-host", *COMPOSE, "zabbix", "keycloak")).files
    backup, restore = f["scripts/db-backup.sh"], f["scripts/db-restore.sh"]
    for service in ("zabbix-db", "keycloak-db"):
        assert f"dc exec -T {service} sh -c 'pg_dump" in backup
        assert f"  {service}-*) service={service};" in restore


def test_agent_de_l_hote_et_port_des_agents_actifs():
    r = gen(project("docker-host", "gitlab", "gitlab-ci", "buildkit", "docker-compose", "zabbix"))
    svc = compose(r.files)["services"]
    host = svc["zabbix-agent-host"]
    assert host["network_mode"] == "host" and host["pid"] == "host" and host["user"] == "0:0"
    assert "/var/run/docker.sock:/var/run/docker.sock:ro" in host["volumes"] and "/:/hostfs:ro,rslave" in host["volumes"]
    # l'image additionne ZBX_SERVER_HOST et ZBX_PASSIVESERVERS : aucune adresse en double, pas de plage en actif
    env = host["environment"]
    assert env["ZBX_SERVER_HOST"] == "127.0.0.1" and env["ZBX_PASSIVESERVERS"] == "172.16.0.0/12"
    assert svc["zabbix-server"]["ports"] == ["10051:10051"]
    assert svc["zabbix-server"]["extra_hosts"] == ["host.docker.internal:host-gateway"]
    guide = r.files["docs/mise-en-route.md"]
    assert "host.create" in guide and 'dns:"host.docker.internal",port:"10050"' in guide
    assert 'ZBX="http://$HOTE:8080/api_jsonrpc.php"' in guide and 'export HOTE="192.168.1.10"' in guide


def test_agent_de_l_hote_desactivable():
    r = gen(project("docker-host", "gitlab", "gitlab-ci", "buildkit", "docker-compose", "zabbix",
                    zabbix={"supervise_host": False}))
    svc = compose(r.files)["services"]
    assert "zabbix-agent-host" not in svc and "extra_hosts" not in svc["zabbix-server"]
    assert svc["zabbix-server"]["ports"] == ["10051:10051"]
    assert "host.create" not in r.files["docs/mise-en-route.md"]


def test_variables_de_port_identiques_dans_compose_et_fichiers_d_environnement():
    """Hôte partagé : la variable lue par Compose est celle qu'écrit deploy/env/<env>.env (défaut corrigé en 0.27)."""
    p = project("docker-host", "gitlab", "gitlab-ci", "buildkit", "docker-compose", "zabbix",
                zabbix={"supervise_host": False})
    for env in p.environments:
        env.host = "srv1"
    r = gen(p)
    text = r.files["deploy/docker-compose.yml"]
    for name in ("PORT_ZABBIX_WEB_8080", "PORT_ZABBIX_SERVER_10051"):
        assert "${" + name in text and all(name + "=" in r.files[f] for f in r.files if f.startswith("deploy/env/"))
