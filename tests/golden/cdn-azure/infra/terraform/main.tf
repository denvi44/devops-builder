# Généré par DevOps Builder — à relire avant usage.

provider "azurerm" {
  features {}
}

resource "azurerm_resource_group" "main" {
  name     = "rg-mon-app"
  location = "francecentral"
}

# --- Azure Blob Storage
# Le compte de stockage de l'état est créé hors de cette pile (amorçage), région francecentral.

# --- Machines de déploiement (Ubuntu 24.04) : cloud-init pose le compte « deploy », la clé de la CI
# et Docker avec son extension Compose.
locals {
  ssh_cidrs  = ["0.0.0.0/0"]
  cloud_init = <<-EOT
    #cloud-config
    users:
      - name: deploy
        sudo: "ALL=(ALL) NOPASSWD:ALL"
        shell: /bin/bash
        ssh_authorized_keys:
          - ${var.ssh_public_key}
    package_update: true
    packages:
      - docker.io
      - docker-compose-v2
    runcmd:
      - systemctl enable --now docker
      - usermod -aG docker deploy
  EOT
}

# --- Azure Virtual Machines : réseau et accès
resource "azurerm_virtual_network" "hosts" {
  name                = "vnet-mon-app"
  address_space       = ["10.20.0.0/16"]
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
}

resource "azurerm_subnet" "hosts" {
  name                 = "snet-hosts"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.hosts.name
  address_prefixes     = ["10.20.1.0/24"]
}

resource "azurerm_network_security_group" "hosts" {
  name                = "nsg-mon-app-hosts"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name

  security_rule {
    name                       = "ssh"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "22"
    source_address_prefixes    = local.ssh_cidrs
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "web"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_ranges    = ["80", "443"]
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }
}

resource "azurerm_subnet_network_security_group_association" "hosts" {
  subnet_id                 = azurerm_subnet.hosts.id
  network_security_group_id = azurerm_network_security_group.hosts.id
}

# --- Azure Virtual Machines : hors-production (Préproduction)
resource "azurerm_public_ip" "hors_production" {
  count               = 1
  name                = "pip-mon-app-hors-production-${count.index + 1}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  allocation_method   = "Static"
  sku                 = "Standard"
}

resource "azurerm_network_interface" "hors_production" {
  count               = 1
  name                = "nic-mon-app-hors-production-${count.index + 1}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name

  ip_configuration {
    name                          = "ipconfig"
    subnet_id                     = azurerm_subnet.hosts.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.hors_production[count.index].id
  }
}

resource "azurerm_linux_virtual_machine" "hors_production" {
  count                 = 1
  name                  = "vm-mon-app-hors-production-${count.index + 1}"
  location              = azurerm_resource_group.main.location
  resource_group_name   = azurerm_resource_group.main.name
  size                  = "Standard_B2s"
  admin_username        = "deploy"
  network_interface_ids = [azurerm_network_interface.hors_production[count.index].id]

  admin_ssh_key {
    username   = "deploy"
    public_key = var.ssh_public_key
  }

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "StandardSSD_LRS"
    disk_size_gb         = 30
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "ubuntu-24_04-lts"
    sku       = "server"
    version   = "latest"
  }
}

# --- Azure Virtual Machines : production (Production)
resource "azurerm_public_ip" "production" {
  count               = 1
  name                = "pip-mon-app-production-${count.index + 1}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  allocation_method   = "Static"
  sku                 = "Standard"
}

resource "azurerm_network_interface" "production" {
  count               = 1
  name                = "nic-mon-app-production-${count.index + 1}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name

  ip_configuration {
    name                          = "ipconfig"
    subnet_id                     = azurerm_subnet.hosts.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.production[count.index].id
  }
}

resource "azurerm_linux_virtual_machine" "production" {
  count                 = 1
  name                  = "vm-mon-app-production-${count.index + 1}"
  location              = azurerm_resource_group.main.location
  resource_group_name   = azurerm_resource_group.main.name
  size                  = "Standard_B2s"
  admin_username        = "deploy"
  network_interface_ids = [azurerm_network_interface.production[count.index].id]

  admin_ssh_key {
    username   = "deploy"
    public_key = var.ssh_public_key
  }

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "StandardSSD_LRS"
    disk_size_gb         = 30
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "ubuntu-24_04-lts"
    sku       = "server"
    version   = "latest"
  }
}

# --- Azure Load Balancer
# --- hors-production : répartiteur
resource "azurerm_public_ip" "lb_hors_production" {
  name                = "pip-mon-app-hors-production-lb"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  allocation_method   = "Static"
  sku                 = "Standard"
}

resource "azurerm_lb" "hors_production" {
  name                = "lb-mon-app-hors-production"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "Standard"

  frontend_ip_configuration {
    name                 = "public"
    public_ip_address_id = azurerm_public_ip.lb_hors_production.id
  }
}

resource "azurerm_lb_backend_address_pool" "hors_production" {
  loadbalancer_id = azurerm_lb.hors_production.id
  name            = "hosts"
}

resource "azurerm_lb_probe" "hors_production" {
  loadbalancer_id = azurerm_lb.hors_production.id
  name            = "tcp-80"
  protocol        = "Tcp"
  port            = 80
}

resource "azurerm_lb_rule" "hors_production_80" {
  loadbalancer_id                = azurerm_lb.hors_production.id
  name                           = "tcp-80"
  protocol                       = "Tcp"
  frontend_port                  = 80
  backend_port                   = 80
  frontend_ip_configuration_name = "public"
  backend_address_pool_ids       = [azurerm_lb_backend_address_pool.hors_production.id]
  probe_id                       = azurerm_lb_probe.hors_production.id
}

resource "azurerm_lb_rule" "hors_production_443" {
  loadbalancer_id                = azurerm_lb.hors_production.id
  name                           = "tcp-443"
  protocol                       = "Tcp"
  frontend_port                  = 443
  backend_port                   = 443
  frontend_ip_configuration_name = "public"
  backend_address_pool_ids       = [azurerm_lb_backend_address_pool.hors_production.id]
  probe_id                       = azurerm_lb_probe.hors_production.id
}

resource "azurerm_network_interface_backend_address_pool_association" "hors_production" {
  count                   = 1
  network_interface_id    = azurerm_network_interface.hors_production[count.index].id
  ip_configuration_name   = "ipconfig"
  backend_address_pool_id = azurerm_lb_backend_address_pool.hors_production.id
}

# --- production : répartiteur
resource "azurerm_public_ip" "lb_production" {
  name                = "pip-mon-app-production-lb"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  allocation_method   = "Static"
  sku                 = "Standard"
}

resource "azurerm_lb" "production" {
  name                = "lb-mon-app-production"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "Standard"

  frontend_ip_configuration {
    name                 = "public"
    public_ip_address_id = azurerm_public_ip.lb_production.id
  }
}

resource "azurerm_lb_backend_address_pool" "production" {
  loadbalancer_id = azurerm_lb.production.id
  name            = "hosts"
}

resource "azurerm_lb_probe" "production" {
  loadbalancer_id = azurerm_lb.production.id
  name            = "tcp-80"
  protocol        = "Tcp"
  port            = 80
}

resource "azurerm_lb_rule" "production_80" {
  loadbalancer_id                = azurerm_lb.production.id
  name                           = "tcp-80"
  protocol                       = "Tcp"
  frontend_port                  = 80
  backend_port                   = 80
  frontend_ip_configuration_name = "public"
  backend_address_pool_ids       = [azurerm_lb_backend_address_pool.production.id]
  probe_id                       = azurerm_lb_probe.production.id
}

resource "azurerm_lb_rule" "production_443" {
  loadbalancer_id                = azurerm_lb.production.id
  name                           = "tcp-443"
  protocol                       = "Tcp"
  frontend_port                  = 443
  backend_port                   = 443
  frontend_ip_configuration_name = "public"
  backend_address_pool_ids       = [azurerm_lb_backend_address_pool.production.id]
  probe_id                       = azurerm_lb_probe.production.id
}

resource "azurerm_network_interface_backend_address_pool_association" "production" {
  count                   = 1
  network_interface_id    = azurerm_network_interface.production[count.index].id
  ip_configuration_name   = "ipconfig"
  backend_address_pool_id = azurerm_lb_backend_address_pool.production.id
}

# --- Azure Front Door et pare-feu WAF
resource "azurerm_cdn_frontdoor_profile" "main" {
  name                = "mon-app-cdn"
  resource_group_name = azurerm_resource_group.main.name
  sku_name            = "Standard_AzureFrontDoor"
}

resource "azurerm_cdn_frontdoor_endpoint" "main" {
  name                     = "mon-app"
  cdn_frontdoor_profile_id = azurerm_cdn_frontdoor_profile.main.id
}

resource "azurerm_cdn_frontdoor_origin_group" "main" {
  name                     = "app"
  cdn_frontdoor_profile_id = azurerm_cdn_frontdoor_profile.main.id

  load_balancing {}

  health_probe {
    path                = "/"
    protocol            = "Https"
    request_type        = "HEAD"
    interval_in_seconds = 100
  }
}

resource "azurerm_cdn_frontdoor_origin" "main" {
  name                           = "app"
  cdn_frontdoor_origin_group_id  = azurerm_cdn_frontdoor_origin_group.main.id
  enabled                        = true
  host_name                      = azurerm_public_ip.lb_production.ip_address
  origin_host_header             = azurerm_public_ip.lb_production.ip_address
  certificate_name_check_enabled = true
  http_port                      = 80
  https_port                     = 443
}

resource "azurerm_cdn_frontdoor_route" "main" {
  name                          = "app"
  cdn_frontdoor_endpoint_id     = azurerm_cdn_frontdoor_endpoint.main.id
  cdn_frontdoor_origin_group_id = azurerm_cdn_frontdoor_origin_group.main.id
  cdn_frontdoor_origin_ids      = [azurerm_cdn_frontdoor_origin.main.id]
  supported_protocols           = ["Http", "Https"]
  patterns_to_match             = ["/*"]
  forwarding_protocol           = "HttpsOnly"
  https_redirect_enabled        = true
  link_to_default_domain        = true
}

resource "azurerm_cdn_frontdoor_firewall_policy" "main" {
  name                = "monappwaf"
  resource_group_name = azurerm_resource_group.main.name
  sku_name            = azurerm_cdn_frontdoor_profile.main.sku_name
  enabled             = true
  mode                = "Prevention"

  custom_rule {
    name                           = "LimiteParAdresse"
    enabled                        = true
    priority                       = 100
    type                           = "RateLimitRule"
    action                         = "Block"
    rate_limit_duration_in_minutes = 1
    rate_limit_threshold           = 2000

    match_condition {
      match_variable     = "RemoteAddr"
      operator           = "IPMatch"
      negation_condition = true
      match_values       = ["255.255.255.255/32"]
    }
  }
}

resource "azurerm_cdn_frontdoor_security_policy" "main" {
  name                     = "mon-app-waf"
  cdn_frontdoor_profile_id = azurerm_cdn_frontdoor_profile.main.id

  security_policies {
    firewall {
      cdn_frontdoor_firewall_policy_id = azurerm_cdn_frontdoor_firewall_policy.main.id

      association {
        patterns_to_match = ["/*"]

        domain {
          cdn_frontdoor_domain_id = azurerm_cdn_frontdoor_endpoint.main.id
        }
      }
    }
  }
}
