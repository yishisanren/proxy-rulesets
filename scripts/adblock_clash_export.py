#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 canonical adblock/ad-reject.json 确定性派生 Clash/mihomo 规则集
输出 adblock/ad-reject-clash.yaml (behavior: domain, format: yaml)
语义映射: domain -> 裸域(exact); domain_suffix -> '+.域'(含自身及子域)
不拉任何上游, 只读已入库 JSON, 保证与 .srs 产物同源同代。
"""
import json, sys, os

os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
d = json.load(open('adblock/ad-reject.json', encoding='utf-8'))
r = d['rules'][0]
def norm(v):
    return [v] if isinstance(v, str) else (v or [])
exact = norm(r.get('domain'))
suffix = norm(r.get('domain_suffix'))
with open('adblock/ad-reject-clash.yaml', 'w', encoding='utf-8') as f:
    f.write("# Clash/mihomo domain rule-set (behavior: domain, format: yaml)\n")
    f.write("# derived from adblock/ad-reject.json — same sources as ad-reject.srs\n")
    f.write(f"# exact={len(exact)} suffix={len(suffix)}\n")
    f.write("payload:\n")
    for x in exact:
        f.write(f"  - '{x}'\n")
    for s in suffix:
        f.write(f"  - '+.{s}'\n")
print(f"clash yaml: exact={len(exact)} suffix={len(suffix)} total={len(exact)+len(suffix)}")
