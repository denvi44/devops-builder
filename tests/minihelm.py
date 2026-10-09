"""Rendu Helm minimal pour les tests : le sous-ensemble de gabarits qu'écrit DevOps Builder.

Le binaire helm n'est pas toujours installé (ni téléchargeable) sur le poste de test ; ce rendu
couvre les expressions des gabarits générés — .Release.Name, .Values.*, if/end, required,
printf, quote, toYaml, nindent — et lève une erreur sur toute autre construction, pour qu'un
gabarit nouveau ne passe pas inaperçu.
"""

from __future__ import annotations

import re
import shlex
from typing import Any

import yaml

TAG = re.compile(r"(\s*)\{\{(-?)\s*(.*?)\s*(-?)\}\}", re.S)


class RenderError(Exception):
    pass


def _lookup(path: str, ctx: dict) -> Any:
    node: Any = ctx
    for part in path.lstrip(".").split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _term(tok: str, ctx: dict) -> Any:
    if tok.startswith('"'):
        return shlex.split(tok)[0]
    if tok.startswith("."):
        return _lookup(tok, ctx)
    if re.fullmatch(r"-?\d+", tok):
        return int(tok)
    raise RenderError(f"terme non pris en charge : {tok}")


def _call(words: list[str], ctx: dict, piped: Any = None, has_pipe: bool = False) -> Any:
    fn, args = words[0], words[1:]
    if fn.startswith(".") or fn.startswith('"'):
        if args:
            raise RenderError(f"arguments inattendus : {words}")
        return _term(fn, ctx)
    vals = [_term(a, ctx) for a in args] + ([piped] if has_pipe else [])
    if fn == "required":
        if vals[1] in (None, ""):
            raise RenderError(vals[0])
        return vals[1]
    if fn == "printf":
        return vals[0] % tuple(vals[1:])
    if fn == "quote":
        return '"' + str(vals[0]).replace('"', '\\"') + '"'
    if fn == "toYaml":
        return yaml.safe_dump(vals[0], sort_keys=False).rstrip("\n")
    if fn == "nindent":
        pad = " " * int(vals[0])
        return "\n" + "\n".join(pad + line for line in str(vals[1]).splitlines())
    raise RenderError(f"fonction non prise en charge : {fn}")


def _eval(expr: str, ctx: dict) -> Any:
    value, first = None, True
    for stage in expr.split("|"):
        words = shlex.split(stage.strip(), posix=False)
        value = _call(words, ctx, value, has_pipe=not first)
        first = False
    return value


def render(template: str, values: dict, release: str = "rel", namespace: str = "ns") -> str:
    ctx = {"Values": values, "Release": {"Name": release, "Namespace": namespace}}
    out: list[str] = []
    stack: list[bool] = []
    pos = 0
    trim_next = False
    for m in TAG.finditer(template):
        text = template[pos:m.start()]
        lead, ltrim, expr, rtrim = m.group(1), m.group(2), m.group(3), m.group(4)
        if trim_next:
            text = text.lstrip()
        if not ltrim:
            text += lead
        active = all(stack)
        if active:
            out.append(text)
        if expr.startswith("if "):
            stack.append(bool(_eval(expr[3:], ctx)) and active)
        elif expr == "end":
            if not stack:
                raise RenderError("end sans if")
            stack.pop()
        elif expr.startswith(("else", "range", "with", "define", "include", "template")):
            raise RenderError(f"construction non prise en charge : {expr}")
        elif active:
            value = _eval(expr, ctx)
            out.append("" if value is None else str(value))
        trim_next = bool(rtrim)
        pos = m.end()
    rest = template[pos:]
    out.append(rest.lstrip() if trim_next else rest)
    if stack:
        raise RenderError("if sans end")
    return "".join(out)


def merge(base: dict, extra: dict) -> dict:
    out = dict(base)
    for k, v in extra.items():
        out[k] = merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def set_path(values: dict, path: str, value: Any) -> dict:
    out = merge(values, {})
    node = out
    parts = path.split(".")
    for part in parts[:-1]:
        node[part] = dict(node.get(part) or {})
        node = node[part]
    node[parts[-1]] = value
    return out


def render_chart(files: dict[str, str], chart: str, values: dict, release: str = "rel") -> list[dict]:
    docs: list[dict] = []
    for rel, text in sorted(files.items()):
        if rel.startswith(f"{chart}/templates/"):
            rendered = render(text, values, release)
            docs += [d for d in yaml.safe_load_all(rendered) if d]
    return docs
