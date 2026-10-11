"""Générateurs de définitions CI à partir de l'IR."""

from __future__ import annotations

import shlex

from ..ir import CI_STAGES, IR, TERRAFORM_IMAGE, TERRAFORM_INSTALL, TOFU_INSTALL, TOFU_VERSION, Step
from .common import AUDIENCES, HEADER, TOKEN_VARS, dump_yaml, full_script

STAGE_ORDER = ["test", "build", "security", "publish", "infra", "deploy"]
assert set(STAGE_ORDER) == set(CI_STAGES)


def _ordered(ir: IR) -> list[Step]:
    return sorted(ir.steps, key=lambda s: STAGE_ORDER.index(s.stage))


def _image_value(ir: IR, tag_expr: str) -> str:
    return f"{ir.image_ref}:{tag_expr}"


def _env_label(ir: IR, st: Step) -> str:
    env = ir.project.env(st.environment) if st.environment else None
    return env.display if env else (st.environment or "")


def _gated(ir: IR) -> list[Step]:
    """Déploiements soumis à approbation."""
    return [st for st in ir.steps if st.environment and st.manual]


def _note_gates(ir: IR, how: str) -> None:
    gated = _gated(ir)
    if gated:
        names = ", ".join(f"« {_env_label(ir, st)} »" for st in gated)
        ir.notes.append(f"Approbation ({names}) : {how}")


def _split_gated(ir: IR) -> tuple[list[Step], list[Step]]:
    """CI sans porte d'approbation native : les déploiements approuvés vont dans un fichier à part."""
    gated = _gated(ir)
    return [st for st in _ordered(ir) if st not in gated], gated


# ------------------------------------------------------------------ GitLab CI
def gitlab_ci(ir: IR) -> dict[str, str]:
    steps = _ordered(ir)

    def stage_of(st: Step) -> str:
        return f"deploy-{st.environment}" if st.environment and ir.multi_env else st.stage

    used: list[str] = []
    for st in steps:
        if stage_of(st) not in used:
            used.append(stage_of(st))
    doc: dict = {
        "stages": used,
        "variables": {"TAG": "$CI_COMMIT_SHORT_SHA", "IMAGE": _image_value(ir, "$CI_COMMIT_SHORT_SHA"),
                      **{v.name: v.value for v in ir.variables if v.value and not v.secret}},
    }
    oidc = ir.project.cloud_auth == "oidc"
    for st in steps:
        job: dict = {"stage": stage_of(st), "image": {"name": st.image, "entrypoint": [""]}}
        if st.environment:
            job["environment"] = {"name": st.environment}
        if st.docker:
            job["services"] = ["docker:27-dind"]
            job["variables"] = {"DOCKER_TLS_CERTDIR": "/certs"}
        if st.services:
            job.setdefault("services", []).extend(
                {"name": sv.image, "alias": sv.alias, **({"variables": dict(sv.env)} if sv.env else {})}
                for sv in st.services)
        if st.lock:
            job["resource_group"] = st.lock
        if st.env:
            job.setdefault("variables", {}).update(st.env)
        if st.cloud and oidc:
            job["id_tokens"] = {TOKEN_VARS[c]: {"aud": AUDIENCES[c]} for c in st.cloud}
        job["script"] = full_script(ir, st, TOKEN_VARS if oidc else None)
        rules = []
        if st.main_only:
            rule: dict = {"if": "$CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH"}
            if st.manual:
                rule["when"] = "manual"
            rules.append(rule)
        if rules:
            job["rules"] = rules
        if st.allow_failure:
            job["allow_failure"] = True
        if st.needs:
            job["needs"] = st.needs
        if st.artifacts:
            job["artifacts"] = {"paths": st.artifacts, "expire_in": "1 week"}
        doc[st.id] = job
    _note_gates(ir, "le job attend un déclenchement manuel dans GitLab ; protéger l'environnement "
                    "(Settings › CI/CD › Protected environments) pour restreindre qui peut le lancer.")
    return {".gitlab-ci.yml": dump_yaml(doc)}


# ------------------------------------------------------- GitHub / Gitea Actions
HOST_SETUP = {
    "cosign": [{"uses": "sigstore/cosign-installer@v3"}],
    "opentofu": [{"uses": "opentofu/setup-opentofu@v1", "with": {"tofu_version": TOFU_VERSION}}],
    "terraform": [{"uses": "hashicorp/setup-terraform@v3",
                   "with": {"terraform_version": TERRAFORM_IMAGE.split(":")[1] + ".x", "terraform_wrapper": False}}],
    "helm": [{"uses": "azure/setup-helm@v4"}],
}


def _gha_cloud_steps(ir: IR, clouds: list[str]) -> list[dict]:
    out: list[dict] = []
    static = ir.project.cloud_auth == "static"
    for c in clouds:
        if c == "aws":
            w = {"aws-region": _gha_ref(ir, "AWS_REGION")}
            if static:
                w |= {"aws-access-key-id": "${{ secrets.AWS_ACCESS_KEY_ID }}",
                      "aws-secret-access-key": "${{ secrets.AWS_SECRET_ACCESS_KEY }}"}
            else:
                w["role-to-assume"] = _gha_ref(ir, "AWS_ROLE_ARN")
            out.append({"uses": "aws-actions/configure-aws-credentials@v4", "with": w})
        elif c == "gcp":
            w = ({"credentials_json": "${{ secrets.GCP_SA_KEY }}"} if static else
                 {"workload_identity_provider": _gha_ref(ir, "GCP_WORKLOAD_IDENTITY_PROVIDER"),
                  "service_account": _gha_ref(ir, "GCP_SERVICE_ACCOUNT")})
            out.append({"uses": "google-github-actions/auth@v2", "with": w})
        elif c == "azure":
            w = {"client-id": _gha_ref(ir, "AZURE_CLIENT_ID"), "tenant-id": _gha_ref(ir, "AZURE_TENANT_ID"),
                 "subscription-id": _gha_ref(ir, "AZURE_SUBSCRIPTION_ID")}
            if static:
                # azure/login : identifiants assemblés à partir des variables déclarées
                secret = "${{ secrets.AZURE_CLIENT_SECRET }}"
                creds = (f'{{"clientId":"{w["client-id"]}","clientSecret":"{secret}",'
                         f'"subscriptionId":"{w["subscription-id"]}","tenantId":"{w["tenant-id"]}"}}')
                w = {"creds": creds}
            out.append({"uses": "azure/login@v2", "with": w})
    return out


def _gha_ref(ir: IR, name: str) -> str:
    """Valeur littérale si le paramètre est renseigné, sinon référence à une variable de dépôt."""
    var = next((v for v in ir.variables if v.name == name), None)
    if var is not None and var.value and not var.secret:
        return var.value
    return "${{ vars." + name + " }}"


def _gha_env_value(ir: IR, name: str) -> str:
    var = next((v for v in ir.variables if v.name == name), None)
    if var is not None and var.value and not var.secret:
        return var.value
    kind = "secrets" if (var is None or var.secret) else "vars"
    return "${{ " + f"{kind}.{name}" + " }}"


def github_actions(ir: IR, path: str = ".github/workflows/pipeline.yml") -> dict[str, str]:
    steps = _ordered(ir)
    image = _image_value(ir, "${{ github.sha }}").replace("ghcr.io/OWNER/", "ghcr.io/${{ github.repository_owner }}/")
    env = {"TAG": "${{ github.sha }}", "IMAGE": image}  # ghcr.io exige un propriétaire en minuscules
    for v in ir.variables:
        if v.name.startswith(("AWS_", "GCP_", "AZURE_")):
            continue  # gérés par les actions d'authentification
        env[v.name] = _gha_env_value(ir, v.name)
    if ir.registry and ir.registry.id == "ghcr":
        env["GITHUB_TOKEN"] = "${{ secrets.GITHUB_TOKEN }}"
    doc: dict = {
        "name": f"Pipeline {ir.project.name}",
        "on": {"push": {"branches": ["main"]}, "pull_request": {}},
        "permissions": {"contents": "read", "id-token": "write", "packages": "write"},
        "env": env,
        "jobs": {},
    }
    previous: dict[str, list[str]] = {}
    for st in steps:
        host = bool(st.cloud or st.docker or st.stage in ("infra", "deploy") or st.tool in HOST_SETUP)
        job: dict = {"name": st.name, "runs-on": "ubuntu-latest"}
        needs = [j for stage in STAGE_ORDER[: STAGE_ORDER.index(st.stage)] for j in previous.get(stage, [])]
        needs += [n for n in st.needs if n not in needs]
        if needs:
            job["needs"] = needs
        if st.main_only:
            job["if"] = "github.ref == 'refs/heads/main'"
        if st.environment:
            job["environment"] = st.environment  # approbation : règles de protection de l'environnement
        elif st.manual:
            job["environment"] = "production"
        if not host:
            job["container"] = st.image
        if st.allow_failure:
            job["continue-on-error"] = True
        if st.lock:
            job["concurrency"] = {"group": st.lock, "cancel-in-progress": False}
        if st.services:
            job["services"] = {sv.alias: {"image": sv.image, **({"env": dict(sv.env)} if sv.env else {}),
                                          "ports": [f"{sv.port}:{sv.port}"]} for sv in st.services}
        if st.env:
            job["env"] = {k: v.replace("$REGISTRY_USER", "${{ secrets.REGISTRY_USER }}")
                          .replace("$REGISTRY_PASSWORD", "${{ secrets.REGISTRY_PASSWORD }}")
                          .replace("$GITHUB_TOKEN", "${{ secrets.GITHUB_TOKEN }}")
                          .replace("$GITHUB_ACTOR", "${{ github.actor }}")
                          for k, v in st.env.items()}
            if host:  # job sur la machine du runner : les services sont publiés sur localhost
                for sv in st.services:
                    job["env"] = {k: v.replace(f"http://{sv.alias}:", "http://localhost:") for k, v in job["env"].items()}
        gsteps: list[dict] = [{"uses": "actions/checkout@v4"}]
        script = list(st.script)
        if host:
            gsteps += _gha_cloud_steps(ir, st.cloud)
            gsteps += HOST_SETUP.get(st.tool, [])
            script = [l for l in script if not l.startswith(("apk add", "yum install", "az aks install-cli"))
                      and "get-helm-3" not in l and l not in TOFU_INSTALL and l not in TERRAFORM_INSTALL]
            if st.tool not in HOST_SETUP and any(l in st.script for l in TOFU_INSTALL[1:]):
                gsteps += HOST_SETUP["opentofu"]
            if st.tool not in HOST_SETUP and any(l in st.script for l in TERRAFORM_INSTALL[1:]):
                gsteps += HOST_SETUP["terraform"]
            if st.tool == "buildkit":
                gsteps.append({"uses": "docker/setup-buildx-action@v3"})
        if st.stage == "infra" and st.id == "iac-apply":
            gsteps.append({"uses": "actions/download-artifact@v4", "with": {"name": "iac-plan", "path": "infra/terraform"}})
        gsteps.append({"name": st.name, "run": "\n".join(script) + "\n"})
        if st.artifacts:
            name = "iac-plan" if st.id == "iac-plan" else st.id
            gsteps.append({"uses": "actions/upload-artifact@v4", "with": {"name": name, "path": "\n".join(st.artifacts)}})
        job["steps"] = gsteps
        doc["jobs"][st.id] = job
        previous.setdefault(st.stage, []).append(st.id)
    _note_gates(ir, "déclarer des relecteurs obligatoires sur l'environnement du dépôt "
                    "(Settings › Environments › Required reviewers), sinon le déploiement part sans attendre.")
    return {path: dump_yaml(doc)}


def gitea_actions(ir: IR) -> dict[str, str]:
    files = github_actions(ir, ".gitea/workflows/pipeline.yml")
    note = ("# Gitea Actions reprend la syntaxe GitHub Actions ; vérifier la disponibilité des actions\n"
            "# tierces et l'émission de jetons OIDC sur votre instance (act_runner).\n")
    return {k: note + v for k, v in files.items()}


# --------------------------------------------------------------------- Jenkins
def _groovy_block(lines: list[str]) -> str:
    body = "\n".join(lines).replace("\\", "\\\\").replace("'''", "\\'\\'\\'")
    return "sh '''\n" + body + "\n'''"


def jenkinsfile(ir: IR) -> dict[str, str]:
    secrets = [v for v in ir.variables if v.secret]
    plain = [v for v in ir.variables if not v.secret]
    env_lines = ["TAG = \"${env.GIT_COMMIT?.take(8)}\"", f"IMAGE = \"{ir.image_ref}:${{env.GIT_COMMIT?.take(8)}}\""]
    env_lines += [f"{v.name} = credentials('{v.name.lower().replace('_', '-')}')" for v in secrets]
    env_lines += [f"{v.name} = '{v.value or 'à-renseigner'}' // {v.description}" for v in plain]
    stages = []
    for st in _ordered(ir):
        if st.docker:
            agent = "agent any  // nécessite Docker sur l'agent"
        else:
            agent = f"agent {{ docker {{ image '{st.image}'; args '--entrypoint= -u root' }} }}"
        when = "\n            when { branch 'main' }" if st.main_only else ""
        if st.manual and st.environment:
            label = _env_label(ir, st).replace("'", "’")
            manual = f"\n            input {{ message 'Déployer en {label} ?' }}"
        elif st.manual:
            manual = "\n            input { message 'Appliquer ?' }"
        else:
            manual = ""
        script = full_script(ir, st, None)
        body = _groovy_block(script)
        if st.allow_failure:
            body = "catchError(buildResult: 'UNSTABLE', stageResult: 'FAILURE') {\n" + body + "\n}"
        body = "\n".join("                " + l for l in body.splitlines())
        stages.append(f"""        stage('{st.name.replace("'", "’")}') {{
            {agent}{when}{manual}
            steps {{
{body}
            }}
        }}""")
    text = f"""// {HEADER}
// Identifiants : créer dans Jenkins des credentials « secret text » nommés comme indiqué.
pipeline {{
    agent none
    options {{ timestamps() }}
    environment {{
{chr(10).join('        ' + l for l in env_lines)}
    }}
    stages {{
{chr(10).join(stages)}
    }}
}}
"""
    return {"Jenkinsfile": text}


# ------------------------------------------------------------------ Woodpecker
def woodpecker(ir: IR) -> dict[str, str]:
    steps = []
    for st in _ordered(ir):
        w: dict = {"name": st.id, "image": st.image}
        # Woodpecker substitue lui-même les variables : « $$ » protège celles du shell.
        w["commands"] = ['export TAG="${CI_COMMIT_SHA:0:8}"',
                         f'export IMAGE="{ir.image_ref}:$TAG"'.replace("$", "$$")]
        w["commands"] += [l.replace("$", "$$") for l in full_script(ir, st, None)]
        if st.docker:
            w["volumes"] = ["/var/run/docker.sock:/var/run/docker.sock"]
        env: dict = {v.name: {"from_secret": v.name.lower()} for v in ir.variables if v.secret}
        env.update({v.name: v.value or "à-renseigner" for v in ir.variables if not v.secret})
        if env:
            w["environment"] = env
        if st.main_only:
            # Approbation : l'étape ne part que sur un pipeline lancé à la main.
            w["when"] = [{"branch": "main", "event": "manual" if st.manual and st.environment else "push"}]
        if st.allow_failure:
            w["failure"] = "ignore"
        extra = {k: v for k, v in st.env.items() if "$" not in v}
        if extra:
            w.setdefault("environment", {}).update(extra)
        steps.append(w)
    note = HEADER + " Les étapes Docker montent le socket de l'hôte : dépôt de confiance requis."
    _note_gates(ir, "Woodpecker n'a pas de porte d'approbation : l'étape ne s'exécute que sur un pipeline "
                    "lancé manuellement depuis l'interface (événement « manual »).")
    services: dict[str, dict] = {}
    for st in _ordered(ir):
        for sv in st.services:
            services.setdefault(sv.alias, {"name": sv.alias, "image": sv.image,
                                           **({"environment": dict(sv.env)} if sv.env else {})})
    doc: dict = {"steps": steps}
    if services:
        doc["services"] = list(services.values())
    return {".woodpecker.yml": dump_yaml(doc, note)}


# ---------------------------------------------------------------------- Tekton
def tekton(ir: IR) -> dict[str, str]:
    main, gated = _split_gated(ir)
    files = {"tekton/pipeline.yaml": _tekton_pipeline(ir, main, f"{ir.app}-pipeline")}
    for st in gated:
        files[f"tekton/pipeline-{st.id}.yaml"] = _tekton_pipeline(ir, [st], f"{ir.app}-{st.id}")
    _note_gates(ir, "Tekton n'a pas de porte d'approbation native : ces déploiements sont des pipelines séparés "
                    "(tekton/pipeline-deploy-*.yaml), à lancer après validation (tkn pipeline start).")
    return files


def _tekton_pipeline(ir: IR, steps: list[Step], name: str) -> str:
    tasks = []
    prev: str | None = None
    for st in steps:
        script = "#!/bin/sh\nset -e\n" + "\n".join(full_script(ir, st, None)) + "\n"
        if st.docker:
            script = "#!/bin/sh\n# Étape Docker : sur Tekton, préférer Buildah (sans démon).\n" + script.split("\n", 1)[1]
        task: dict = {
            "name": st.id,
            "workspaces": [{"name": "source", "workspace": "source"}],
            "taskSpec": {
                "workspaces": [{"name": "source"}],
                "steps": [{
                    "name": st.id,
                    "image": st.image,
                    "workingDir": "$(workspaces.source.path)",
                    "env": [{"name": "TAG", "value": "$(params.tag)"},
                            {"name": "IMAGE", "value": f"{ir.image_ref}:$(params.tag)"}],
                    "script": script,
                }],
                "params": [{"name": "tag", "type": "string"}],
            },
            "params": [{"name": "tag", "value": "$(params.tag)"}],
        }
        if prev:
            task["runAfter"] = [prev]
        tasks.append(task)
        prev = st.id
    doc = {
        "apiVersion": "tekton.dev/v1",
        "kind": "Pipeline",
        "metadata": {"name": name},
        "spec": {
            "params": [{"name": "tag", "type": "string", "description": "Tag de l'image (commit)"}],
            "workspaces": [{"name": "source"}],
            "tasks": tasks,
        },
    }
    note = HEADER + " Le clone du dépôt (tâche git-clone du Hub) et les secrets sont à brancher sur l'espace « source »."
    return dump_yaml(doc, note)


# ------------------------------------------------------------- Azure Pipelines
def _az_script(ir: IR, st: Step) -> dict:
    """Étape script ; les variables secrètes ne sont visibles des scripts que si elles sont mappées."""
    step: dict = {"script": "\n".join(full_script(ir, st, None)) + "\n", "displayName": st.name}
    secrets = {v.name: f"$({v.name})" for v in ir.variables if v.secret}
    if secrets:
        step["env"] = secrets
    return step


def azure_pipelines(ir: IR) -> dict[str, str]:
    stages_out = []
    main_cond = "and(succeeded(), eq(variables['Build.SourceBranch'], 'refs/heads/main'))"
    for stage in STAGE_ORDER:
        jobs = []
        for st in [s for s in _ordered(ir) if s.stage == stage]:
            if st.environment:
                # Job de déploiement : historique et approbations portés par l'environnement Azure DevOps.
                sid = st.environment.replace("-", "_")
                stages_out.append({
                    "stage": f"deploy_{sid}",
                    "displayName": f"Déploiement — {_env_label(ir, st)}",
                    "condition": main_cond,
                    "jobs": [{
                        "deployment": f"deploy_{sid}",
                        "displayName": st.name,
                        "environment": st.environment,
                        "pool": {"vmImage": "ubuntu-latest"},
                        "strategy": {"runOnce": {"deploy": {"steps": [
                            {"checkout": "self"},
                            _az_script(ir, st),
                        ]}}},
                    }],
                })
                continue
            job: dict = {"job": st.id.replace("-", "_"), "displayName": st.name,
                         "pool": {"vmImage": "ubuntu-latest"}}
            if not (st.docker or st.cloud):
                job["container"] = st.image
            if st.main_only:
                job["condition"] = main_cond
            job["steps"] = [_az_script(ir, st)]
            if st.allow_failure:
                job["continueOnError"] = True
            jobs.append(job)
        if jobs:
            stages_out.append({"stage": stage, "jobs": jobs})
    doc = {
        "trigger": ["main"],
        "variables": {"TAG": "$(Build.SourceVersion)", "IMAGE": f"{ir.image_ref}:$(Build.SourceVersion)"},
        "stages": stages_out,
    }
    note = HEADER + " Pour Azure, préférer une connexion de service à fédération d'identité (tâche AzureCLI@2)."
    _note_gates(ir, "ajouter une vérification « Approvals » sur l'environnement Azure DevOps correspondant "
                    "(Pipelines › Environments › Approvals and checks).")
    return {"azure-pipelines.yml": dump_yaml(doc, note)}


# ---------------------------------------------------------------- AWS CodeBuild
def _docker_run(st: Step, lines: list[str]) -> str:
    inner = " && ".join(lines)
    return (f"docker run --rm -v \"$PWD\":/src -w /src --entrypoint sh "
            f"-e TAG -e IMAGE {st.image} -c {shlex.quote(inner)}")


def aws_codebuild(ir: IR) -> dict[str, str]:
    main, gated = _split_gated(ir)
    files = {"buildspec.yml": _buildspec(ir, main)}
    for st in gated:
        files[f"buildspec-{st.id}.yml"] = _buildspec(ir, [st])
    _note_gates(ir, "placer une action d'approbation manuelle CodePipeline avant le projet CodeBuild "
                    "qui exécute buildspec-deploy-*.yml.")
    return files


def _buildspec(ir: IR, steps: list[Step]) -> str:
    commands: list[str] = ['export TAG="${CODEBUILD_RESOLVED_SOURCE_VERSION:0:8}"',
                           f'export IMAGE="{ir.image_ref}:$TAG"']
    for st in steps:
        commands.append(f'echo "--- {st.name}"')
        script = full_script(ir, st, None)
        if st.docker or "aws" in st.cloud:
            commands += script
        else:
            commands.append(_docker_run(st, script))
    doc = {"version": 0.2, "phases": {"build": {"commands": commands}},
           "artifacts": {"files": ["**/*"], "discard-paths": "no"}}
    note = HEADER + " Activer le mode privilégié du projet CodeBuild (Docker)."
    return dump_yaml(doc, note)


# ------------------------------------------------------------ Google Cloud Build
def google_cloud_build(ir: IR) -> dict[str, str]:
    main, gated = _split_gated(ir)
    files = {"cloudbuild.yaml": _cloudbuild(ir, main)}
    for st in gated:
        files[f"cloudbuild-{st.id}.yaml"] = _cloudbuild(ir, [st])
    _note_gates(ir, "créer pour cloudbuild-deploy-*.yaml un déclencheur Cloud Build avec l'option "
                    "« Approbation requise ».")
    return files


def _cloudbuild(ir: IR, steps_in: list[Step]) -> str:
    steps = []
    for st in steps_in:
        script = ['export TAG="$SHORT_SHA"', f'export IMAGE="{ir.image_ref}:$SHORT_SHA"']
        script += full_script(ir, st, None)
        image = "gcr.io/cloud-builders/docker" if st.docker else st.image
        steps.append({"id": st.id, "name": image, "entrypoint": "sh",
                      "args": ["-c", "\n".join(script).replace("$", "$$").replace("$$SHORT_SHA", "$SHORT_SHA")]})
    doc = {"steps": steps, "options": {"logging": "CLOUD_LOGGING_ONLY"}}
    note = HEADER + " Les secrets se déclarent via availableSecrets (Secret Manager)."
    return dump_yaml(doc, note)


RENDERERS = {
    "gitlab-ci": gitlab_ci,
    "github-actions": github_actions,
    "gitea-actions": gitea_actions,
    "jenkins": jenkinsfile,
    "woodpecker": woodpecker,
    "tekton": tekton,
    "azure-pipelines": azure_pipelines,
    "aws-codebuild": aws_codebuild,
    "google-cloud-build": google_cloud_build,
}
