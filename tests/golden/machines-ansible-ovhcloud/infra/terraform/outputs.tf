# Généré par DevOps Builder — à relire avant usage.

output "hosts" {
  description = "Adresses publiques des machines, par groupe (scripts/tf-inventory.sh)"
  value = {
    "hors-production" = [for vm in ovh_cloud_project_instance.hors_production : [for a in vm.addresses : a.ip if a.version == 4][0]]
    "production"      = [for vm in ovh_cloud_project_instance.production : [for a in vm.addresses : a.ip if a.version == 4][0]]
  }
}
