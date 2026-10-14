# Feuille de route vers la 1.0

La 1.0 est une promesse : un fichier projet ouvert en 1.0 s'ouvre dans toutes les 1.x ; ce qui est marqué
« pris en charge » fonctionne au premier vrai déploiement ; l'installation ne demande pas Python ; le
catalogue est entretenu, et une contribution (fiche, règle, générateur) a un chemin documenté. Jusque-là,
aucune brique nouvelle : chaque version ferme des écarts.

## 0.16 — Gel du périmètre et contrat de compatibilité (fait)

Niveau de prise en charge de chaque fiche, fichiers de toutes les versions relus sans perte, ligne de
commande stable (codes de sortie, `--json`), journal des modifications. En 0.16.1 : licence Apache 2.0 et
préparation du dépôt public.

## 0.17 — Vérification sur une vraie infrastructure

Cluster kind réel (Helm, Kustomize, Argo CD, CloudNativePG, Keycloak, External Secrets, OpenBao) ; hôte
Docker réel (Compose, Traefik, Keycloak, sauvegarde et restauration) ; `apply` puis `destroy` sur au moins un
cloud ; Dex exécuté. Seules les cibles qui passent restent « pris en charge ».

## 0.18 — Fermer les limites qui piègent

Moindre privilège des rôles de CI créés par le mode d'emploi, verrou d'état Terraform pour Scaleway, OVHcloud
et Outscale, connexion OIDC de Harbor et SonarQube, job Renovate hors GitHub. Deux ajouts décidés le 14 octobre
parce qu'ils changent la qualité d'un pipeline : **ZAP** (DAST, scan de la préproduction après chaque
déploiement) et l'**aide au dimensionnement des machines** (besoin calculé à partir des briques posées sur
l'hôte, type d'instance proposé pour chaque cloud).

## 0.19 — Ouverture du dépôt et distribution

Dépôt public sur GitHub, CI publique complète (références, miroir OpenTofu, ShellCheck, kubeconform), script
de version, `pipx install devops-builder`, exécutables Windows, macOS et Linux signés avec attestation de
provenance.

## 0.20 — Qualité produit

Audit RGAA de l'application (lecteurs d'écran NVDA et Orca, clavier seul, contrastes des deux thèmes) et
corrections ; guide utilisateur publié avec tutoriels ; messages d'erreur relus ; performances sur un gros
projet.

## Après la 1.0

- 1.1 : pile Elastic sur hôte Docker (Elasticsearch, Kibana, Logstash), comme Zabbix ; schéma d'architecture
  en 2D exporté (SVG, PNG) depuis l'interface et la ligne de commande.
- 1.2 : CircleCI ; schéma isométrique (vue en relief des environnements, hôtes et services).
- Puppet, Chef, Burp Suite et Drone restent des fiches sans générateur : Ansible, ZAP et Woodpecker couvrent
  leur usage.

## 1.0

Bêta publique de quelques semaines avec des projets pilotes, puis versionnage sémantique : les 1.x ajoutent
sans rompre le format, les 1.x.y corrigent et rafraîchissent le catalogue.
