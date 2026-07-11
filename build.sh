#!/usr/bin/env bash
# 一键重建全部代理规则集（去广告 adblock + 券商分流 broker）
# 产物：
#   adblock/ad-reject.srs (v2, Karing/新版 sing-box)   + ad-reject.json (v3 source)
#   adblock/ad-reject-nekobox.srs (v1, NekoBox)         + ad-reject-nekobox.json (v1 source)
#   adblock/domains.txt (明文核对清单)
#   broker/broker-hk.srs (v1) + broker/broker-hk.json (v1 source)  <- 由 CI 自动生成
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

echo "############ 1/2  去广告规则集 (adblock) ############"
echo "==> 拉取上游 6 源"
TMP=$(mktemp -d)
curl -sL --max-time 60 "https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Clash/AdvertisingLite/AdvertisingLite_Domain.yaml" -o "$TMP/advlite.yaml"
curl -sL --max-time 60 "https://raw.githubusercontent.com/yishisanren/adhost/refs/heads/main/adhosts.yaml" -o "$TMP/adhosts.yaml"
curl -sL --max-time 60 "https://raw.githubusercontent.com/yishisanren/adhost/refs/heads/main/10007.yaml" -o "$TMP/adhosts10007.yaml"
curl -sL --max-time 60 "https://raw.githubusercontent.com/liandu2024/clash/refs/heads/main/list/Block.list" -o "$TMP/block.list"
curl -sL --max-time 60 "https://anti-ad.net/domains.txt" -o "$TMP/antiad-domains.txt"
curl -sL --max-time 60 "https://raw.githubusercontent.com/lingeringsound/10007/main/all" -o "$TMP/all10007.hosts"

echo "==> 转换合并去重 -> adblock/ad-reject.json (v3) + domains.txt"
( cd "$TMP" && python3 "$OLDPWD/scripts/adblock_convert.py" )
mv "$TMP/ad-reject.json" adblock/ad-reject.json
mv "$TMP/domains.txt"    adblock/domains.txt
rm -rf "$TMP"

echo "==> 编译 Karing 版 .srs（随当前 sing-box 内核，通常 SRS v2）"
"$SB" rule-set compile --output adblock/ad-reject.srs adblock/ad-reject.json

echo "==> 生成 NekoBox 兼容版（SRS binary v1，兼容旧内核）"
python3 -c "import json; d=json.load(open('adblock/ad-reject.json')); d['version']=1; json.dump(d, open('adblock/ad-reject-nekobox.json','w'), ensure_ascii=False, separators=(',',':'))"
"$SB" rule-set compile --output adblock/ad-reject-nekobox.srs adblock/ad-reject-nekobox.json

echo "############ 2/2  券商分流 (broker) ############"
echo "==> broker/*.list -> source json(v1) + binary srs(v1)"
shopt -s nullglob
for f in broker/*.list; do
  name="$(basename "${f%.list}")"
  python3 scripts/loon2singbox.py "$f" "broker/${name}.json"
done

echo "############ 闭环校验 ############"
# NOTE: `sing-box rule-set match` prints the match result to STDERR, not stdout.
# Merge stderr into stdout (2>&1) before grep, else every check is a false MISS.
_match () { "$SB" rule-set match -f binary "$1" "$2" 2>&1 | grep -q 'match rules'; }
echo "-- adblock NekoBox 版 --"
for d in doubleclick.net googlesyndication.com; do _match adblock/ad-reject-nekobox.srs "$d" && echo "  [hit ] $d" || echo "  [MISS] $d!"; done
for d in github.com momcozy.com;             do _match adblock/ad-reject-nekobox.srs "$d" && echo "  [FAIL] $d 误伤!" || echo "  [pass] $d 不命中"; done
echo "-- broker 版 --"
for d in futunn.com laohu8.com; do _match broker/broker-hk.srs "$d" && echo "  [hit ] $d" || echo "  [MISS] $d!"; done
for d in google.com;            do _match broker/broker-hk.srs "$d" && echo "  [FAIL] $d 误命中!" || echo "  [pass] $d 不命中"; done

echo "==> 全部完成"
ls -lh adblock/*.srs broker/*.srs
