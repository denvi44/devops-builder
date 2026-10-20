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
Reste : signer les exécutables (certificat Authenticode, compte Apple Developer pour la notarisation). Un
exécutable macOS Intel s'y ajoute en 0.25.

## 0.20 — Qualité produit (publiée le 17 octobre)

Audit d'accessibilité automatisé (EN 301 549 / WCAG 2.1 AA, RGAA en regard) dans les deux thèmes et corrections :
textes de Qt traduits, anneau de focus, contrastes, annonces aux lecteurs d'écran, taille du texte jusqu'à
200 %, équivalent clavier de chaque glisser. Arbres lus comme Orca et NVDA vérifiés en CI. Guide utilisateur
publié avec quatre tutoriels confrontés aux fichiers générés ; messages d'erreur traduits ; libyaml (deux à trois
fois plus rapide sur un gros projet).
Reste : une session d'écoute complète avec NVDA, Orca et VoiceOver ; suivre le mode contraste élevé et la taille
de police du système.

## 0.21 à 0.25 — Pipelines types, instances, entrée, adresses, bases dédiées (publiées jusqu'à la 0.24)

- 0.21 : douze modèles de pipeline par fournisseur (AWS, Google Cloud, Azure, OVHcloud, Scaleway, Outscale).
- 0.22 : plusieurs instances d'un même outil (Compose, ports, Helm, interface, règle R55) ; entrée Ingress ou
  Gateway API en HTTPS (cert-manager).
- 0.23 : adresses IP acceptées partout (règle R56), registre HTTP déclaré automatiquement ; base de données
  dédiée par outil (PostgreSQL pour Gitea, SonarQube, Grafana).
- 0.24 : choix étendu à MariaDB et MySQL, Harbor sur PostgreSQL externe.
- 0.25 : scénario de bout en bout `compose-bases-dediees`, exécutable macOS Intel.

Reste avant la 1.0, et qui demande des ressources hors de ce dépôt :

- `apply` puis `destroy` sur un vrai compte cloud (le modèle AWS EC2 passe déjà sur l'émulateur Floci, jusqu'au déploiement par Ansible ; la pile du modèle ECS passe aussi, sans la suppression de la base RDS) ; les modèles et les identités de CI à droits réduits restent à éprouver ;
- signature des exécutables (Authenticode, notarisation Apple) ;
- sessions d'écoute NVDA, Orca, VoiceOver ; suivi du contraste élevé et de la taille de police du système ;
- clés `--set` des charts Helm : contrôlées contre les valeurs des charts par le scénario `kind-plateforme` (deux défauts corrigés) ; reste à les éprouver à l'installation réelle sur un cluster ;
- Dex exécuté sur Kubernetes ; connexion unique des instances nommées (seule l'instance principale est câblée).

## Après la 1.0

- 1.1 : services des fournisseurs cloud, par capacités (voir plus bas) ; pile Elastic sur hôte Docker
  (Elasticsearch, Kibana, Logstash), comme Zabbix ; schéma d'architecture en 2D exporté (SVG, PNG) depuis
  l'interface et la ligne de commande.
- 1.2 : CircleCI ; schéma isométrique (vue en relief des environnements, hôtes et services).
- Puppet, Chef, Burp Suite et Drone restent des fiches sans générateur : Ansible, ZAP et Woodpecker couvrent
  leur usage.

## 1.0

Bêta publique de quelques semaines avec des projets pilotes, puis versionnage sémantique : les 1.x ajoutent
sans rompre le format, les 1.x.y corrigent et rafraîchissent le catalogue.

## 1.1 — Services des fournisseurs cloud, par capacités

Les catalogues des fournisseurs sont bien plus larges que le nôtre (Azure en liste environ 370), mais la plupart
des services (IA, IoT, médias, analytique) ne changent rien à un pipeline. Trois règles pour ne pas noyer les
utilisateurs :

1. Une brique doit changer les fichiers générés (ressources OpenTofu, variables de la CI, configuration de
   l'application). Sinon, elle n'a pas sa place.
2. Des capacités plutôt que des produits : une seule brique, par exemple « Cache managé », qui devient le service du
   cloud du projet. Huit capacités couvrent les six clouds, au lieu d'une cinquantaine de fiches.
3. La palette ne montre que ce que le cloud du projet sait faire. Vérifié : elle écarte déjà tout service d'un autre
   fournisseur que celui du projet (`compat.incompatibility`) ; une nouvelle brique n'a rien à ajouter.

| Capacité | AWS | Google Cloud | Azure | Scaleway | OVHcloud | Outscale |
|---|---|---|---|---|---|---|
| 1. Réseau privé | VPC | VPC | Réseau virtuel | VPC, réseau privé | Private Network (vRack) | VPC |
| 2. Répartiteur de charge | ALB | Cloud Load Balancing | Load Balancer, Application Gateway | Load Balancer | Load Balancer | LBU |
| 3. DNS | Route 53 | Cloud DNS | Azure DNS | Domaines | hors Public Cloud | — |
| 4. Cache managé | ElastiCache | Memorystore | Azure Cache for Redis | Managed Redis | Valkey | — |
| 5. File de messages | SQS | Pub/Sub | Service Bus | Queues | Kafka | — |
| 6. Fonctions serverless | Lambda | Cloud Run functions | Functions | Serverless Functions | annoncé « bientôt » | — |
| 7. Chiffrement (KMS) | KMS | Cloud KMS | Key Vault (clés) | Key Manager | KMS | — |
| 8. CDN et pare-feu applicatif | CloudFront, WAF | Cloud CDN, Cloud Armor | Front Door, WAF | Edge Services, WAF | — | — |

Ce que chaque capacité ajoute aux fichiers générés :

1. **Réseau privé** : créé une fois, puis rattaché aux machines, bases et clusters ; remplace les identifiants de
   réseau saisis à la main (ce qui bloquait l'`apply` sur Floci).
   *Fait dans la 0.26.0* : une brique par cloud ; OVHcloud (instances et bases) reste à rattacher.
2. **Répartiteur de charge** : devant les machines ou le cluster, avec sa sonde de santé ; adresse publique en sortie.
3. **DNS** : la zone et l'enregistrement vers le répartiteur.
4. **Cache managé** : le cache, et son adresse de connexion rangée dans les secrets comme la base de données.
5. **File de messages** : la file, et son adresse transmise à l'application.
6. **Fonctions serverless** : la fonction, son déclencheur HTTP et son déploiement par la CI.
7. **Chiffrement** : une clé, utilisée pour l'état OpenTofu, les disques et les secrets.
8. **CDN et pare-feu** : le CDN devant l'application, avec le pare-feu applicatif.

Ordre de travail : le réseau privé d'abord, puis le répartiteur et le DNS, puis le cache et les files, enfin les
fonctions, le chiffrement et le CDN. Le Secret Manager et l'IAM d'OVHcloud, absents du catalogue, s'y ajoutent.

À confirmer au développement : le nom exact des ressources dans chaque fournisseur OpenTofu et leurs options, et ce
que la documentation d'Outscale détaille au-delà de sa page des services (Net, sous-réseaux, DNS, KMS). Sources :
pages produits d'AWS, Google Cloud, Azure, Scaleway et OVHcloud, et page des services d'Outscale, consultées le
20 octobre 2026.
