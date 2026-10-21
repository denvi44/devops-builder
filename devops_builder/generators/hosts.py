# SPDX-License-Identifier: Apache-2.0
"""Machines virtuelles créées par Terraform / OpenTofu, et chaînage vers Ansible ou le déploiement SSH.

Un groupe de machines par environnement — ou par hôte partagé, quand des environnements indiquent le
même « Hôte Docker partagé ». Chaque machine reçoit, par cloud-init, le compte de déploiement et la
clé publique de la CI. La sortie Terraform « hosts » ({groupe: [adresses]}) est lue au déploiement par
scripts/tf-inventory.sh, qui écrit l'inventaire Ansible de l'environnement (ou donne l'adresse au
déploiement SSH) : l'inventaire suit la pile sans être recopié à la main.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass

from ..ir import IR
from . import network
from .common import HEADER, align_attrs

COMPUTE = {"aws-ec2": "aws", "gce": "gcp", "azure-vm": "azure", "scaleway-instance": "scaleway",
           "ovh-instance": "ovhcloud", "outscale-vm": "outscale"}
COMPUTE_PROVIDER = COMPUTE
INVENTORY_SCRIPT = "scripts/tf-inventory.sh"


@dataclass
class HostGroup:
    key: str          # nom du groupe (hôte partagé ou identifiant d'environnement)
    label: str        # suffixe d'étiquette Terraform
    envs: list        # environnements servis
    params: dict


def compute_tool(ir: IR) -> str | None:
    return next((t for t in COMPUTE if ir.has(t)), None)


def creates_hosts(ir: IR) -> bool:
    """Les hôtes de déploiement sont créés par la pile Terraform du projet."""
    return (compute_tool(ir) is not None and ir.project.target in ("docker-host", "vm")
            and bool(ir.iac and ir.iac.id in ("terraform", "opentofu")))


def deploy_user(ir: IR) -> str:
    return str(ir.params("ansible").get("user") or "deploy") if ir.has("ansible") else "deploy"


def groups(ir: IR) -> list[HostGroup]:
    tool = compute_tool(ir)
    out: dict[str, HostGroup] = {}
    ordered = [e for e in ir.envs if e.kind == "production"] + [e for e in ir.envs if e.kind != "production"]
    for env in ordered:
        key = env.host.strip() or env.id
        if key not in out:
            label = re.sub(r"[^a-z0-9_]", "_", key.lower())
            out[key] = HostGroup(key, label, [], ir.params(tool, env) if tool else {})
        out[key].envs.append(env)
    keys = [env.host.strip() or env.id for env in ir.envs]
    return sorted(out.values(), key=lambda g: keys.index(g.key))


def group_of(env) -> str:
    return env.host.strip() or env.id


def _web_ports(ir: IR) -> list[int]:
    if ir.has("traefik"):
        return [80, 443]
    return sorted({80, 443, ir.project.app.port})


def _cidrs(params: dict) -> str:
    items = [c.strip() for c in str(params.get("ssh_cidrs") or "0.0.0.0/0").split(",") if c.strip()]
    return "[" + ", ".join(f'"{c}"' for c in items) + "]"


def terraform_blocks(ir: IR) -> tuple[list[str], list[str]]:
    """Blocs de main.tf et sorties pour les machines ; vide si la pile ne crée pas les hôtes."""
    if not creates_hosts(ir):
        return [], []
    tool = compute_tool(ir)
    gs = groups(ir)
    user = deploy_user(ir)
    cidrs = _cidrs(gs[0].params)
    blocks = [f'''# --- Machines de déploiement (Ubuntu 24.04) : cloud-init pose le compte « {user} », la clé de la CI
# et Docker avec son extension Compose.
locals {{
  ssh_cidrs  = {cidrs}
  cloud_init = <<-EOT
    #cloud-config
    users:
      - name: {user}
        sudo: "ALL=(ALL) NOPASSWD:ALL"
        shell: /bin/bash
        ssh_authorized_keys:
          - ${{var.ssh_public_key}}
    package_update: true
    packages:
      - docker.io
      - docker-compose-v2
    runcmd:
      - systemctl enable --now docker
      - usermod -aG docker {user}
  EOT
}}''']
    shared, per_group, ip = _renderer(tool)(ir, gs)
    blocks.append(f"# --- {ir.catalog[tool].name} : réseau et accès\n{shared}")
    for g in gs:
        envs = ", ".join(e.display for e in g.envs)
        blocks.append(f"# --- {ir.catalog[tool].name} : {g.key} ({envs})\n{per_group(g)}")
    width = max(len(g.key) for g in gs) + 2
    entries = "\n".join("    " + f'"{g.key}"'.ljust(width) + f" = {ip(g)}" for g in gs)
    output = (f'output "hosts" {{\n  description = "Adresses publiques des machines, par groupe ({INVENTORY_SCRIPT})"\n'
              f"  value = {{\n{entries}\n  }}\n}}")
    ir.cover(tool)
    return blocks, [output]


def _renderer(tool: str):
    return {"aws-ec2": _aws, "gce": _gce, "azure-vm": _azure, "scaleway-instance": _scaleway,
            "ovh-instance": _ovh, "outscale-vm": _outscale}[tool]


def address_exprs(ir: IR) -> dict[str, str]:
    """Expression OpenTofu (liste d'adresses publiques) des machines de chaque groupe ; vide sans machines créées."""
    if not creates_hosts(ir):
        return {}
    gs = groups(ir)
    _shared, _per_group, ip = _renderer(compute_tool(ir))(ir, gs)
    return {g.key: ip(g) for g in gs}


def _name(ir: IR, g: HostGroup) -> str:
    return f"{ir.app}-{re.sub(r'[^a-z0-9-]', '-', g.key.lower())}"


def _count(g: HostGroup) -> int:
    return max(1, int(g.params.get("count") or 1))


# ------------------------------------------------------------------ fournisseurs
def _aws(ir: IR, gs: list[HostGroup]):
    vpc = "\n  vpc_id      = aws_vpc.main.id" if network.present(ir, "aws-vpc") else ""
    subnet = ("\n  subnet_id              = aws_subnet.public[count.index % 2].id"
              if network.present(ir, "aws-vpc") else "")
    ingress = "\n\n".join(
        f'  ingress {{\n    description = "{d}"\n    from_port   = {p}\n    to_port     = {p}\n    protocol    = "tcp"\n'
        f"    cidr_blocks = {c}\n  }}"
        for d, p, c in [("SSH", 22, "local.ssh_cidrs"), *[(f"Port {p}", p, '["0.0.0.0/0"]') for p in _web_ports(ir)]])
    shared = f'''data "aws_ami" "ubuntu" {{
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {{
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
  }}
}}

resource "aws_key_pair" "deploy" {{
  key_name   = "{ir.app}-deploy"
  public_key = var.ssh_public_key
}}

resource "aws_security_group" "hosts" {{
  name        = "{ir.app}-hosts"
  description = "SSH depuis local.ssh_cidrs, web depuis Internet"{vpc}

{ingress}

  egress {{
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }}
}}'''

    def per_group(g: HostGroup) -> str:
        kms_disk = "\n    kms_key_id  = aws_kms_key.main.arn" if ir.has("aws-kms") else ""
        return f'''resource "aws_instance" "{g.label}" {{
  count                  = {_count(g)}
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = "{g.params.get("instance_type", "t3.small")}"
  key_name               = aws_key_pair.deploy.key_name
  vpc_security_group_ids = [aws_security_group.hosts.id]{subnet}
  user_data              = local.cloud_init

  metadata_options {{
    http_tokens = "required"
  }}

  root_block_device {{
    volume_size = {int(g.params.get("disk_gb") or 30)}
    volume_type = "gp3"
    encrypted   = true{kms_disk}
  }}

  tags = {{
    Name                   = "{_name(ir, g)}-${{count.index + 1}}"
    "devops-builder:hosts" = "{g.key}"
  }}
}}'''
    return shared, per_group, lambda g: f"aws_instance.{g.label}[*].public_ip"


def _gce(ir: IR, gs: list[HostGroup]):
    ports = ", ".join(f'"{p}"' for p in _web_ports(ir))
    vpc = network.present(ir, "gcp-vpc")
    net = "google_compute_network.main.name" if vpc else '"default"'
    nic = ("    network    = google_compute_network.main.id\n    subnetwork = google_compute_subnetwork.main.id"
           if vpc else '    network = "default"')
    shared = f'''resource "google_compute_firewall" "ssh" {{
  name          = "{ir.app}-ssh"
  network       = {net}
  source_ranges = local.ssh_cidrs
  target_tags   = ["{ir.app}"]

  allow {{
    protocol = "tcp"
    ports    = ["22"]
  }}
}}

resource "google_compute_firewall" "web" {{
  name          = "{ir.app}-web"
  network       = {net}
  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["{ir.app}"]

  allow {{
    protocol = "tcp"
    ports    = [{ports}]
  }}
}}'''
    region = ir.params("gcp").get("region", "europe-west9")

    def per_group(g: HostGroup) -> str:
        return f'''resource "google_compute_instance" "{g.label}" {{
  count        = {_count(g)}
  name         = "{_name(ir, g)}-${{count.index + 1}}"
  machine_type = "{g.params.get("instance_type", "e2-small")}"
  zone         = "{region}-a"
  tags         = ["{ir.app}"]

  boot_disk {{
    initialize_params {{
      image = "ubuntu-os-cloud/ubuntu-2404-lts-amd64"
      size  = {int(g.params.get("disk_gb") or 30)}
    }}
  }}

  network_interface {{
{nic}
    access_config {{}}
  }}

  metadata = {{
    user-data = local.cloud_init
  }}

  shielded_instance_config {{
    enable_secure_boot = true
  }}
}}'''
    return shared, per_group, lambda g: (f"[for vm in google_compute_instance.{g.label} : "
                                         "vm.network_interface[0].access_config[0].nat_ip]")


def _azure(ir: IR, gs: list[HostGroup]):
    web = ", ".join(f'"{p}"' for p in _web_ports(ir))
    vnet = f'''resource "azurerm_virtual_network" "hosts" {{
  name                = "vnet-{ir.app}"
  address_space       = ["10.20.0.0/16"]
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
}}

resource "azurerm_subnet" "hosts" {{
  name                 = "snet-hosts"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.hosts.name
  address_prefixes     = ["10.20.1.0/24"]
}}
'''
    if network.present(ir, "azure-vnet"):
        vnet = ""   # le réseau et le sous-réseau « hosts » viennent de la brique Azure Virtual Network
    shared = vnet + f'''
resource "azurerm_network_security_group" "hosts" {{
  name                = "nsg-{ir.app}-hosts"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name

  security_rule {{
    name                       = "ssh"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "22"
    source_address_prefixes    = local.ssh_cidrs
    destination_address_prefix = "*"
  }}

  security_rule {{
    name                       = "web"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_ranges    = [{web}]
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }}
}}

resource "azurerm_subnet_network_security_group_association" "hosts" {{
  subnet_id                 = azurerm_subnet.hosts.id
  network_security_group_id = azurerm_network_security_group.hosts.id
}}'''
    shared = shared.lstrip("\n")
    user = deploy_user(ir)

    def per_group(g: HostGroup) -> str:
        n, c = _name(ir, g), _count(g)
        return f'''resource "azurerm_public_ip" "{g.label}" {{
  count               = {c}
  name                = "pip-{n}-${{count.index + 1}}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  allocation_method   = "Static"
  sku                 = "Standard"
}}

resource "azurerm_network_interface" "{g.label}" {{
  count               = {c}
  name                = "nic-{n}-${{count.index + 1}}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name

  ip_configuration {{
    name                          = "ipconfig"
    subnet_id                     = azurerm_subnet.hosts.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.{g.label}[count.index].id
  }}
}}

resource "azurerm_linux_virtual_machine" "{g.label}" {{
  count                 = {c}
  name                  = "vm-{n}-${{count.index + 1}}"
  location              = azurerm_resource_group.main.location
  resource_group_name   = azurerm_resource_group.main.name
  size                  = "{g.params.get("instance_type", "Standard_B2s")}"
  admin_username        = "{user}"
  network_interface_ids = [azurerm_network_interface.{g.label}[count.index].id]

  admin_ssh_key {{
    username   = "{user}"
    public_key = var.ssh_public_key
  }}

  os_disk {{
    caching              = "ReadWrite"
    storage_account_type = "StandardSSD_LRS"
    disk_size_gb         = {int(g.params.get("disk_gb") or 30)}
  }}

  source_image_reference {{
    publisher = "Canonical"
    offer     = "ubuntu-24_04-lts"
    sku       = "server"
    version   = "latest"
  }}
}}'''
    return shared, per_group, lambda g: f"azurerm_public_ip.{g.label}[*].ip_address"


def _scaleway(ir: IR, gs: list[HostGroup]):
    web = "\n\n".join(f'  inbound_rule {{\n    action = "accept"\n    port   = {p}\n  }}' for p in _web_ports(ir))
    shared = f'''resource "scaleway_iam_ssh_key" "deploy" {{
  name       = "{ir.app}-deploy"
  public_key = var.ssh_public_key
}}

resource "scaleway_instance_security_group" "hosts" {{
  name                    = "{ir.app}-hosts"
  inbound_default_policy  = "drop"
  outbound_default_policy = "accept"

  dynamic "inbound_rule" {{
    for_each = local.ssh_cidrs
    content {{
      action   = "accept"
      port     = 22
      ip_range = inbound_rule.value
    }}
  }}

{web}
}}'''

    pn = ("\n\n  private_network {\n    pn_id = scaleway_vpc_private_network.main.id\n  }"
          if network.present(ir, "scaleway-vpc") else "")

    def per_group(g: HostGroup) -> str:
        c = _count(g)
        return f'''resource "scaleway_instance_ip" "{g.label}" {{
  count = {c}
}}

resource "scaleway_instance_server" "{g.label}" {{
  count             = {c}
  name              = "{_name(ir, g)}-${{count.index + 1}}"
  type              = "{g.params.get("instance_type", "PLAY2-NANO")}"
  image             = "ubuntu_noble"
  ip_id             = scaleway_instance_ip.{g.label}[count.index].id
  security_group_id = scaleway_instance_security_group.hosts.id{pn}
  user_data = {{
    cloud-init = local.cloud_init
  }}

  root_volume {{
    size_in_gb = {int(g.params.get("disk_gb") or 30)}
  }}

  depends_on = [scaleway_iam_ssh_key.deploy]
}}'''
    return shared, per_group, lambda g: f"scaleway_instance_ip.{g.label}[*].address"


def _ovh(ir: IR, gs: list[HostGroup]):
    p0 = gs[0].params
    region = p0.get("region", "GRA11")
    shared = f'''data "ovh_cloud_project_images" "linux" {{
  service_name = var.ovh_service_name
  region       = "{region}"
  os_type      = "linux"
}}

data "ovh_cloud_project_flavors" "hosts" {{
  service_name = var.ovh_service_name
  region       = "{region}"
  name_filter  = "{p0.get("instance_type", "b3-8")}"
}}

# Les instances Public Cloud n'ont pas de pare-feu par défaut : le restreindre (SSH depuis local.ssh_cidrs)
# avec un groupe de sécurité OpenStack ou ufw.'''

    def per_group(g: HostGroup) -> str:
        return f'''resource "ovh_cloud_project_instance" "{g.label}" {{
  count          = {_count(g)}
  service_name   = var.ovh_service_name
  region         = "{g.params.get("region", region)}"
  billing_period = "hourly"
  name           = "{_name(ir, g)}-${{count.index + 1}}"
  user_data      = local.cloud_init

  flavor {{
    flavor_id = [for f in data.ovh_cloud_project_flavors.hosts.flavors : f.id if f.name == "{g.params.get("instance_type", "b3-8")}"][0]
  }}

  boot_from {{
    image_id = [for image in data.ovh_cloud_project_images.linux.images : image.id if image.name == "Ubuntu 24.04"][0]
  }}

  ssh_key_create {{
    name       = "{_name(ir, g)}-${{count.index + 1}}"
    public_key = var.ssh_public_key
  }}

  network {{
    public = true
  }}
}}'''
    return shared, per_group, lambda g: (f"[for vm in ovh_cloud_project_instance.{g.label} : "
                                         "[for a in vm.addresses : a.ip if a.version == 4][0]]")


def _outscale(ir: IR, gs: list[HostGroup]):
    region = ir.params("outscale").get("region", "eu-west-2")
    vpc = network.present(ir, "outscale-net")
    sg_net = "\n  net_id              = outscale_net.main.net_id" if vpc else ""
    web = "\n\n".join(f'  rules {{\n    from_port_range = {p}\n    to_port_range   = {p}\n    ip_protocol     = "tcp"\n'
                      f'    ip_ranges       = ["0.0.0.0/0"]\n  }}' for p in _web_ports(ir))
    shared = f'''data "outscale_images" "ubuntu" {{
  filter {{
    name   = "account_aliases"
    values = ["Outscale"]
  }}

  filter {{
    name   = "image_names"
    values = ["Ubuntu-24.04-*"]
  }}
}}

resource "outscale_keypair" "deploy" {{
  keypair_name = "{ir.app}-deploy"
  public_key   = var.ssh_public_key
}}

resource "outscale_security_group" "hosts" {{
  security_group_name = "{ir.app}-hosts"
  description         = "SSH depuis local.ssh_cidrs, web depuis Internet"{sg_net}
}}

resource "outscale_security_group_rule" "ssh" {{
  flow              = "Inbound"
  security_group_id = outscale_security_group.hosts.security_group_id

  rules {{
    from_port_range = 22
    to_port_range   = 22
    ip_protocol     = "tcp"
    ip_ranges       = local.ssh_cidrs
  }}
}}

resource "outscale_security_group_rule" "web" {{
  flow              = "Inbound"
  security_group_id = outscale_security_group.hosts.security_group_id

{web}
}}'''

    placement = ("  subnet_id                = outscale_subnet.main.subnet_id" if vpc
                 else f'  placement_subregion_name = "{region}a"')
    link_after = "\n\n  depends_on = [outscale_route.internet]" if vpc else ""

    def per_group(g: HostGroup) -> str:
        c = _count(g)
        return align_attrs(f'''resource "outscale_vm" "{g.label}" {{
  count                    = {c}
  image_id                 = data.outscale_images.ubuntu.images[0].image_id
  vm_type                  = "{g.params.get("instance_type", "tinav6.c2r4p2")}"
  keypair_name             = outscale_keypair.deploy.keypair_name
  security_group_ids       = [outscale_security_group.hosts.security_group_id]
{placement}
  user_data                = base64encode(local.cloud_init)

  block_device_mappings {{
    device_name = "/dev/sda1"
    bsu {{
      volume_size = {int(g.params.get("disk_gb") or 30)}
      volume_type = "gp2"
    }}
  }}

  tags {{
    key   = "name"
    value = "{_name(ir, g)}-${{count.index + 1}}"
  }}
}}

resource "outscale_public_ip" "{g.label}" {{
  count = {c}
}}

resource "outscale_public_ip_link" "{g.label}" {{
  count     = {c}
  vm_id     = outscale_vm.{g.label}[count.index].vm_id
  public_ip = outscale_public_ip.{g.label}[count.index].public_ip{link_after}
}}''')
    return shared, per_group, lambda g: f"outscale_public_ip.{g.label}[*].public_ip"


# ------------------------------------------------------------------ inventaire
_SCRIPT = r"""#!/usr/bin/env bash
# @HEADER@
# Inventaire Ansible d'un environnement à partir de la sortie Terraform « hosts » (machines créées par
# infra/terraform). Lancé par la CI avant chaque déploiement ; en local, après un apply.
#
#   scripts/tf-inventory.sh <environnement>          écrit l'inventaire de l'environnement
#   scripts/tf-inventory.sh --first <environnement>  affiche la première adresse (déploiement SSH)
#
# Environnements : @ENVS@. TF=tofu|terraform (défaut : @TF@). Il faut jq et l'accès à l'état distant.
# TF_DIR=<dossier>  lit la pile d'un autre dossier (par exemple celui que garde KEEP=1 scripts/tf-floci.sh apply).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TF_BIN="${TF:-@TF@}"
MODE="write"
if [ "${1:-}" = "--first" ]; then MODE=first; shift; fi
ENV_ID="${1:?environnement attendu (@ENVS@)}"
case "$ENV_ID" in
@CASES@
  *) echo "Environnement inconnu : $ENV_ID (attendu : @ENVS@)" >&2; exit 2 ;;
esac

cd "${TF_DIR:-$ROOT/infra/terraform}"
if [ ! -d .terraform ]; then "$TF_BIN" init -input=false >/dev/null; fi
mapfile -t HOSTS < <("$TF_BIN" output -json hosts | jq -r --arg g "$GROUP" '.[$g][]? // empty')
if [ "${#HOSTS[@]}" -eq 0 ]; then
  echo "Aucune machine pour « $GROUP » dans les sorties Terraform : lancer d'abord l'apply de la pile." >&2
  exit 1
fi
if [ "$MODE" = first ]; then
  printf '%s\n' "${HOSTS[0]}"
  exit 0
fi
{
  echo "# @HEADER@"
  echo "# Écrit par scripts/tf-inventory.sh à partir des sorties Terraform (groupe « $GROUP »)."
  echo "[app]"
  printf '%s\n' "${HOSTS[@]}"
  echo
  echo "[all:vars]"
  echo "ansible_user=@USER@"
  echo "deploy_env=$ENV_ID"
} > "$ROOT/$INVENTORY"
echo "Inventaire $INVENTORY : ${#HOSTS[@]} machine(s)."
"""


def inventory_script(ir: IR) -> dict[str, str]:
    if not creates_hosts(ir):
        return {}
    cases = "\n".join(f"  {e.id}) GROUP={shlex.quote(group_of(e))}; INVENTORY={shlex.quote(ir.inventory(e))} ;;"
                      for e in ir.envs)
    envs = ", ".join(e.id for e in ir.envs)
    text = (_SCRIPT.replace("@HEADER@", HEADER).replace("@ENVS@", envs).replace("@TF@", ir.iac_cmd)
            .replace("@CASES@", cases).replace("@USER@", deploy_user(ir)))
    ir.notes.append(f"Machines créées par {ir.iac.name} ({ir.catalog[compute_tool(ir)].name}) : la clé publique de "
                    "SSH_PRIVATE_KEY va dans TF_VAR_ssh_public_key ; au déploiement, "
                    f"`{INVENTORY_SCRIPT}` lit la sortie « hosts » de la pile et écrit l'inventaire de "
                    "l'environnement. Lancer l'apply de la pile avant le premier déploiement.")
    if gs := groups(ir):
        if str(gs[0].params.get("ssh_cidrs") or "0.0.0.0/0").strip() == "0.0.0.0/0":
            ir.notes.append("SSH des machines ouvert à tout Internet (clé seulement) : restreindre « Accès SSH "
                            "autorisé » aux adresses de l'équipe et des runners quand c'est possible.")
    return {INVENTORY_SCRIPT: text}
