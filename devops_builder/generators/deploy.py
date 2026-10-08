"""Fichiers de déploiement : Compose, chart Helm, Kustomize, Argo CD, Flux, Ansible."""

from __future__ import annotations

from ..ir import IR
from .common import HEADER, dump_yaml, dump_yaml_docs
from .platform import compose_platform_services


def compose(ir: IR) -> dict[str, str]:
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
            f"traefik.http.routers.{app}.rule=Host(`{app}.example.com`)",
            f"traefik.http.routers.{app}.entrypoints=websecure",
            f"traefik.http.services.{app}.loadbalancer.server.port={port}",
        ]
    else:
        service["ports"] = [f"{port}:{port}"]
    services = {app: service}
    services.update(compose_platform_services(ir))
    volumes = sorted({v.split(":")[0] for s in services.values() for v in s.get("volumes", [])
                      if not v.startswith("/")})
    doc: dict = {"name": app, "services": services}
    if volumes:
        doc["volumes"] = {v: {} for v in volumes}
    ir.cover("docker-compose")
    return {"deploy/docker-compose.yml": dump_yaml(doc)}


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
    return {
        f"{base}/Chart.yaml": dump_yaml(chart),
        f"{base}/values.yaml": dump_yaml(values),
        f"{base}/templates/deployment.yaml": deployment,
        f"{base}/templates/service.yaml": service,
    }


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
    base_k = {"apiVersion": "kustomize.config.k8s.io/v1beta1", "kind": "Kustomization",
              "resources": ["deployment.yaml", "service.yaml"]}
    image_name = ir.image_ref  # référence sans tag ; le tag est posé par la CI
    overlay = {"apiVersion": "kustomize.config.k8s.io/v1beta1", "kind": "Kustomization",
               "namespace": app, "resources": ["../../base"],
               "images": [{"name": app, "newName": image_name, "newTag": "latest"}]}
    root = "deploy/kustomize"
    ir.cover("kustomize")
    return {
        f"{root}/base/deployment.yaml": dump_yaml(deployment),
        f"{root}/base/service.yaml": dump_yaml(service),
        f"{root}/base/kustomization.yaml": dump_yaml(base_k),
        f"{root}/overlays/production/kustomization.yaml": dump_yaml(overlay),
    }


def _source_path(ir: IR) -> str:
    return f"charts/{ir.app}" if ir.has("helm") else "deploy/kustomize/overlays/production"


def argo_cd(ir: IR) -> dict[str, str]:
    app = {
        "apiVersion": "argoproj.io/v1alpha1", "kind": "Application",
        "metadata": {"name": ir.app, "namespace": "argocd"},
        "spec": {
            "project": "default",
            "source": {"repoURL": "https://git.example.com/groupe/gitops.git", "targetRevision": "main",
                       "path": _source_path(ir)},
            "destination": {"server": "https://kubernetes.default.svc", "namespace": ir.app},
            "syncPolicy": {"automated": {"prune": True, "selfHeal": True},
                           "syncOptions": ["CreateNamespace=true"]},
        },
    }
    ir.cover("argo-cd")
    return {"deploy/argocd/application.yaml": dump_yaml(app)}


def flux(ir: IR) -> dict[str, str]:
    repo = {"apiVersion": "source.toolkit.fluxcd.io/v1", "kind": "GitRepository",
            "metadata": {"name": "gitops", "namespace": "flux-system"},
            "spec": {"interval": "1m", "url": "https://git.example.com/groupe/gitops.git", "ref": {"branch": "main"}}}
    if ir.has("helm"):
        release = {"apiVersion": "helm.toolkit.fluxcd.io/v2", "kind": "HelmRelease",
                   "metadata": {"name": ir.app, "namespace": ir.app},
                   "spec": {"interval": "5m",
                            "chart": {"spec": {"chart": f"./charts/{ir.app}",
                                               "sourceRef": {"kind": "GitRepository", "name": "gitops",
                                                             "namespace": "flux-system"}}}}}
        docs = [repo, release]
    else:
        ks = {"apiVersion": "kustomize.toolkit.fluxcd.io/v1", "kind": "Kustomization",
              "metadata": {"name": ir.app, "namespace": "flux-system"},
              "spec": {"interval": "5m", "path": f"./{_source_path(ir)}", "prune": True,
                       "sourceRef": {"kind": "GitRepository", "name": "gitops"},
                       "targetNamespace": ir.app}}
        docs = [repo, ks]
    ir.cover("flux")
    return {"deploy/flux/gitops.yaml": dump_yaml_docs(docs)}


def ansible(ir: IR) -> dict[str, str]:
    files: dict[str, str] = {}
    files["ansible/inventory.ini"] = (
        f"# {HEADER}\n[app]\napp1.example.com ansible_user=deploy\n\n"
        + ("[k3s]\nk3s1.example.com ansible_user=deploy\n" if ir.has("k3s") else "")
    )
    deploy_play = [{
        "name": f"Déployer {ir.app}",
        "hosts": "app",
        "become": True,
        "vars": {"image": f"{ir.image_ref}:latest", "app_dir": "/opt/app"},
        "tasks": [
            {"name": "Créer le répertoire de l'application",
             "ansible.builtin.file": {"path": "{{ app_dir }}", "state": "directory", "mode": "0755"}},
            {"name": "Copier le fichier Compose",
             "ansible.builtin.copy": {"src": "../deploy/docker-compose.yml", "dest": "{{ app_dir }}/docker-compose.yml"}},
            {"name": "Démarrer les services",
             "community.docker.docker_compose_v2": {"project_src": "{{ app_dir }}", "pull": "always",
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
