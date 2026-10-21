# SPDX-License-Identifier: Apache-2.0
"""CDN et pare-feu applicatif du projet (capacité « CDN et pare-feu » de la 1.1) : un CDN devant l'application.

Une brique par cloud qui en propose un (aws-cloudfront avec WAF, gcp-cdn avec Cloud Armor, azure-front-door avec son
pare-feu, scaleway-edge-services avec son WAF) ; OVHcloud et Outscale n'en ont pas. L'origine est le répartiteur de
charge du projet s'il existe, sinon les machines de la production, sinon le nom donné dans la brique (`origin`) ou, à
défaut, la variable `cdn_origin`. Le pare-feu bloque les attaques courantes et limite le débit par adresse. La mise en
cache est coupée par défaut (`cache` = aucun) : une application dynamique ne doit pas être mise en cache par surprise.
"""

from __future__ import annotations

import re

from ..ir import IR
from . import hosts, lb
from .common import align_attrs

CDN = {"aws-cloudfront": "aws", "gcp-cdn": "gcp", "azure-front-door": "azure", "scaleway-edge-services": "scaleway"}
CACHING_DISABLED = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
CACHING_OPTIMIZED = "658327ea-f89d-4fab-a63d-7e88639e58f6"
ALL_VIEWER = "216adef6-5c7f-47e4-b989-5492eafa07d3"


def tool(ir: IR) -> str | None:
    return next((t for t in CDN if ir.has(t)), None)


def _prod_group(ir: IR):
    return next((g for g in hosts.groups(ir) if any(e.kind == "production" for e in g.envs)), None)


def origin(ir: IR, tid: str, p: dict) -> tuple[str, bool, bool]:
    """(expression, est une adresse IP, vient d'une variable) de l'origine du CDN."""
    given = str(p.get("origin") or "").strip()
    if given:
        return f'"{given}"', False, False
    cloud = CDN[tid]
    machines = hosts.creates_hosts(ir) and hosts.COMPUTE[hosts.compute_tool(ir)] == cloud
    g = _prod_group(ir) if machines else None
    if g is not None:
        balanced = lb.tool(ir) and lb.LB[lb.tool(ir)] == cloud
        if balanced:
            if cloud == "aws":
                return f"aws_lb.{g.label}.dns_name", False, False
            if cloud == "gcp":
                return f"google_compute_address.lb_{g.label}.address", True, False
            if cloud == "azure":
                return f"azurerm_public_ip.lb_{g.label}.ip_address", True, False
        elif cloud == "aws":
            return f"aws_instance.{g.label}[0].public_dns", False, False
        else:
            return f"tolist({hosts.address_exprs(ir)[g.key]})[0]", True, False
    return "var.cdn_origin", False, True


def variables(ir: IR) -> list[str]:
    tid = tool(ir)
    if tid and origin(ir, tid, ir.params(tid))[2]:
        return ['variable "cdn_origin" {\n  type        = string\n'
                '  description = "Nom d\'hôte public de l\'application, vers lequel le CDN renvoie les requêtes"\n'
                '  default     = ""\n}']
    return []


def _out(label: str, desc: str, value: str) -> str:
    return f'output "{label}" {{\n  description = "{desc}"\n  value       = {value}\n}}'


def _aws(ir, p, org, is_ip):
    app = ir.app
    limit = max(10, int(p.get("rate_limit") or 2000) * 5)     # AWS compte sur cinq minutes
    cache = CACHING_OPTIMIZED if p.get("cache") == "standard" else CACHING_DISABLED
    metric = lambda n: (f'    visibility_config {{\n      cloudwatch_metrics_enabled = true\n'  # noqa: E731
                        f'      metric_name                = "{app}-{n}"\n      sampled_requests_enabled   = true\n    }}')
    waf = f'''# Un pare-feu CloudFront se crée obligatoirement en us-east-1.
resource "aws_wafv2_web_acl" "cdn" {{
  provider = aws.us_east_1
  name     = "{app}-cdn"
  scope    = "CLOUDFRONT"

  default_action {{
    allow {{}}
  }}

  rule {{
    name     = "regles-communes"
    priority = 1

    override_action {{
      none {{}}
    }}

    statement {{
      managed_rule_group_statement {{
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name = "AWS"
      }}
    }}

{metric("regles-communes")}
  }}

  rule {{
    name     = "limite-par-adresse"
    priority = 2

    action {{
      block {{}}
    }}

    statement {{
      rate_based_statement {{
        limit              = {limit}
        aggregate_key_type = "IP"
      }}
    }}

{metric("limite-par-adresse")}
  }}

  visibility_config {{
    cloudwatch_metrics_enabled = true
    metric_name                = "{app}-cdn"
    sampled_requests_enabled   = true
  }}
}}'''
    dist = f'''resource "aws_cloudfront_distribution" "main" {{
  enabled         = true
  comment         = "{app}"
  is_ipv6_enabled = true
  price_class     = "PriceClass_100"
  web_acl_id      = aws_wafv2_web_acl.cdn.arn

  origin {{
    domain_name = {org}
    origin_id   = "app"

    custom_origin_config {{
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "{p.get("origin_protocol", "https-only")}"
      origin_ssl_protocols   = ["TLSv1.2"]
    }}
  }}

  default_cache_behavior {{
    target_origin_id         = "app"
    viewer_protocol_policy   = "redirect-to-https"
    allowed_methods          = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods           = ["GET", "HEAD"]
    cache_policy_id          = "{cache}"
    origin_request_policy_id = "{ALL_VIEWER}"
  }}

  restrictions {{
    geo_restriction {{
      restriction_type = "none"
    }}
  }}

  viewer_certificate {{
    cloudfront_default_certificate = true
  }}
}}'''
    return [waf, dist], [_out("cdn_domain", "Nom de domaine du CDN (CloudFront)", "aws_cloudfront_distribution.main.domain_name")]


def _gcp(ir, p, org, is_ip):
    app = ir.app
    domain = str(p.get("domain") or "").strip()
    standard = p.get("cache") == "standard"
    kind, field = ("INTERNET_IP_PORT", "ip_address") if is_ip else ("INTERNET_FQDN_PORT", "fqdn")
    limit = int(p.get("rate_limit") or 2000)
    rule = lambda prio, expr, name: (f'  rule {{\n    action      = "deny(403)"\n    priority    = {prio}\n'  # noqa: E731
                                     f'    description = "{name}"\n\n    match {{\n      expr {{\n'
                                     f'        expression = "{expr}"\n      }}\n    }}\n  }}')
    blocks = [
        align_attrs(f'''resource "google_compute_global_network_endpoint_group" "cdn" {{
  name                  = "{app}-cdn-origin"
  network_endpoint_type = "{kind}"
  default_port          = 443
}}

resource "google_compute_global_network_endpoint" "cdn" {{
  global_network_endpoint_group = google_compute_global_network_endpoint_group.cdn.id
  {field} = {org}
  port = 443
}}'''),
        f'''resource "google_compute_security_policy" "cdn" {{
  name = "{app}-cdn"

{rule(1000, "evaluatePreconfiguredWaf('sqli-v33-stable')", "Injections SQL")}

{rule(1001, "evaluatePreconfiguredWaf('xss-v33-stable')", "Scripts intersites")}

  rule {{
    action      = "throttle"
    priority    = 2000
    description = "Limite par adresse"

    match {{
      versioned_expr = "SRC_IPS_V1"
      config {{
        src_ip_ranges = ["*"]
      }}
    }}

    rate_limit_options {{
      conform_action = "allow"
      exceed_action  = "deny(429)"
      enforce_on_key = "IP"

      rate_limit_threshold {{
        count        = {limit}
        interval_sec = 60
      }}
    }}
  }}

  rule {{
    action      = "allow"
    priority    = 2147483647
    description = "Règle par défaut"

    match {{
      versioned_expr = "SRC_IPS_V1"
      config {{
        src_ip_ranges = ["*"]
      }}
    }}
  }}
}}''',
        f'''resource "google_compute_backend_service" "cdn" {{
  name                  = "{app}-cdn"
  protocol              = "HTTPS"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  enable_cdn            = true
  security_policy       = google_compute_security_policy.cdn.id

  backend {{
    group = google_compute_global_network_endpoint_group.cdn.id
  }}

  cdn_policy {{
    cache_mode = "{"CACHE_ALL_STATIC" if standard else "USE_ORIGIN_HEADERS"}"
  }}

  depends_on = [google_compute_global_network_endpoint.cdn]
}}

resource "google_compute_url_map" "cdn" {{
  name            = "{app}-cdn"
  default_service = google_compute_backend_service.cdn.id
}}''']
    tail = [f'''resource "google_compute_target_http_proxy" "cdn" {{
  name    = "{app}-cdn-http"
  url_map = google_compute_url_map.cdn.id
}}

resource "google_compute_global_address" "cdn" {{
  name = "{app}-cdn"
}}

resource "google_compute_global_forwarding_rule" "cdn_http" {{
  name                  = "{app}-cdn-http"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  ip_address            = google_compute_global_address.cdn.id
  port_range            = "80"
  target                = google_compute_target_http_proxy.cdn.id
}}''']
    if domain:
        tail.append(f'''resource "google_compute_managed_ssl_certificate" "cdn" {{
  name = "{app}-cdn"

  managed {{
    domains = ["{domain}"]
  }}
}}

resource "google_compute_target_https_proxy" "cdn" {{
  name             = "{app}-cdn-https"
  url_map          = google_compute_url_map.cdn.id
  ssl_certificates = [google_compute_managed_ssl_certificate.cdn.id]
}}

resource "google_compute_global_forwarding_rule" "cdn_https" {{
  name                  = "{app}-cdn-https"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  ip_address            = google_compute_global_address.cdn.id
  port_range            = "443"
  target                = google_compute_target_https_proxy.cdn.id
}}''')
    return blocks + tail, [_out("cdn_ip", "Adresse IP du CDN (Cloud CDN)", "google_compute_global_address.cdn.address")]


def _azure(ir, p, org, is_ip):
    app = ir.app
    sku = str(p.get("sku") or "Standard_AzureFrontDoor")
    premium = sku.startswith("Premium")
    limit = int(p.get("rate_limit") or 2000)
    waf_name = re.sub(r"[^a-zA-Z0-9]", "", app) + "waf"
    managed = ('\n\n  managed_rule {\n    type    = "Microsoft_DefaultRuleSet"\n    version = "2.1"\n    action  = "Block"\n  }'
               if premium else "")
    cache = ('\n\n  cache {\n    query_string_caching_behavior = "UseQueryString"\n    compression_enabled           = true\n'
             '    content_types_to_compress     = ["text/html", "text/css", "application/javascript", "application/json"]\n  }'
             if p.get("cache") == "standard" else "")
    res = f'''resource "azurerm_cdn_frontdoor_profile" "main" {{
  name                = "{app}-cdn"
  resource_group_name = azurerm_resource_group.main.name
  sku_name            = "{sku}"
}}

resource "azurerm_cdn_frontdoor_endpoint" "main" {{
  name                     = "{app}"
  cdn_frontdoor_profile_id = azurerm_cdn_frontdoor_profile.main.id
}}

resource "azurerm_cdn_frontdoor_origin_group" "main" {{
  name                     = "app"
  cdn_frontdoor_profile_id = azurerm_cdn_frontdoor_profile.main.id

  load_balancing {{}}

  health_probe {{
    path                = "/"
    protocol            = "Https"
    request_type        = "HEAD"
    interval_in_seconds = 100
  }}
}}

resource "azurerm_cdn_frontdoor_origin" "main" {{
  name                           = "app"
  cdn_frontdoor_origin_group_id  = azurerm_cdn_frontdoor_origin_group.main.id
  enabled                        = true
  host_name                      = {org}
  origin_host_header             = {org}
  certificate_name_check_enabled = true
  http_port                      = 80
  https_port                     = 443
}}

resource "azurerm_cdn_frontdoor_route" "main" {{
  name                          = "app"
  cdn_frontdoor_endpoint_id     = azurerm_cdn_frontdoor_endpoint.main.id
  cdn_frontdoor_origin_group_id = azurerm_cdn_frontdoor_origin_group.main.id
  cdn_frontdoor_origin_ids      = [azurerm_cdn_frontdoor_origin.main.id]
  supported_protocols           = ["Http", "Https"]
  patterns_to_match             = ["/*"]
  forwarding_protocol           = "HttpsOnly"
  https_redirect_enabled        = true
  link_to_default_domain        = true{cache}
}}

resource "azurerm_cdn_frontdoor_firewall_policy" "main" {{
  name                = "{waf_name}"
  resource_group_name = azurerm_resource_group.main.name
  sku_name            = azurerm_cdn_frontdoor_profile.main.sku_name
  enabled             = true
  mode                = "Prevention"

  custom_rule {{
    name                           = "LimiteParAdresse"
    enabled                        = true
    priority                       = 100
    type                           = "RateLimitRule"
    action                         = "Block"
    rate_limit_duration_in_minutes = 1
    rate_limit_threshold           = {limit}

    match_condition {{
      match_variable     = "RemoteAddr"
      operator           = "IPMatch"
      negation_condition = true
      match_values       = ["255.255.255.255/32"]
    }}
  }}{managed}
}}

resource "azurerm_cdn_frontdoor_security_policy" "main" {{
  name                     = "{app}-waf"
  cdn_frontdoor_profile_id = azurerm_cdn_frontdoor_profile.main.id

  security_policies {{
    firewall {{
      cdn_frontdoor_firewall_policy_id = azurerm_cdn_frontdoor_firewall_policy.main.id

      association {{
        patterns_to_match = ["/*"]

        domain {{
          cdn_frontdoor_domain_id = azurerm_cdn_frontdoor_endpoint.main.id
        }}
      }}
    }}
  }}
}}'''
    return [res], [_out("cdn_hostname", "Nom d'hôte du CDN (Front Door)", "azurerm_cdn_frontdoor_endpoint.main.host_name")]


def _scaleway(ir, p, org, is_ip):
    g = _prod_group(ir)
    ttl = 3600 if p.get("cache") == "standard" else 0
    res = f'''resource "scaleway_edge_services_pipeline" "main" {{
  name = "{ir.app}"
}}

resource "scaleway_edge_services_backend_stage" "main" {{
  pipeline_id = scaleway_edge_services_pipeline.main.id

  lb_backend_config {{
    lb_config {{
      id          = scaleway_lb.{g.label}.id
      frontend_id = scaleway_lb_frontend.{g.label}_80.id
      is_ssl      = false
      zone        = scaleway_lb.{g.label}.zone
    }}
  }}
}}

resource "scaleway_edge_services_waf_stage" "main" {{
  pipeline_id      = scaleway_edge_services_pipeline.main.id
  backend_stage_id = scaleway_edge_services_backend_stage.main.id
  mode             = "enable"
  paranoia_level   = 2
}}

resource "scaleway_edge_services_cache_stage" "main" {{
  pipeline_id  = scaleway_edge_services_pipeline.main.id
  waf_stage_id = scaleway_edge_services_waf_stage.main.id
  fallback_ttl = {ttl}
}}

resource "scaleway_edge_services_head_stage" "main" {{
  pipeline_id   = scaleway_edge_services_pipeline.main.id
  head_stage_id = scaleway_edge_services_cache_stage.main.id
}}'''
    return [res], [_out("cdn_pipeline_id", "Identifiant du pipeline Edge Services", "scaleway_edge_services_pipeline.main.id")]


RENDER = {"aws-cloudfront": _aws, "gcp-cdn": _gcp, "azure-front-door": _azure, "scaleway-edge-services": _scaleway}


def terraform_blocks(ir: IR) -> tuple[list[str], list[str]]:
    tid = tool(ir)
    if tid is None:
        return [], []
    ir.cover(tid)
    name = ir.catalog[tid].name
    p = ir.params(tid)
    if tid == "scaleway-edge-services":
        machines = hosts.creates_hosts(ir) and hosts.COMPUTE[hosts.compute_tool(ir)] == "scaleway"
        if not (machines and lb.tool(ir) and lb.LB[lb.tool(ir)] == "scaleway" and _prod_group(ir)):
            ir.notes.append(f"{name} : le pipeline protège le répartiteur de charge Scaleway du projet ; sans "
                            "répartiteur devant des machines créées par la pile, rien n'est écrit.")
            return [], []
    org, is_ip, from_var = origin(ir, tid, p)
    blocks, outs = RENDER[tid](ir, p, org, is_ip)
    ir.notes.append(f"{name} : CDN devant l'application avec pare-feu applicatif (attaques courantes bloquées, "
                    f"{int(p.get('rate_limit') or 2000)} requêtes par minute et par adresse au plus) ; "
                    + ("la mise en cache est active. " if p.get("cache") == "standard" else
                       "la mise en cache est coupée (cache = standard pour l'activer). ")
                    + "Pointer le DNS du site vers l'adresse du CDN donnée en sortie.")
    if from_var:
        ir.notes.append(f"{name} : aucune machine ni répartiteur créés par la pile pour ce cloud : renseigner le nom "
                        "d'hôte de l'application dans la variable cdn_origin (ou le champ « origine » de la brique).")
    if tid == "aws-cloudfront":
        ir.notes.append("Amazon CloudFront : l'origine reçoit les requêtes en HTTPS ; son certificat doit couvrir le nom "
                        "d'origine (utiliser un nom du DNS plutôt que celui du répartiteur), ou passer "
                        "origin_protocol à http-only. Le pare-feu est créé en us-east-1 (obligatoire pour CloudFront).")
    elif tid == "gcp-cdn":
        ir.notes.append("Google Cloud CDN : le CDN passe par un équilibreur HTTP(S) global ; sans domaine renseigné "
                        "dans la brique, seul le port 80 est ouvert (ajouter un domaine pour un certificat géré).")
    elif tid == "azure-front-door":
        ir.notes.append("Azure Front Door : les règles gérées Microsoft demandent l'offre Premium ; en Standard, "
                        "seule la limite de débit protège l'application.")
    elif tid == "scaleway-edge-services":
        ir.notes.append("Scaleway Edge Services : le pipeline est créé ; son nom de domaine public et son certificat "
                        "se règlent ensuite (étapes DNS et TLS), la limite de débit n'existe pas chez Scaleway.")
    return [f"# --- {name}\n" + "\n\n".join(blocks)], outs
