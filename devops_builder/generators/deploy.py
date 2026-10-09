"""Fichiers de déploiement : Compose, chart Helm, Kustomize, Argo CD, Flux, Ansible."""

from __future__ import annotations

from ..ir import IR
from . import data
from .common import HEADER, dump_yaml, dump_yaml_docs
from .platform import compose_platform_services

REPLICAS = {"sandbox": 1, "dev": 1, "recette": 1, "staging": 1, "production": 2}


def _published(ir: IR, component: str, host: int, container: int) -> str:
    """« hôte:conteneur », ou variable du fichier deploy/env/<env>.env quand les ports sont décalés."""
    from ..ports import parametrized, port_variable
    if parametrized(ir.project):
        return "${" + port_variable(component, container) + f":-{host}" + "}" + f":{container}"
    return f"{host}:{container}"


def _app_host(ir: IR) -> str:
    from ..ports import parametrized
    host = f"{ir.app}.example.com"
    return "${APP_HOST:-" + host + "}" if parametrized(ir.project) else host


def compose(ir: IR) -> dict[str, str]:
    from ..ports import env_file, parametrized, port_plan
    app = ir.app
    port = ir.project.app.port
    service: dict = {
        "image": "${IMAGE:-" + f"{ir.image_ref}:latest" + "}",
        "restart": "unless-stopped",
        "environment": {"PORT": str(port)},
    }
    if ir.has("traefik"):
        service["labels"] = [
            "traefik.enable=true",
            f"traefik.http.routers.{app}.rule=Host(`{_app_host(ir)}`)",
            f"traefik.http.routers.{app}.entrypoints=websecure",
            f"traefik.http.services.{app}.loadbalancer.server.port={port}",
        ]
    else:
        service["ports"] = [_published(ir, "app", port, port)]
    services = {app: service}
    services.update(data.compose_parts(ir, service, service["image"]))
    services.update(compose_platform_services(ir))
    files: dict[str, str] = {}
    if parametrized(ir.project):
        for tid, svc in services.items():
            if tid != app and svc.get("ports"):
                svc = dict(svc)
                svc["ports"] = [_published(ir, tid, int(p.split(":")[0]), int(p.split(":")[1])) for p in svc["ports"]]
                services[tid] = svc
        plan = port_plan(ir.project, ir.catalog)
        for env in ir.envs:
            files[f"deploy/env/{env.id}.env"] = env_file(ir.project, env, plan)
        ir.notes.append("Plusieurs environnements partagent un hôte Docker : leurs ports publiés sont décalés "
                        "(deploy/env/<environnement>.env, copié en .env à côté du fichier Compose).")
    volumes = sorted({v.split(":")[0] for s in services.values() for v in s.get("volumes", [])
                      if not v.startswith("/")})
    doc: dict = {"name": app, "services": services}
    if volumes:
        doc["volumes"] = {v: {} for v in volumes}
    files.update(data.secrets_script(ir))
    files.update(data.backup_script(ir))
    ir.cover("docker-compose")
    files["deploy/docker-compose.yml"] = dump_yaml(doc)
    return files


def helm_chart(ir: IR) -> dict[str, str]:
    app = ir.app
    port = ir.project.app.port
    base = f"charts/{app}"
    chart = {"apiVersion": "v2", "name": app, "description": f"Chart de {ir.project.name}",
             "type": "application", "version": "0.1.0", "appVersion": "0.1.0"}
    values: dict = {
        "replicaCount": 2,
        "image": {"repository": ir.image_ref, "tag": "latest", "pullPolicy": "IfNotPresent"},
        "service": {"type": "ClusterIP", "port": 80, "targetPort": port},
        "resources": {"requests": {"cpu": "100m", "memory": "128Mi"}, "limits": {"memory": "256Mi"}},
    }
    db_values, db_templates, db_env, db_init = data.helm_parts(ir)
    values.update(db_values)
    deployment = f"""apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{{{ .Release.Name }}}}
  labels:
    app.kubernetes.io/name: {app}
spec:
  replicas: {{{{ .Values.replicaCount }}}}
  selector:
    matchLabels:
      app.kubernetes.io/name: {app}
  template:
    metadata:
      labels:
        app.kubernetes.io/name: {app}
    spec:
      securityContext:
        runAsNonRoot: true
      containers:
        - name: {app}
          image: "{{{{ .Values.image.repository }}}}:{{{{ .Values.image.tag }}}}"
          imagePullPolicy: {{{{ .Values.image.pullPolicy }}}}
          ports:
            - containerPort: {{{{ .Values.service.targetPort }}}}
          resources:
            {{{{- toYaml .Values.resources | nindent 12 }}}}
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
"""
    if db_env:
        deployment += _indent({"env": db_env}, 10)
    if db_init:
        deployment = deployment.replace("      containers:\n", _indent({"initContainers": db_init}, 6) + "      containers:\n", 1)
    service = f"""apiVersion: v1
kind: Service
metadata:
  name: {{{{ .Release.Name }}}}
spec:
  type: {{{{ .Values.service.type }}}}
  selector:
    app.kubernetes.io/name: {app}
  ports:
    - port: {{{{ .Values.service.port }}}}
      targetPort: {{{{ .Values.service.targetPort }}}}
"""
    ir.cover("helm")
    env_files = {}
    if ir.multi_env:
        for env in ir.envs:
            env_files[ir.helm_values(env)] = dump_yaml(
                {"replicaCount": REPLICAS[env.kind], "image": {"tag": "latest"}, **data.helm_env_values(ir, env)},
                f"{HEADER} Valeurs propres à l'environnement « {env.display} ».")
    data.gitops_note(ir)
    return {
        **env_files,
        f"{base}/Chart.yaml": dump_yaml(chart),
        f"{base}/values.yaml": dump_yaml(values),
        f"{base}/templates/deployment.yaml": deployment,
        f"{base}/templates/service.yaml": service,
        **{f"{base}/{k}": v for k, v in db_templates.items()},
    }


def _indent(obj: dict, spaces: int) -> str:
    """Fragment YAML indenté, à insérer dans un gabarit Helm écrit à la main."""
    import yaml
    text = yaml.safe_dump(obj, sort_keys=False, allow_unicode=True, width=200)
    return "".join(" " * spaces + line + "\n" for line in text.splitlines())


def kustomize(ir: IR) -> dict[str, str]:
    app = ir.app
    port = ir.project.app.port
    deployment = {
        "apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": app},
        "spec": {"replicas": 2, "selector": {"matchLabels": {"app": app}},
                 "template": {"metadata": {"labels": {"app": app}},
                              "spec": {"containers": [{"name": app, "image": f"{app}:latest",
                                                       "ports": [{"containerPort": port}]}]}}},
    }
    service = {"apiVersion": "v1", "kind": "Service", "metadata": {"name": app},
               "spec": {"selector": {"app": app}, "ports": [{"port": 80, "targetPort": port}]}}
    db_files, db_resources, db_env, db_init = data.kustomize_parts(ir)
    pod = deployment["spec"]["template"]["spec"]
    if db_env:
        pod["containers"][0]["env"] = db_env
    if db_init:
        deployment["spec"]["template"]["spec"] = {"initContainers": db_init, **pod}
    base_k = {"apiVersion": "kustomize.config.k8s.io/v1beta1", "kind": "Kustomization",
              "resources": ["deployment.yaml", "service.yaml", *db_resources]}
    image_name = ir.image_ref  # référence sans tag ; le tag est posé par la CI
    root = "deploy/kustomize"
    ir.cover("kustomize")
    files = {
        f"{root}/base/deployment.yaml": dump_yaml(deployment),
        f"{root}/base/service.yaml": dump_yaml(service),
        f"{root}/base/kustomization.yaml": dump_yaml(base_k),
        **{f"{root}/base/{k}": v for k, v in db_files.items()},
    }
    if not ir.has("helm"):
        data.gitops_note(ir)
    for env in ir.envs:
        overlay: dict = {"apiVersion": "kustomize.config.k8s.io/v1beta1", "kind": "Kustomization",
                         "namespace": ir.namespace(env), "resources": ["../../base"],
                         "images": [{"name": app, "newName": image_name, "newTag": "latest"}]}
        if ir.multi_env:
            overlay["replicas"] = [{"name": app, "count": REPLICAS[env.kind]}]
        patches = data.kustomize_patches(ir, env)
        if patches:
            overlay["patches"] = patches
        files[f"{ir.overlay(env)}/kustomization.yaml"] = dump_yaml(overlay)
    return files


def _source(ir: IR, env) -> dict:
    """Source Git d'un environnement : chart Helm + fichier de valeurs, ou overlay Kustomize."""
    repo = "https://git.example.com/groupe/gitops.git"
    if ir.has("helm"):
        src: dict = {"repoURL": repo, "targetRevision": "main", "path": f"charts/{ir.app}"}
        if ir.multi_env:
            src["helm"] = {"valueFiles": ["values.yaml", f"values-{env.id}.yaml"]}
        return src
    return {"repoURL": repo, "targetRevision": "main", "path": ir.overlay(env)}


def _clusters_note(ir: IR, tool: str) -> None:
    clusters = {c.id for e in ir.envs if (c := ir.cluster_for(e))}
    if len(clusters) > 1:
        ir.notes.append(f"{tool} : les environnements utilisent plusieurs clusters ; enregistrer les clusters distants "
                        "auprès du contrôleur et adapter la destination de chaque environnement.")


def argo_cd(ir: IR) -> dict[str, str]:
    docs = []
    for env in ir.envs:
        docs.append({
            "apiVersion": "argoproj.io/v1alpha1", "kind": "Application",
            "metadata": {"name": ir.namespace(env), "namespace": "argocd",
                         "labels": {"app.kubernetes.io/part-of": ir.app, "environment": env.id}},
            "spec": {
                "project": "default",
                "source": _source(ir, env),
                "destination": {"server": "https://kubernetes.default.svc", "namespace": ir.namespace(env)},
                "syncPolicy": {"automated": {"prune": True, "selfHeal": True},
                               "syncOptions": ["CreateNamespace=true"]},
            },
        })
    _clusters_note(ir, "Argo CD")
    ir.cover("argo-cd")
    return {"deploy/argocd/application.yaml": dump_yaml_docs(docs)}


def flux(ir: IR) -> dict[str, str]:
    repo = {"apiVersion": "source.toolkit.fluxcd.io/v1", "kind": "GitRepository",
            "metadata": {"name": "gitops", "namespace": "flux-system"},
            "spec": {"interval": "1m", "url": "https://git.example.com/groupe/gitops.git", "ref": {"branch": "main"}}}
    docs: list[dict] = [repo]
    for env in ir.envs:
        ns = ir.namespace(env)
        if ir.has("helm"):
            chart: dict = {"chart": f"./charts/{ir.app}",
                           "sourceRef": {"kind": "GitRepository", "name": "gitops", "namespace": "flux-system"}}
            if ir.multi_env:
                chart["valuesFiles"] = [f"./charts/{ir.app}/values.yaml", f"./{ir.helm_values(env)}"]
            docs.append({"apiVersion": "helm.toolkit.fluxcd.io/v2", "kind": "HelmRelease",
                         "metadata": {"name": ns, "namespace": "flux-system"},
                         "spec": {"interval": "5m", "releaseName": ns, "targetNamespace": ns,
                                  "install": {"createNamespace": True}, "chart": {"spec": chart}}})
        else:
            docs.append({"apiVersion": "kustomize.toolkit.fluxcd.io/v1", "kind": "Kustomization",
                         "metadata": {"name": ns, "namespace": "flux-system"},
                         "spec": {"interval": "5m", "path": f"./{ir.overlay(env)}", "prune": True,
                                  "sourceRef": {"kind": "GitRepository", "name": "gitops"},
                                  "targetNamespace": ns}})
    _clusters_note(ir, "Flux")
    ir.cover("flux")
    return {"deploy/flux/gitops.yaml": dump_yaml_docs(docs)}


def _ports_shifted(ir: IR) -> bool:
    from ..ports import parametrized
    return parametrized(ir.project)


def _ansible_db_tasks(ir: IR) -> list[dict]:
    """Secrets des bases (écrits par deploy/secrets.sh dans la CI) et sauvegarde planifiée."""
    tasks: list[dict] = []
    if data.needs_secrets(ir):
        tasks.append({"name": "Copier les secrets des bases de données",
                      "ansible.builtin.copy": {"src": "../.secrets/", "dest": "{{ app_dir }}/secrets/",
                                               "mode": "0600", "directory_mode": "0700"},
                      "no_log": True})
    if data.backup_script(ir):
        tasks += [
            {"name": "Copier le script de sauvegarde des bases",
             "ansible.builtin.copy": {"src": f"../{data.BACKUP_SCRIPT}", "dest": "{{ app_dir }}/db-backup.sh",
                                      "mode": "0750"}},
            {"name": "Planifier la sauvegarde quotidienne des bases",
             "ansible.builtin.cron": {"name": "sauvegarde des bases {{ project }}", "hour": "3", "minute": "15",
                                      "job": "{{ app_dir }}/db-backup.sh {{ app_dir }} >/dev/null"}},
        ]
    return tasks


def ansible(ir: IR) -> dict[str, str]:
    files: dict[str, str] = {}
    for env in ir.envs:
        host = f"app1.{env.id}.example.com" if ir.multi_env else "app1.example.com"
        files[ir.inventory(env)] = (
            f"# {HEADER}\n" + (f"# Environnement : {env.display}\n" if ir.multi_env else "")
            + f"[app]\n{host} ansible_user=deploy\n\n"
            + (f"[k3s]\nk3s1{('.' + env.id) if ir.multi_env else ''}.example.com ansible_user=deploy\n" if ir.has("k3s") else "")
        )
    deploy_play = [{
        "name": f"Déployer {ir.app}",
        "hosts": "app",
        "become": True,
        "vars": {"image": f"{ir.image_ref}:latest", "project": ir.app, "app_dir": "/opt/{{ project }}"},
        "tasks": [
            {"name": "Créer le répertoire de l'application",
             "ansible.builtin.file": {"path": "{{ app_dir }}", "state": "directory", "mode": "0755"}},
            {"name": "Copier le fichier Compose",
             "ansible.builtin.copy": {"src": "../deploy/docker-compose.yml", "dest": "{{ app_dir }}/docker-compose.yml"}},
            *([{"name": "Copier les ports de l'environnement",
                "ansible.builtin.copy": {"src": "../deploy/env/{{ deploy_env }}.env", "dest": "{{ app_dir }}/.env"}}]
              if _ports_shifted(ir) else []),
            *_ansible_db_tasks(ir),
            {"name": "Démarrer les services",
             "community.docker.docker_compose_v2": {"project_src": "{{ app_dir }}", "project_name": "{{ project }}",
                                                    "pull": "always",
                                                    "state": "present"},
             "environment": {"IMAGE": "{{ image }}"}},
        ],
    }]
    files["ansible/deploy.yml"] = dump_yaml(deploy_play)
    site: list[dict] = [{
        "name": "Préparer les hôtes Docker",
        "hosts": "app",
        "become": True,
        "tasks": [
            {"name": "Installer Docker",
             "ansible.builtin.package": {"name": ["docker.io", "docker-compose-v2"], "state": "present"}},
            {"name": "Activer Docker",
             "ansible.builtin.service": {"name": "docker", "state": "started", "enabled": True}},
        ],
    }]
    if ir.has("k3s"):
        from .extras import k3s_exec_flags
        site.append({
            "name": "Installer k3s",
            "hosts": "k3s",
            "become": True,
            "tasks": [{"name": "Installer k3s (script officiel)",
                       "ansible.builtin.shell": "curl -sfL https://get.k3s.io | sh -",
                       "environment": {"INSTALL_K3S_EXEC": k3s_exec_flags(ir)},
                       "args": {"creates": "/usr/local/bin/k3s"}}],
        })
        ir.cover("k3s")
    files["ansible/site.yml"] = dump_yaml(site)
    ir.cover("ansible")
    return files
