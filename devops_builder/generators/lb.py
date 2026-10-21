# SPDX-License-Identifier: Apache-2.0
"""Répartiteur de charge devant les machines créées par la pile (capacité « répartiteur de charge » de la 1.1).

Une brique par cloud (aws-elb, gcp-lb, azure-lb, scaleway-lb, ovh-load-balancer, outscale-lbu). Un répartiteur est
créé par groupe de machines (hôte partagé ou environnement), en TCP sur les ports web : Traefik, sur les machines,
garde la terminaison TLS et le routage. La sonde est un test de connexion TCP sur le port 80 (ou le port de
l'application). L'adresse du répartiteur est une sortie de la pile (« lb_<groupe> ») : le DNS pointe vers elle.

Sur un cluster Kubernetes, le répartiteur est celui que le Service ou l'entrée demande au cloud : la brique n'écrit
alors aucune ressource et le rappelle dans les notes.
"""

from __future__ import annotations

import re

from ..ir import IR
from . import hosts, network
from .common import align_attrs

LB = {"aws-elb": "aws", "gcp-lb": "gcp", "azure-lb": "azure", "scaleway-lb": "scaleway",
      "ovh-load-balancer": "ovhcloud", "outscale-lbu": "outscale"}


def tool(ir: IR) -> str | None:
    return next((t for t in LB if ir.has(t)), None)


def _slug(ir: IR, g, port: int | None = None) -> str:
    name = f"{ir.app}-{re.sub(r'[^a-z0-9-]', '-', g.key.lower())}"
    return name + (f"-{port}" if port else "")


def _probe_port(ports: list[int]) -> int:
    return 80 if 80 in ports else ports[0]


def _aws(ir: IR, gs, ports):
    vpc = network.present(ir, "aws-vpc")
    shared = "" if vpc else ('data "aws_vpc" "default" {\n  default = true\n}\n\n'
                             'data "aws_subnets" "default" {\n  filter {\n    name   = "vpc-id"\n    values = [data.aws_vpc.default.id]\n  }\n}')
    vpc_id = "aws_vpc.main.id" if vpc else "data.aws_vpc.default.id"
    subnets = "aws_subnet.public[*].id" if vpc else "data.aws_subnets.default.ids"
    probe = _probe_port(ports)
    out, outs = [], []
    for g in gs:
        n, c = _slug(ir, g), hosts._count(g)
        parts = [align_attrs(f'''resource "aws_lb" "{g.label}" {{
  name               = "{n[:32]}"
  load_balancer_type = "network"
  internal           = false
  subnets            = {subnets}
}}''')]
        for p in ports:
            parts.append(align_attrs(f'''resource "aws_lb_target_group" "{g.label}_{p}" {{
  name        = "{_slug(ir, g, p)[:32]}"
  port        = {p}
  protocol    = "TCP"
  target_type = "instance"
  vpc_id      = {vpc_id}

  health_check {{
    protocol = "TCP"
    port     = "{probe}"
  }}
}}

resource "aws_lb_target_group_attachment" "{g.label}_{p}" {{
  count            = {c}
  target_group_arn = aws_lb_target_group.{g.label}_{p}.arn
  target_id        = aws_instance.{g.label}[count.index].id
  port             = {p}
}}

resource "aws_lb_listener" "{g.label}_{p}" {{
  load_balancer_arn = aws_lb.{g.label}.arn
  port              = {p}
  protocol          = "TCP"

  default_action {{
    type             = "forward"
    target_group_arn = aws_lb_target_group.{g.label}_{p}.arn
  }}
}}'''))
        out.append(f"# --- {g.key} : répartiteur\n" + "\n\n".join(parts))
        outs.append(f'output "lb_{g.label}" {{\n  description = "Adresse DNS du répartiteur de {g.key}"\n'
                    f'  value       = aws_lb.{g.label}.dns_name\n}}')
    return ([shared] if shared else []) + out, outs


def _gcp(ir: IR, gs, ports):
    region = ir.params("gcp").get("region", "europe-west9")
    probe = _probe_port(ports)
    plist = ", ".join(f'"{p}"' for p in ports)
    out, outs = [], []
    for g in gs:
        n = _slug(ir, g)
        out.append(f"# --- {g.key} : répartiteur\n" + align_attrs(f'''resource "google_compute_address" "lb_{g.label}" {{
  name   = "{n}-lb"
  region = "{region}"
}}

resource "google_compute_instance_group" "{g.label}" {{
  name      = "{n}"
  zone      = "{region}-a"
  instances = google_compute_instance.{g.label}[*].self_link
}}

resource "google_compute_region_health_check" "{g.label}" {{
  name   = "{n}"
  region = "{region}"

  tcp_health_check {{
    port = {probe}
  }}
}}

resource "google_compute_region_backend_service" "{g.label}" {{
  name                  = "{n}"
  region                = "{region}"
  protocol              = "TCP"
  load_balancing_scheme = "EXTERNAL"
  health_checks         = [google_compute_region_health_check.{g.label}.id]

  backend {{
    group          = google_compute_instance_group.{g.label}.id
    balancing_mode = "CONNECTION"
  }}
}}

resource "google_compute_forwarding_rule" "{g.label}" {{
  name                  = "{n}"
  region                = "{region}"
  ip_protocol           = "TCP"
  load_balancing_scheme = "EXTERNAL"
  ports                 = [{plist}]
  backend_service       = google_compute_region_backend_service.{g.label}.id
  ip_address            = google_compute_address.lb_{g.label}.address
}}'''))
        outs.append(f'output "lb_{g.label}" {{\n  description = "Adresse IP du répartiteur de {g.key}"\n'
                    f'  value       = google_compute_address.lb_{g.label}.address\n}}')
    return out, outs


def _azure(ir: IR, gs, ports):
    probe = _probe_port(ports)
    loc = ("location            = azurerm_resource_group.main.location\n"
           "  resource_group_name = azurerm_resource_group.main.name")
    out, outs = [], []
    for g in gs:
        n, c = _slug(ir, g), hosts._count(g)
        rules = "\n\n".join(f'''resource "azurerm_lb_rule" "{g.label}_{p}" {{
  loadbalancer_id                = azurerm_lb.{g.label}.id
  name                           = "tcp-{p}"
  protocol                       = "Tcp"
  frontend_port                  = {p}
  backend_port                   = {p}
  frontend_ip_configuration_name = "public"
  backend_address_pool_ids       = [azurerm_lb_backend_address_pool.{g.label}.id]
  probe_id                       = azurerm_lb_probe.{g.label}.id
}}''' for p in ports)
        out.append(f"# --- {g.key} : répartiteur\n" + f'''resource "azurerm_public_ip" "lb_{g.label}" {{
  name                = "pip-{n}-lb"
  {loc}
  allocation_method   = "Static"
  sku                 = "Standard"
}}

resource "azurerm_lb" "{g.label}" {{
  name                = "lb-{n}"
  {loc}
  sku                 = "Standard"

  frontend_ip_configuration {{
    name                 = "public"
    public_ip_address_id = azurerm_public_ip.lb_{g.label}.id
  }}
}}

resource "azurerm_lb_backend_address_pool" "{g.label}" {{
  loadbalancer_id = azurerm_lb.{g.label}.id
  name            = "hosts"
}}

resource "azurerm_lb_probe" "{g.label}" {{
  loadbalancer_id = azurerm_lb.{g.label}.id
  name            = "tcp-{probe}"
  protocol        = "Tcp"
  port            = {probe}
}}

{rules}

resource "azurerm_network_interface_backend_address_pool_association" "{g.label}" {{
  count                   = {c}
  network_interface_id    = azurerm_network_interface.{g.label}[count.index].id
  ip_configuration_name   = "ipconfig"
  backend_address_pool_id = azurerm_lb_backend_address_pool.{g.label}.id
}}''')
        outs.append(f'output "lb_{g.label}" {{\n  description = "Adresse IP du répartiteur de {g.key}"\n'
                    f'  value       = azurerm_public_ip.lb_{g.label}.ip_address\n}}')
    return out, outs


def _scaleway(ir: IR, gs, ports):
    out, outs = [], []
    for g in gs:
        n = _slug(ir, g)
        pairs = "\n\n".join(f'''resource "scaleway_lb_backend" "{g.label}_{p}" {{
  lb_id            = scaleway_lb.{g.label}.id
  name             = "tcp-{p}"
  forward_protocol = "tcp"
  forward_port     = {p}
  server_ips       = scaleway_instance_ip.{g.label}[*].address

  health_check_tcp {{}}
}}

resource "scaleway_lb_frontend" "{g.label}_{p}" {{
  lb_id        = scaleway_lb.{g.label}.id
  backend_id   = scaleway_lb_backend.{g.label}_{p}.id
  name         = "tcp-{p}"
  inbound_port = {p}
}}''' for p in ports)
        out.append(f"# --- {g.key} : répartiteur\n" + f'''resource "scaleway_lb_ip" "{g.label}" {{
}}

resource "scaleway_lb" "{g.label}" {{
  name   = "{n}"
  type   = "LB-S"
  ip_ids = [scaleway_lb_ip.{g.label}.id]
}}

{pairs}''')
        outs.append(f'output "lb_{g.label}" {{\n  description = "Adresse IP du répartiteur de {g.key}"\n'
                    f'  value       = scaleway_lb_ip.{g.label}.ip_address\n}}')
    return out, outs


def _ovh(ir: IR, gs, ports):
    out, outs = [], []
    for g in gs:
        n = _slug(ir, g)
        region = g.params.get("region", "GRA11")
        listeners = "\n\n".join(f'''resource "ovh_cloud_loadbalancer_listener" "{g.label}_{p}" {{
  service_name    = var.ovh_service_name
  loadbalancer_id = ovh_cloud_loadbalancer.{g.label}.id
  name            = "tcp-{p}"
  protocol        = "TCP"
  protocol_port   = {p}
  default_pool_id = ovh_cloud_loadbalancer_pool.{g.label}.id
}}''' for p in ports)
        out.append(f"# --- {g.key} : répartiteur\n" + f'''# Les instances ne sont pas encore rattachées au réseau privé : ajouter leurs adresses privées au pool avec
# ovh_cloud_loadbalancer_pool_member (address, protocol_port, subnet_id).
resource "ovh_cloud_loadbalancer" "{g.label}" {{
  service_name = var.ovh_service_name
  name         = "{n}"
  region       = "{region}"
  flavor_name  = "SMALL"

  network = {{
    id        = {network.OVH_NETWORK_ID}
    subnet_id = ovh_cloud_project_network_private_subnet.main.id
  }}
}}

resource "ovh_cloud_loadbalancer_pool" "{g.label}" {{
  service_name    = var.ovh_service_name
  loadbalancer_id = ovh_cloud_loadbalancer.{g.label}.id
  name            = "{n}"
  protocol        = "TCP"
  algorithm       = "ROUND_ROBIN"

  health_monitor = {{
    type        = "TCP"
    delay       = 5
    timeout     = 3
    max_retries = 3
  }}
}}

{listeners}''')
        outs.append(f'output "lb_{g.label}" {{\n  description = "Identifiant du répartiteur de {g.key}"\n'
                    f'  value       = ovh_cloud_loadbalancer.{g.label}.id\n}}')
    return out, outs


def _outscale(ir: IR, gs, ports):
    region = ir.params("outscale").get("region", "eu-west-2")
    vpc = network.present(ir, "outscale-net")
    probe = _probe_port(ports)
    out, outs = [], []
    for g in gs:
        n = _slug(ir, g)
        listeners = "\n\n".join(f'''  listeners {{
    backend_port           = {p}
    backend_protocol       = "TCP"
    load_balancer_port     = {p}
    load_balancer_protocol = "TCP"
  }}''' for p in ports)
        where = ('  load_balancer_type = "internet-facing"\n  subnets            = [outscale_subnet.main.subnet_id]\n'
                 '  security_groups    = [outscale_security_group.hosts.security_group_id]\n' if vpc
                 else f'  subregion_names    = ["{region}a"]\n')
        out.append(f"# --- {g.key} : répartiteur\n" + f'''resource "outscale_load_balancer" "{g.label}" {{
  load_balancer_name = "{n[:32]}"
{where}
{listeners}

  health_check = [{{
    healthy_threshold   = 3
    unhealthy_threshold = 3
    check_interval      = 30
    timeout             = 5
    protocol            = "TCP"
    port                = {probe}
  }}]
}}

resource "outscale_load_balancer_vms" "{g.label}" {{
  load_balancer_name = outscale_load_balancer.{g.label}.load_balancer_name
  backend_vm_ids     = outscale_vm.{g.label}[*].vm_id
}}''')
        outs.append(f'output "lb_{g.label}" {{\n  description = "Nom DNS du répartiteur de {g.key}"\n'
                    f'  value       = outscale_load_balancer.{g.label}.dns_name\n}}')
    return out, outs


RENDER = {"aws-elb": _aws, "gcp-lb": _gcp, "azure-lb": _azure, "scaleway-lb": _scaleway,
          "ovh-load-balancer": _ovh, "outscale-lbu": _outscale}


def terraform_blocks(ir: IR) -> tuple[list[str], list[str]]:
    """Blocs de main.tf et sorties des répartiteurs ; vide sans brique ou sans machines créées par la pile."""
    tid = tool(ir)
    if tid is None:
        return [], []
    ir.cover(tid)
    name = ir.catalog[tid].name
    if not hosts.creates_hosts(ir) or hosts.COMPUTE_PROVIDER.get(hosts.compute_tool(ir)) != LB[tid]:
        ir.notes.append(f"{name} : aucune machine n'est créée par la pile, donc aucun répartiteur n'est écrit. Sur "
                        "Kubernetes, le Service de type LoadBalancer ou l'entrée le demande au cloud.")
        return [], []
    ports = hosts._web_ports(ir)
    blocks, outs = RENDER[tid](ir, hosts.groups(ir), ports)
    ir.notes.append(f"{name} : un répartiteur TCP par groupe de machines (ports {', '.join(map(str, ports))}), sonde "
                    f"TCP sur le port {_probe_port(ports)} ; le DNS pointe vers sa sortie « lb_<groupe> ».")
    if tid == "ovh-load-balancer":
        ir.notes.append("OVHcloud Load Balancer : ajouter les adresses privées des machines au pool "
                        "(ovh_cloud_loadbalancer_pool_member) : les instances ne sont pas encore sur le réseau privé.")
    return [f"# --- {name}\n" + "\n\n".join(b for b in blocks if b)], outs
