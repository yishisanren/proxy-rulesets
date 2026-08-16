#!/usr/bin/env bash
# 一键重建全部代理规则集（去广告 adblock + 券商分流 broker + AI）
# 产物：
#   adblock/ad-reject.srs (v2, Karing/新版 sing-box)   + ad-reject.json (v3 source)
#   adblock/ad-reject-nekobox.srs (v1, NekoBox)         + ad-reject-nekobox.json (v1 source)
#   adblock/domains.txt (明文核对清单)
#   broker/broker-hk.srs (v1) + broker/broker-hk-karing.srs (v2)
#   ai/ai-all.srs (v1) + ai/ai-all-karing.srs (v2)
set -euo pipefail
cd "$(dirname "$0")"

# Resolve sing-box to an absolute path up front so every sub-shell (incl. the
# _match verifier) sees it regardless of PATH inheritance. Fail loudly if absent.
SB="${SB:-sing-box}"
if ! command -v "$SB" >/dev/null 2>&1; then
  echo "ERROR: sing-box not found (SB=$SB). Install it or set SB=/abs/path/to/sing-box" >&2
  exit 127
fi
SB="$(command -v "$SB")"
echo "using sing-box: $SB"

echo "############ 1/3  去广告规则集 (adblock) ############"
echo "==> 拉取上游 4 源"
TMP=$(mktemp -d)
curl -sL --max-time 60 "https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Clash/AdvertisingLite/AdvertisingLite_Domain.yaml" -o "$TMP/advlite.yaml"
# yishisanren/adhost 仓库已删除(2026-08-16 404)——其内容本就来自 lingeringsound/10007，已由下方 all10007.hosts 覆盖
curl -sL --max-time 60 "https://raw.githubusercontent.com/liandu2024/clash/refs/heads/main/list/Block.list" -o "$TMP/block.list"
curl -sL --max-time 60 "https://anti-ad.net/domains.txt" -o "$TMP/antiad-domains.txt"
curl -sL --max-time 60 "https://raw.githubusercontent.com/lingeringsound/10007/main/all" -o "$TMP/all10007.hosts"

echo "==> 转换合并去重 -> adblock/ad-reject.json (v3) + domains.txt"
( cd "$TMP" && python3 "$OLDPWD/scripts/adblock_convert.py" )
mv "$TMP/ad-reject.json" adblock/ad-reject.json
mv "$TMP/domains.txt"    adblock/domains.txt
rm -rf "$TMP"

echo "==> 派生 Clash/mihomo 版 (behavior:domain yaml)"
python3 scripts/adblock_clash_export.py

echo "==> 编译 Karing 版 .srs（随当前 sing-box 内核，通常 SRS v2）"
"$SB" rule-set compile --output adblock/ad-reject.srs adblock/ad-reject.json

echo "==> 生成 NekoBox 兼容版（SRS binary v1，兼容旧内核）"
python3 -c "import json; d=json.load(open('adblock/ad-reject.json')); d['version']=1; json.dump(d, open('adblock/ad-reject-nekobox.json','w'), ensure_ascii=False, separators=(',',':'))"
"$SB" rule-set compile --output adblock/ad-reject-nekobox.srs adblock/ad-reject-nekobox.json

echo "############ 2/3  券商分流 (broker) ############"
echo "==> broker/*.list -> NekoBox v1 + Karing v2"
shopt -s nullglob
export SB   # let loon2singbox.py reuse the exact same sing-box binary we resolved
for f in broker/*.list; do
  name="$(basename "${f%.list}")"
  # Pass the .srs path explicitly so the binary rule-set is ALWAYS rebuilt,
  # regardless of whether sing-box happens to be on PATH in this environment.
  python3 scripts/loon2singbox.py "$f" "broker/${name}.json" "broker/${name}.srs"
  python3 scripts/set_ruleset_version.py \
    "broker/${name}.json" "broker/${name}-karing.json" 2
  "$SB" rule-set compile \
    --output "broker/${name}-karing.srs" "broker/${name}-karing.json"
done

echo "############ 3/3  AI 聚合分流 ############"
echo "==> ai/ai-all.json -> Karing source json(v2) + binary srs(v2)"
python3 scripts/set_ruleset_version.py ai/ai-all.json ai/ai-all-karing.json 2
"$SB" rule-set compile --output ai/ai-all-karing.srs ai/ai-all-karing.json

echo "############ 闭环校验 ############"
# NOTE: `sing-box rule-set match` prints the match result to STDERR, not stdout.
# Merge stderr into stdout (2>&1) before grepping, else every check is a false MISS.
# IMPORTANT: do NOT use `grep -q` here. Under `set -o pipefail`, grep -q closes the
# pipe on first match, sing-box then dies with SIGPIPE (rc=141), and pipefail turns
# that into a false MISS for domains that actually matched. Capture full output and
# test it with a non-short-circuiting matcher instead.
_match () {
  local out
  out="$("$SB" rule-set match -f binary "$1" "$2" 2>&1)"
  [[ "$out" == *"match rules"* ]]
}
echo "-- adblock Karing 版 --"
for d in doubleclick.net googlesyndication.com; do _match adblock/ad-reject.srs "$d" && echo "  [hit ] $d" || echo "  [MISS] $d!"; done
for d in github.com momcozy.com;             do _match adblock/ad-reject.srs "$d" && echo "  [FAIL] $d 误伤!" || echo "  [pass] $d 不命中"; done
echo "-- broker Karing 版 --"
for d in futunn.com laohu8.com; do _match broker/broker-hk-karing.srs "$d" && echo "  [hit ] $d" || echo "  [MISS] $d!"; done
for d in google.com;            do _match broker/broker-hk-karing.srs "$d" && echo "  [FAIL] $d 误命中!" || echo "  [pass] $d 不命中"; done
echo "-- AI Karing 版 --"
for d in chatgpt.com anthropic.com; do _match ai/ai-all-karing.srs "$d" && echo "  [hit ] $d" || echo "  [MISS] $d!"; done
for d in momcozy.com;                do _match ai/ai-all-karing.srs "$d" && echo "  [FAIL] $d 误命中!" || echo "  [pass] $d 不命中"; done

echo "==> 全部完成"
du -h adblock/*.srs broker/*.srs ai/*.srs
