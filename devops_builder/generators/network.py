# SPDX-License-Identifier: Apache-2.0
"""Réseau privé du projet (capacité « réseau privé » de la 1.1).

Une brique par cloud (aws-vpc, gcp-vpc, azure-vnet, scaleway-vpc, ovh-private-network, outscale-net) crée le réseau
une seule fois dans la pile OpenTofu. Les clusters, les machines et les bases managées du projet s'y rattachent :
leurs ressources lisent ce réseau au lieu d'attendre des identifiants saisis à la main (VPC, sous-réseaux,
groupe de sous-réseaux RDS…). Sans la brique, rien ne change : AWS demande toujours les variables, les autres
clouds gardent leur réseau par défaut.

Les sous-réseaux sont calculés ici et écrits en clair dans main.tf : la plage choisie reste lisible dans la pile.
"""

from __future__ import annotations

import ipaddress

from ..ir import IR

NETWORK = {"aws-vpc": "aws", "gcp-vpc": "gcp", "azure-vnet": "azure", "scaleway-vpc": "scaleway",
           "ovh-private-network": "ovhcloud", "outscale-net": "outscale"}


def tool(ir: IR) -> str | None:
    return next((t for t in NETWORK if ir.has(t)), None)


def present(ir: IR, tool_id: str | None = None) -> bool:
    return tool(ir) == tool_id if tool_id else tool(ir) is not None


def _net(ir: IR, tool_id: str) -> ipaddress.IPv4Network:
    return ipaddress.ip_network(str(ir.params(tool_id).get("cidr")), strict=False)


def _subnets(net: ipaddress.IPv4Network, bits: int) -> list[ipaddress.IPv4Network]:
    return list(net.subnets(new_prefix=min(net.prefixlen + bits, 28)))


def _list(items) -> str:
    return "[" + ", ".join(f'"{i}"' for i in items) + "]"


# ------------------------------------------------------------------ AWS
def aws_nat(ir: IR) -> bool:
    choice = str(ir.params("aws-vpc").get("nat") or "auto")
    return choice == "oui" or (choice == "auto" and ir.has("eks"))


def _aws_has_rds(ir: IR) -> bool:
    from .data import managed_dbs
    return any(d.id == "aws-rds" for d in managed_dbs(ir))


def _aws(ir: IR) -> tuple[list[str], list[str]]:
    app = ir.app
    net = _net(ir, "aws-vpc")
    subs = _subnets(net, 4)
    region = ir.params("aws").get("region", "eu-west-3")
    nat = aws_nat(ir)
    blocks = [f'''# Deux zones de disponibilité : les sous-réseaux publics portent les machines et les répartiteurs, les
# sous-réseaux privés le cluster et les bases (sans adresse publique).
locals {{
  vpc_azs              = ["{region}a", "{region}b"]
  public_subnet_cidrs  = {_list(subs[0:2])}
  private_subnet_cidrs = {_list(subs[2:4])}
}}

resource "aws_vpc" "main" {{
  cidr_block           = "{net}"
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {{
    Name = "{app}"
  }}
}}

resource "aws_internet_gateway" "main" {{
  vpc_id = aws_vpc.main.id

  tags = {{
    Name = "{app}"
  }}
}}

resource "aws_subnet" "public" {{
  count                   = 2
  vpc_id                  = aws_vpc.main.id
  cidr_block              = local.public_subnet_cidrs[count.index]
  availability_zone       = local.vpc_azs[count.index]
  map_public_ip_on_launch = true

  tags = {{
    Name                     = "{app}-public-${{count.index + 1}}"
    "kubernetes.io/role/elb" = "1"
  }}
}}

resource "aws_subnet" "private" {{
  count             = 2
  vpc_id            = aws_vpc.main.id
  cidr_block        = local.private_subnet_cidrs[count.index]
  availability_zone = local.vpc_azs[count.index]

  tags = {{
    Name                              = "{app}-private-${{count.index + 1}}"
    "kubernetes.io/role/internal-elb" = "1"
  }}
}}

resource "aws_route_table" "public" {{
  vpc_id = aws_vpc.main.id

  route {{
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }}

  tags = {{
    Name = "{app}-public"
  }}
}}

resource "aws_route_table_association" "public" {{
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}}''']
    if nat:
        blocks.append(f'''# Sortie vers Internet des sous-réseaux privés (images, mises à jour) : une seule passerelle NAT, facturée à
# l'heure ; passer « Sortie vers Internet » à « non » dans la brique pour s'en passer.
resource "aws_eip" "nat" {{
  domain = "vpc"
}}

resource "aws_nat_gateway" "main" {{
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public[0].id

  tags = {{
    Name = "{app}"
  }}

  depends_on = [aws_internet_gateway.main]
}}

resource "aws_route_table" "private" {{
  vpc_id = aws_vpc.main.id

  route {{
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.main.id
  }}

  tags = {{
    Name = "{app}-private"
  }}
}}

resource "aws_route_table_association" "private" {{
  count          = 2
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}}''')
    if _aws_has_rds(ir):
        blocks.append(f'''# Bases RDS : sous-réseaux privés, joignables depuis tout le réseau (restreindre à un groupe de sécurité de
# l'application si besoin).
resource "aws_db_subnet_group" "main" {{
  name       = "{app}-db"
  subnet_ids = aws_subnet.private[*].id
}}

resource "aws_security_group" "db" {{
  name        = "{app}-db"
  description = "Accès aux bases depuis le réseau {net}"
  vpc_id      = aws_vpc.main.id

  ingress {{
    description = "PostgreSQL"
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = [aws_vpc.main.cidr_block]
  }}

  ingress {{
    description = "MySQL et MariaDB"
    from_port   = 3306
    to_port     = 3306
    protocol    = "tcp"
    cidr_blocks = [aws_vpc.main.cidr_block]
  }}
}}''')
    outs = ['output "vpc_id" {\n  value = aws_vpc.main.id\n}',
            'output "public_subnet_ids" {\n  value = aws_subnet.public[*].id\n}',
            'output "private_subnet_ids" {\n  value = aws_subnet.private[*].id\n}']
    if not nat and ir.has("eks"):
        ir.notes.append("Amazon VPC : sans passerelle NAT, les nœuds du cluster (sous-réseaux privés) ne peuvent pas "
                        "télécharger d'images : remettre « Sortie vers Internet » à « auto » ou « oui ».")
    elif nat:
        ir.notes.append("Amazon VPC : une passerelle NAT est créée (facturée à l'heure), pour la sortie vers Internet "
                        "des sous-réseaux privés.")
    return blocks, outs


# ------------------------------------------------------------------ Google Cloud
def _gcp(ir: IR) -> tuple[list[str], list[str]]:
    app = ir.app
    p = ir.params("gcp-vpc")
    net = _net(ir, "gcp-vpc")
    region = ir.params("gcp").get("region", "europe-west9")
    blocks = [f'''resource "google_compute_network" "main" {{
  name                    = "{app}"
  auto_create_subnetworks = false
}}

resource "google_compute_subnetwork" "main" {{
  name                     = "{app}"
  region                   = "{region}"
  network                  = google_compute_network.main.id
  ip_cidr_range            = "{net}"
  private_ip_google_access = true
}}''']
    if str(p.get("nat") or "non") == "oui":
        blocks.append(f'''# Sortie vers Internet des machines sans adresse publique (Cloud NAT, facturé à l'usage).
resource "google_compute_router" "main" {{
  name    = "{app}"
  region  = "{region}"
  network = google_compute_network.main.id
}}

resource "google_compute_router_nat" "main" {{
  name                               = "{app}"
  router                             = google_compute_router.main.name
  region                             = "{region}"
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"
}}''')
    if ir.has("cloud-sql"):
        blocks.append(f'''# Cloud SQL en adresse privée : accès aux services Google par appairage du réseau (l'API Service Networking
# doit être activée dans le projet).
resource "google_compute_global_address" "private_services" {{
  name          = "{app}-private-services"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.main.id
}}

resource "google_service_networking_connection" "private_services" {{
  network                 = google_compute_network.main.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_services.name]
}}''')
    outs = ['output "network" {\n  value = google_compute_network.main.name\n}',
            'output "subnetwork" {\n  value = google_compute_subnetwork.main.name\n}']
    return blocks, outs


# ------------------------------------------------------------------ Azure
def azure_data_engine(ir: IR) -> str | None:
    from .data import managed_dbs
    for d in managed_dbs(ir):
        if d.id == "azure-database":
            return "mysql" if str(ir.params("azure-database").get("engine") or "postgres") == "mysql" else "postgres"
    return None


def _azure(ir: IR) -> tuple[list[str], list[str]]:
    from .hosts import creates_hosts
    app = ir.app
    net = _net(ir, "azure-vnet")
    small = _subnets(net, 8)
    wide = list(net.subnets(new_prefix=min(net.prefixlen + 6, 28)))
    rg = ("location            = azurerm_resource_group.main.location\n"
          "  resource_group_name = azurerm_resource_group.main.name")
    blocks = [f'''resource "azurerm_virtual_network" "main" {{
  name                = "vnet-{app}"
  address_space       = ["{net}"]
  {rg}
}}''']
    subnets: list[str] = []
    if creates_hosts(ir):
        subnets.append(f'''resource "azurerm_subnet" "hosts" {{
  name                 = "snet-hosts"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["{small[1]}"]
}}''')
    if ir.has("aks"):
        subnets.append(f'''resource "azurerm_subnet" "aks" {{
  name                 = "snet-aks"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["{wide[1]}"]
}}''')
    engine = azure_data_engine(ir)
    if engine:
        svc = "Microsoft.DBforMySQL/flexibleServers" if engine == "mysql" else "Microsoft.DBforPostgreSQL/flexibleServers"
        zone = "privatelink.mysql.database.azure.com" if engine == "mysql" else "privatelink.postgres.database.azure.com"
        subnets.append(f'''# Bases managées : sous-réseau délégué aux serveurs flexibles, zone DNS privée pour leur nom.
resource "azurerm_subnet" "data" {{
  name                 = "snet-data"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["{small[3]}"]

  delegation {{
    name = "flexible-server"

    service_delegation {{
      name    = "{svc}"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }}
  }}
}}

resource "azurerm_private_dns_zone" "data" {{
  name                = "{zone}"
  resource_group_name = azurerm_resource_group.main.name
}}

resource "azurerm_private_dns_zone_virtual_network_link" "data" {{
  name                  = "vnet-{app}"
  resource_group_name   = azurerm_resource_group.main.name
  private_dns_zone_name = azurerm_private_dns_zone.data.name
  virtual_network_id    = azurerm_virtual_network.main.id
}}''')
    if not subnets:
        subnets.append(f'''resource "azurerm_subnet" "default" {{
  name                 = "snet-default"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["{small[1]}"]
}}''')
    blocks += subnets
    return blocks, ['output "vnet_id" {\n  value = azurerm_virtual_network.main.id\n}']


# ------------------------------------------------------------------ Scaleway
def _scaleway(ir: IR) -> tuple[list[str], list[str]]:
    net = _net(ir, "scaleway-vpc")
    blocks = [f'''resource "scaleway_vpc_private_network" "main" {{
  name = "{ir.app}"

  ipv4_subnet {{
    subnet = "{net}"
  }}
}}''']
    return blocks, ['output "private_network_id" {\n  value = scaleway_vpc_private_network.main.id\n}']


# ------------------------------------------------------------------ OVHcloud
OVH_NETWORK_ID = "tolist(ovh_cloud_project_network_private.main.regions_attributes[*].openstackid)[0]"


def _ovh(ir: IR) -> tuple[list[str], list[str]]:
    p = ir.params("ovh-private-network")
    net = _net(ir, "ovh-private-network")
    region = p.get("region", "GRA11")
    hosts = list(net.hosts())
    start = hosts[max(9, len(hosts) // 3)]
    end = hosts[-1]
    blocks = [f'''resource "ovh_cloud_project_network_private" "main" {{
  service_name = var.ovh_service_name
  name         = "{ir.app}"
  regions      = ["{region}"]
  vlan_id      = 10
}}

resource "ovh_cloud_project_network_private_subnet" "main" {{
  service_name = var.ovh_service_name
  network_id   = ovh_cloud_project_network_private.main.id
  region       = "{region}"
  network      = "{net}"
  start        = "{start}"
  end          = "{end}"
  dhcp         = true
  no_gateway   = false
}}''']
    return blocks, ['output "private_network_id" {\n  value = ovh_cloud_project_network_private.main.id\n}']


# ------------------------------------------------------------------ Outscale
def _outscale(ir: IR) -> tuple[list[str], list[str]]:
    net = _net(ir, "outscale-net")
    subnet = _subnets(net, 8)[0]
    region = ir.params("outscale").get("region", "eu-west-2")
    name = '  tags {\n    key   = "name"\n    value = "%s"\n  }' % ir.app
    blocks = [f'''resource "outscale_net" "main" {{
  ip_range = "{net}"

{name}
}}

resource "outscale_subnet" "main" {{
  net_id         = outscale_net.main.net_id
  ip_range       = "{subnet}"
  subregion_name = "{region}a"
}}

# Sortie vers Internet : service Internet du Net, route par défaut de la table associée au sous-réseau.
resource "outscale_internet_service" "main" {{
}}

resource "outscale_internet_service_link" "main" {{
  internet_service_id = outscale_internet_service.main.internet_service_id
  net_id              = outscale_net.main.net_id
}}

resource "outscale_route_table" "main" {{
  net_id = outscale_net.main.net_id
}}

resource "outscale_route" "internet" {{
  route_table_id       = outscale_route_table.main.route_table_id
  gateway_id           = outscale_internet_service.main.internet_service_id
  destination_ip_range = "0.0.0.0/0"

  depends_on = [outscale_internet_service_link.main]
}}

resource "outscale_route_table_link" "main" {{
  subnet_id      = outscale_subnet.main.subnet_id
  route_table_id = outscale_route_table.main.route_table_id
}}''']
    return blocks, ['output "net_id" {\n  value = outscale_net.main.net_id\n}',
                    'output "subnet_id" {\n  value = outscale_subnet.main.subnet_id\n}']


RENDER = {"aws-vpc": _aws, "gcp-vpc": _gcp, "azure-vnet": _azure, "scaleway-vpc": _scaleway,
          "ovh-private-network": _ovh, "outscale-net": _outscale}


def terraform_blocks(ir: IR) -> tuple[list[str], list[str]]:
    """Blocs de main.tf et sorties du réseau ; vide sans brique réseau. Les blocs portent leur titre."""
    tid = tool(ir)
    if tid is None:
        return [], []
    blocks, outs = RENDER[tid](ir)
    name = ir.catalog[tid].name
    ir.cover(tid)
    return [f"# --- {name}\n" + "\n\n".join(blocks)], outs


def host_note(ir: IR) -> None:
    """Machines OVHcloud : le rattachement au réseau privé n'est pas encore écrit."""
    if present(ir, "ovh-private-network") and ir.has("ovh-instance"):
        ir.notes.append("OVHcloud Private Network : les instances restent sur le réseau public ; rattacher le réseau "
                        "privé aux machines à la main (bloc network de ovh_cloud_project_instance).")
