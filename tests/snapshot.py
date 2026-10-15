# SPDX-License-Identifier: Apache-2.0
"""Instantanés de non-régression : ce que l'application génère pour un corpus fixe de projets.

    python tests/snapshot.py sortie/      écrit un instantané (un dossier par projet)

Le corpus réunit les exemples livrés, la matrice des tests de génération et un échantillon
déterministe des combinaisons de l'assistant. Pour chaque projet : tous les fichiers
générés (date du rapport neutralisée) et les diagnostics des règles. tests/test_regression.py
compare la génération courante à l'instantané enregistré dans tests/golden/.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

from devops_builder.catalog import build_catalog  # noqa: E402
from devops_builder.generators import generate  # noqa: E402
from devops_builder.model import Project  # noqa: E402
from devops_builder.rules import RuleEngine  # noqa: E402

EXAMPLES = HERE.parent / "devops_builder" / "data" / "examples"
GOLDEN = HERE / "golden"
WIZARD_STEP = 97  # une combinaison de l'assistant sur 97 (≈ 50 projets)
LEGACY_ENV_PRESETS = ("prod", "staging-prod", "dev-staging-prod")
DATE = re.compile(r"le \d{4}-\d{2}-\d{2}\.")
UID = re.compile(r"\buid: '?[0-9a-f]{8}'?")


def _stable_uids(text: str) -> str:
    """Les identifiants de briques sont aléatoires : numérotés dans l'ordre pour l'instantané."""
    counter = iter(range(1, 10_000))
    return UID.sub(lambda _m: f"uid: brique{next(counter):03d}", text)


def corpus() -> dict[str, Project]:
    from test_generators import MATRIX
    from test_starter import all_answers

    from devops_builder.starter import build_starter
    catalog = packaged_catalog()
    cases: dict[str, Project] = {}
    for path in sorted(EXAMPLES.glob("*.devops.yaml")):
        cases[f"exemple-{path.name.split('.')[0]}"] = Project.load(path)
    for name, p in MATRIX.items():
        cases[f"matrice-{name}"] = p
    # Échantillon historique : seulement les modèles d'environnements de la 0.4, pour que
    # l'ajout d'un modèle ne décale pas la numérotation des cas déjà figés.
    legacy = [a for a in all_answers() if a.envs in LEGACY_ENV_PRESETS]
    for i, answers in enumerate(legacy):
        if i % WIZARD_STEP == 0:
            cases[f"assistant-{i:04d}"] = build_starter(answers, catalog)
    for name, project in extra_cases(catalog).items():
        cases[name] = project
    return cases


def extra_cases(catalog) -> dict[str, Project]:
    """Cas ajoutés après la 0.4 : un par fonctionnalité qui change les fichiers générés."""
    from devops_builder.starter import StarterAnswers, build_starter
    out: dict[str, Project] = {}
    try:
        from devops_builder.model import ENV_PRESETS
    except ImportError:  # pragma: no cover
        return out
    for preset in ENV_PRESETS:
        if preset in LEGACY_ENV_PRESETS:
            continue
        for hosting, cloud in (("docker-host", None), ("kubernetes", None), ("kubernetes-managed", "aws")):
            a = StarterAnswers(forge="gitlab", hosting=hosting, cloud=cloud, envs=preset, gitops=False)
            out[f"envs-{preset}-{hosting}"] = build_starter(a, catalog)
    # hôte Docker partagé par les environnements hors production : ports décalés
    shared = build_starter(StarterAnswers(forge="gitlab", hosting="docker-host", envs="dev-staging-prod"), catalog)
    for env in shared.environments:
        if env.kind != "production" and hasattr(env, "host"):
            env.host = "vm-hors-prod"
    out["ports-hote-partage"] = shared
    # 0.8 : étape Données — base autogérée, opérateur, services managés, migrations
    if "database" in getattr(StarterAnswers, "__dataclass_fields__", {}):
        db_cases = {
            "donnees-hote-docker": dict(hosting="docker-host", envs="dev-recette-prod", database="postgresql",
                                        cache=True, migrations="alembic upgrade head"),
            "donnees-vm-ansible": dict(hosting="vm", envs="prod", database="mariadb"),
            "donnees-k3s-cloudnativepg": dict(hosting="kubernetes", envs="dev-staging-prod", database="postgresql",
                                              migrations="npx prisma migrate deploy"),
            "donnees-k3s-gitops-kustomize": dict(hosting="kubernetes", envs="staging-prod", gitops=True,
                                                 k8s_deploy="kustomize", database="mongodb", cache=True),
            "donnees-serverless-gcp": dict(hosting="serverless", cloud="gcp", envs="prod", database="postgresql"),
        }
        for cloud in ("aws", "gcp", "azure", "scaleway", "ovhcloud"):
            db_cases[f"donnees-managee-{cloud}"] = dict(hosting="kubernetes-managed", cloud=cloud, envs="staging-prod",
                                                       database="mysql" if cloud == "azure" else "postgresql")
        for name, answers in db_cases.items():
            out[name] = build_starter(StarterAnswers(forge="gitlab", **answers), catalog)
    # 0.9 : outillage Terraform (TFLint, Infracost) et Floci
    if "floci" in catalog:
        from devops_builder.model import env_preset
        for forge, ci in (("gitlab", "gitlab-ci"), ("github", "github-actions")):
            p = Project(name="IaC AWS et Floci", target="kubernetes-managed", environments=env_preset("staging-prod"))
            p.app.image_name = "boutique"
            for t in (forge, ci, "buildkit", "unit-tests", "aws", "ecr", "eks", "helm", "opentofu", "s3", "aws-rds",
                      "tflint", "infracost", "floci"):
                p.add(t, catalog[t].stage)
            p.bricks_for("eks")[0].params = {"cluster_name": "boutique"}
            p.bricks_for("s3")[0].params = {"bucket": "boutique-tfstate"}
            out[f"iac-floci-{forge}"] = p
        # 0.10 : Ansible — hôtes par environnement, sans Compose, registre privé
        hosts = Project(name="Ansible", target="vm", environments=env_preset("staging-prod"))
        hosts.app.image_name = "site"
        for t in ("gitlab", "gitlab-ci", "buildkit", "harbor", "ansible", "ansible-lint", "docker-compose", "traefik"):
            hosts.add(t, catalog[t].stage)
        hosts.bricks_for("harbor")[0].params = {"url": "registry.exemple.fr"}
        hosts.bricks_for("ansible")[0].params = {"hosts": "app1.exemple.fr, app2.exemple.fr"}
        hosts.env("staging").overrides["ansible"] = {"hosts": "recette.exemple.fr"}
        out["ansible-hotes-par-environnement"] = hosts
        alone = Project(name="Ansible seul", target="vm")
        alone.app.image_name = "site"
        for t in ("github", "github-actions", "buildkit", "ghcr", "ansible"):
            alone.add(t, catalog[t].stage)
        out["ansible-sans-compose"] = alone
        # 0.11 : machines créées par Terraform, inventaire Ansible et hôte SSH lus dans ses sorties
        from devops_builder.starter import host_clouds
        for cloud in host_clouds("vm", False):
            out[f"machines-ansible-{cloud}"] = build_starter(StarterAnswers(
                forge="gitlab", hosting="vm", cloud=cloud, envs="dev-recette-prod", shared_host=True,
                secnumcloud=cloud == "outscale"), catalog)
        out["machines-ssh-aws-github"] = build_starter(StarterAnswers(
            forge="github", hosting="docker-host", cloud="aws", envs="staging-prod"), catalog)
        for cloud in ("scaleway", "ovhcloud", "outscale"):
            out[f"iac-etat-{cloud}"] = build_starter(StarterAnswers(
                forge="gitlab", hosting="kubernetes-managed", cloud=cloud, envs="staging-prod",
                secnumcloud=cloud == "outscale"), catalog)
    # 0.12 : secrets — SOPS, Vault / OpenBao lus par la CI, External Secrets, coffres des clouds
    if "secrets" in getattr(StarterAnswers, "__dataclass_fields__", {}):
        sec_cases = {
            "secrets-sops-ansible-github": dict(forge="github", hosting="vm", envs="staging-prod",
                                                database="postgresql", cache=True, secrets="sops"),
            "secrets-openbao-eso-helm": dict(hosting="kubernetes", envs="dev-staging-prod", database="mysql",
                                             secrets="openbao"),
            "secrets-openbao-eso-kustomize": dict(hosting="kubernetes", envs="staging-prod", k8s_deploy="kustomize",
                                                  database="postgresql", cache=True, secrets="openbao"),
            "secrets-serverless-gcp": dict(hosting="serverless", cloud="gcp", envs="staging-prod",
                                           database="postgresql", secrets="cloud"),
        }
        for cloud in ("aws", "gcp", "azure"):
            sec_cases[f"secrets-coffre-{cloud}"] = dict(hosting="kubernetes-managed", cloud=cloud, envs="staging-prod",
                                                        database="postgresql", cache=True, secrets="cloud")
        for name, answers in sec_cases.items():
            answers.setdefault("forge", "gitlab")
            out[name] = build_starter(StarterAnswers(**answers), catalog)
        bao = build_starter(StarterAnswers(forge="gitlab", hosting="docker-host", envs="staging-prod",
                                           database="postgresql", secrets="openbao"), catalog)
        bao.bricks_for("openbao")[0].params = {"address": "https://coffre.exemple.fr", "kv_mount": "apps"}
        out["secrets-openbao-existant-compose"] = bao
        vault = Project(name="Vault lu par la CI", target="kubernetes")
        vault.app.image_name = "boutique"
        for t in ("github", "github-actions", "buildkit", "ghcr", "k3s", "helm", "postgresql", "vault"):
            vault.add(t, catalog[t].stage)
        vault.bricks_for("vault")[0].params = {"address": "https://vault.exemple.fr", "jwt_role": "boutique-deploy"}
        out["secrets-vault-ci-helm"] = vault
    # 0.14 : connexion réglable, poste de développement, restauration, sauvegardes CloudNativePG
    if "connections" in getattr(StarterAnswers, "__dataclass_fields__", {}):
        def brick(p: Project, tool: str, **params) -> Project:
            p.bricks_for(tool)[0].params.update(params)
            return p
        out["donnees-spring-jdbc-compose"] = brick(build_starter(StarterAnswers(
            forge="gitlab", hosting="docker-host", envs="staging-prod", language="java", database="postgresql",
            connections={"sql": {"url_var": "SPRING_DATASOURCE_URL", "url_format": "jdbc"}}), catalog),
            "postgresql")
        out["donnees-variables-separees-k3s"] = brick(build_starter(StarterAnswers(
            forge="github", hosting="kubernetes", envs="staging-prod", database="mariadb", cache=True,
            connections={"sql": {"url_var": "DB_URL", "url_format": "parts"}}), catalog), "mariadb")
        s3 = build_starter(StarterAnswers(forge="gitlab", hosting="kubernetes", envs="dev-staging-prod",
                                          database="postgresql"), catalog)
        out["donnees-cnpg-sauvegarde-s3"] = brick(s3, "cloudnative-pg", backup_destination="s3://boutique-sauvegardes",
                                                  backup_endpoint="https://s3.fr-par.scw.cloud", url_format="jdbc")
        for cloud in ("aws", "gcp"):
            p = build_starter(StarterAnswers(forge="gitlab", hosting="kubernetes-managed", cloud=cloud,
                                             envs="staging-prod"), catalog)
            p.add("cloudnative-pg", "data")
            out[f"donnees-cnpg-sauvegarde-{cloud}"] = p
    # 0.15 : fournisseur d'identité — Keycloak, Dex, connexion unique des outils et de l'application
    if "identity" in getattr(StarterAnswers, "__dataclass_fields__", {}):
        kc = {"hostname": "auth.boutique.fr", "tools_domain": "boutique.fr", "app_url": "https://boutique.fr"}
        compose = build_starter(StarterAnswers(forge="gitlab", hosting="docker-host", envs="staging-prod",
                                               database="postgresql", identity="keycloak", secrets="openbao"), catalog)
        compose.add("grafana", catalog["grafana"].stage)
        out["identite-keycloak-compose"] = brick(brick(compose, "keycloak", **kc), "openbao",
                                                 address="https://coffre.boutique.fr")
        k3s = build_starter(StarterAnswers(forge="github", hosting="kubernetes", envs="dev-staging-prod",
                                           gitops=True, identity="keycloak", secrets="openbao"), catalog)
        out["identite-keycloak-k3s-gitops"] = brick(k3s, "keycloak", **kc)
        dex = build_starter(StarterAnswers(forge="gitlab", hosting="kubernetes-managed", cloud="gcp",
                                           envs="staging-prod", identity="dex", k8s_deploy="kustomize"), catalog)
        out["identite-dex-gke"] = brick(dex, "dex", hostname="dex.boutique.fr", org="boutique")
        # 0.17 : Zabbix sur hôte Docker (Traefik, variables CI) et sur VM (Ansible, SOPS)
        zbx = build_starter(StarterAnswers(forge="gitlab", hosting="docker-host", envs="staging-prod",
                                           database="postgresql", observability="none"), catalog)
        zbx.add("zabbix", "observability", hostname="zabbix.boutique.fr")
        out["supervision-zabbix-compose"] = zbx
        zvm = build_starter(StarterAnswers(forge="github", hosting="vm", envs="prod", observability="none",
                                           secrets="sops"), catalog)
        zvm.add("zabbix", "observability")
        out["supervision-zabbix-vm-sops"] = zvm
        # 1.0 : ZAP après le déploiement de l'environnement analysé, dans chaque famille de CI
        zg = build_starter(StarterAnswers(forge="gitlab", hosting="docker-host", envs="staging-prod"), catalog)
        zg.add("zap", "security", target_url="https://recette.boutique.fr")
        out["dast-zap-gitlab-compose"] = zg
        zh = build_starter(StarterAnswers(forge="github", hosting="kubernetes", envs="dev-staging-prod"), catalog)
        zh.add("zap", "security", scan="full", blocking=True, environment="dev")
        next(e for e in zh.environments if e.id == "dev").overrides["zap"] = {"target_url": "https://dev.boutique.fr"}
        out["dast-zap-github-k8s-bloquant"] = zh
        for ci_id in ("tekton", "azure-pipelines", "google-cloud-build"):
            zc = build_starter(StarterAnswers(forge="github", ci=ci_id, hosting="kubernetes-managed",
                                              cloud="gcp" if ci_id == "google-cloud-build" else "azure",
                                              envs="staging-prod"), catalog)
            zc.add("zap", "security", scan="api", target_url="https://api-recette.boutique.fr/openapi.json")
            out[f"dast-zap-{ci_id}"] = zc
        # 0.18 : SonarQube relié à Keycloak en SAML (hôte Docker), Harbor en OIDC avec Dex (Kubernetes)
        sq = build_starter(StarterAnswers(forge="gitlab", hosting="docker-host", envs="prod", identity="keycloak"),
                           catalog)
        sq.add("sonarqube", "test")
        sq.add("grafana", "observability")
        out["identite-keycloak-sonarqube-compose"] = brick(sq, "keycloak", hostname="auth.boutique.fr",
                                                            tools_domain="boutique.fr")
        hb = build_starter(StarterAnswers(forge="github", hosting="kubernetes", envs="staging-prod", identity="dex"),
                           catalog)
        for b in list(hb.bricks_for("ghcr")):
            hb.remove(b.uid)
        hb.add("harbor", "artifacts", url="harbor.boutique.fr")
        hb.add("sonarqube", "test")
        out["identite-dex-harbor-k3s"] = brick(hb, "dex", hostname="dex.boutique.fr", tools_domain="boutique.fr")
        out["identite-dex-compose-github"] = brick(build_starter(StarterAnswers(
            forge="github", hosting="vm", envs="staging-prod", identity="dex"), catalog), "dex",
            hostname="dex.boutique.fr")
    return out


_CATALOG = None


def packaged_catalog():
    """Catalogue livré seul : un catalogue utilisateur ne doit pas changer l'instantané."""
    global _CATALOG
    if _CATALOG is None:
        _CATALOG = build_catalog(user_dir=None)
    return _CATALOG


def render_case(project: Project) -> dict[str, str]:
    catalog = packaged_catalog()
    engine = RuleEngine(catalog)
    diags = engine.evaluate(project)
    lines = [f"{d.severity.value} {d.rule_id} {d.message}" for d in diags]
    out = {"_diagnostics.txt": "\n".join(sorted(lines)) + "\n"}
    if RuleEngine.blocking(diags):
        return out
    result = generate(project, catalog, engine)
    for rel, content in result.files.items():
        content = DATE.sub("le AAAA-MM-JJ.", content) if rel == "PIPELINE.md" else content
        out[rel] = _stable_uids(content) if rel == "devops-builder.yaml" else content
    return out


def write_snapshot(root: Path) -> int:
    count = 0
    for name, project in corpus().items():
        for rel, content in render_case(project).items():
            path = root / name / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            count += 1
    return count


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else GOLDEN
    print(f"{write_snapshot(target)} fichiers écrits dans {target}")
