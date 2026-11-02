#!/usr/bin/env python3
"""Convert Quantumult X rewrite snippets into Loon plugins.

Usage: qx2loon.py [sources.json]   (default: loon/sources.json)

For every entry in sources.json this fetches the upstream ``.snippet``, writes
``loon/<id>.plugin`` and mirrors every script the snippet references into
``loon/scripts/`` wrapped by ``loon/compat/qx-compat.js``, so QX-only APIs
($prefs, $notify, echo responses, ``statusCode``) keep working under Loon.
Plugins point at the mirrored copies, never at the upstream scripts.

Anything the converter does not understand raises instead of being dropped,
so an upstream format change fails the build rather than shipping a plugin
that silently lost rules.
"""
import json
import os
import re
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOON_DIR = os.path.join(ROOT, "loon")
SCRIPTS_DIR = os.path.join(LOON_DIR, "scripts")
COMPAT_PATH = os.path.join(LOON_DIR, "compat", "qx-compat.js")
SCRIPT_URL_BASE = "https://raw.githubusercontent.com/yishisanren/proxy-rulesets/main/loon/scripts/"
SCRIPT_MARKER = "/*__QX_SCRIPT__*/"

# QX filter type -> Loon rule type
RULE_TYPES = {
    "host": "DOMAIN",
    "host-suffix": "DOMAIN-SUFFIX",
    "host-keyword": "DOMAIN-KEYWORD",
    "ip-cidr": "IP-CIDR",
    "ip6-cidr": "IP-CIDR6",
}
POLICIES = {"reject": "REJECT", "direct": "DIRECT", "proxy": "PROXY"}
# QX rewrite action -> Loon [Rewrite] action (the documented Loon spellings)
REWRITE_ACTIONS = {
    "reject": "reject",
    "reject-200": "reject-200",
    "reject-img": "reject-img",
    "reject-dict": "reject-dict",
    "reject-array": "reject-array",
}
REDIRECT_ACTIONS = {"302", "307"}
# QX script action -> (Loon script type, requires-body)
SCRIPT_ACTIONS = {
    "script-request-header": ("http-request", False),
    "script-request-body": ("http-request", True),
    "script-response-header": ("http-response", False),
    "script-response-body": ("http-response", True),
    # Echo scripts answer the request themselves; qx-compat.js reshapes
    # their QX return value into Loon's {response: {...}}.
    "script-echo-response": ("http-request", False),
    "script-analyze-echo-response": ("http-request", True),
}


class ConvertError(ValueError):
    pass


def split_header_pattern(pattern):
    """QX ``url-and-header`` regex -> (URL regex, header regex).

    QX matches these against the URL followed by ``\\r\\n`` and the request
    headers. Loon script rules only see the URL, so the URL half is kept and
    the header half is returned for the caller to account for.
    """
    url, sep, header = pattern.partition(r"\r\n")
    url = re.sub(r"\(\?[a-z]+\)\s*$", "", url).strip()
    if not sep or not header.strip() or not re.fullmatch(r"\S+", url):
        raise ConvertError(f"unsupported url-and-header pattern: {pattern}")
    return url, header.strip()


def wildcard_rule(pattern):
    """QX host-wildcard -> Loon rule body.

    Loon documents no wildcard rule type, but does document AND rules, so
    ``mquic-*.meituan.com`` becomes keyword ``mquic-`` AND suffix
    ``meituan.com``. Only that ``<literal>*.<suffix>`` shape is accepted.
    """
    m = re.fullmatch(r"([^*?]*)\*\.([^*?]+)", pattern)
    if not m:
        raise ConvertError(f"unsupported host-wildcard pattern: {pattern}")
    prefix, suffix = m.groups()
    if not prefix:
        return f"DOMAIN-SUFFIX,{suffix}"
    return f"AND,((DOMAIN-KEYWORD,{prefix}),(DOMAIN-SUFFIX,{suffix}))"


def convert_rule(line):
    parts = [p.strip() for p in line.split(",")]
    if len(parts) < 3:
        raise ConvertError(f"malformed filter line: {line}")
    qx_type, value, policy = parts[0].lower(), parts[1], parts[2].lower()
    if policy not in POLICIES:
        raise ConvertError(f"unsupported policy in: {line}")
    if qx_type == "host-wildcard":
        body = wildcard_rule(value)
    elif qx_type in RULE_TYPES:
        body = f"{RULE_TYPES[qx_type]},{value}"
    else:
        raise ConvertError(f"unsupported filter type in: {line}")
    rule = f"{body},{POLICIES[policy]}"
    if qx_type in ("ip-cidr", "ip6-cidr"):
        rule += ",no-resolve"
    return rule


def parse_snippet(text):
    """Split a QX snippet into meta, rules, rewrites, scripts and hostnames."""
    snippet = {"meta": {}, "rules": [], "rewrites": [], "scripts": [], "hostnames": []}
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#!"):
            key, _, value = line[2:].partition("=")
            snippet["meta"][key.strip().lower()] = value.strip()
            continue
        if line.startswith(("#", ";", "//")):
            continue
        if re.match(r"hostname\s*=", line, re.I):
            hosts = line.split("=", 1)[1]
            snippet["hostnames"] += [h.strip() for h in hosts.split(",") if h.strip()]
            continue
        if re.match(r"(host|host-suffix|host-keyword|host-wildcard|ip-cidr|ip6-cidr)\s*,", line, re.I):
            snippet["rules"].append(convert_rule(line))
            continue
        tokens = line.split()
        if "url-and-header" in tokens:
            i = tokens.index("url-and-header")
            pattern, header = split_header_pattern(" ".join(tokens[:i]))
            rest = tokens[i + 1:]
            if len(rest) != 2 or rest[0] not in SCRIPT_ACTIONS:
                raise ConvertError(f"unsupported url-and-header rewrite: {line}")
            snippet["scripts"].append({"pattern": pattern, "action": rest[0], "url": rest[1], "header": header})
            continue
        if len(tokens) < 3 or tokens[1] != "url":
            raise ConvertError(f"unrecognised line: {line}")
        pattern, action = tokens[0], tokens[2]
        if action in REWRITE_ACTIONS and len(tokens) == 3:
            snippet["rewrites"].append(f"{pattern} {REWRITE_ACTIONS[action]}")
        elif action in REDIRECT_ACTIONS and len(tokens) == 4:
            snippet["rewrites"].append(f"{pattern} {action} {tokens[3]}")
        elif action in SCRIPT_ACTIONS and len(tokens) == 4:
            snippet["scripts"].append({"pattern": pattern, "action": action, "url": tokens[3]})
        else:
            raise ConvertError(f"unsupported rewrite: {line}")
    return snippet


def script_name(url):
    name = url.rstrip("/").rsplit("/", 1)[-1]
    if not re.fullmatch(r"[A-Za-z0-9._-]+\.js", name):
        raise ConvertError(f"unexpected script url: {url}")
    return name


def render_plugin(source, snippet, binary_scripts=frozenset()):
    """Render a Loon plugin.

    ``binary_scripts`` names scripts that read QX's ``bodyBytes``; their body
    scripts run with Loon's ``binary-body-mode`` so binary payloads arrive
    intact (qx-compat.js still hands them a decoded ``body`` as well).
    """
    meta = snippet["meta"]
    snippet_file = source["snippet"].rsplit("/", 1)[-1]
    origin = f"由 Quantumult X 规则 {snippet_file} 自动转换"
    if meta.get("update"):
        origin += f"，上游更新于 {meta['update']}"
    desc = f"{meta['desc']}（{origin}）" if meta.get("desc") else origin + "。"

    out = [
        f"#!name = {meta.get('name') or source['id']}",
        f"#!desc = {desc}",
        f"#!author = {meta.get('author', 'unknown')}",
        f"#!homepage = {source.get('homepage', source['snippet'])}",
        "",
    ]
    if snippet["rules"]:
        out += ["[Rule]", *snippet["rules"], ""]
    if snippet["rewrites"]:
        out += ["[Rewrite]", *snippet["rewrites"], ""]

    skipped = set(source.get("skip_request_body_scripts", []))
    header_ok = set(source.get("header_match_in_script", []))
    script_lines = []
    counts = {}
    for s in snippet["scripts"]:
        name = script_name(s["url"])
        if s["action"] == "script-request-body" and name in skipped:
            continue
        if s.get("header") and name not in header_ok:
            raise ConvertError(
                f"{s['pattern']} also matches headers ({s['header']}), which Loon cannot; "
                f"list {name} in header_match_in_script only if the script checks them itself"
            )
        loon_type, requires_body = SCRIPT_ACTIONS[s["action"]]
        counts[name] = counts.get(name, 0) + 1
        tag = f"{source['id']}-{name[:-3]}-{counts[name]}"
        opts = [f"script-path={SCRIPT_URL_BASE}{name}"]
        if requires_body:
            opts.append("requires-body=true")
            if name in binary_scripts:
                opts.append("binary-body-mode=true")
        opts.append(f"tag={tag}")
        script_lines.append(f"{loon_type} {s['pattern']} {', '.join(opts)}")
    if script_lines:
        out += ["[Script]", *script_lines, ""]
    if snippet["hostnames"]:
        out += ["[MITM]", "hostname = " + ", ".join(snippet["hostnames"]), ""]
    return "\n".join(out)


def wrap_script(template, source_url, code):
    if SCRIPT_MARKER not in template:
        raise ConvertError("compat template lost its script marker")
    head, tail = template.split(SCRIPT_MARKER)
    return head.replace("__QX_SOURCE_URL__", source_url) + code.rstrip() + "\n" + tail


def fetch(url, attempts=4):
    for i in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return r.read().decode("utf-8")
        except OSError:
            if i == attempts - 1:
                raise
            time.sleep(2 ** (i + 1))


def build(sources, fetch=fetch):
    """Return {repo-relative path: content} for every generated file."""
    with open(COMPAT_PATH, encoding="utf-8") as f:
        template = f.read()
    files = {}
    script_urls = {}
    parsed = []
    for source in sources:
        snippet = parse_snippet(fetch(source["snippet"]))
        parsed.append((source, snippet))
        for s in snippet["scripts"]:
            name = script_name(s["url"])
            if script_urls.setdefault(name, s["url"]) != s["url"]:
                raise ConvertError(f"two upstream scripts share the name {name}")
    binary_scripts = set()
    for name, url in script_urls.items():
        code = fetch(url)
        if re.search(r"\bbodyBytes\b", code):
            binary_scripts.add(name)
        files[f"loon/scripts/{name}"] = wrap_script(template, url, code)
    for source, snippet in parsed:
        files[f"loon/{source['id']}.plugin"] = render_plugin(source, snippet, binary_scripts)
    return files


def main(argv):
    config = argv[1] if len(argv) > 1 else os.path.join(LOON_DIR, "sources.json")
    with open(config, encoding="utf-8") as f:
        sources = json.load(f)["plugins"]
    files = build(sources)
    os.makedirs(SCRIPTS_DIR, exist_ok=True)
    # Drop mirrored scripts no plugin references any more.
    for name in os.listdir(SCRIPTS_DIR):
        if f"loon/scripts/{name}" not in files:
            os.remove(os.path.join(SCRIPTS_DIR, name))
    for rel, content in files.items():
        with open(os.path.join(ROOT, rel), "w", encoding="utf-8") as f:
            f.write(content)
        print(f"wrote {rel}")


if __name__ == "__main__":
    main(sys.argv)
