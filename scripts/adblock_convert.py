#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 clash.yaml 里 target=REJECT 的去广告规则集，统一转成 sing-box rule-set source JSON。
源 & 各自语义：
  1) AdvertisingLite_Domain.yaml (blackmatrix7)  : Clash domain yaml, 混合裸域(exact)+ '+.'(suffix)
  2) adhosts.yaml (yishisanren)                  : Clash payload 纯裸 host  -> suffix
  3) 10007.yaml   (yishisanren)                  : Clash payload 纯裸 host  -> suffix
  4) Block.list   (liandu2024)                   : Clash classical, DOMAIN-SUFFIX 等 -> 按类型
  5) anti-AD domains.txt                         : 纯裸域, anti-AD 语义=suffix -> suffix
输出:
  rules[0].domain         (精确匹配集合)
  rules[0].domain_suffix  (后缀匹配集合, 含自身及所有子域)
去重: 若某域已在 suffix 集合, 则从 exact 集合剔除(suffix 已覆盖)。
"""
import sys, json, re

def clean(d):
    d = d.strip().strip("'\"").strip().lower().rstrip('.')
    # 去掉可能的前导 * . 空
    if d.startswith('*.'):
        d = d[2:]
    if not d or d.startswith('#'):
        return None
    # 合法域名字符校验(允许 xn-- punycode 与中划线)
    if not re.match(r'^[a-z0-9]([a-z0-9\-\.]*[a-z0-9])?$', d):
        return None
    if '.' not in d:
        return None
    return d

exact = set()
suffix = set()

def add_suffix(d):
    d = clean(d)
    if d: suffix.add(d)

def add_exact(d):
    d = clean(d)
    if d: exact.add(d)

# ---- 1) AdvertisingLite: 逐行, '+.' -> suffix, 裸域 -> exact ----
for line in open('advlite.yaml', encoding='utf-8', errors='ignore'):
    m = re.search(r"-\s*'?\"?([^'\"\s]+)'?\"?\s*$", line)
    if not m: continue
    v = m.group(1)
    if v in ('payload:',): continue
    if v.startswith('+.'):
        add_suffix(v[2:])
    elif v.startswith('.'):
        add_suffix(v[1:])
    elif '.' in v and not v.startswith('#'):
        add_exact(v)

# ---- 2,3) adhosts / 10007: payload 纯裸 host -> suffix ----
for fn in ('adhosts.yaml', 'adhosts10007.yaml'):
    for line in open(fn, encoding='utf-8', errors='ignore'):
        m = re.search(r"-\s*'?\"?([^'\"\s]+)'?\"?\s*$", line)
        if m and m.group(1) != 'payload:':
            add_suffix(m.group(1))

# ---- 4) Block.list: DOMAIN-SUFFIX,x / DOMAIN,x / DOMAIN-KEYWORD(跳过) ----
for line in open('block.list', encoding='utf-8', errors='ignore'):
    line = line.strip()
    if not line or line.startswith('#'): continue
    parts = [p.strip() for p in line.split(',')]
    if len(parts) < 2: 
        # 可能是裸域
        add_suffix(line); continue
    t, val = parts[0].upper(), parts[1]
    if t == 'DOMAIN-SUFFIX': add_suffix(val)
    elif t == 'DOMAIN': add_exact(val)
    # DOMAIN-KEYWORD / IP-CIDR 等广告拦截罕见, 跳过(sing-box domain rule 不支持 keyword 于同集)

# ---- 5) anti-AD domains.txt: 裸域 -> suffix ----
for line in open('antiad-domains.txt', encoding='utf-8', errors='ignore'):
    line = line.strip()
    if not line or line.startswith('#'): continue
    add_suffix(line)

# ---- 去重: suffix 覆盖优先, 从 exact 剔除已被 suffix 命中的 ----
def covered_by_suffix(d):
    # d 或其任一父域在 suffix 集合
    parts = d.split('.')
    for i in range(len(parts)):
        cand = '.'.join(parts[i:])
        if cand in suffix:
            return True
    return False

exact_final = sorted(d for d in exact if not covered_by_suffix(d))
suffix_final = sorted(suffix)

ruleset = {
    "version": 3,
    "rules": [
        {
            "domain": exact_final,
            "domain_suffix": suffix_final
        }
    ]
}

with open('ad-reject.json', 'w', encoding='utf-8') as f:
    json.dump(ruleset, f, ensure_ascii=False, indent=None, separators=(',', ':'))

# 明文合并域名清单(便于人工核对 / 其他客户端复用): suffix 加前缀 '.' 表示含子域
with open('domains.txt', 'w', encoding='utf-8') as f:
    f.write("# Momcozy/yishisanren merged ad-reject domain list\n")
    f.write("# sources: anti-AD, AdvertisingLite(blackmatrix7), adhosts, adhosts-10007, Block(liandu2024)\n")
    f.write(f"# exact={len(exact_final)}  suffix={len(suffix_final)}\n")
    for d in exact_final: f.write(d+'\n')
    for d in suffix_final: f.write('.'+d+'\n')

print(f"exact(domain)        = {len(exact_final)}")
print(f"suffix(domain_suffix)= {len(suffix_final)}")
print(f"total unique         = {len(exact_final)+len(suffix_final)}")
