# SPDX-License-Identifier: Apache-2.0
"""DNS du projet (capacité « DNS » de la 1.1) : la zone du domaine et un enregistrement par groupe de machines.

Une brique par cloud qui a un service DNS (aws-route53, gcp-dns, azure-dns, scaleway-domains) ; OVHcloud (hors
Public Cloud) et Outscale n'en ont pas. L'enregistrement pointe vers le répartiteur de charge du projet s'il existe
(alias chez AWS), sinon vers l'adresse publique des machines. Le groupe de la production reçoit le nom choisi dans la
brique (« boutique » → boutique.exemple.fr), les autres groupes ce nom suffixé. La zone est créée par la pile, sauf
chez Scaleway où le domaine, géré par Scaleway, existe déjà : seuls les enregistrements y sont écrits.
"""

from __future__ import annotations

import re
from collections import defaultdict

from ..ir import IR
from . import hosts, lb
from .common import align_attrs

DNS = {"aws-route53": "aws", "gcp-dns": "gcp", "azure-dns": "azure", "scaleway-domains": "scaleway"}


def tool(ir: IR) -> str | None:
    return next((t for t in DNS if ir.has(t)), None)


def _record(ir: IR, tid: str, g) -> str:
    base = str(ir.params(tid).get("record") or ir.app)
    prod = any(e.kind == "production" for e in g.envs)
    return base if prod else f"{base}-{re.sub(r'[^a-z0-9-]', '-', g.key.lower())}"


def _balancer(ir: IR, tid: str) -> bool:
    lb_tool = lb.tool(ir)
    return bool(lb_tool and lb.LB[lb_tool] == DNS[tid] and hosts.creates_hosts(ir))


def _aws(ir, tid, p, zone, ttl, targets, balanced):
    blocks = [f'resource "aws_route53_zone" "main" {{\n  name = "{zone}"\n}}']
    for g in hosts.groups(ir):
        name = f"{_record(ir, tid, g)}.{zone}"
        if balanced:
            body = (f'  alias {{\n    name                   = aws_lb.{g.label}.dns_name\n'
                    f'    zone_id                = aws_lb.{g.label}.zone_id\n    evaluate_target_health = true\n  }}')
        else:
            body = f"  ttl     = {ttl}\n  records = {targets[g.key]}"
        blocks.append(align_attrs(f'''resource "aws_route53_record" "{g.label}" {{
  zone_id = aws_route53_zone.main.zone_id
  name    = "{name}"
  type    = "A"
{body}
}}''') if not balanced else f'''resource "aws_route53_record" "{g.label}" {{
  zone_id = aws_route53_zone.main.zone_id
  name    = "{name}"
  type    = "A"

{body}
}}''')
    return blocks, ['output "dns_name_servers" {\n  description = "Serveurs de noms à indiquer chez le registrar du domaine"\n'
                    '  value       = aws_route53_zone.main.name_servers\n}']


def _gcp(ir, tid, p, zone, ttl, targets, balanced):
    blocks = [align_attrs(f'''resource "google_dns_managed_zone" "main" {{
  name        = "{zone.replace(".", "-")}"
  dns_name    = "{zone}."
  description = "Zone de {ir.app}"
}}''')]
    for g in hosts.groups(ir):
        rr = f"[google_compute_address.lb_{g.label}.address]" if balanced else targets[g.key]
        blocks.append(align_attrs(f'''resource "google_dns_record_set" "{g.label}" {{
  managed_zone = google_dns_managed_zone.main.name
  name         = "{_record(ir, tid, g)}.{zone}."
  type         = "A"
  ttl          = {ttl}
  rrdatas      = {rr}
}}'''))
    return blocks, ['output "dns_name_servers" {\n  description = "Serveurs de noms à indiquer chez le registrar du domaine"\n'
                    '  value       = google_dns_managed_zone.main.name_servers\n}']


def _azure(ir, tid, p, zone, ttl, targets, balanced):
    rg = "azurerm_resource_group.main.name"
    blocks = [align_attrs(f'resource "azurerm_dns_zone" "main" {{\n  name                = "{zone}"\n  resource_group_name = {rg}\n}}')]
    for g in hosts.groups(ir):
        recs = f"[azurerm_public_ip.lb_{g.label}.ip_address]" if balanced else targets[g.key]
        blocks.append(align_attrs(f'''resource "azurerm_dns_a_record" "{g.label}" {{
  name                = "{_record(ir, tid, g)}"
  zone_name           = azurerm_dns_zone.main.name
  resource_group_name = {rg}
  ttl                 = {ttl}
  records             = {recs}
}}'''))
    return blocks, ['output "dns_name_servers" {\n  description = "Serveurs de noms à indiquer chez le registrar du domaine"\n'
                    '  value       = azurerm_dns_zone.main.name_servers\n}']


def _scaleway(ir, tid, p, zone, ttl, targets, balanced):
    blocks = []
    for g in hosts.groups(ir):
        data = f"scaleway_lb_ip.{g.label}.ip_address" if balanced else f"tolist({targets[g.key]})[0]"
        blocks.append(align_attrs(f'''resource "scaleway_domain_record" "{g.label}" {{
  dns_zone = "{zone}"
  name     = "{_record(ir, tid, g)}"
  type     = "A"
  data     = {data}
  ttl      = {ttl}
}}'''))
    return blocks, []


RENDER = {"aws-route53": _aws, "gcp-dns": _gcp, "azure-dns": _azure, "scaleway-domains": _scaleway}


def terraform_blocks(ir: IR) -> tuple[list[str], list[str]]:
    """Blocs de main.tf et sorties du DNS ; la zone est écrite même sans machines, les enregistrements non."""
    tid = tool(ir)
    if tid is None:
        return [], []
    ir.cover(tid)
    name = ir.catalog[tid].name
    p = ir.params(tid)
    zone = str(p.get("zone"))
    ttl = int(p.get("ttl") or 300)
    machines = hosts.creates_hosts(ir) and hosts.COMPUTE[hosts.compute_tool(ir)] == DNS[tid]
    targets = hosts.address_exprs(ir) if machines else {}
    balanced = machines and _balancer(ir, tid)
    if machines:
        blocks, outs = RENDER[tid](ir, tid, p, zone, ttl, targets, balanced)
        where = "le répartiteur de charge" if balanced else "l'adresse publique des machines"
        ir.notes.append(f"{name} : un enregistrement A par groupe de machines vers {where} (production : "
                        f"{_record(ir, tid, hosts.groups(ir)[0])}.{zone}).")
    else:
        blocks, outs = ([], [])
        if tid != "scaleway-domains":
            blocks, outs = RENDER[tid](ir, tid, p, zone, ttl, defaultdict(lambda: "[]"), False)
            blocks = blocks[:1]   # la zone seule
        ir.notes.append(f"{name} : aucune machine n'est créée par la pile, donc aucun enregistrement n'est écrit "
                        "(Kubernetes : les enregistrements viennent du Service ou de l'entrée, par external-dns par exemple).")
    if tid == "scaleway-domains":
        ir.notes.append(f"Scaleway Domains and DNS : le domaine {zone} doit déjà être géré par Scaleway (zone existante) ; "
                        "seuls les enregistrements sont écrits.")
    elif outs:
        ir.notes.append(f"{name} : déléguer {zone} chez le registrar avec les serveurs de noms de la sortie dns_name_servers.")
    return ([f"# --- {name}\n" + "\n\n".join(blocks)] if blocks else []), outs
