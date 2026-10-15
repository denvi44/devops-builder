# SPDX-License-Identifier: Apache-2.0
"""Tests de bout en bout : les fichiers générés, exécutés pour de vrai (lot 0.17).

    python tools/e2e/run.py --list                 scénarios disponibles
    python tools/e2e/run.py kind-helm-cnpg         lance un scénario (Docker, kind, kubectl, helm requis)
    python tools/e2e/run.py compose-postgresql --plan   affiche les étapes sans rien exécuter

Chaque scénario construit un projet avec l'API de l'application, génère ses fichiers dans un dossier
jetable, puis exécute ce qu'un utilisateur exécuterait : scripts générés, docker compose, kubectl.
L'application déployée est tools/e2e/app : elle répond 200 sur /db seulement si chaque base accepte une
connexion authentifiée avec les secrets que le pipeline lui a transmis.

Le rapport (étapes, durées, sortie des échecs) est écrit sur la sortie standard et, dans GitHub Actions,
dans le résumé du job ($GITHUB_STEP_SUMMARY). Code de sortie : 0 si tout passe, 1 sinon, 2 si usage.
"""

from __future__ import annotations

import argparse
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

from devops_builder.catalog import build_catalog  # noqa: E402
from devops_builder.generators import generate  # noqa: E402
from devops_builder.model import Project, env_preset  # noqa: E402
from devops_builder.rules import RuleEngine  # noqa: E402
from devops_builder.starter import StarterAnswers, build_starter  # noqa: E402

APP_DIR = HERE / "app"
APP = "boutique"
GH = ("github", "github-actions", "buildkit", "ghcr")


@dataclass
class Step:
    name: str
    command: list[str] | str            # liste : exécutée telle quelle ; texte : par bash -euo pipefail
    cwd: Path | None = None
    env: dict[str, str] = field(default_factory=dict)
    retries: int = 1                     # tentatives (attente d'un service)
    always: bool = False                 # nettoyage : exécutée même après un échec
    evidence: bool = False               # sa sortie prouve le résultat : publiée en annotation GitHub


@dataclass
class Result:
    step: Step
    ok: bool
    seconds: float
    output: str


@dataclass
class Scenario:
    name: str
    description: str
    project: Callable[[], Project]
    steps: Callable[[Path, object], list[Step]]   # (dossier généré, IR) → étapes
    tools: tuple[str, ...]


def _project(target: str, *tools: str, envs: str = "prod", **params) -> Project:
    p = Project(name="Boutique e2e", target=target, environments=env_preset(envs))
    p.app.image_name, p.app.port = APP, 8000
    catalog = _catalog()
    for t in tools:
        p.add(t, catalog[t].stage, **params.get(t.replace("-", "_"), {}))
    return p


_CAT = None


def _with(project: Project, **params: dict) -> Project:
    """Réglages saisis dans le panneau Propriétés, par identifiant d'outil."""
    for _, brick in project.all_bricks():
        brick.params.update(params.get(brick.tool.replace("-", "_"), {}))
    return project


def _catalog():
    global _CAT
    if _CAT is None:
        _CAT = build_catalog(user_dir=None)
    return _CAT


# ------------------------------------------------------------------ Kubernetes (kind)
def _kind_steps(out: Path, ir) -> list[Step]:
    env = ir.envs[0]
    ns = ir.namespace(env)
    cluster = f"{ir.app}-test"[:40]
    ctx = f"kind-{cluster}"
    image = f"devops-builder.local/{ir.app}:e2e"
    check_db = f"""
kubectl --context {ctx} -n {ns} port-forward service/{ir.app} 18081:80 >/tmp/pf.log 2>&1 &
pf=$!
trap 'kill $pf 2>/dev/null || true' EXIT
for _ in $(seq 1 30); do
  code=$(curl -s -o /tmp/db.json -w '%{{http_code}}' http://127.0.0.1:18081/db || true)
  [ "$code" = 200 ] && {{ cat /tmp/db.json; exit 0; }}
  sleep 2
done
echo "réponse $code :"; cat /tmp/db.json 2>/dev/null || true
kubectl --context {ctx} -n {ns} logs deployment/{ir.app} --tail=40 || true
exit 1
"""
    return [
        Step("Image de l'application de démonstration", ["docker", "build", "-t", image, str(APP_DIR)]),
        Step("scripts/test-kind.sh : cluster, chart ou overlay, rollout, réponse HTTP",
             ["bash", "scripts/test-kind.sh", env.id], cwd=out, env={"IMAGE": image, "KEEP_CLUSTER": "1"}),
        Step("Connexion authentifiée aux bases depuis le pod (/db)", check_db, cwd=out, evidence=True),
        Step("État du cluster", f"kubectl --context {ctx} get pods -A -o wide", always=True),
        Step("Suppression du cluster", ["kind", "delete", "cluster", "--name", cluster], always=True),
    ]


# ------------------------------------------------------------------ hôte Docker (Compose)
def _compose_steps(out: Path, ir) -> list[Step]:
    host = out.parent / "opt" / ir.app        # disposition d'un hôte réel : /opt/<application>
    backups = out.parent / "sauvegardes"
    image = f"devops-builder.local/{ir.app}:e2e"
    password = secrets.token_hex(12)
    env = {"POSTGRESQL_PASSWORD": password, "VALKEY_PASSWORD": secrets.token_hex(12), "IMAGE": image}
    dc = f"docker compose --project-directory {host} -p {ir.app}"
    probe = (f"{dc} exec -T {ir.app} python -c \"import sys,urllib.request as u;"
             "r=u.urlopen('http://127.0.0.1:8000/db',timeout=10);print(r.read().decode());"
             "sys.exit(0 if r.status==200 else 1)\"")
    psql = f"{dc} exec -T postgresql sh -c 'psql -v ON_ERROR_STOP=1 -U \"$POSTGRES_USER\" -d \"$POSTGRES_DB\" -tA'"

    def sql(statement: str) -> str:  # requête par l'entrée standard : pas de guillemets imbriqués
        return f"{psql} <<'SQL'\n{statement}\nSQL"
    return [
        Step("Image de l'application de démonstration", ["docker", "build", "-t", image, str(APP_DIR)]),
        Step("Fichiers posés comme sur l'hôte (/opt/<application>)",
             f"mkdir -p {host} && cp -R {out}/deploy/. {host}/ && ls -la {host}"),
        Step("deploy/secrets.sh : fichiers de secrets", ["sh", "secrets.sh", "secrets"], cwd=host, env=env),
        Step("docker compose up (santé des services attendue)", f"{dc} up -d --wait --wait-timeout 180",
             cwd=host, env={"IMAGE": image}),   # comme le déploiement par SSH : secrets par secrets/*.env
        Step("Connexion authentifiée aux bases depuis l'application (/db)", probe, retries=10, env=env,
             evidence=True),
        Step("Donnée témoin écrite", sql("create table temoin(v text); insert into temoin values ('avant');"),
             env=env),
        Step("scripts/db-backup.sh", ["sh", str(out / "scripts" / "db-backup.sh"), str(host), str(backups)], env=env),
        Step("Donnée témoin modifiée après la sauvegarde", sql("update temoin set v = 'apres';"), env=env),
        Step("scripts/db-restore.sh refuse sans --oui",
             f"! sh {out}/scripts/db-restore.sh {host} \"$(ls {backups}/postgresql-*.dump | head -n 1)\"", env=env),
        Step("scripts/db-restore.sh --oui",
             f"sh {out}/scripts/db-restore.sh {host} \"$(ls {backups}/postgresql-*.dump | head -n 1)\" --oui", env=env),
        Step("Donnée témoin revenue à l'état sauvegardé",
             f"v=$({sql('select v from temoin;')}\n)\necho \"valeur : $v\"\ntest \"$v\" = avant", env=env,
             evidence=True),
        Step("Consommation mesurée (docker stats), à comparer à data/sizing.yaml",
             "docker stats --no-stream --format '{{.Name}} {{.MemUsage}} {{.CPUPerc}}'", always=True, evidence=True),
        Step("Journaux des services", f"{dc} ps -a; {dc} logs --tail=30", always=True, env=env),
        Step("Arrêt et suppression des volumes", f"{dc} down -v --remove-orphans", always=True, env=env),
    ]


def _starter(params: dict[str, dict] | None = None, **answers) -> Callable[[], Project]:
    """Projet construit par l'assistant, comme le ferait un utilisateur : cluster autogéré, un environnement.
    params : réglages de briques saisis ensuite dans le panneau Propriétés, par identifiant d'outil."""
    base = dict(hosting="kubernetes", forge="github", envs="prod", gitops=False, observability="none",
                security=False, quality=False, image_name=APP, port=8000)

    def build() -> Project:
        project = build_starter(StarterAnswers(**{**base, **answers}), _catalog())
        project.name = "Boutique e2e"
        for _, brick in project.all_bricks():
            brick.params.update((params or {}).get(brick.tool, {}))
        return project
    return build


def _port_forward(ctx: str, ns: str, target: str, local: int, remote: int, work: Path) -> str:
    """Redirection de port qui survit à l'étape (sortie détachée), arrêtée par l'étape de nettoyage."""
    name = target.replace("/", "-")
    return f"""
nohup kubectl --context {ctx} -n {ns} port-forward {target} {local}:{remote} >{work}/pf-{name}.log 2>&1 &
echo $! >{work}/pf-{name}.pid
for _ in $(seq 1 30); do
  (exec 3<>/dev/tcp/127.0.0.1/{local}) 2>/dev/null && exit 0
  sleep 1
done
cat {work}/pf-{name}.log; exit 1
"""


def _kind_common(ir, work: Path) -> tuple[str, str, list[Step], list[Step]]:
    cluster = f"{ir.app}-test"[:40]
    ctx = f"kind-{cluster}"
    start = [
        Step("Cluster kind", ["kind", "create", "cluster", "--name", cluster, "--wait", "180s"]),
        Step("platform/install.sh (contexte du cluster de test)",
             f"kubectl config use-context {ctx}\nbash platform/install.sh", cwd=work / "projet"),
    ]
    end = [
        Step("Diagnostic du cluster",
             f"kubectl --context {ctx} get pods -A -o wide; kubectl --context {ctx} get events -A "
             f"--sort-by=.lastTimestamp | tail -n 40", always=True),
        Step("Arrêt des redirections de port", f"for f in {work}/pf-*.pid; do [ -f \"$f\" ] && kill \"$(cat \"$f\")\" "
             "2>/dev/null; done; true", always=True),
        Step("Suppression du cluster", ["kind", "delete", "cluster", "--name", cluster], always=True),
    ]
    return cluster, ctx, start, end


# ------------------------------------------------------------------ coffre : OpenBao + External Secrets
def _vault_steps(out: Path, ir) -> list[Step]:
    work = out.parent
    cluster, ctx, start, end = _kind_common(ir, work)
    ns = ir.namespace(ir.envs[0])
    image = f"devops-builder.local/{ir.app}:e2e"
    bao = f"kubectl --context {ctx} -n openbao exec openbao-0 --"
    vault_env = {"VAULT_ADDR": "http://127.0.0.1:8200"}
    token = f"export VAULT_TOKEN=\"$(jq -r .root_token {work}/bao-init.json)\"\n"
    chart = f"charts/{ir.app}"
    return [
        Step("Image de l'application de démonstration", ["docker", "build", "-t", image, str(APP_DIR)]),
        *start,
        Step("OpenBao démarré (scellé, en attente d'initialisation)",
             f"kubectl --context {ctx} -n openbao wait pod/openbao-0 --for=jsonpath='{{.status.phase}}'=Running "
             "--timeout=300s"),
        # Mode d'emploi : 5 clés, seuil 3, saisies à la main ; le test se contente d'une clé.
        Step("Initialisation et descellement (mode d'emploi, une seule clé pour le test)",
             f"{bao} bao operator init -key-shares=1 -key-threshold=1 -format=json >{work}/bao-init.json\n"
             f"{bao} bao operator unseal \"$(jq -r '.unseal_keys_b64[0]' {work}/bao-init.json)\" >/dev/null\n"
             f"{bao} bao status"),
        Step("Redirection vers OpenBao", _port_forward(ctx, "openbao", "svc/openbao", 8200, 8200, work)),
        Step("scripts/vault-setup.sh", token + "bash scripts/vault-setup.sh", cwd=out, env=vault_env),
        Step("scripts/secrets-seed.sh", token + f"VALKEY_PASSWORD=\"$(openssl rand -hex 16)\" "
             f"bash scripts/secrets-seed.sh {ir.envs[0].id}", cwd=out, env=vault_env),
        Step("Chart de l'application (secrets par External Secrets, pas createSecret)",
             f"kind load docker-image {image} --name {cluster}\n"
             f"kubectl --context {ctx} create namespace {ns} --dry-run=client -o yaml | kubectl --context {ctx} apply -f -\n"
             f"helm --kube-context {ctx} upgrade --install {ir.app} {chart} -n {ns} -f {chart}/values.yaml "
             f"$([ -f {chart}/values-{ir.envs[0].id}.yaml ] && echo -f {chart}/values-{ir.envs[0].id}.yaml) "
             f"--set image.repository={image.rsplit(':', 1)[0]} --set image.tag=e2e --set image.pullPolicy=IfNotPresent "
             "--set replicaCount=1 --set database.postgresql.instances=1", cwd=out),
        Step("ExternalSecret synchronisé depuis OpenBao",
             f"kubectl --context {ctx} -n {ns} wait externalsecret/{ir.app}-valkey --for=condition=Ready "
             f"--timeout=240s\nkubectl --context {ctx} -n {ns} get externalsecret {ir.app}-valkey "
             "-o jsonpath='{.status.conditions[0].message}'", evidence=True),
        Step("Application démarrée", f"kubectl --context {ctx} -n {ns} rollout status deployment/{ir.app} --timeout=420s"),
        Step("Connexion authentifiée aux bases depuis le pod (/db)", _check_db(ctx, ns, ir.app), evidence=True),
        Step("État du coffre et des secrets",
             f"kubectl --context {ctx} -n {ns} describe externalsecret; kubectl --context {ctx} get clustersecretstore "
             "-o wide", always=True),
        *end,
    ]


# ------------------------------------------------------------------ identité : Keycloak derrière Traefik
def _identity_steps(out: Path, ir) -> list[Step]:
    work = out.parent
    cluster, ctx, start, end = _kind_common(ir, work)
    host = "auth.boutique.test"
    realm = APP
    admin = (f"export KEYCLOAK_USER=\"$(kubectl --context {ctx} -n keycloak get secret keycloak-initial-admin "
             "-o jsonpath='{.data.username}' | base64 -d)\"\n"
             f"export KEYCLOAK_PASSWORD=\"$(kubectl --context {ctx} -n keycloak get secret keycloak-initial-admin "
             "-o jsonpath='{.data.password}' | base64 -d)\"\n")
    tf_env = {"TF_VAR_keycloak_url": "http://127.0.0.1:8180", "TF_IN_AUTOMATION": "1", "TF_CLI_ARGS": "-no-color"}
    groups = admin + f"""
kc=http://127.0.0.1:8180
tok=$(curl -fsS -d client_id=admin-cli -d grant_type=password --data-urlencode "username=$KEYCLOAK_USER" \
  --data-urlencode "password=$KEYCLOAK_PASSWORD" $kc/realms/master/protocol/openid-connect/token | jq -r .access_token)
api() {{ curl -fsS -H "Authorization: Bearer $tok" -H 'Content-Type: application/json' "$@"; }}
api -X POST -d '{{"username":"alice","enabled":true,"email":"alice@boutique.test","firstName":"Alice","lastName":"Test"}}' \
  $kc/admin/realms/{realm}/users
uid=$(api "$kc/admin/realms/{realm}/users?username=alice&exact=true" | jq -r '.[0].id')
gid=$(api "$kc/admin/realms/{realm}/groups?search=admins&exact=true" | jq -r '.[0].id')
api -X PUT $kc/admin/realms/{realm}/users/$uid/groups/$gid
cid=$(api "$kc/admin/realms/{realm}/clients?clientId={ir.app}" | jq -r '.[0].id')
claims=$(api "$kc/admin/realms/{realm}/clients/$cid/evaluate-scopes/generate-example-access-token?userId=$uid&scope=openid")
echo "$claims" | jq -c '{{iss, groups}}'
echo "$claims" | jq -e '.groups | index("admins")' >/dev/null
"""
    discovery = f"""
for _ in $(seq 1 60); do
  body=$(curl -sk --resolve {host}:8443:127.0.0.1 https://{host}:8443/realms/master/.well-known/openid-configuration || true)
  iss=$(printf '%s' "$body" | jq -r .issuer 2>/dev/null || true)
  [ "$iss" = "https://{host}/realms/master" ] && {{ echo "émetteur : $iss"; exit 0; }}
  sleep 5
done
echo "réponse : ${{body:0:300}}"; exit 1
"""
    return [
        *start,
        Step("Keycloak prêt (opérateur, base dédiée, 2 instances)", f"""
for _ in $(seq 1 90); do
  if kubectl --context {ctx} -n keycloak wait keycloak/keycloak --for=condition=Ready --timeout=5s >/dev/null 2>&1; then
    kubectl --context {ctx} -n keycloak get keycloak keycloak -o jsonpath='{{.status.conditions}}'; exit 0
  fi
  r=$(kubectl --context {ctx} -n keycloak get pod keycloak-0 -o jsonpath='{{.status.containerStatuses[0].restartCount}}' \\
      2>/dev/null || echo 0)
  if [ "${{r:-0}}" -ge 4 ]; then echo "keycloak-0 a redémarré $r fois : arrêt de l'attente"; exit 1; fi
  sleep 5
done
exit 1
"""),
        Step("Redirection vers Traefik (HTTPS)", _port_forward(ctx, "traefik", "svc/traefik", 8443, 443, work)),
        Step("Découverte OpenID par l'Ingress et Traefik", discovery, evidence=True),
        Step("Redirection vers Keycloak (administration)",
             _port_forward(ctx, "keycloak", "svc/keycloak-service", 8180, 8080, work)),
        Step("infra/keycloak : tofu init et apply", admin + "tofu init -input=false\ntofu apply -auto-approve -input=false",
             cwd=out / "infra" / "keycloak", env=tf_env),
        Step("infra/keycloak : relu sans écart (plan -detailed-exitcode)",
             admin + "tofu plan -detailed-exitcode -input=false", cwd=out / "infra" / "keycloak", env=tf_env,
             evidence=True),
        Step("Revendication « groups » d'un membre du groupe admins", groups, evidence=True),
        Step("Diagnostic de Keycloak",
             f"kubectl --context {ctx} -n keycloak get keycloak keycloak -o jsonpath='{{.status}}'; echo\n"
             f"kubectl --context {ctx} -n keycloak get pods,pvc -o wide\n"
             f"kubectl --context {ctx} -n keycloak get pod keycloak-0 -o jsonpath='{{.status.containerStatuses[0].lastState}}'; echo\n"
             f"kubectl --context {ctx} -n keycloak logs deployment/keycloak-operator --tail=8 || true\n"
             f"echo '--- journal de keycloak-0 (instance précédente)'\n"
             f"kubectl --context {ctx} -n keycloak logs keycloak-0 --previous --tail=30 "
             f"|| kubectl --context {ctx} -n keycloak logs keycloak-0 --tail=30 || true", always=True),
        *end,
    ]


# ------------------------------------------------------------------ hôte Docker : services de plateforme
def runbook_blocks(out: Path, title: str) -> list[str]:
    """Blocs ```bash de la section « ## N. <titre> » du mode d'emploi généré, dans l'ordre."""
    text = (out / "docs" / "mise-en-route.md").read_text(encoding="utf-8")
    section = re.split(r"^## \d+\. ", text, flags=re.M)
    body = next((part for part in section if part.startswith(title)), "")
    return re.findall(r"```bash\n(.*?)```", body, flags=re.S)


def _compose_host(out: Path, ir, env: dict[str, str]) -> tuple[Path, str, list[Step], list[Step]]:
    """Fichiers posés comme sur l'hôte, secrets, démarrage ; puis journaux et arrêt (toujours)."""
    host = out.parent / "opt" / ir.app
    image = f"devops-builder.local/{ir.app}:e2e"
    dc = f"docker compose --project-directory {host} -p {ir.app}"
    curlrc = out.parent / "curl"
    start = [
        Step("Image de l'application de démonstration", ["docker", "build", "-t", image, str(APP_DIR)]),
        Step("Fichiers posés comme sur l'hôte (/opt/<application>)",
             f"mkdir -p {host} && cp -R {out}/deploy/. {host}/ && ls {host}"),
        Step("deploy/secrets.sh : fichiers de secrets", ["sh", "secrets.sh", "secrets"], cwd=host, env=env),
        # comme le déploiement par SSH : seule IMAGE est passée, les secrets ne viennent que de secrets/*.env
        Step("docker compose up (santé des services attendue)", f"{dc} up -d --wait --wait-timeout 300",
             cwd=host, env={"IMAGE": image}),
    ]
    end = [
        Step("Consommation mesurée (docker stats), à comparer à data/sizing.yaml",
             "docker stats --no-stream --format '{{.Name}} {{.MemUsage}} {{.CPUPerc}}'", always=True, evidence=True),
        Step("Journaux des services", f"{dc} ps -a; {dc} logs --tail=25", always=True, env={**env, "IMAGE": image}),
        Step("Arrêt et suppression des volumes", f"{dc} down -v --remove-orphans", always=True,
             env={**env, "IMAGE": image}),
    ]
    curlrc.mkdir(parents=True, exist_ok=True)
    return host, str(curlrc), start, end


def _curl_env(curlrc: str, *hosts: str) -> dict[str, str]:
    """Pas de DNS ni de certificat public sur la machine de test : curl est dirigé vers Traefik (127.0.0.1:443)
    et accepte son certificat par défaut. Les commandes du mode d'emploi s'exécutent sans modification."""
    lines = ["insecure", *(f'resolve = "{h}:443:127.0.0.1"' for h in hosts)]
    Path(curlrc, ".curlrc").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"CURL_HOME": curlrc}


def _zabbix_steps(out: Path, ir) -> list[Step]:
    from devops_builder.generators import zabbix
    env = {"ZABBIX_DB_PASSWORD": secrets.token_hex(12)}
    host, curlrc, start, end = _compose_host(out, ir, env)
    web = zabbix.host(ir)
    cenv = {**_curl_env(curlrc, web), "ZBX": f"https://{web}/api_jsonrpc.php"}
    blocks = runbook_blocks(out, "Zabbix")
    change, check = (blocks + ["false", "false"])[:2]
    # le mot de passe choisi par le premier bloc est réutilisé par le second : même shell
    guide = f"""
{change}
for _ in $(seq 1 30); do
  host="$({check})" || true
  echo "$host"
  printf '%s' "$host" | jq -e '.interfaces[0].available == "1"' >/dev/null && break
  sleep 10
done
printf '%s' "$host" | jq -e '.interfaces[0].available == "1"' >/dev/null
old=$(curl -fsS -H 'Content-Type: application/json-rpc' -d '{{"jsonrpc":"2.0","method":"user.login","params":{{"username":"Admin","password":"zabbix"}},"id":9}}' "$ZBX")
printf '%s' "$old" | jq -e '.error' >/dev/null && echo "ancien mot de passe refusé"
"""
    return [
        *start,
        Step("Interface Zabbix par Traefik en HTTPS",
             f"for _ in $(seq 1 30); do curl -fsS -o /dev/null -w '%{{http_code}}\\n' https://{web}/ && exit 0; "
             "sleep 5; done; exit 1", env=cenv, evidence=True),
        # le serveur crée le schéma de sa base au premier démarrage : la connexion Admin n'aboutit qu'ensuite
        Step("Serveur prêt : connexion Admin acceptée par l'API (schéma créé)",
             "for _ in $(seq 1 60); do curl -fsS -H 'Content-Type: application/json-rpc' -d "
             "'{\"jsonrpc\":\"2.0\",\"method\":\"user.login\",\"params\":{\"username\":\"Admin\","
             "\"password\":\"zabbix\"},\"id\":1}' \"$ZBX\" | jq -e .result >/dev/null && exit 0; sleep 5; done; exit 1",
             env=cenv),
        Step("Mode d'emploi joué tel quel : mot de passe Admin changé, agent disponible", guide,
             env=cenv, evidence=True),
        Step("scripts/db-backup.sh : base de Zabbix sauvegardée",
             f"sh {out}/scripts/db-backup.sh {host} {out.parent}/sauvegardes\nls -l {out.parent}/sauvegardes/zabbix-db-*.dump",
             env=env, evidence=True),
        Step("scripts/db-restore.sh --oui : base de Zabbix restaurée, serveur toujours joignable",
             f"sh {out}/scripts/db-restore.sh {host} \"$(ls {out.parent}/sauvegardes/zabbix-db-*.dump | head -n 1)\" --oui\n"
             "curl -fsS -H 'Content-Type: application/json-rpc' -d '{\"jsonrpc\":\"2.0\",\"method\":\"apiinfo.version\","
             "\"params\":{},\"id\":1}' \"$ZBX\" | jq -e .result", env={**env, **cenv}, evidence=True),
        *end,
    ]


def _keycloak_compose_steps(out: Path, ir) -> list[Step]:
    from devops_builder.generators import identity
    env = {"KEYCLOAK_DB_PASSWORD": secrets.token_hex(12), "KEYCLOAK_ADMIN_PASSWORD": secrets.token_hex(12)}
    host, curlrc, start, end = _compose_host(out, ir, env)
    auth = identity.host(ir)
    cenv = _curl_env(curlrc, auth)
    realm = identity.realm(ir)
    kc_ip = (f"$(docker inspect -f '{{{{range .NetworkSettings.Networks}}}}{{{{.IPAddress}}}}{{{{end}}}}' "
             f"$(docker compose --project-directory {host} -p {ir.app} ps -q keycloak))")
    tf = {"TF_IN_AUTOMATION": "1", "TF_CLI_ARGS": "-no-color", "KEYCLOAK_USER": "admin-temporaire",
          "KEYCLOAK_PASSWORD": env["KEYCLOAK_ADMIN_PASSWORD"]}
    url = f'export TF_VAR_keycloak_url="http://{kc_ip}:8080"\n'
    groups = f"""
kc="http://{kc_ip}:8080"
tok=$(curl -fsS -d client_id=admin-cli -d grant_type=password -d username=admin-temporaire \
  --data-urlencode "password=$KEYCLOAK_PASSWORD" $kc/realms/master/protocol/openid-connect/token | jq -r .access_token)
api() {{ curl -fsS -H "Authorization: Bearer $tok" -H 'Content-Type: application/json' "$@"; }}
api -X POST -d '{{"username":"alice","enabled":true,"email":"alice@boutique.test","firstName":"Alice","lastName":"Test"}}' \
  $kc/admin/realms/{realm}/users
uid=$(api "$kc/admin/realms/{realm}/users?username=alice&exact=true" | jq -r '.[0].id')
gid=$(api "$kc/admin/realms/{realm}/groups?search={identity.ADMINS}&exact=true" | jq -r '.[0].id')
api -X PUT $kc/admin/realms/{realm}/users/$uid/groups/$gid
cid=$(api "$kc/admin/realms/{realm}/clients?clientId={ir.app}" | jq -r '.[0].id')
claims=$(api "$kc/admin/realms/{realm}/clients/$cid/evaluate-scopes/generate-example-access-token?userId=$uid&scope=openid")
echo "$claims" | jq -c '{{iss, groups}}'
echo "$claims" | jq -e '.groups | index("{identity.ADMINS}")' >/dev/null
"""
    discovery = f"""
for _ in $(seq 1 60); do
  iss=$(curl -fsS https://{auth}/realms/master/.well-known/openid-configuration 2>/dev/null | jq -r .issuer || true)
  [ "$iss" = "https://{auth}/realms/master" ] && {{ echo "émetteur : $iss"; exit 0; }}
  sleep 5
done
exit 1
"""
    return [
        *start,
        Step("Découverte OpenID par Traefik en HTTPS", discovery, env=cenv, evidence=True),
        Step("infra/keycloak : tofu init et apply", url + "tofu init -input=false\ntofu apply -auto-approve -input=false",
             cwd=out / "infra" / "keycloak", env=tf),
        Step("infra/keycloak : relu sans écart (plan -detailed-exitcode)",
             url + "tofu plan -detailed-exitcode -input=false", cwd=out / "infra" / "keycloak", env=tf, evidence=True),
        Step("Revendication « groups » d'un membre du groupe admins", groups, env=tf, evidence=True),
        *_sonarqube_steps(out, ir, curlrc),
        *end,
    ]


def _sonarqube_steps(out: Path, ir, curlrc: str) -> list[Step]:
    """SonarQube relié à Keycloak en SAML par le mode d'emploi joué tel quel, puis une connexion suivie jusqu'à la
    page de Keycloak : le realm doit reconnaître la demande SAML du client sonarqube."""
    from devops_builder.generators import identity
    client = next((c for c in identity.clients(ir) if c.tool == "sonarqube"), None)
    if client is None:
        return []
    sonar = identity.tool_url(ir, client)
    cenv = _curl_env(curlrc, identity.host(ir), sonar.split("://", 1)[1])
    block = "\n".join(runbook_blocks(out, "SonarQube")) or "false"
    ready = (f"for _ in $(seq 1 90); do s=$(curl -fsS {sonar}/api/system/status 2>/dev/null | jq -r .status || true); "
             '[ "$s" = UP ] && { echo "SonarQube : $s"; exit 0; }; sleep 5; done; exit 1')
    login = f"""
{{
{block}
}} | tee /tmp/saml-redirect.txt
loc=$(tail -n 1 /tmp/saml-redirect.txt)
echo "redirection : ${{loc%%\\?*}}"
case "$loc" in {identity.issuer(ir)}/protocol/saml?SAMLRequest=*) ;; *) echo "redirection inattendue"; exit 1 ;; esac
code=$(curl -sS -o /tmp/kc-login.html -w '%{{http_code}}' "$loc")
echo "page de Keycloak : HTTP $code"
grep -o 'id="kc-form-login"' /tmp/kc-login.html
"""
    return [
        Step("SonarQube démarré, derrière Traefik en HTTPS", ready, env=cenv),
        Step("Mode d'emploi SonarQube joué tel quel (mot de passe, SAML, groupe admins) ; connexion jusqu'à la page "
             "de Keycloak", login, env=cenv, evidence=True),
    ]


def _dex_steps(out: Path, ir) -> list[Step]:
    """Dex en Compose derrière Traefik : découverte OpenID, puis une demande de connexion de l'application suivie
    jusqu'à la forge. Sans compte sur la forge, le parcours s'arrête à sa page d'autorisation, qui doit recevoir
    l'identifiant de l'application OAuth transmis par le pipeline."""
    from devops_builder.generators import identity
    connector_id = "e2e-" + secrets.token_hex(6)
    env = {"DEX_CONNECTOR_ID": connector_id, "DEX_CONNECTOR_SECRET": secrets.token_hex(16),
           **{identity.secret_env_name(c): secrets.token_hex(12) for c in identity.clients(ir)}}
    host, curlrc, start, end = _compose_host(out, ir, env)
    dex = identity.host(ir)
    iss = identity.issuer(ir)
    cenv = {**_curl_env(curlrc, dex), "DEX_CONNECTOR_ID": connector_id}
    redirect = f"{identity.app_url(ir)}/callback"
    auth = (f"{iss}/auth?client_id={ir.app}&redirect_uri=$(printf %s '{redirect}' | jq -sRr @uri)"
            "&response_type=code&scope=openid+profile+email+groups&state=e2e")
    discovery = f"""
for _ in $(seq 1 60); do
  got=$(curl -fsS https://{dex}/.well-known/openid-configuration 2>/dev/null | jq -r .issuer || true)
  [ "$got" = "{iss}" ] && {{ echo "émetteur : $got"; exit 0; }}
  sleep 3
done
exit 1
"""
    journey = f"""
next="{auth}"
for i in 1 2 3 4; do
  loc=$(curl -sS -o /dev/null -w '%{{redirect_url}}' "$next")
  echo "redirection $i : ${{loc%%\\?*}}"
  case "$loc" in
    https://github.com/login/oauth/authorize*|https://gitlab.com/oauth/authorize*) break ;;
    https://{dex}/*) next="$loc" ;;
    *) echo "redirection inattendue : $loc"; exit 1 ;;
  esac
done
printf '%s\n' "$loc" | tr '?&' '\n\n' | grep -E '^(client_id|redirect_uri|scope)='
printf '%s' "$loc" | grep -q "client_id=$DEX_CONNECTOR_ID" || {{ echo "identifiant de l'application OAuth absent"; exit 1; }}
printf '%s' "$loc" | grep -q "redirect_uri=$(printf %s '{iss}/callback' | jq -sRr @uri)"
"""
    refused = f"""
next="{iss}/auth?client_id={ir.app}&redirect_uri=https%3A%2F%2Fpirate.test%2Fcallback&response_type=code&scope=openid"
for i in 1 2 3 4; do
  out=$(curl -sS -o /tmp/dex-refus.html -w '%{{http_code}} %{{redirect_url}}' "$next")
  code=${{out%% *}}; loc=${{out#* }}
  echo "étape $i : HTTP $code ${{loc%%\\?*}}"
  case "$loc" in https://{dex}/*) next="$loc" ;; *) break ;; esac
done
grep -o -i 'unregistered redirect_uri[^<]*' /tmp/dex-refus.html | head -n 1 || true
test "$code" -ge 400
"""
    return [
        *start,
        Step("Découverte OpenID par Traefik en HTTPS", discovery, env=cenv, evidence=True),
        Step("Connexion de l'application : Dex renvoie vers la forge avec l'application OAuth du pipeline", journey,
             env=cenv, evidence=True),
        Step("Adresse de retour non déclarée refusée", refused, env=cenv, evidence=True),
        *end,
    ]


GITEA_IMAGE = "gitea/gitea:1.27.3"


def _argocd_steps(out: Path, ir) -> list[Step]:
    """GitOps de bout en bout : dépôt privé sur Gitea (réseau de kind), Argo CD installé par platform/install.sh et
    branché par le mode d'emploi, puis le job de déploiement de la CI générée joué tel quel dans alpine, comme sur un
    runner GitLab : la nouvelle étiquette poussée dans le dépôt arrive dans le cluster."""
    import yaml as _yaml
    work = out.parent
    cluster, ctx, start, end = _kind_common(ir, work)
    ns = ir.namespace(ir.envs[0])
    ci = _yaml.safe_load((out / ".gitlab-ci.yml").read_text(encoding="utf-8"))
    job = next(j for j in ci.values() if isinstance(j, dict) and any("GITOPS_REPO" in str(line)
                                                                      for line in j.get("script", [])))
    (work / "ci-deploy.sh").write_text("\n".join(job["script"]) + "\n", encoding="utf-8")
    repo = ci["variables"]["GITOPS_REPO"]
    image = "registry.e2e.test/boutique"
    token = work / "gitea-token"
    password = secrets.token_hex(12)

    def ci_job(tag: str) -> str:
        return (f"docker run --rm --network kind -e TAG={tag} -e IMAGE={image}:{tag} -e GITOPS_REPO={repo} "
                f"-e GITOPS_TOKEN=\"$(cat {token})\" -v {work}/ci-deploy.sh:/job.sh:ro alpine:3.20 sh -e /job.sh")

    def deployed(tag: str) -> str:
        return f"""
kubectl --context {ctx} -n argocd annotate application {ns} argocd.argoproj.io/refresh=normal --overwrite >/dev/null
for _ in $(seq 1 60); do
  img=$(kubectl --context {ctx} -n {ns} get deployment {ir.app} -o jsonpath='{{.spec.template.spec.containers[0].image}}' \
        2>/dev/null || true)
  [ "$img" = "{image}:{tag}" ] && break
  sleep 5
done
echo "image déployée : $img"
test "$img" = "{image}:{tag}"
kubectl --context {ctx} -n {ns} rollout status deployment/{ir.app} --timeout=180s
kubectl --context {ctx} -n argocd get application {ns} -o jsonpath='{{.status.sync.status}} {{.status.health.status}}{{"\\n"}}'
"""
    gitea = f"""
docker run -d --name gitea-e2e --network kind --network-alias gitea -p 3000:3000 \
  -e GITEA__security__INSTALL_LOCK=true -e GITEA__server__ROOT_URL=http://gitea:3000/ {GITEA_IMAGE}
for _ in $(seq 1 60); do curl -fsS http://127.0.0.1:3000/api/healthz >/dev/null 2>&1 && break; sleep 2; done
docker exec -u git gitea-e2e gitea admin user create --username e2e --password "$GITEA_PASSWORD" \
  --email e2e@boutique.test --admin --must-change-password=false
docker exec -u git gitea-e2e gitea admin user generate-access-token --username e2e --token-name ci \
  --scopes write:repository,read:user --raw > {token}
curl -fsS -u "e2e:$GITEA_PASSWORD" -H 'Content-Type: application/json' \
  -d '{{"name":"gitops","private":true,"default_branch":"main"}}' http://127.0.0.1:3000/api/v1/user/repos >/dev/null
echo "dépôt privé e2e/gitops créé"
"""
    push = (f"git init -q -b main && git add -A && git -c user.email=e2e@boutique.test -c user.name=e2e commit -qm "
            f"'Fichiers générés' && git push -q \"http://e2e:$(cat {token})@127.0.0.1:3000/e2e/gitops.git\" main")
    guide = "\n".join(runbook_blocks(out, "Argo CD")) or "false"
    log = (f"curl -fsS -H \"Authorization: token $(cat {token})\" "
           "'http://127.0.0.1:3000/api/v1/repos/e2e/gitops/commits?limit=5' | jq -r '.[].commit.message'")
    return [
        Step("Image de l'application de démonstration, deux étiquettes",
             f"docker build -t {image}:e2e-1 {APP_DIR} && docker tag {image}:e2e-1 {image}:e2e-2"),
        *start,
        Step("Images chargées dans le cluster (registre simulé)",
             ["kind", "load", "docker-image", f"{image}:e2e-1", f"{image}:e2e-2", "--name", cluster]),
        Step("Forge Gitea sur le réseau de kind, dépôt GitOps privé", gitea, env={"GITEA_PASSWORD": password}),
        Step("Fichiers générés poussés dans le dépôt GitOps", push, cwd=out),
        Step("Job de déploiement de la CI générée (alpine, comme GitLab) : étiquette e2e-1", ci_job("e2e-1"),
             evidence=True),
        Step("Mode d'emploi Argo CD joué tel quel (secret du dépôt, applications, synchronisation)",
             f"kubectl config use-context {ctx}\nexport GITOPS_READ_TOKEN=\"$(cat {token})\"\n{guide}", cwd=out,
             evidence=True),
        Step("Application synchronisée par Argo CD : image e2e-1 en place", deployed("e2e-1"), evidence=True),
        Step("Nouveau pipeline : job de déploiement, étiquette e2e-2", ci_job("e2e-2"), evidence=True),
        Step("Argo CD applique le nouveau commit (lecture du dépôt demandée)", deployed("e2e-2"), evidence=True),
        Step("Pipeline relancé sur la même image : rien à pousser, pas d'échec", ci_job("e2e-2"), evidence=True),
        Step("Historique du dépôt GitOps", log, evidence=True),
        *end[:-1],
        Step("Arrêt de Gitea", "docker rm -f gitea-e2e", always=True),
        end[-1],
    ]


def _renovate_steps(out: Path, ir) -> list[Step]:
    """Renovate tel que le workflow Gitea généré le lance (image, variables), contre une vraie forge Gitea : il lit
    renovate.json et ouvre son tableau de bord et ses demandes de fusion sur les images du dépôt."""
    import yaml as _yaml
    work = out.parent
    wf = _yaml.safe_load((out / ".gitea" / "workflows" / "renovate.yml").read_text(encoding="utf-8"))
    job = wf["jobs"]["renovate"]
    token = work / "gitea-token"
    repo = "e2e/boutique"
    subst = {"${{ github.server_url }}": "http://gitea:3000", "${{ github.repository }}": repo}
    envs = []
    for k, v in job["env"].items():
        if "secrets.RENOVATE_TOKEN" in v:
            envs.append(f'-e {k}="$(cat {token})"')
        else:
            for a, b in subst.items():
                v = v.replace(a, b)
            envs.append(f"-e {k}={v}")
    run = (f"docker run --rm --network e2e-forge {' '.join(envs)} -e LOG_LEVEL=info {job['container']} "
           f"{job['steps'][0]['run']} 2>&1 | tail -n 40")
    gitea = f"""
docker network create e2e-forge >/dev/null
docker run -d --name gitea-e2e --network e2e-forge --network-alias gitea -p 3000:3000 \\
  -e GITEA__security__INSTALL_LOCK=true -e GITEA__server__ROOT_URL=http://gitea:3000/ {GITEA_IMAGE}
for _ in $(seq 1 60); do curl -fsS http://127.0.0.1:3000/api/healthz >/dev/null 2>&1 && break; sleep 2; done
docker exec -u git gitea-e2e gitea admin user create --username e2e --password "$GITEA_PASSWORD" \\
  --email e2e@boutique.test --admin --must-change-password=false
docker exec -u git gitea-e2e gitea admin user generate-access-token --username e2e --token-name renovate \\
  --scopes all --raw > {token}
curl -fsS -u "e2e:$GITEA_PASSWORD" -H 'Content-Type: application/json' \\
  -d '{{"name":"boutique","private":true,"default_branch":"main"}}' http://127.0.0.1:3000/api/v1/user/repos >/dev/null
"""
    push = (f"git init -q -b main && git add -A && git -c user.email=e2e@boutique.test -c user.name=e2e commit -qm "
            f"'Fichiers générés' && git push -q \"http://e2e:$(cat {token})@127.0.0.1:3000/{repo}.git\" main")
    api = f"curl -fsS -H \"Authorization: token $(cat {token})\" http://127.0.0.1:3000/api/v1/repos/{repo}"
    check = f"""
{api}/issues?type=issues\\&state=open | jq -r '.[].title' | tee /tmp/issues.txt
grep -q 'Dependency Dashboard' /tmp/issues.txt
echo "--- demandes de fusion ouvertes par Renovate :"
{api}/pulls?state=open | jq -r '.[] | "\\(.head.ref) : \\(.title)"'
"""
    return [
        Step("Forge Gitea, dépôt privé", gitea, env={"GITEA_PASSWORD": secrets.token_hex(12)}),
        Step("Fichiers générés poussés dans le dépôt", push, cwd=out),
        Step("Renovate lancé comme le workflow .gitea/workflows/renovate.yml", run, evidence=True),
        Step("Tableau de bord et demandes de fusion de Renovate sur la forge", check, evidence=True),
        Step("Arrêt de Gitea", "docker rm -f gitea-e2e; docker network rm e2e-forge", always=True),
    ]


PLATFORM_TOOLS = ("k3s", "helm", "traefik", "cert-manager", "dex", "harbor", "sonarqube", "prometheus", "grafana",
                  "loki", "tempo", "argo-cd", "argo-rollouts", "kyverno", "falco", "keda", "opencost", "jaeger",
                  "fluent-bit", "otel-collector", "cloudnative-pg", "kubescape", "gitea", "jenkins", "crossplane",
                  "zot", "longhorn", "litmus", "chaos-mesh", "opensearch")

HELM_TEMPLATE = r"""#!/usr/bin/env bash
# « helm upgrade --install » rendu par « helm template » : chaque chart, avec les options du script généré, passe
# ses propres contrôles (valeurs obligatoires, schéma) sans être installé ; les autres commandes passent telles quelles.
set -euo pipefail
if [ "${1:-}" = upgrade ] && [ "${2:-}" = --install ]; then
  shift 2
  args=()
  for a in "$@"; do case "$a" in --wait|--create-namespace|--atomic) ;; *) args+=("$a") ;; esac; done
  "$HELM_REAL" template "${args[@]}" > "$RENDER_DIR/${args[0]}.yaml" 2> >(sed "s/^/[${args[0]}] /" >&2)
  echo "rendu : ${args[0]} ($(grep -c '^kind:' "$RENDER_DIR/${args[0]}.yaml") ressources)"
  exit 0
fi
exec "$HELM_REAL" "$@"
"""


def _platform_steps(out: Path, ir) -> list[Step]:
    """platform/install.sh d'un projet qui pose presque tous les charts de plateforme : chaque « helm upgrade »
    rendu par « helm template » avec ses options (valeurs exigées par le chart, OIDC de Harbor), dans un vrai
    cluster pour les commandes kubectl du script ; manifestes rendus passés à kubeconform."""
    work = out.parent
    cluster, ctx, start, end = _kind_common(ir, work)
    wrapper = work / "bin" / "helm"
    render = work / "rendu"
    prep = Step("Enveloppe helm → helm template", f"mkdir -p {wrapper.parent} {render}\n"
                f"cat > {wrapper} <<'SH'\n{HELM_TEMPLATE}SH\nchmod +x {wrapper}\ncommand -v helm")
    run = Step("platform/install.sh, charts rendus avec les options générées",
               f"export HELM_REAL=\"$(command -v helm)\" RENDER_DIR={render} PATH={wrapper.parent}:$PATH\n"
               f"export HARBOR_OIDC_SECRET=e2e-secret\nkubectl config use-context {ctx}\nbash platform/install.sh",
               cwd=out, evidence=True)
    check = Step("Réglages OIDC de Harbor et charts exigeants (SonarQube) dans le rendu",
                 f"grep -l CONFIG_OVERWRITE_JSON {render}/harbor.yaml\n"
                 f"grep -o 'https://harbor.boutique.test' {render}/harbor.yaml | head -n 1\n"
                 f"grep -c 'kind: StatefulSet' {render}/sonarqube.yaml\nls {render} | wc -l",
                 evidence=True)
    # « subschemas 0, 1 matched » : targetPort entier ou chaîne accepté deux fois par le schéma (défaut du schéma)
    conform = Step("kubeconform sur les manifestes rendus (schémas Kubernetes ; CRD ignorées)",
                   f"kubeconform -ignore-missing-schemas -skip CustomResourceDefinition -summary {render}/*.yaml "
                   "> /tmp/kubeconform.txt || true\ncat /tmp/kubeconform.txt\n"
                   "! grep ' is invalid' /tmp/kubeconform.txt | grep -v 'subschemas 0, 1 matched'",
                   evidence=True)
    return [start[0], prep, run, check, conform, *end]


def _sops_steps(out: Path, ir) -> list[Step]:
    """SOPS comme le mode d'emploi : clé age, clé publique dans la brique et projet régénéré, valeurs chiffrées par
    secrets-seed.sh ; puis les lignes mêmes de la CI générée (sops vérifié, déchiffrement, deploy/secrets.sh)."""
    work = out.parent
    host = work / "opt" / ir.app
    image = f"devops-builder.local/{ir.app}:e2e"
    dc = f"docker compose --project-directory {host} -p {ir.app}"
    env_id = ir.envs[0].id
    key = work / "age" / "keys.txt"
    ci_file = next((f for f in (".gitlab-ci.yml",) if (out / f).exists()), None)
    ci_glob = ci_file or ".github/workflows/*.yml"
    # lignes de la CI qui installent sops et chargent les secrets, extraites du fichier généré
    extract = (f"grep -h -E 'local/bin|sops|secrets-fetch.sh|SECRETS_ENV|deploy/secrets.sh' {ci_glob} "
               "| grep -v -E 'ansible|ssh |scp ' | sed -E 's/^ *(- )?//' | awk '!seen[$0]++' > ci-secrets.sh\n"
               "cat ci-secrets.sh")
    probe = (f"{dc} exec -T {ir.app} python -c \"import sys,urllib.request as u;"
             "r=u.urlopen('http://127.0.0.1:8000/db',timeout=10);print(r.read().decode());"
             "sys.exit(0 if r.status==200 else 1)\"")
    return [
        Step("Image de l'application de démonstration", ["docker", "build", "-t", image, str(APP_DIR)]),
        Step("Clé age du projet (mode d'emploi)", f"mkdir -p {key.parent}\nage-keygen -o {key}\nage-keygen -y {key}"),
        Step("Clé publique dans la brique SOPS, projet régénéré par la ligne de commande",
             f"pub=$(age-keygen -y {key})\n"
             f"python3 - \"$pub\" <<'PY'\nimport sys, yaml\np = yaml.safe_load(open('devops-builder.yaml'))\n"
             "for bricks in p['stages'].values():\n    for b in bricks:\n        if b['tool'] == 'sops':\n"
             "            b.setdefault('params', {})['age_recipients'] = sys.argv[1]\n"
             "yaml.safe_dump(p, open('devops-builder.yaml', 'w'), sort_keys=False, allow_unicode=True)\nPY\n"
             f"{sys.executable} -m devops_builder generate devops-builder.yaml -o . --overwrite\n"
             "grep \"$pub\" .sops.yaml", cwd=out, env={"PYTHONPATH": str(ROOT)}),
        Step("scripts/secrets-seed.sh : valeurs chiffrées dans le dépôt",
             f"export SOPS_AGE_KEY_FILE={key}\n"
             f"POSTGRESQL_PASSWORD=$(openssl rand -hex 12) VALKEY_PASSWORD=$(openssl rand -hex 12) "
             f"bash scripts/secrets-seed.sh {env_id}\n"
             f"grep -q 'ENC\\[AES256_GCM' deploy/secrets/{env_id}.enc.env && echo 'fichier chiffré' && "
             f"! grep -q -E '^(POSTGRESQL|VALKEY)_PASSWORD=[0-9a-f]+$' deploy/secrets/{env_id}.enc.env", cwd=out,
             evidence=True),
        Step("Lignes de la CI générée : sops vérifié, secrets déchiffrés, deploy/secrets.sh",
             f"{extract}\nexport SOPS_AGE_KEY=\"$(grep AGE-SECRET-KEY {key})\"\nbash -euo pipefail ci-secrets.sh\n"
             "ls .secrets", cwd=out, evidence=True),
        Step("Fichiers posés comme sur l'hôte, secrets compris",
             f"mkdir -p {host}/secrets && cp -R {out}/deploy/. {host}/ && cp {out}/.secrets/* {host}/secrets/"),
        Step("docker compose up (santé des services attendue)", f"{dc} up -d --wait --wait-timeout 300",
             cwd=host, env={"IMAGE": image}),
        Step("Connexion authentifiée aux bases depuis l'application (/db)", probe, retries=10, evidence=True),
        Step("Journaux des services", f"{dc} ps -a; {dc} logs --tail=25", always=True, env={"IMAGE": image}),
        Step("Arrêt et suppression des volumes", f"{dc} down -v --remove-orphans", always=True, env={"IMAGE": image}),
    ]


def _zap_steps(out: Path, ir) -> list[Step]:
    """Le job ZAP de la CI générée, extrait du workflow et lancé comme ses deux familles de runners : GitHub
    Actions (conteneur en root, option du job) et GitLab CI (utilisateur de l'image, dépôt inscriptible par tous)."""
    import yaml as _yaml

    from devops_builder.generators import dast
    host, curlrc, start, end = _compose_host(out, ir, {})
    start = [s for s in start if "secrets.sh" not in s.name]   # application sans base : aucun secret
    url = dast.target_url(ir)
    web = url.split("://", 1)[1].split("/", 1)[0]
    wf = _yaml.safe_load((out / ".github" / "workflows" / "pipeline.yml").read_text(encoding="utf-8"))
    job = next(j for j in wf["jobs"].values() if "zap" in str(j.get("container", "")))
    image = job["container"]["image"]
    user = job["container"]["options"].split()[-1]
    run = next(s["run"] for s in job["steps"] if "run" in s)
    (out.parent / "zap-job.sh").write_text(run, encoding="utf-8")
    fail_ids = ",".join(rid for rid, _ in dast.FAIL_RULES)
    check = f"""
python3 - "$code" <<'PY'
import json, sys
code = int(sys.argv[1])
report = json.load(open("zap-report.json"))
alerts = {{(a["pluginid"], a["name"]) for s in report["site"] for a in s["alerts"]}}
for pid, name in sorted(alerts):
    print(f"{{pid}} {{name}}")
fail = {{pid for pid, _ in alerts}} & set("{fail_ids}".split(","))
expected = 1 if fail else 0
print(f"code {{code}}, règles FAIL déclenchées : {{sorted(fail) or 'aucune'}}")
sys.exit(0 if code == expected else 1)
PY
"""

    def zap_run(label: str, slug: str, run_as: str, writable: bool) -> Step:
        d = out.parent / f"zap-{slug}"
        prep = f"chmod -R a+rwX {d}" if writable else ":"
        return Step(f"Job ZAP de la CI générée, {label} (utilisateur {run_as})",
                    f"rm -rf {d} && mkdir -p {d} && cp -R {out}/.zap {d}/ && cp {out.parent}/zap-job.sh {d}/\n{prep}\n"
                    f"code=0\ndocker run --rm --network host --add-host {web}:127.0.0.1 --user {run_as} "
                    f"-v {d}:/depot -w /depot -e ZAP_TARGET_URL={url} {image} bash zap-job.sh || code=$?\n"
                    f"echo \"code de sortie du job : $code\"\ncd {d} && ls -l zap-report.html zap-report.json\n{check}",
                    evidence=True)
    return [
        *start,
        Step("Application par Traefik en HTTPS", f"for _ in $(seq 1 30); do curl -fsS {url}/ && exit 0; sleep 3; done; "
             "exit 1", env=_curl_env(curlrc, web)),
        Step("Image ZAP de la CI générée", ["docker", "pull", image]),
        zap_run("GitHub Actions", "github", user, False),
        # GitLab CI : utilisateur de l'image (zap), dépôt extrait avec un umask 0000
        zap_run("GitLab CI", "gitlab", "zap", True),
        *end,
    ]


def _check_db(ctx: str, ns: str, app: str) -> str:
    return f"""
kubectl --context {ctx} -n {ns} port-forward service/{app} 18081:80 >/tmp/pf-db.log 2>&1 &
pf=$!
trap 'kill $pf 2>/dev/null || true' EXIT
for _ in $(seq 1 30); do
  code=$(curl -s -o /tmp/db.json -w '%{{http_code}}' http://127.0.0.1:18081/db || true)
  [ "$code" = 200 ] && {{ cat /tmp/db.json; exit 0; }}
  sleep 2
done
echo "réponse $code :"; cat /tmp/db.json 2>/dev/null || true
kubectl --context {ctx} -n {ns} logs deployment/{app} --tail=40 || true
exit 1
"""


SCENARIOS = {s.name: s for s in [
    Scenario("kind-helm-cnpg", "k3s + chart Helm + PostgreSQL par CloudNativePG, dans kind",
             lambda: _project("kubernetes", *GH, "k3s", "helm", "cloudnative-pg"),
             _kind_steps, ("docker", "kind", "kubectl", "helm", "curl")),
    Scenario("kind-kustomize-postgresql", "k3s + overlays Kustomize + PostgreSQL et Valkey en StatefulSet",
             lambda: _project("kubernetes", "gitlab", "gitlab-ci", "buildkit", "k3s", "kustomize", "postgresql",
                              "valkey"),
             _kind_steps, ("docker", "kind", "kubectl", "curl")),
    Scenario("compose-postgresql", "Hôte Docker : Compose, PostgreSQL, Valkey, sauvegarde puis restauration",
             lambda: _project("docker-host", "gitlab", "gitlab-ci", "buildkit", "docker-compose", "traefik",
                              "postgresql", "valkey"),
             _compose_steps, ("docker",)),
    Scenario("compose-zabbix", "Hôte Docker : Zabbix derrière Traefik en HTTPS, mode d'emploi joué tel quel "
             "(mot de passe Admin, agent disponible)",
             lambda: _with(_project("docker-host", "gitlab", "gitlab-ci", "buildkit", "docker-compose", "traefik",
                                    "zabbix"), zabbix={"hostname": "zabbix.boutique.test"}),
             _zabbix_steps, ("docker", "curl", "jq")),
    Scenario("compose-sops", "Hôte Docker : secrets chiffrés par SOPS et age comme le mode d'emploi, déchiffrés par "
             "les lignes de la CI générée, bases jointes par l'application",
             _starter(hosting="docker-host", forge="github", database="postgresql", cache=True, secrets="sops"),
             _sops_steps, ("docker", "age-keygen", "openssl", "curl")),
    Scenario("compose-zap", "Hôte Docker : application derrière Traefik analysée par le job ZAP de la CI générée, "
             "rapport et règles FAIL de .zap/rules.tsv vérifiés",
             lambda: _project("docker-host", *GH, "docker-compose", "traefik", "zap"),
             _zap_steps, ("docker", "curl", "python3")),
    Scenario("compose-dex", "Hôte Docker : Dex derrière Traefik en HTTPS, connexion de l'application suivie jusqu'à "
             "la page d'autorisation de la forge",
             lambda: _with(_project("docker-host", *GH, "docker-compose", "traefik", "dex"),
                           dex={"hostname": "dex.boutique.test", "tools_domain": "boutique.test",
                                "app_url": "https://boutique.test"}),
             _dex_steps, ("docker", "curl", "jq")),
    Scenario("gitea-renovate", "Renovate lancé comme le workflow Gitea généré, contre une vraie forge Gitea : "
             "tableau de bord et demandes de fusion sur les images du dépôt",
             _starter(hosting="docker-host", forge="gitea", ci="gitea-actions", database="postgresql"),
             _renovate_steps, ("docker", "curl", "jq", "git")),
    Scenario("compose-identite-keycloak", "Hôte Docker : Keycloak et sa base derrière Traefik en HTTPS, realm "
             "appliqué par OpenTofu, revendication groups",
             lambda: _with(_project("docker-host", "gitlab", "gitlab-ci", "buildkit", "docker-compose", "traefik",
                                    "keycloak", "sonarqube"), keycloak={"hostname": "auth.boutique.test",
                                                           "tools_domain": "boutique.test",
                                                           "app_url": "https://boutique.test"}),
             _keycloak_compose_steps, ("docker", "curl", "jq", "tofu")),
    Scenario("kind-argocd", "GitOps : dépôt privé sur Gitea, Argo CD branché par le mode d'emploi, le job de "
             "déploiement de la CI générée pousse l'étiquette et Argo CD l'applique",
             _starter(gitops=True, forge="gitlab",
                      params={"argo-cd": {"repo_url": "http://gitea:3000/e2e/gitops.git"}}),
             _argocd_steps, ("docker", "kind", "kubectl", "helm", "curl", "jq", "git")),
    Scenario("kind-plateforme", "platform/install.sh d'un projet à trente charts : chacun rendu avec les options "
             "générées (helm template), kubectl contre un vrai cluster, kubeconform",
             lambda: _project("kubernetes", *GH, *PLATFORM_TOOLS,
                              dex={"hostname": "dex.boutique.test", "tools_domain": "boutique.test",
                                   "app_url": "https://boutique.test"}),
             _platform_steps, ("docker", "kind", "kubectl", "helm", "kubeconform")),
    Scenario("kind-coffre-openbao", "OpenBao initialisé et configuré par les scripts générés, External Secrets, "
             "Valkey lu dans le coffre, PostgreSQL par CloudNativePG",
             _starter(secrets="openbao", database="postgresql", cache=True),
             _vault_steps, ("docker", "kind", "kubectl", "helm", "curl", "jq", "openssl")),
    Scenario("kind-identite-keycloak", "Keycloak par son opérateur derrière Traefik, realm appliqué par OpenTofu, "
             "revendication groups",
             _starter(identity="keycloak", params={"keycloak": {"hostname": "auth.boutique.test",
                                                                 "tools_domain": "boutique.test",
                                                                 "app_url": "https://boutique.test"}}),
             _identity_steps, ("docker", "kind", "kubectl", "helm", "curl", "jq", "tofu")),
]}


# ------------------------------------------------------------------ exécution
def prepare(scenario: Scenario, work: Path):
    """Projet construit, contrôlé (aucune erreur bloquante) et généré dans work/projet."""
    catalog = _catalog()
    project = scenario.project()
    blocking = RuleEngine.blocking(RuleEngine(catalog).evaluate(project))
    if blocking:
        raise SystemExit(f"{scenario.name} : projet bloqué par les règles : {[d.message for d in blocking]}")
    result = generate(project, catalog)
    out = work / "projet"
    result.write(out)
    project.save(out / "devops-builder.yaml")
    return out, result.ir


def run_step(step: Step, timeout: int = 900) -> Result:
    env = {**os.environ, **step.env}
    cmd = step.command if isinstance(step.command, list) else ["bash", "-euo", "pipefail", "-c", step.command]
    start, output, ok = time.monotonic(), "", False
    for attempt in range(step.retries):
        try:
            p = subprocess.run(cmd, cwd=step.cwd, env=env, capture_output=True, text=True, timeout=timeout)
            output, ok = (p.stdout + p.stderr), p.returncode == 0
        except subprocess.TimeoutExpired as exc:
            output, ok = f"délai dépassé ({timeout} s)\n{exc.stdout or ''}{exc.stderr or ''}", False
        if ok:
            break
        if attempt + 1 < step.retries:
            time.sleep(6)
    return Result(step, ok, time.monotonic() - start, output)


def _escape(text: str, prop: bool = False) -> str:
    text = text.replace("%", "%25").replace("\r", "").replace("\n", "%0A")
    return text.replace(":", "%3A").replace(",", "%2C") if prop else text


def annotations(scenario: Scenario, results: list[Result]) -> list[str]:
    """Commandes d'annotation GitHub : la preuve de chaque étape marquée et, après un échec, la sortie des
    étapes de diagnostic ; lisibles sur la page du passage et par l'API."""
    failed = any(not r.ok for r in results)
    out = []
    for r in results:
        if r.step.evidence or not r.ok or (failed and r.step.always):
            lines = r.output.strip().splitlines()
            text = "\n".join(lines[-40:] if (failed and r.step.always) else lines[-6:])[:3500] or "(sans sortie)"
            level = "notice" if r.ok else "error"
            out.append(f"::{level} title={_escape(f'{scenario.name} — {r.step.name}', prop=True)}::{_escape(text)}")
    return out


def report(scenario: Scenario, results: list[Result], missing: list[str]) -> str:
    ok = not missing and all(r.ok for r in results)
    lines = [f"## {'✅' if ok else '❌'} {scenario.name}", "", scenario.description, ""]
    if missing:
        lines += [f"Outils absents : {', '.join(missing)}", ""]
    lines += ["| Étape | Résultat | Durée |", "| --- | --- | --- |"]
    lines += [f"| {r.step.name} | {'ok' if r.ok else '**échec**'} | {r.seconds:.0f} s |" for r in results]
    for r in results:
        if not r.ok:
            tail = "\n".join(r.output.strip().splitlines()[-60:])
            lines += ["", f"### Échec : {r.step.name}", "", "```", tail, "```"]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Tests de bout en bout des fichiers générés.")
    parser.add_argument("scenario", nargs="?")
    parser.add_argument("--list", action="store_true", help="Lister les scénarios")
    parser.add_argument("--plan", action="store_true", help="Générer et afficher les étapes sans les exécuter")
    parser.add_argument("--keep", help="Dossier de travail à conserver (défaut : dossier temporaire supprimé)")
    args = parser.parse_args(argv)
    if args.list or not args.scenario:
        for s in SCENARIOS.values():
            print(f"{s.name:28} {s.description}")
        return 0 if args.list else 2
    scenario = SCENARIOS.get(args.scenario)
    if scenario is None:
        print(f"Scénario inconnu : {args.scenario}", file=sys.stderr)
        return 2
    work = Path(args.keep) if args.keep else Path(tempfile.mkdtemp(prefix=f"e2e-{scenario.name}-"))
    work.mkdir(parents=True, exist_ok=True)
    try:
        out, ir = prepare(scenario, work)
        steps = scenario.steps(out, ir)
        if args.plan:
            for i, s in enumerate(steps, 1):
                cmd = s.command if isinstance(s.command, str) else " ".join(s.command)
                print(f"{i:2}. {s.name}{' (toujours)' if s.always else ''}\n    {cmd.strip()[:300]}")
            return 0
        missing = [t for t in scenario.tools if shutil.which(t) is None]
        results: list[Result] = []
        failed = bool(missing)
        for step in steps:
            if failed and not step.always:
                continue
            print(f"==> {step.name}", flush=True)
            r = run_step(step)
            results.append(r)
            if not r.ok and not step.always:
                failed = True
        text = report(scenario, results, missing)
        print(text)
        if os.environ.get("GITHUB_ACTIONS") == "true":
            print("\n".join(annotations(scenario, results)))
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a", encoding="utf-8") as fh:
                fh.write(text)
        return 1 if failed else 0
    finally:
        if not args.keep:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
