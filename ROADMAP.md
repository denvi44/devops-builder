# Feuille de route vers la 1.0

La 1.0 est une promesse : un fichier projet ouvert en 1.0 s'ouvre dans toutes les 1.x ; ce qui est marqué
« pris en charge » fonctionne au premier vrai déploiement ; l'installation ne demande pas Python ; le
catalogue est entretenu, et une contribution (fiche, règle, générateur) a un chemin documenté. Jusque-là,
aucune brique nouvelle : chaque version ferme des écarts.

## 0.16 — Gel du périmètre et contrat de compatibilité (fait)

Niveau de prise en charge de chaque fiche, fichiers de toutes les versions relus sans perte, ligne de
commande stable (codes de sortie, `--json`), journal des modifications. En 0.16.1 : licence Apache 2.0 et
préparation du dépôt public.

## 0.17 — Vérification sur une vraie infrastructure (publiée le 15 octobre)

Onze scénarios exécutent les fichiers générés sur les machines de GitHub Actions, chaque nuit : Helm,
Kustomize, CloudNativePG, OpenBao et External Secrets, Keycloak et Argo CD dans kind ; Compose, Traefik en
HTTPS, sauvegarde et restauration, Keycloak, Dex, SOPS, Zabbix et ZAP sur un hôte Docker. Une dizaine de
défauts trouvés et corrigés (voir CHANGELOG). ZAP et l'aide au dimensionnement, prévus en 0.18, y sont déjà.
Reste pour une 0.17.x : `apply` puis `destroy` sur au moins un cloud (compte de test à fournir), et Dex
exécuté sur Kubernetes.

## 0.18 — Fermer les limites qui piègent (publiée le 15 octobre)

Deux identités de CI par cloud (infrastructure aux droits étendus, déploiement limité), verrou d'état Terraform
sur Scaleway et OVHcloud, connexion unique de Harbor (OIDC) et SonarQube (SAML avec Keycloak), Renovate planifié
dans GitLab CI et Gitea Actions. Le scénario `kind-plateforme` rend vingt-huit charts avec les options générées.
Reste : éprouver les droits réduits de la CI sur un vrai compte cloud.

## 0.19 — Distribution (publiée le 16 octobre)

`pipx install izinum-devops-builder` (« devops-builder » était pris sur PyPI) ; exécutables Windows, macOS
(Apple Silicon) et Linux avec attestation de provenance et sommes SHA-256 ; workflow de publication qui crée
l'étiquette, publie sur PyPI sans secret stocké et rédige la publication depuis le journal ; CI complète
(OpenTofu et son miroir de providers, kubeconform, sops, Ansible) où aucun test n'est sauté.
Reste : signer les exécutables (certificat Authenticode, compte Apple Developer pour la notarisation) et un
exécutable macOS Intel.

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
