# Guide de l'utilisateur

Ce guide mène de l'installation au premier déploiement. Il suppose de connaître sa forge (GitLab, GitHub…)
et la cible visée ; il n'exige pas de connaître chaque outil généré : les fichiers produits sont commentés, et
chaque projet reçoit un mode d'emploi, `docs/mise-en-route.md`, qui donne les gestes à faire dans l'ordre.

## Installer

Avec Python 3.11 à 3.14, par [pipx](https://pipx.pypa.io/) :

```bash
pipx install izinum-devops-builder
devops-builder
```

Sans Python : télécharger l'exécutable de son système sur la
[page des publications](https://github.com/denvi44/devops-builder/releases) (Linux, Windows, macOS Apple Silicon),
le décompresser et le lancer. Les exécutables ne sont pas encore signés : le
[README](https://github.com/denvi44/devops-builder#installation) explique comment passer l'avertissement de
Windows et de macOS, et comment vérifier leur provenance.

## Le cycle de travail

1. **Décrire le projet** avec l'assistant (Ctrl+N) : le dossier de l'application, la forge, l'hébergement, les
   environnements et les options. L'assistant lit le dossier s'il est donné (langage, port, Dockerfile, bases de
   données, CI déjà en place) et pré-remplit ses réponses.
2. **Ajuster le pipeline** sur le canevas : ajouter, déplacer ou retirer des briques, renseigner leurs
   paramètres dans le panneau Propriétés.
3. **Corriger les diagnostics** : chaque incohérence est signalée avec sa gravité (bloquant, avertissement,
   info) et, le plus souvent, une correction en un clic.
4. **Générer** (Ctrl+G) : aperçu des fichiers, puis écriture dans un dossier (avec les différences avant
   d'écraser), dans une archive .zip, ou export vers une nouvelle branche Git avec demande de fusion.
5. **Mettre en route** en suivant `docs/mise-en-route.md` du projet généré, puis pousser : la CI déploie chaque
   environnement dans l'ordre, la production après approbation.
6. **Valider** (Ctrl+Maj+V) : les fichiers passent les outils installés sur le poste (schémas, actionlint,
   ShellCheck, `tofu validate`, kubeconform…), puis, pour Kubernetes, un déploiement d'essai dans un cluster kind.

Le projet s'enregistre dans un fichier `.devops.yaml` (Ctrl+S), lisible et versionnable ; une copie,
`devops-builder.yaml`, accompagne les fichiers générés pour qu'on sache d'où ils viennent.

## Pour commencer

- [Prise en main de l'interface](interface.md) : les zones de l'écran, le clavier, les réglages d'affichage.
- Tutoriels, chacun de bout en bout :
    - [Site web sur un hôte Docker](tutoriels/hote-docker.md) — GitLab, Docker Compose, PostgreSQL ;
    - [API sur k3s en GitOps](tutoriels/k3s-gitops.md) — GitHub, Helm, Argo CD ;
    - [Plateforme sur Amazon EKS](tutoriels/eks.md) — GitLab, OpenTofu, RDS, coffre de secrets AWS ;
    - [Hébergement souverain SecNumCloud](tutoriels/souverain.md) — Outscale, machines virtuelles, Ansible, SOPS.

Les quatre tutoriels partent des réponses enregistrées dans `tools/tutoriels.py` ; un test vérifie que chaque
fichier qu'ils citent est bien généré, pour que le guide suive l'application.
