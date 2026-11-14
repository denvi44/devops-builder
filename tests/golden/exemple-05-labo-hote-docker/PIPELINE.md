# Labo DevOps sur hôte Docker — pipeline généré

Généré par DevOps Builder le AAAA-MM-JJ. Cible : Hôte Docker unique.

## Environnements

Projet « plateforme seule » : les outils tournent sur l'hôte Docker, sans application à livrer.

| Environnement | Type | Approbation | Cluster | Espace de noms / projet |
| --- | --- | --- | --- | --- |
| Production (`production`) | Production | non | — | `labo-devops-sur-hote-docker` |

## Ports

| Composant | Port publié | Port du conteneur | Usage | Exposition |
| --- | --- | --- | --- | --- |
| Prometheus | 9090 | 9090 | interface et API | publié sur l'hôte Docker |
| Grafana | 3000 | 3000 | interface web | publié sur l'hôte Docker |
| Gitea | 3001 | 3000 | interface web | publié sur l'hôte Docker |
| Gitea | 2222 | 22 | SSH Git | publié sur l'hôte Docker |
| Zabbix | 8080 | 8080 | interface web | publié sur l'hôte Docker |
| Zabbix | 10051 | 10051 | agents actifs et trappeur | publié sur l'hôte Docker |
| Zabbix | 10050 | 10050 | agent de l'hôte | réseau de l'hôte Docker |

## Dimensionnement

Besoin estimé à partir des services Compose de l'hôte (marge de 25 %), pour chaque environnement porté, plus le système et Docker. Un ordre de grandeur pour une charge modeste, à confirmer par la supervision.

Services : prometheus (1024 Mio, estimé), grafana (512 Mio), gitea (1024 Mio, estimé), zabbix-server (512 Mio, estimé), zabbix-web (256 Mio, estimé), zabbix-agent (64 Mio, estimé), zabbix-db (512 Mio, estimé), zabbix-agent-host (64 Mio, estimé).

| Environnements | Besoin | Type retenu | Verdict |
| --- | --- | --- | --- |
| production | 2 vCPU, 5,3 Gio | hôte existant | prévoir au moins 2 vCPU et 5,3 Gio |

## Briques

| Étape | Brique | Licence | Fiche |
| --- | --- | --- | --- |
| Source | Gitea | MIT | vérifiée |
| Déploiement | Docker Compose | Apache-2.0 | vérifiée |
| Observabilité | Zabbix | AGPL-3.0 | vérifiée |
| Observabilité | Prometheus | Apache-2.0 | vérifiée |
| Observabilité | Grafana | AGPL-3.0 | vérifiée |

## Étapes CI

Aucune : sans application, il n'y a rien à construire ni à livrer. La pile se démarre à la main (docs/mise-en-route.md).

## Diagnostics restants

Aucun.

## Notes

- Mise en route pas à pas, avec les commandes du projet : docs/mise-en-route.md.
- Zabbix : interface sur http://<hôte>:8080 ; compte Admin / zabbix au premier accès, à changer aussitôt (docs/mise-en-route.md). Un agent supervise le serveur Zabbix, un second l'hôte Docker et ses conteneurs (à déclarer une fois, docs/mise-en-route.md) : ce second agent lit le socket Docker, ce qui lui donne des droits étendus sur l'hôte. Les autres machines reçoivent chacune un agent, qui s'annonce sur le port 10051.

## Fichiers générés

- `PIPELINE.md`
- `deploy/docker-compose.yml`
- `deploy/secrets.sh`
- `devops-builder.yaml`
- `docs/mise-en-route.md`
- `scripts/db-backup.sh`
- `scripts/db-restore.sh`
