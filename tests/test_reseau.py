# SPDX-License-Identifier: Apache-2.0
"""1.1 : capacité « réseau privé » — une brique par cloud, rattachée aux clusters, machines et bases."""

from __future__ import annotations

import re
import shutil
import subprocess

import pytest

from devops_builder.catalog import default_catalog
from devops_builder.compat import adapted
from devops_builder.generators import generate, network
from devops_builder.params import check_value
from devops_builder.rules import RuleEngine
from devops_builder.starter import StarterAnswers, build_starter

CATALOG = default_catalog()
ENGINE = RuleEngine(CATALOG)
CLOUDS = ["aws", "gcp", "azure", "scaleway", "ovhcloud", "outscale"]


def make(cloud: str, hosting: str = "kubernetes-managed", with_network: bool = True, **kw):
    a = StarterAnswers(forge="gitlab", hosting=hosting, cloud=cloud, envs="staging-prod",
                       secnumcloud=cloud == "outscale", **kw)
    p = build_starter(a, CATALOG)
    if with_network:
        p.add(CATALOG[cloud].services["network"], "infrastructure")
    return p


def tf(p, name="main.tf") -> str:
    return generate(p, CATALOG, ENGINE, allow_blocking=True).files[f"infra/terraform/{name}"]


def test_chaque_fournisseur_declare_sa_brique_reseau():
    assert set(network.NETWORK) == {CATALOG[c].services["network"] for c in CLOUDS}
    for tool_id, cloud in network.NETWORK.items():
        assert CATALOG[tool_id].provider == cloud and "private-network" in CATALOG[tool_id].provides


EXPECTED = {
    "aws": 'resource "aws_vpc" "main"', "gcp": 'resource "google_compute_network" "main"',
    "azure": 'resource "azurerm_virtual_network" "main"', "scaleway": 'resource "scaleway_vpc_private_network" "main"',
    "ovhcloud": 'resource "ovh_cloud_project_network_private" "main"', "outscale": 'resource "outscale_net" "main"',
}


@pytest.mark.parametrize("cloud", CLOUDS)
def test_la_brique_cree_le_reseau_et_ses_sorties(cloud):
    hosting = "vm" if cloud == "outscale" else "kubernetes-managed"
    p = make(cloud, hosting)
    assert EXPECTED[cloud] in tf(p)
    assert "output" in tf(p, "outputs.tf")
    sans = tf(make(cloud, hosting, with_network=False))
    assert EXPECTED[cloud] not in sans


def test_aws_ne_demande_plus_les_identifiants_de_reseau():
    sans = make("aws", with_network=False, database="postgresql")
    assert {"vpc_id", "subnet_ids", "db_subnet_group", "db_security_group_ids"} <= set(
        v for v in ("vpc_id", "subnet_ids", "db_subnet_group", "db_security_group_ids")
        if f'variable "{v}"' in tf(sans, "variables.tf"))
    p = make("aws", database="postgresql")
    variables, main = tf(p, "variables.tf"), tf(p)
    for v in ("vpc_id", "subnet_ids", "db_subnet_group", "db_security_group_ids"):
        assert f'variable "{v}"' not in variables
    assert "vpc_id             = aws_vpc.main.id" in main
    assert "subnet_ids         = aws_subnet.private[*].id" in main
    assert "db_subnet_group_name        = aws_db_subnet_group.main.name" in main
    assert "vpc_security_group_ids      = [aws_security_group.db.id]" in main
    assert "infra/terraform/terraform.tfvars.example" not in generate(p, CATALOG, ENGINE, allow_blocking=True).files


def test_aws_passerelle_nat_selon_le_choix():
    assert "aws_nat_gateway" in tf(make("aws"))                                  # auto + EKS : nécessaire
    vm = make("aws", "vm")
    assert "aws_nat_gateway" not in tf(vm)                                       # auto sans cluster : inutile
    vm.bricks_for("aws-vpc")[0].params["nat"] = "oui"
    assert "aws_nat_gateway" in tf(vm)
    eks = make("aws")
    eks.bricks_for("aws-vpc")[0].params["nat"] = "non"
    assert "aws_nat_gateway" not in tf(eks)


def test_aws_machines_dans_les_sous_reseaux_publics():
    main = tf(make("aws", "vm"))
    assert "subnet_id              = aws_subnet.public[count.index % 2].id" in main
    assert "vpc_id      = aws_vpc.main.id" in main
    assert "aws_subnet" not in tf(make("aws", "vm", with_network=False))


def test_gcp_cluster_machines_et_base_sur_le_reseau():
    main = tf(make("gcp", database="postgresql"))
    assert "network    = google_compute_network.main.id" in main
    assert "private_network = google_compute_network.main.id" in main
    assert "google_service_networking_connection.private_services" in main
    vm = tf(make("gcp", "vm"))
    assert 'network       = google_compute_network.main.name' in vm
    assert 'network = "default"' not in vm and "subnetwork = google_compute_subnetwork.main.id" in vm


def test_azure_un_seul_reseau_pour_machines_cluster_et_base():
    main = tf(make("azure", database="mysql"))
    assert "vnet_subnet_id = azurerm_subnet.aks.id" in main
    assert re.search(r"delegated_subnet_id\s+= azurerm_subnet.data.id", main)
    assert "public_network_access_enabled" not in main   # calculé par le provider avec un sous-réseau délégué
    assert "privatelink.mysql.database.azure.com" in main
    vm = tf(make("azure", "vm"))
    assert vm.count('resource "azurerm_virtual_network"') == 1
    assert "azurerm_virtual_network.hosts" not in vm and "subnet_id                     = azurerm_subnet.hosts.id" in vm


def test_scaleway_ovh_outscale_rattachent_leurs_ressources():
    sw = tf(make("scaleway", database="postgresql"))
    assert sw.count("scaleway_vpc_private_network.main.id") >= 3          # réseau, Kapsule, base
    assert "pn_id = scaleway_vpc_private_network.main.id" in tf(make("scaleway", "vm"))
    assert "private_network_id" in tf(make("ovhcloud")) and "nodes_subnet_id" in tf(make("ovhcloud"))
    o = tf(make("outscale", "vm"))
    assert re.search(r"subnet_id\s+= outscale_subnet.main.subnet_id", o) and re.search(r"net_id\s+= outscale_net.main.net_id", o)
    assert "placement_subregion_name" not in o


def test_ovhcloud_machines_notent_la_limite():
    r = generate(make("ovhcloud", "vm"), CATALOG, ENGINE, allow_blocking=True)
    assert any("rattacher le réseau privé" in n for n in r.ir.notes)


def test_sous_reseaux_calcules_dans_la_plage_choisie():
    p = make("aws")
    p.bricks_for("aws-vpc")[0].params["cidr"] = "172.20.0.0/16"
    main = tf(p)
    assert 'cidr_block           = "172.20.0.0/16"' in main
    assert 'public_subnet_cidrs  = ["172.20.0.0/20", "172.20.16.0/20"]' in main


def test_plage_invalide_refusee():
    spec = CATALOG["aws-vpc"].param_schema["cidr"]
    for bad in ("8.8.8.0/24", "10.0.0.0/8", "10.0.0.0/28", "pas-une-plage"):
        assert check_value(spec, bad), bad
    assert not check_value(spec, "10.1.0.0/20")


def test_la_palette_ne_propose_que_le_reseau_du_cloud_du_projet():
    p = make("aws", with_network=False)
    keep, reasons = adapted([CATALOG[t] for t in network.NETWORK], p, CATALOG)
    assert [t.id for t in keep] == ["aws-vpc"] and set(reasons) == set(network.NETWORK) - {"aws-vpc"}


def test_reseau_sans_son_fournisseur_est_signale():
    p = make("aws", with_network=False)
    p.add("gcp-vpc", "infrastructure")
    assert "R09" in {d.rule_id for d in ENGINE.evaluate(p)}


@pytest.mark.skipif(not shutil.which("tofu"), reason="tofu absent")
@pytest.mark.parametrize("cloud", CLOUDS)
def test_pile_reseau_conforme_a_tofu_fmt(cloud, tmp_path):
    for hosting in ("kubernetes-managed", "vm"):
        if cloud == "outscale" and hosting != "vm":
            continue
        files = generate(make(cloud, hosting, database="postgresql" if hosting != "vm" else None), CATALOG, ENGINE,
                         allow_blocking=True).files
        d = tmp_path / hosting
        d.mkdir()
        for name, content in files.items():
            if name.startswith("infra/terraform/"):
                (d / name.rsplit("/", 1)[1]).write_text(content)
        r = subprocess.run(["tofu", "fmt", "-check", "-diff", "-no-color", str(d)], capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr
