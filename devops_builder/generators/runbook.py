# SPDX-License-Identifier: Apache-2.0
"""docs/mise-en-route.md : les gestes à faire à la main, dans l'ordre, avec les valeurs du projet.

Chaque section ne paraît que si sa brique est dans le pipeline. Les commandes sont prêtes à copier ;
ce qui dépend de l'organisation (dépôt, compte, adresse) est posé une fois en tête du document.
"""

from __future__ import annotations

from ..ir import IR
from . import secrets as sec
from .common import HEADER

PATH = "docs/mise-en-route.md"


def _sh(*lines: str) -> list[str]:
    return ["```bash", *lines, "```", ""]


def _repo_hint(ir: IR) -> str:
    if ir.forge and ir.forge.id == "github":
        return "propriétaire/dépôt"
    return "groupe/projet"


# ------------------------------------------------------------------ sections
def _values(ir: IR, files: dict[str, str], used: str) -> list[str]:
    """Valeurs propres à l'organisation, posées une fois ; seulement celles que le document emploie."""
    lines = []
    if "$REPO" in used or "${REPO}" in used:
        lines.append(f'export REPO="{_repo_hint(ir)}"   # dépôt de l\'application sur la forge')
    if "AWS_ACCOUNT_ID" in used:
        lines.append('export AWS_ACCOUNT_ID="123456789012"')
    if "$GITOPS_REPO" in used:
        lines.append('export GITOPS_REPO="git.example.com/groupe/gitops.git"   # même valeur que la variable CI')
    tool = sec.vault_tool(ir) if "$VAULT_ADDR" in used else None
    if tool:
        addr = str(sec.vault_params(ir).get("address") or "")
        if not addr and _in_cluster(ir, files):
            lines.append('export VAULT_ADDR="http://127.0.0.1:8200"   # par kubectl port-forward (section du coffre)')
        else:
            lines.append(f'export VAULT_ADDR="{addr or "https://coffre.example.com"}"'
                         + ("" if addr else "   # adresse du coffre vue depuis le poste"))
    if not lines:
        return []
    return ["## Valeurs à adapter", "",
            "À poser une fois dans le terminal ; les commandes suivantes les reprennent.", "", *_sh(*lines)]


def _in_cluster(ir: IR, files: dict[str, str]) -> bool:
    """Vault / OpenBao installé dans le cluster par platform/install.sh."""
    from .platform import external_vault
    tool = sec.vault_tool(ir)
    return bool(tool and not external_vault(ir, tool) and "platform/install.sh" in files
                and f"install {tool} " in files["platform/install.sh"])


def _state(ir: IR) -> list[str]:
    from .iac import S3_COMPATIBLE, backend_tool, s3_compatible_region
    tool = backend_tool(ir)
    if not tool or not (ir.iac and ir.iac.id in ("terraform", "opentofu")):
        return []
    name = ir.catalog[tool].name
    out = ["## État Terraform", "",
           f"Le stockage de l'état ({name}) se crée avant le premier `init` : la pile ne le crée pas, "
           "elle s'en sert.", ""]
    if tool == "s3":
        bucket = ir.params("s3").get("bucket")
        region = ir.params("aws").get("region", "eu-west-3")
        out += _sh(f'aws s3api create-bucket --bucket {bucket} --region {region} '
                   f'--create-bucket-configuration LocationConstraint={region}',
                   f"aws s3api put-bucket-versioning --bucket {bucket} --versioning-configuration Status=Enabled",
                   f"aws s3api put-public-access-block --bucket {bucket} --public-access-block-configuration "
                   "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true")
    elif tool == "gcs":
        bucket = ir.params("gcs").get("bucket")
        region = ir.params("gcp").get("region", "europe-west9")
        pid = ir.params("gcp").get("project_id", "mon-projet")
        out += _sh(f"gcloud storage buckets create gs://{bucket} --project {pid} --location {region} "
                   "--uniform-bucket-level-access --public-access-prevention",
                   f"gcloud storage buckets update gs://{bucket} --versioning")
    elif tool == "azure-blob":
        b = ir.params("azure-blob")
        rg = ir.params("azure").get("resource_group", "rg-mon-projet")
        loc = ir.params("azure").get("location", "francecentral")
        out += _sh(f"az group create --name {rg} --location {loc}",
                   f"az storage account create --name {b.get('storage_account')} --resource-group {rg} "
                   "--sku Standard_ZRS --min-tls-version TLS1_2 --allow-blob-public-access false",
                   f"az storage container create --name {b.get('container')} --account-name "
                   f"{b.get('storage_account')} --auth-mode login")
    else:
        region = s3_compatible_region(ir, tool)
        endpoint = S3_COMPATIBLE[tool][0].format(region=region)
        _, key, secret = S3_COMPATIBLE[tool]
        bucket = ir.params(tool).get("bucket")
        out += _sh(f'export AWS_ACCESS_KEY_ID="${key}" AWS_SECRET_ACCESS_KEY="${secret}"',
                   f"aws s3api create-bucket --bucket {bucket} --endpoint-url {endpoint}",
                   f"aws s3api put-bucket-versioning --bucket {bucket} --endpoint-url {endpoint} "
                   "--versioning-configuration Status=Enabled")
    return out


def _ci_cloud(ir: IR) -> list[str]:
    clouds = sorted({c for st in ir.steps for c in st.cloud})
    if not clouds or ir.project.cloud_auth != "oidc" or not ir.ci or ir.ci.id not in sec.JWT_ISSUERS:
        return []
    gitlab = ir.ci.id == "gitlab-ci"
    issuer = sec.JWT_ISSUERS[ir.ci.id][1]
    host = issuer.removeprefix("https://")
    sub = "project_path:${REPO}:ref_type:branch:ref:main" if gitlab else "repo:${REPO}:*"
    out = ["## Connexion de la CI au cloud", "",
           f"La CI s'authentifie par jeton OIDC ({sec.JWT_ISSUERS[ir.ci.id][0]}), sans clé statique. "
           "Une fois par cloud :", ""]
    if "aws" in clouds:
        aud = "sts.amazonaws.com"
        cond = "StringEquals" if gitlab else "StringLike"
        out += ["**AWS** — fournisseur d'identité OIDC et rôle assumé par la CI ; sa valeur va dans `AWS_ROLE_ARN`.",
                "", *_sh(f"aws iam create-open-id-connect-provider --url {issuer} --client-id-list {aud}",
                         "cat > /tmp/trust.json <<EOF",
                         '{"Version": "2012-10-17", "Statement": [{"Effect": "Allow", '
                         f'"Principal": {{"Federated": "arn:aws:iam::${{AWS_ACCOUNT_ID}}:oidc-provider/{host}"}}, '
                         '"Action": "sts:AssumeRoleWithWebIdentity", '
                         f'"Condition": {{"StringEquals": {{"{host}:aud": "{aud}"}}, '
                         f'"{cond}": {{"{host}:sub": "{sub}"}}}}}}]}}',
                         "EOF",
                         f"aws iam create-role --role-name {ir.app}-ci --assume-role-policy-document file:///tmp/trust.json",
                         "# droits du rôle : la pile crée des rôles IAM (EKS, External Secrets) ; à restreindre ensuite",
                         f"aws iam attach-role-policy --role-name {ir.app}-ci "
                         "--policy-arn arn:aws:iam::aws:policy/AdministratorAccess")]
    if "gcp" in clouds:
        pid = ir.params("gcp").get("project_id", "mon-projet")
        attr = "attribute.project_path" if gitlab else "attribute.repository"
        mapping = ("google.subject=assertion.sub,attribute.project_path=assertion.project_path" if gitlab else
                   "google.subject=assertion.sub,attribute.repository=assertion.repository")
        out += ["**Google Cloud** — pool Workload Identity et compte de service ; le nom complet du fournisseur va "
                "dans `GCP_WORKLOAD_IDENTITY_PROVIDER`.", "",
                *_sh(f"gcloud iam workload-identity-pools create ci --project {pid} --location global",
                     f"gcloud iam workload-identity-pools providers create-oidc ci --project {pid} --location global "
                     f'--workload-identity-pool ci --issuer-uri {issuer} --attribute-mapping "{mapping}" '
                     f"--attribute-condition \"assertion.{attr.split('.')[1]} == '${{REPO}}'\"",
                     f"gcloud iam service-accounts create {ir.app}-ci --project {pid}",
                     f'NUM="$(gcloud projects describe {pid} --format="value(projectNumber)")"',
                     f"gcloud iam service-accounts add-iam-policy-binding {ir.app}-ci@{pid}.iam.gserviceaccount.com "
                     '--role roles/iam.workloadIdentityUser --member '
                     f'"principalSet://iam.googleapis.com/projects/$NUM/locations/global/workloadIdentityPools/ci/'
                     f'{attr}/${{REPO}}"',
                     *[f"gcloud projects add-iam-policy-binding {pid} --member "
                       f"serviceAccount:{ir.app}-ci@{pid}.iam.gserviceaccount.com --role {role}"
                       for role in ("roles/editor", "roles/resourcemanager.projectIamAdmin")],
                     'echo "GCP_WORKLOAD_IDENTITY_PROVIDER=projects/$NUM/locations/global/workloadIdentityPools/ci/'
                     'providers/ci"')]
    if "azure" in clouds:
        subjects = ["project_path:${REPO}:ref_type:branch:ref:main"] if gitlab else (
            ["repo:${REPO}:ref:refs/heads/main"] + [f"repo:${{REPO}}:environment:{e.id}" for e in ir.envs])
        creds = [f"az ad app federated-credential create --id \"$APP_ID\" --parameters "
                 f"'{{\"name\": \"ci-{i}\", \"issuer\": \"{issuer}\", \"subject\": \"'\"{s}\"'\", "
                 "\"audiences\": [\"api://AzureADTokenExchange\"]}'" for i, s in enumerate(subjects, 1)]
        out += ["**Azure** — application Entra ID et identifiants fédérés ; `AZURE_CLIENT_ID`, `AZURE_TENANT_ID` "
                "et `AZURE_SUBSCRIPTION_ID` en variables CI.", "",
                *_sh(f'APP_ID="$(az ad app create --display-name {ir.app}-ci --query appId -o tsv)"',
                     'az ad sp create --id "$APP_ID" >/dev/null', *creds,
                     *[f'az role assignment create --assignee "$APP_ID" --role "{role}" '
                       '--scope "/subscriptions/$(az account show --query id -o tsv)"'
                       for role in ("Contributor", "Role Based Access Control Administrator")])]
    return out


def _infra(ir: IR, files: dict[str, str]) -> list[str]:
    if "infra/terraform/main.tf" not in files:
        return []
    cmd = ir.iac_cmd
    out = ["## Premier apply", "",
           "Le premier passage se fait depuis le poste (ou par le job manuel de la CI) ; les suivants passent par la CI.",
           ""]
    lines = []
    if "infra/terraform/terraform.tfvars.example" in files:
        lines.append("cp infra/terraform/terraform.tfvars.example infra/terraform/terraform.tfvars"
                     "   # valeurs à renseigner, fichier non versionné")
    c = f"{cmd} -chdir=infra/terraform"
    lines += [f"{c} init", f"{c} plan -out=plan.tfplan", f"{c} apply plan.tfplan", f"{c} output"]
    out += _sh(*lines)
    return out


def _platform(ir: IR, files: dict[str, str]) -> list[str]:
    out: list[str] = []
    scripts = [f for f in ("infra/cluster/install-k3s.sh", "infra/cluster/install-rke2.sh") if f in files]
    if not scripts and "platform/install.sh" not in files:
        return []
    out += ["## Cluster et plateforme", ""]
    if scripts:
        out += [f"Sur le nœud serveur : `sudo bash {scripts[0]}`, puis récupérer le kubeconfig "
                "(`/etc/rancher/k3s/k3s.yaml` ou `/etc/rancher/rke2/rke2.yaml`, adresse du serveur à corriger).", ""]
    if "platform/install.sh" in files:
        before = " après le premier apply (le script lit les sorties de la pile)" if sec.eso_identity(ir) else ""
        out += [f"Avec le kubeconfig du cluster, une fois{before} :", "",
                *_sh("kubectl config current-context", "bash platform/install.sh",
                     "kubectl get pods -A | grep -v Running   # rien ne doit rester en attente")]
    return out


def _vault(ir: IR, files: dict[str, str]) -> list[str]:
    from .platform import external_vault
    tool = sec.vault_tool(ir)
    if not tool:
        return []
    name = ir.catalog[tool].name
    cli = "vault" if tool == "vault" else "bao"
    out = [f"## Coffre {name}", ""]
    kube = ir.project.target in ("kubernetes", "kubernetes-managed") or ir.cluster is not None
    init: list[str] = []
    if not external_vault(ir, tool):
        if kube and _in_cluster(ir, files):
            exe = f"kubectl -n {tool} exec -ti {tool}-0 --"
        elif ir.has("docker-compose"):
            ns = ir.namespace(ir.envs[-1])
            exe = f'ssh "<hôte>" cd /opt/{ns} "&&" docker compose -p {ns} exec {tool}'

        else:
            exe = ""
        if exe:
            init = [f"{exe} {cli} operator init -key-shares=5 -key-threshold=3   # clés et jeton racine : hors de l'hôte",
                    f"{exe} {cli} operator unseal   # trois fois, trois clés différentes ; après chaque redémarrage",
                    f"{exe} {cli} status"]
    if init:
        out += ["Initialiser puis desceller le serveur (une fois, puis descellement à chaque redémarrage) :", "",
                *_sh(*init)]
    if _in_cluster(ir, files):
        out += ["Joindre l'API du coffre depuis le poste :", "",
                *_sh(f"kubectl -n {tool} port-forward svc/{tool} 8200:8200 &")]
    setup = files.get(sec.VAULT_SETUP)
    if setup:
        env = []
        if "CI_REPO" in setup:
            env.append('CI_REPO="$REPO"')
        if "CI_ISSUER" in setup and ir.forge and ir.forge.id == "gitlab":
            env.append("# GitLab autohébergé : CI_ISSUER=https://gitlab.example.com")
        k8s_extra = []
        if "KUBE_HOST" in setup and external_vault(ir, tool):
            k8s_extra = ["# coffre hors du cluster : adresse de l'API, autorité et jeton de relecture",
                         "export KUBE_HOST=https://<api-du-cluster>:6443 KUBE_CA_FILE=ca.crt "
                         "KUBE_REVIEWER_JWT=\"$(kubectl -n external-secrets create token external-secrets)\""]
        who = " et ".join(w for w, on in (("de la CI", "auth/jwt" in setup or "CI_REPO" in setup),
                                           ("d'External Secrets", "auth/kubernetes" in setup)) if on)
        out += [f"Configurer le coffre (moteur KV, politiques, connexion {who}) ; le script est relançable :", "",
                *_sh('export VAULT_TOKEN="<jeton racine>"', *k8s_extra,
                     f"{' '.join(e for e in env if not e.startswith('#'))} bash {sec.VAULT_SETUP}".strip(),
                     *[e for e in env if e.startswith("#")]),
                "Ensuite, créer un accès d'administration nominatif (OIDC, userpass) et révoquer le jeton racine :",
                "", *_sh('curl -fsS -X POST -H "X-Vault-Token: $VAULT_TOKEN" "$VAULT_ADDR/v1/auth/token/revoke-self"'),
                "Vérifier : `curl -s $VAULT_ADDR/v1/sys/health | jq` (`sealed: false`, `initialized: true`).", ""]
    return out


def _app_secrets(ir: IR, files: dict[str, str]) -> list[str]:
    from .data import compose_dbs
    dbs = compose_dbs(ir)
    vals = sec.values(ir, dbs)
    seed = files.get(sec.SEED_SCRIPT)
    tf = sec.tf_dbs(ir, dbs)
    if not vals:
        return []
    out = ["## Secrets de l'application", ""]
    names = sorted({v for v, tool, _ in vals if tool not in {d.id for d in tf}})
    gen = " ".join(f'{n}="$(openssl rand -hex 24)"' for n in names)
    if sec.source(ir) == "sops":
        out += ["Une paire de clés age pour le projet. La clé publique va dans la brique SOPS (paramètre "
                "« Destinataires age ») : régénérer le projet pour mettre `.sops.yaml` à jour. La clé privée va dans "
                "la variable CI `SOPS_AGE_KEY`.", "",
                *_sh("mkdir -p ~/.config/sops/age",
                     "age-keygen -o ~/.config/sops/age/keys.txt   # affiche la clé publique age1…",
                     "export SOPS_AGE_KEY_FILE=~/.config/sops/age/keys.txt"),
                "Puis, avec `.sops.yaml` à jour, chiffrer les valeurs de chaque environnement :", "",
                *_sh(*[f"{gen} bash {sec.SEED_SCRIPT} {e.id}" for e in ir.envs],
                     "git add deploy/secrets/*.enc.env .sops.yaml && git commit -m \"secrets chiffrés\""),
                "Nouvelle clé publique (arrivée ou départ) : la brique, puis `sops updatekeys deploy/secrets/*.enc.env`.",
                ""]
    elif seed:
        where = ir.catalog[sec.store(ir)].name
        auth = 'export VAULT_TOKEN="<jeton d\'administration>"' if sec.store(ir) in sec.VAULTS else \
            f"# compte autorisé à écrire dans {where}"
        out += [f"Écrire les valeurs dans {where}, une fois par environnement (et à chaque rotation) :", "",
                *_sh(auth, *[f"{gen} bash {sec.SEED_SCRIPT} {e.id}" for e in ir.envs])]
        if sec.store(ir) == "azure-key-vault" and sec.eso_identity(ir):
            out += ["Le coffre est en mode RBAC : le compte qui lance le script a besoin du rôle "
                    "« Key Vault Secrets Officer » sur le coffre.", ""]
    elif any(v.name.startswith(tuple(names)) for v in ir.variables):
        out += ["Valeurs dans des variables CI, une par environnement : `scripts/ci-variables.sh` les déclare "
                "(section Variables CI). Générer chaque mot de passe avec `openssl rand -hex 24`.", ""]
    from .data import SERVERLESS_SECRETS
    for tid, how in SERVERLESS_SECRETS.items():
        if ir.has(tid):
            out += [f"Brancher l'URL de connexion au service — {how}.", ""]
    if tf:
        st = sec.tf_store(ir)
        key = sec.remote_key(ir, ir.envs[0], tf[0].id)
        check = {"aws-secrets-manager": f"aws secretsmanager get-secret-value --secret-id {key} --query Name",
                 "gcp-secret-manager": f"gcloud secrets describe {key}",
                 "azure-key-vault": f"az keyvault secret show --vault-name "
                                    f"{ir.params('azure-key-vault').get('vault_name', 'kv-' + ir.app)} --name {key} "
                                    "--query name"}[st]
        out += [f"{', '.join(d.tool.name for d in tf)} : la pile Terraform écrit ces secrets à l'apply ; vérifier :",
                "", *_sh(check)]
    return out


def _eso(ir: IR) -> list[str]:
    if not sec.eso(ir) or not (ir.project.target in ("kubernetes", "kubernetes-managed") or ir.cluster):
        return []
    from .data import compose_dbs
    out = ["## External Secrets", ""]
    st = sec.store(ir)
    if sec.eso_identity(ir):
        out += ["La pile Terraform donne au contrôleur la lecture du coffre (identité de charge de travail) ; "
                "installer External Secrets après l'apply, ou le redémarrer : "
                "`kubectl -n external-secrets rollout restart deployment external-secrets`.", ""]
    elif st in sec.CLOUD_STORES:
        out += ["Donner au compte de service `external-secrets/external-secrets` la lecture du coffre : rôle IAM "
                "en annotation (IRSA), Workload Identity ou identité managée, selon le cluster.", ""]
    ns = ir.namespace(ir.envs[-1])
    lines = [f"kubectl get clustersecretstore {ir.app}   # READY True"]
    if any(d.mode != "operator" for d in compose_dbs(ir)):
        lines.append(f"kubectl -n {ns} get externalsecret   # STATUS SecretSynced")
    out += ["Vérifier, après `platform/install.sh` et le premier déploiement :", "", *_sh(*lines)]
    return out


def _hosts(ir: IR) -> list[str]:
    from .hosts import creates_hosts, deploy_user
    if ir.project.target not in ("docker-host", "vm") or not ir.has("docker-compose") and not ir.has("ansible"):
        return []
    user = deploy_user(ir)
    out = ["## Hôtes", ""]
    if creates_hosts(ir):
        from .hosts import INVENTORY_SCRIPT
        return out + [f"Les machines sont créées par la pile : cloud-init pose le compte `{user}`, la clé de la CI "
                      "(`TF_VAR_ssh_public_key`) et Docker. Rien à préparer à la main. Pour joindre une machine "
                      "depuis le poste :", "",
                      *_sh(f"bash {INVENTORY_SCRIPT} {ir.envs[0].id}   # écrit l'inventaire de l'environnement"
                           if ir.has("ansible") else
                           f"ssh \"{user}@$(bash {INVENTORY_SCRIPT} --first {ir.envs[0].id})\" docker ps")]
    else:
        out += [f"Sur chaque hôte : un compte `{user}` avec la clé publique de la CI (la clé privée va dans "
                "`SSH_PRIVATE_KEY`)" + (" et sudo sans mot de passe." if ir.has("ansible") else
                                        ", membre du groupe docker, Docker et son extension Compose installés."), "",
                *_sh("ssh-keygen -t ed25519 -N '' -f ci_deploy -C ci-deploy   # sur le poste",
                     f"sudo useradd -m -s /bin/bash {user}",
                     f"sudo install -d -m 700 -o {user} -g {user} /home/{user}/.ssh",
                     f"sudo tee /home/{user}/.ssh/authorized_keys < ci_deploy.pub",
                     *([f"echo '{user} ALL=(ALL) NOPASSWD:ALL' | sudo tee /etc/sudoers.d/{user}"]
                       if ir.has("ansible") else [f"sudo usermod -aG docker {user}"])),
                "Empreinte des hôtes dans `SSH_KNOWN_HOSTS` (facultatif, recommandé) : `ssh-keyscan <hôte>`.", ""]
    if ir.has("ansible"):
        out += ["Préparer les hôtes (Docker depuis son dépôt officiel), une fois par environnement :", "",
                *_sh("pip install 'ansible-core>=2.21,<2.22' && ansible-galaxy collection install -r ansible/requirements.yml",
                     *[f"ANSIBLE_CONFIG=ansible/ansible.cfg ansible-playbook -i {ir.inventory(e)} ansible/site.yml"
                       for e in ir.envs])]
    return out


def _gitops(ir: IR, files: dict[str, str]) -> list[str]:
    if "deploy/argocd/application.yaml" in files:
        return ["## Argo CD", "",
                "Le dépôt GitOps (variable `GITOPS_REPO`) doit être connu d'Argo CD, puis les applications créées :", "",
                *_sh('argocd repo add "https://$GITOPS_REPO" --username ci --password "<jeton de lecture>"',
                     "# adresse du dépôt GitOps à reporter dans deploy/argocd/application.yaml (repoURL)",
                     "kubectl apply -f deploy/argocd/application.yaml",
                     "argocd app list"), ]
    if "deploy/flux/gitops.yaml" in files:
        return ["## Flux", "",
                "Flux installé sur le cluster, avec l'accès au dépôt GitOps, puis les ressources du projet :", "",
                *_sh("flux install",
                     'flux create secret git gitops --url "https://$GITOPS_REPO" --username ci --password "<jeton>"',
                     "# adresse du dépôt et secretRef à reporter dans deploy/flux/gitops.yaml (GitRepository)",
                     "kubectl apply -f deploy/flux/gitops.yaml",
                     "flux get all -A")]
    return []


def _ci_vars(ir: IR, files: dict[str, str]) -> list[str]:
    if "scripts/ci-variables.sh" not in files:
        return []
    count = sum(1 for v in ir.variables if not v.value)
    return ["## Variables CI", "",
            f"{count} variable(s) à déclarer (liste dans `PIPELINE.md`). Le script les déclare avec l'outil de la "
            "forge, sans écrire les valeurs dans le dépôt :", "",
            *_sh("bash scripts/ci-variables.sh --dry-run   # ce qui serait déclaré", "bash scripts/ci-variables.sh")]


def _first_deploy(ir: IR) -> list[str]:
    if not any(st.stage == "deploy" for st in ir.steps):
        return []
    last = ir.envs[-1]
    ns = ir.namespace(last)
    out = ["## Premier déploiement", "",
           "Pousser sur la branche principale : chaque environnement se déploie dans l'ordre"
           + (", la production après approbation." if any(e.approval for e in ir.envs) else "."), ""]
    if ir.project.target in ("kubernetes", "kubernetes-managed") or ir.cluster:
        out += _sh(f"kubectl -n {ns} rollout status deployment/{ir.app}",
                   f"kubectl -n {ns} get pods")
    elif ir.has("docker-compose"):
        out += _sh(f'ssh "<hôte>" "cd /opt/{ns} && docker compose -p {ns} ps"')
    return out


def _upkeep(ir: IR, files: dict[str, str]) -> list[str]:
    items = []
    from .data import BACKUP_SCRIPT
    if BACKUP_SCRIPT in files:
        planned = "planifiée par Ansible" if ir.has("ansible") else "à planifier sur l'hôte (cron)"
        items.append(f"Sauvegardes : `{BACKUP_SCRIPT}` {planned} ; copier les fichiers hors de la machine et "
                     "tester une restauration (section Sauvegardes).")
    if (sec.source(ir) != "ci" or sec.eso(ir)) and sec.values(ir, _dbs(ir)):
        by = " (ou par la pile)" if sec.tf_dbs(ir, _dbs(ir)) else ""
        items.append(f"Rotation d'un mot de passe : nouvelle valeur par `scripts/secrets-seed.sh`{by}, puis "
                     "redéploiement" + (" ; External Secrets relit le coffre toutes les heures." if sec.eso(ir)
                                        else "."))
    from .platform import external_vault
    if sec.vault_tool(ir) and not external_vault(ir, sec.vault_tool(ir)):
        items.append("Coffre : desceller après chaque redémarrage, ou configurer le descellement automatique "
                     "(transit, KMS du cloud) ; sauvegarder le stockage intégré (`operator raft snapshot save`).")
    if ir.has("renovate") and not (ir.forge and ir.forge.id == "github"):
        items.append("Renovate : job planifié (quotidien) avec l'image renovate/renovate et `RENOVATE_TOKEN`.")
    if not items:
        return []
    return ["## Entretien", "", *[f"- {i}" for i in items], ""]


def _dbs(ir: IR):
    from .data import compose_dbs
    return compose_dbs(ir)


def _identity(ir: IR, files: dict[str, str]) -> list[str]:
    from . import identity
    tool = identity.idp(ir)
    if not tool:
        return []
    name = ir.catalog[tool].name
    out = [f"## {name}", ""]
    if tool == "keycloak":
        if identity.compose_target(ir):
            ns = ir.namespace(ir.envs[-1])
            first = ['# administrateur temporaire : admin-temporaire / KEYCLOAK_ADMIN_PASSWORD (deploy/secrets.sh)',
                     f'ssh "<hôte>" "cd /opt/{ns} && docker compose -p {ns} logs keycloak | tail -n 5"']
        else:
            first = ["kubectl -n keycloak wait keycloak/keycloak --for=condition=Ready --timeout=300s",
                     "kubectl -n keycloak get secret keycloak-initial-admin -o jsonpath='{.data.username}' | base64 -d; echo",
                     "kubectl -n keycloak get secret keycloak-initial-admin -o jsonpath='{.data.password}' | base64 -d; echo"]
        out += ["Keycloak démarre avec un administrateur temporaire, à remplacer par un compte nominatif dans le "
                "realm master (Console › Users), puis supprimer :", "", *_sh(*first),
                f"Décrire le realm « {identity.realm(ir)} » (groupes {identity.ADMINS} et {identity.DEVELOPERS}, "
                "clients de l'application et des outils) :", "",
                *_sh('export KEYCLOAK_USER="<administrateur>" KEYCLOAK_PASSWORD="<mot de passe>"',
                     f"{ir.iac_cmd} -chdir={identity.KC_DIR} init",
                     f"{ir.iac_cmd} -chdir={identity.KC_DIR} apply",
                     f"curl -fsS {identity.issuer(ir)}/.well-known/openid-configuration | jq -r .issuer"),
                f"Ajouter les personnes au groupe « {identity.ADMINS} » (droits d'administration des outils) ou "
                f"« {identity.DEVELOPERS} ».", ""]
    else:
        forge = "GitHub (Settings › Developer settings › OAuth Apps)" if (
            str(identity.params(ir).get("connector") or "") == "github" or (ir.forge and ir.forge.id == "github")) \
            else "GitLab (Préférences › Applications, portée read_user openid)"
        secrets = " ".join(f'--from-literal={identity.secret_env_name(c)}="$(openssl rand -hex 24)"'
                           for c in identity.clients(ir))
        lines = ['kubectl create namespace dex --dry-run=client -o yaml | kubectl apply -f -',
                 f'kubectl -n dex create secret generic dex-secrets --from-literal=DEX_CONNECTOR_ID="<id>" '
                 f'--from-literal=DEX_CONNECTOR_SECRET="<secret>" {secrets}'.rstrip()] \
            if identity.kube_target(ir) else ["# DEX_CONNECTOR_ID dans la configuration (compose), DEX_CONNECTOR_SECRET "
                                              "et les secrets des clients en variables CI (section Variables CI)"]
        out += [f"Dex délègue la connexion à {forge} : y créer une application OAuth avec l'adresse de retour "
                f"`{identity.issuer(ir)}/callback`, puis :", "", *_sh(*lines),
                f"Vérifier : `curl -fsS {identity.issuer(ir)}/.well-known/openid-configuration | jq -r .issuer`.", ""]
    wired = [ir.catalog[c.tool].name for c in identity.clients(ir)]
    if wired:
        out += [f"Outils branchés : {', '.join(wired)}. Vault / OpenBao : relancer `scripts/vault-setup.sh` avec "
                "`OIDC_CLIENT_SECRET` pour la connexion des personnes ; Argo CD et Grafana : `platform/install.sh` "
                "reprend leurs secrets. Harbor et SonarQube : renseigner l'émetteur et le client dans leur "
                "administration.", ""]
    return out


def _backups(ir: IR, files: dict[str, str]) -> list[str]:
    from .data import BACKUP_SECRET, RESTORE_SCRIPT, backup_needs_secret, cnpg_backup
    out: list[str] = []
    if RESTORE_SCRIPT in files:
        ns = ir.namespace(ir.envs[0])
        out += ["Sur l'hôte, une sauvegarde puis une restauration d'essai (la restauration remplace la base) :", "",
                *_sh(f"sudo /opt/{ns}/db-backup.sh /opt/{ns} /var/backups/{ns}",
                     f'last="$(sudo ls -t /var/backups/{ns} | head -n 1)"',
                     f'sudo /opt/{ns}/db-restore.sh /opt/{ns} "/var/backups/{ns}/$last" --oui')]
    target = cnpg_backup(ir)
    if target:
        secret = BACKUP_SECRET.format(app=ir.app)
        if backup_needs_secret(ir):
            dest = target[0]
            if dest.startswith("s3://"):
                lits = '--from-literal=ACCESS_KEY_ID="<clé>" --from-literal=ACCESS_SECRET_KEY="<secret>"'
            elif dest.startswith("gs://"):
                lits = "--from-file=credentials.json=<clé-du-compte-de-service>.json"
            else:
                lits = '--from-literal=AZURE_STORAGE_ACCOUNT="<compte>" --from-literal=AZURE_STORAGE_KEY="<clé>"'
            out += [f"CloudNativePG sauvegarde vers {target[0]} (plugin Barman Cloud) avec les identifiants du Secret "
                    f"`{secret}`, à créer dans chaque espace de noms :", "",
                    *_sh(*[f"kubectl -n {ir.namespace(e)} create secret generic {secret} {lits}" for e in ir.envs])]
        else:
            out += [f"CloudNativePG sauvegarde vers {target[0]} : bucket et accès créés par la pile Terraform.", ""]
        ns = ir.namespace(ir.envs[-1])
        out += ["Vérifier l'archivage et la sauvegarde quotidienne, puis restaurer pour essai dans un autre Cluster "
                "(`bootstrap.recovery`, voir la documentation du plugin) :", "",
                *_sh(f"kubectl -n {ns} get cluster {ir.app}-pg -o jsonpath='{{.status.conditions}}'   # ContinuousArchiving",
                     f"kubectl -n {ns} get scheduledbackup,backup")]
    if not out:
        return []
    return ["## Sauvegardes", "", *out]


def _dev(ir: IR, files: dict[str, str]) -> list[str]:
    from ..databases import migration_command
    from .data import DEV_DIR
    if f"{DEV_DIR}/compose.yaml" not in files:
        return []
    lines = [f"docker compose -f {DEV_DIR}/compose.yaml up -d --wait",
             f"set -a && . {DEV_DIR}/app.env && set +a   # variables de connexion pour l'application lancée sur le poste"]
    command = migration_command(ir.project, ir.catalog)
    if command:
        lines.append(command)
    if "adminer" in files[f"{DEV_DIR}/compose.yaml"]:
        lines.append(f"docker compose -f {DEV_DIR}/compose.yaml --profile outils up -d adminer   # http://127.0.0.1:8081")
    return ["## Poste de développement", "",
            "Les mêmes bases qu'en production, en version identique, sur le poste (ports liés à 127.0.0.1, mot de "
            f"passe `dev`). Les fichiers de `{DEV_DIR}/init/<base>/` sont joués à la création :", "", *_sh(*lines)]


def _zabbix(ir: IR) -> list[str]:
    from . import zabbix
    if not zabbix.enabled(ir):
        return []
    api = f"{zabbix.web_url(ir)}/api_jsonrpc.php"
    login = ('tok="$(curl -fsS -H \'Content-Type: application/json-rpc\' -d \'{"jsonrpc":"2.0","method":"user.login",'
             '"params":{"username":"Admin","password":"zabbix"},"id":1}\' "$ZBX" | jq -er "$ok")"')
    change = ('curl -fsS -H \'Content-Type: application/json-rpc\' -H "Authorization: Bearer $tok" -d "{\\"jsonrpc\\":'
              '\\"2.0\\",\\"method\\":\\"user.update\\",\\"params\\":{\\"userid\\":\\"1\\",\\"current_passwd\\":'
              '\\"zabbix\\",\\"passwd\\":\\"$ZABBIX_ADMIN_PASSWORD\\"},\\"id\\":2}" "$ZBX" | jq -e "$ok"')
    check = ('curl -fsS -H \'Content-Type: application/json-rpc\' -H "Authorization: Bearer $tok" -d \'{"jsonrpc":"2.0",'
             '"method":"host.get","params":{"output":["host","active_available"],"selectInterfaces":["available"],'
             '"filter":{"host":["Zabbix server"]}},"id":3}\' "$ZBX" | jq -c \'.result[0]\'')
    relogin = login.replace('\\"password\\":\\"zabbix\\"', '').replace(
        '"password":"zabbix"}', '"password":"\'"$ZABBIX_ADMIN_PASSWORD"\'"}')
    return ["## Zabbix", "",
            f"L'interface répond sur {zabbix.web_url(ir)} une fois le premier déploiement fait ; le serveur crée le "
            "schéma de sa base au premier démarrage (une à deux minutes). Le compte **Admin / zabbix** est connu de "
            "tous : le changer aussitôt, ici par l'API (ou dans l'interface, Utilisateurs → Admin) :", "",
            *_sh(f'ZBX="{api}"',
                 "ok='.result // error(.error | tostring)'   # réponse de l'API, ou son message d'erreur",
                 'ZABBIX_ADMIN_PASSWORD="$(openssl rand -hex 16)"; echo "$ZABBIX_ADMIN_PASSWORD"   # à ranger',
                 login, change),
            "Vérifier que l'agent fourni répond : l'hôte « Zabbix server » (le serveur lui-même) doit être disponible "
            "(`available` = 1 sur son interface ; ses contrôles par défaut sont passifs, `active_available` reste à 0) :", "",
            *_sh(relogin, check),
            "Les autres machines se supervisent avec un agent 2 chacune (paquet `zabbix-agent2` du dépôt officiel, "
            "https://www.zabbix.com/download), `Server=` pointant vers cet hôte Docker, puis un hôte déclaré dans "
            "l'interface.", ""]


SECTIONS = (_state, _ci_cloud, _infra, _platform, _identity, _vault, _app_secrets, _eso, _hosts, _gitops, _ci_vars,
            _first_deploy, _zabbix, _backups, _dev, _upkeep)


def runbook(ir: IR, files: dict[str, str]) -> dict[str, str]:
    parts: list[list[str]] = []
    for fn in SECTIONS:
        args = (ir, files) if fn.__code__.co_argcount == 2 else (ir,)
        lines = fn(*args)
        if lines:
            parts.append(lines)
    if not parts:
        return {}
    numbered = []
    for i, lines in enumerate(parts, 1):
        numbered.append([lines[0].replace("## ", f"## {i}. ", 1), *lines[1:]])
    values = _values(ir, files, "\n".join(line for lines in parts for line in lines))
    if values:
        numbered.insert(0, values)
    head = [f"# Mise en route — {ir.project.name}", "", f"<!-- {HEADER} -->", "",
            "Les gestes à faire une fois, dans l'ordre, avant le premier pipeline. Chaque section se vérifie "
            "avant de passer à la suivante.", ""]
    text = "\n".join(head + [line for lines in numbered for line in lines]).rstrip() + "\n"
    return {PATH: text}
