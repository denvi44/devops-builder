# Mise en route — Mon projet

<!-- Généré par DevOps Builder — à relire avant usage. -->

Les gestes à faire une fois, dans l'ordre, avant le premier pipeline. Chaque section se vérifie avant de passer à la suivante.

## 1. Hôtes

Sur chaque hôte : un compte `deploy` avec la clé publique de la CI (la clé privée va dans `SSH_PRIVATE_KEY`), membre du groupe docker, Docker et son extension Compose installés.

```bash
ssh-keygen -t ed25519 -N '' -f ci_deploy -C ci-deploy   # sur le poste
sudo useradd -m -s /bin/bash deploy
sudo install -d -m 700 -o deploy -g deploy /home/deploy/.ssh
sudo tee /home/deploy/.ssh/authorized_keys < ci_deploy.pub
sudo usermod -aG docker deploy
```

Empreinte des hôtes dans `SSH_KNOWN_HOSTS` (facultatif, recommandé) : `ssh-keyscan <hôte>`.

## 2. Variables CI

5 variable(s) à déclarer (liste dans `PIPELINE.md`). Le script les déclare avec l'outil de la forge, sans écrire les valeurs dans le dépôt :

```bash
bash scripts/ci-variables.sh --dry-run   # ce qui serait déclaré
bash scripts/ci-variables.sh
```

## 3. Premier déploiement

Pousser sur la branche principale : chaque environnement se déploie dans l'ordre, la production après approbation.

```bash
ssh "<hôte>" "cd /opt/mon-app && docker compose -p mon-app ps"
```

## 4. Analyse dynamique (ZAP)

Le job ZAP analyse l'application juste après son déploiement : l'adresse `ZAP_TARGET_URL` doit répondre depuis les machines de la CI (une préproduction réservée au réseau interne demande un runner dans ce réseau). Vérifier, puis lancer la même analyse depuis le poste pour voir le rapport avant le pipeline (le dossier `.zap` doit être inscriptible par l'utilisateur de l'image) :

```bash
curl -fsS -o /dev/null -w '%{http_code}\n' "https://recette.boutique.fr"   # 200 (ou 30x) attendu
chmod a+w .zap
docker run --rm -v "$PWD/.zap:/zap/wrk:rw" ghcr.io/zaproxy/zaproxy:2.17.0 zap-baseline.py -t "https://recette.boutique.fr" -c rules.tsv -r zap-report.html -I; echo "code $?"   # 0 : rien de bloquant, 1 : règle FAIL, 3 : erreur
```

Rapport : `.zap/zap-report.html` (à ne pas committer) ; dans la CI, artefact du job. Une alerte sans objet se passe à `IGNORE` dans `.zap/rules.tsv`, avec la raison en commentaire ; une alerte à corriger sans attendre passe à `FAIL`.

## 5. Entretien

- Renovate : job planifié (quotidien) avec l'image renovate/renovate et `RENOVATE_TOKEN`.
