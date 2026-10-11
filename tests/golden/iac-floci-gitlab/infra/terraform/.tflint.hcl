# Généré par DevOps Builder — à relire avant usage.
# Règles de base du langage ; ajouter le jeu de règles du cloud (tflint-ruleset-aws, -google, -azurerm)
# avec une version épinglée pour vérifier types d'instance, régions et arguments propres au fournisseur.
plugin "terraform" {
  enabled = true
  preset  = "recommended"
}
