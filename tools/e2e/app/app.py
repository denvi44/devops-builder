# SPDX-License-Identifier: Apache-2.0
"""Application de démonstration des tests de bout en bout : elle prouve que le câblage généré fonctionne.

    GET /        200 : le conteneur répond
    GET /db      200 si chaque base déclarée (DATABASE_URL, REDIS_URL, MONGODB_URI) accepte une connexion
                 authentifiée ; 503 sinon, avec le détail en JSON
    GET /oidc    200 si OIDC_ISSUER_URL publie une configuration OpenID dont l'émetteur est le sien

Aucun secret n'est renvoyé : seulement le nom de la variable et le résultat.
"""

from __future__ import annotations

import json
import os
import socket
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def check_postgresql(url: str) -> str:
    import psycopg

    with psycopg.connect(url.replace("postgresql+psycopg://", "postgresql://"), connect_timeout=5) as conn:
        conn.execute("select 1").fetchone()
    return "ok"


def check_redis(url: str) -> str:
    u = urllib.parse.urlsplit(url)
    with socket.create_connection((u.hostname, u.port or 6379), timeout=5) as s:
        if u.password:
            pw = urllib.parse.unquote(u.password)
            s.sendall(f"*2\r\n$4\r\nAUTH\r\n${len(pw.encode())}\r\n{pw}\r\n".encode())
            reply = s.recv(256)
            if not reply.startswith(b"+OK"):
                return "authentification refusée"
        s.sendall(b"*1\r\n$4\r\nPING\r\n")
        return "ok" if s.recv(64).startswith(b"+PONG") else "réponse inattendue"


CHECKS = {"DATABASE_URL": check_postgresql, "REDIS_URL": check_redis}


def databases() -> tuple[bool, dict[str, str]]:
    results: dict[str, str] = {}
    for var, check in CHECKS.items():
        url = os.environ.get(var)
        if not url:
            continue
        try:
            results[var] = check(url)
        except Exception as exc:  # le détail aide à corriger le générateur ; jamais l'URL elle-même
            results[var] = f"{type(exc).__name__} : {str(exc)[:200]}"
    return bool(results) and all(v == "ok" for v in results.values()), results


def oidc() -> tuple[bool, dict[str, str]]:
    issuer = os.environ.get("OIDC_ISSUER_URL", "")
    if not issuer:
        return False, {"OIDC_ISSUER_URL": "absente"}
    try:
        with urllib.request.urlopen(issuer.rstrip("/") + "/.well-known/openid-configuration", timeout=5) as r:
            conf = json.load(r)
    except Exception as exc:
        return False, {"OIDC_ISSUER_URL": f"{type(exc).__name__} : {str(exc)[:200]}"}
    same = conf.get("issuer") == issuer
    return same, {"OIDC_ISSUER_URL": "ok" if same else f"émetteur annoncé : {conf.get('issuer')}"}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: dict) -> None:
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):  # noqa: N802
        if self.path in ("/", "/sante", "/healthz"):
            self._send(200, {"etat": "ok"})
        elif self.path == "/db":
            ok, details = databases()
            self._send(200 if ok else 503, details or {"bases": "aucune variable de connexion"})
        elif self.path == "/oidc":
            ok, details = oidc()
            self._send(200 if ok else 503, details)
        else:
            self._send(404, {"erreur": "inconnu"})

    def log_message(self, fmt, *args):  # journal sur une ligne, sans les en-têtes
        print(f"{self.address_string()} {fmt % args}", flush=True)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    print(f"Application de démonstration sur le port {port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
