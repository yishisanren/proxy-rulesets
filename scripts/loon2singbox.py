#!/usr/bin/env python3
"""Convert a Loon/Surge/Clash-style .list rule file into a sing-box
rule-set: a source .json AND a compiled binary .srs.

Usage: loon2singbox.py <input.list> <output.json> [output.srs]

Output format notes
-------------------
- The source JSON is emitted as **version 1**. Rule-set schema version 1
  already covers every matcher this converter produces (domain /
  domain_suffix / domain_keyword / domain_regex / ip_cidr), and v1 is the
  most widely compatible: older sing-box cores embedded in clients like
  **NekoBox / NekoRay** reject the newer SRS binary v2/v3 produced from a
  version 2/3 source, but accept v1. Emitting v1 keeps the generated
  ``.srs`` loadable on those older cores while remaining fully valid for
  current sing-box.
- When an output .srs path is given (or ``sing-box`` is on PATH), the
  script also compiles the source JSON to a binary ``.srs`` so clients
  that want the binary "remote / binary" ruleset form can subscribe to it.

Each matcher type is emitted as its own rule object so the rule-set
matches with OR semantics across types (sing-box AND-combines different
fields within a single rule object).
"""
import json
import os
import shutil
import subprocess
import sys

# Loon rule type -> sing-box source rule-set field
TYPE_MAP = {
    "DOMAIN": "domain",
    "DOMAIN-SUFFIX": "domain_suffix",
    "DOMAIN-KEYWORD": "domain_keyword",
    "DOMAIN-WILDCARD": "domain_regex",  # best-effort
    "IP-CIDR": "ip_cidr",
    "IP-CIDR6": "ip_cidr",
}
# Field emission order (stable, readable output)
FIELD_ORDER = ["domain", "domain_suffix", "domain_keyword", "domain_regex", "ip_cidr"]


def convert(in_path, out_path, srs_path=None):
    buckets = {f: [] for f in FIELD_ORDER}
    seen = {f: set() for f in FIELD_ORDER}
    skipped = []

    with open(in_path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or line.startswith(";"):
                continue
            parts = [p.strip() for p in line.split(",")]
            rtype = parts[0].upper()
            if rtype not in TYPE_MAP or len(parts) < 2:
                skipped.append(line)
                continue
            field = TYPE_MAP[rtype]
            value = parts[1]
            if not value:
                continue
            if value not in seen[field]:
                seen[field].add(value)
                buckets[field].append(value)

    rules = []
    for field in FIELD_ORDER:
        if buckets[field]:
            rules.append({field: buckets[field]})

    # version 1: widest client compatibility (see module docstring).
    out = {"version": 1, "rules": rules}
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    total = sum(len(v) for v in buckets.values())
    print(f"{in_path} -> {out_path}: {total} entries, {len(rules)} rule group(s)")
    if skipped:
        print(f"  skipped {len(skipped)} unsupported line(s):", file=sys.stderr)
        for s in skipped:
            print(f"    {s}", file=sys.stderr)

    # Optionally compile to a binary .srs for clients that subscribe to the
    # binary ruleset form (NekoBox "remote / binary", etc.).
    if srs_path is None:
        # Default: sibling <name>.srs next to the json, only if sing-box exists.
        if shutil.which("sing-box"):
            srs_path = os.path.splitext(out_path)[0] + ".srs"
    if srs_path:
        sb = shutil.which("sing-box") or "sing-box"
        try:
            subprocess.run(
                [sb, "rule-set", "compile", "--output", srs_path, out_path],
                check=True,
            )
            print(f"  compiled -> {srs_path} (SRS binary v1)")
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            print(f"  skipped .srs compile ({exc})", file=sys.stderr)


if __name__ == "__main__":
    if len(sys.argv) not in (3, 4):
        print(__doc__)
        sys.exit(1)
    convert(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) == 4 else None)
