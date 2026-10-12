#!/usr/bin/env bash
# Généré par DevOps Builder — à relire avant usage.
# Configure OpenBao pour mon-app, sans rien supprimer ; relançable sans risque :
#   moteur KV v2 « secret », politique de lecture mon-app-ci-read et admin,
#   connexion JWT de la CI (GitLab, rôle « mon-app-ci »),
#   connexion OIDC des personnes (Keycloak, groupe admins)
#
#   VAULT_ADDR=https://… VAULT_TOKEN=<jeton d'administration> CI_REPO=groupe/projet scripts/vault-setup.sh
#
# Variables : VAULT_ADDR, VAULT_TOKEN (racine au premier passage, puis à révoquer),
#   CI_REPO (groupe/projet), CI_BRANCH (main par défaut),
#   CI_ISSUER (https://gitlab.com par défaut ; GitLab autohébergé : son adresse),
#   CI_AUDIENCE (VAULT_ADDR par défaut : l'audience que la CI demande),
#   OIDC_CLIENT_SECRET (secret du client OIDC du coffre), OIDC_REDIRECT_BASE (adresse de l'interface)
set -euo pipefail
command -v jq >/dev/null || { echo "Outil manquant : jq" >&2; exit 3; }
: "${VAULT_ADDR:?VAULT_ADDR manquant}"
: "${VAULT_TOKEN:?VAULT_TOKEN manquant : jeton administrateur}"
: "${CI_REPO:?CI_REPO manquant (groupe/projet)}"
api() {  # api MÉTHODE CHEMIN [JSON] : corps de la réponse ; l'erreur du coffre sur la sortie d'erreur
  local out code
  out="$(curl -sS -X "$1" -H "X-Vault-Token: $VAULT_TOKEN" ${3:+-H "Content-Type: application/json" -d "$3"} \
    -w '\n%{http_code}' "$VAULT_ADDR/v1/$2")" || return 1
  code="${out##*$'\n'}"
  out="${out%$'\n'*}"
  if [ "$code" -ge 300 ]; then
    echo "$1 $2 : HTTP $code $out" >&2
    return 1
  fi
  printf '%s' "$out"
}
enabled() {  # enabled sys/mounts|sys/auth CHEMIN : déjà activé ?
  api GET "$1" | jq -e --arg p "$2/" '(.data // .) | has($p)' >/dev/null
}
policy() {  # policy NOM PRÉFIXE… : lecture de <moteur>/data/<préfixe>/*
  local name="$1" rules=""
  shift
  for prefix in "$@"; do
    rules+="path \"secret/data/$prefix/*\" { capabilities = [\"read\"] }"$'\n'
  done
  api PUT "sys/policies/acl/$name" "$(jq -n --arg p "$rules" '{policy: $p}')" >/dev/null
  echo "Politique $name : lecture de secret/data/<préfixe>/* ($*)"
}

api GET auth/token/lookup-self >/dev/null || { echo "VAULT_TOKEN refusé par $VAULT_ADDR" >&2; exit 1; }
if enabled sys/mounts "secret"; then
  echo "Moteur secret déjà activé"
else
  api POST "sys/mounts/secret" '{"type": "kv", "options": {"version": "2"}}' >/dev/null
  echo "Moteur KV v2 secret activé"
fi

# Connexion de la CI (GitLab) : jeton OIDC du job, limité au dépôt et à la branche protégée
policy "mon-app-ci-read" mon-app mon-app-staging
ISSUER="${CI_ISSUER:-https://gitlab.com}"
if ! enabled sys/auth jwt; then
  api POST sys/auth/jwt '{"type": "jwt"}' >/dev/null
  echo "Méthode auth/jwt activée"
fi
api POST auth/jwt/config "$(jq -n --arg i "$ISSUER" '{oidc_discovery_url: $i, bound_issuer: $i}')" >/dev/null
api POST auth/jwt/role/mon-app-ci "$(jq -n --arg aud "${CI_AUDIENCE:-$VAULT_ADDR}" --arg repo "$CI_REPO" \
  --arg branch "${CI_BRANCH:-main}" '{
    role_type: "jwt", user_claim: "sub", bound_audiences: [$aud],
    bound_claims_type: "string", bound_claims: {project_path: $repo, ref_type: "branch", ref: $branch, ref_protected: "true"},
    token_policies: ["mon-app-ci-read"], token_ttl: "15m", token_max_ttl: "30m"}')" >/dev/null
echo "Rôle auth/jwt/role/mon-app-ci : $CI_REPO, branche ${CI_BRANCH:-main}, émetteur $ISSUER"

# Connexion des personnes : OIDC par Keycloak ; le groupe « admins » reçoit la politique admin
OIDC_SECRET="${OIDC_CLIENT_SECRET:-}"
[ -n "$OIDC_SECRET" ] || OIDC_SECRET="$(tofu -chdir="$(dirname "$0")/../infra/keycloak" output -raw openbao_client_secret 2>/dev/null || true)"
if [ -z "$OIDC_SECRET" ]; then
  echo "OIDC_CLIENT_SECRET absent : connexion OIDC des personnes non configurée (relancer avec la valeur)" >&2
else
  api PUT sys/policies/acl/admin "$(jq -n '{policy: "path \"*\" { capabilities = [\"create\", \"read\", \"update\", \"delete\", \"list\", \"sudo\"] }"}')" >/dev/null
  if ! enabled sys/auth oidc; then
    api POST sys/auth/oidc '{"type": "oidc"}' >/dev/null
    echo "Méthode auth/oidc activée"
  fi
  api POST auth/oidc/config "$(jq -n --arg i "https://auth.boutique.fr/realms/mon-app" --arg s "$OIDC_SECRET" \
    '{oidc_discovery_url: $i, oidc_client_id: "openbao", oidc_client_secret: $s, default_role: "admin"}')" >/dev/null
  UI="${OIDC_REDIRECT_BASE:-https://coffre.boutique.fr}"
  api POST auth/oidc/role/admin "$(jq -n --arg ui "$UI" '{
      user_claim: "sub", groups_claim: "groups", oidc_scopes: ["openid", "profile", "email", "groups"],
      allowed_redirect_uris: [($ui + "/ui/vault/auth/oidc/oidc/callback"), "http://localhost:8250/oidc/callback"],
      bound_claims: {groups: ["admins"]}, token_policies: ["admin"], token_ttl: "8h"}')" >/dev/null
  echo "Rôle auth/oidc/role/admin : groupe admins de Keycloak (https://auth.boutique.fr/realms/mon-app)"
fi

echo "Configuration terminée. Écrire ensuite les secrets : scripts/secrets-seed.sh <environnement>"
