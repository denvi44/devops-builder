# Hébergement souverain SecNumCloud

**Objectif** : une application exigeant un hébergement qualifié SecNumCloud (téléservice d'une
administration, données de santé…) : deux machines virtuelles créées par OpenTofu chez Outscale, configurées et
déployées par Ansible avec Docker Compose, secrets chiffrés dans le dépôt avec SOPS et age, base PostgreSQL sur
chaque machine.

**Il faut** : un compte Outscale et ses clés d'accès ; un projet GitLab ; sur le poste, `tofu`, `age`, `sops`,
`aws` (pour le stockage objet compatible S3) et Ansible. Durée : une heure et demie environ.

![Le pipeline créé par l'assistant : GitLab, GitLab CI, BuildKit, Renovate, tests, Gitleaks, Trivy, Cosign,
Outscale, Ansible, machines Outscale, OpenTofu, stockage objet Outscale, PostgreSQL, Docker Compose, Traefik,
SOPS, Prometheus et Grafana](../captures/souverain.png)

## Ce que garantit l'exigence SecNumCloud, et ce qu'elle ne garantit pas

Paramètres du projet › « Exiger un hébergement qualifié SecNumCloud » écarte du catalogue, et signale par la
règle bloquante R12, toute brique qui dépend d'un cloud dont les régions publiques ne sont pas qualifiées. Le
catalogue tient Outscale pour qualifié (cloud public, SecNumCloud 3.2) ; OVHcloud n'est que partiellement
qualifié (Bare Metal Pod), à vérifier offre par offre.

L'application ne voit que les briques du pipeline. Restent hors de son contrôle, et à placer soi-même dans le
périmètre qualifié : **la forge et ses exécuteurs de CI** (gitlab.com et ses exécuteurs partagés ne le sont pas :
installer GitLab et ses exécuteurs sur une infrastructure qualifiée), les registres d'où viennent les images de
base, et les services tiers appelés par l'application. La qualification de chaque offre se vérifie dans le
[catalogue des solutions qualifiées de l'ANSSI](https://cyber.gouv.fr/produits-services-qualifies), mis à jour
chaque mois, avant de s'engager.

## 1. Décrire le projet

Ctrl+N ouvre l'assistant :

1. **Application** : *Téléservice*, *Python*, image *teleservice*, port *8000*.
2. **Code et intégration continue** : *GitLab* (instance hébergée dans le périmètre qualifié).
3. **Hébergement** : *Des machines virtuelles (Ansible)* ; cocher « Exiger un hébergement qualifié
   SecNumCloud » : la liste des clouds se réduit à Outscale et OVHcloud. Choisir *Outscale — machines créées par
   Terraform*.
4. **Environnements et options** : *Préproduction → production* ; base *PostgreSQL* ; secrets *Chiffrés dans
   le dépôt (SOPS + age)*.
5. **Récapitulatif** : « Créer le projet ».

## 2. Renseigner les paramètres

Trois avertissements R34 : la brique **Outscale Object Storage (OOS)** › « Bucket de l'état Terraform »,
la brique **SOPS** › « Destinataires age », et **Traefik** › « Adresse publique de l'application ». Le
destinataire age se règle après avoir créé la clé (étape 4 ci-dessous) : on y revient alors, puis on régénère.

## 3. Générer

| Fichier | Rôle |
| --- | --- |
| `infra/terraform/` | deux machines Outscale (une par environnement) dimensionnées pour leurs services, leur pare-feu (SSH, HTTP, HTTPS), une adresse publique chacune, cloud-init qui pose le compte `deploy` et Docker ; état dans le stockage objet d'Outscale |
| `ansible/` | `site.yml` prépare les hôtes, `deploy.yml` déploie l'application ; un inventaire par environnement, rempli depuis les sorties de la pile par `scripts/tf-inventory.sh` |
| `deploy/docker-compose.yml` | l'application, PostgreSQL, Traefik, Prometheus et Grafana |
| `.sops.yaml`, `scripts/secrets-seed.sh`, `scripts/secrets-fetch.sh` | chiffrement des secrets de chaque environnement dans `deploy/secrets/`, et leur lecture par la CI |
| `.gitlab-ci.yml` | tests et analyses, image, plan puis apply OpenTofu, déploiement Ansible par environnement, la production après approbation |

`PIPELINE.md` donne le type de machine retenu pour chaque environnement (`tinav6.c2r4p2`, 2 vCPU et 4 Gio, pour
les services de ce pipeline) et la marge prise.

## 4. Mettre en route

Dans l'ordre de `docs/mise-en-route.md` :

1. **État OpenTofu** : créer le bucket dans le stockage objet d'Outscale, avec les clés Outscale et l'outil
   `aws` (le service est compatible S3). Ce backend n'a pas de verrou d'état : la CI sérialise les apply, mais
   un apply lancé à la main pendant un job reste possible.
2. **Premier apply**, depuis le poste : `tofu -chdir=infra/terraform init`, `plan`, `apply`. La clé publique
   de déploiement est passée par `TF_VAR_ssh_public_key`.
3. **Clé age et secrets** : `age-keygen` crée la paire ; la clé publique va dans la brique SOPS (« Destinataires
   age »), on régénère le projet pour mettre `.sops.yaml` à jour ; la clé privée va dans la variable CI
   `SOPS_AGE_KEY`. Puis `scripts/secrets-seed.sh staging` et `production` chiffrent un mot de passe par
   environnement, à committer.
4. **Hôtes** : rien à préparer, cloud-init l'a fait ; `bash scripts/tf-inventory.sh staging` écrit
   l'inventaire Ansible. Faire pointer les noms d'hôte de l'application vers l'adresse publique de chaque
   machine.
5. **Variables de la CI** : `OSC_ACCESS_KEY`, `OSC_SECRET_KEY`, `SOPS_AGE_KEY`, `SSH_PRIVATE_KEY`… déclarées par
   `bash scripts/ci-variables.sh`. Outscale n'offre pas de fédération d'identité pour la CI : ses clés sont
   statiques, à protéger (branche principale seulement) et à renouveler.
6. **Premier déploiement** : pousser sur la branche principale.
7. **Sauvegardes** : une sauvegarde et une restauration d'essai sur la préproduction ; Ansible planifie
   ensuite `db-backup.sh`. Copier les sauvegardes hors de la machine, dans le périmètre qualifié.

## 5. Vérifier

- Projet › Valider : `tofu validate` sur la pile, `ansible-playbook --syntax-check` sur les playbooks (avec la
  collection `community.docker`, installée par `ansible-galaxy collection install -r ansible/requirements.yml`),
  ShellCheck sur les scripts, `docker compose config`.
- Sur une machine : `ssh deploy@<adresse> "cd /opt/teleservice && docker compose -p teleservice ps"`.

## Limites à connaître

La création des machines n'a été vérifiée que par `tofu validate`, sans apply réel. Le Kubernetes managé
d'Outscale (OKS) n'a pas encore de ressource OpenTofu générée : pour Kubernetes en souverain, la règle R31 le
signale et seul un commentaire est écrit. Voir la section « Limites connues » du
[README](https://github.com/denvi44/devops-builder#limites-connues).
