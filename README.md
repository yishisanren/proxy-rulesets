# proxy-rulesets

个人自用代理规则集合仓库 —— 覆盖多种代理客户端的**去广告**与**分流**规则。
由 [`karing-ruleset`](https://github.com/yishisanren/karing-ruleset) 和 [`loon-rules`](https://github.com/yishisanren/loon-rules) 两个旧仓库整合而来。

## 目录结构

```
proxy-rulesets/
├── adblock/          去广告规则集（6 源合并去重，147,315 条）
│   ├── ad-reject.srs            SRS binary v2 — Karing / 新版 sing-box
│   ├── ad-reject.json           source v3     — 源码，可 review / 二次编译
│   ├── ad-reject-nekobox.srs    SRS binary v1 — NekoBox / NekoRay / 旧内核
│   ├── ad-reject-nekobox.json   source v1     — 最保险，任何 core 都吃
│   └── domains.txt              明文合并清单（`.`前缀=后缀匹配含子域）
├── broker/           券商分流规则（富途 + 老虎证券，走香港节点）
│   ├── broker-hk-karing.srs     SRS binary v2 — Karing / 新版 sing-box
│   ├── broker-hk-karing.json    source v2
│   ├── broker-hk.srs            SRS binary v1 — NekoBox / NekoRay / 旧内核
│   ├── broker-hk.json           source v1
│   └── broker-hk.list           Loon / Surge / Clash 源格式
├── ai/               AI 聚合规则（7 类服务，630 条）
│   ├── ai-all-karing.srs        SRS binary v2 — Karing / 新版 sing-box
│   ├── ai-all-karing.json       source v2
│   ├── ai-all.srs               SRS binary v1 — NekoBox / NekoRay / 旧内核
│   └── ai-all.json              source v1
├── loon/             Loon 插件（由上游 QX 规则每日自动转换，来源见 sources.json）
│   ├── meituan.plugin           美团 App 净化
│   ├── hellobike.plugin         哈啰 App 净化
│   ├── txsports.plugin          腾讯体育 App 净化
│   ├── hupu.plugin              虎扑 App 净化
│   ├── txvideo.plugin           腾讯视频 App 净化
│   ├── sources/                 自维护的 QX 规则源（上游规则需改动时放这里）
│   ├── scripts/                 插件引用的脚本（上游原脚本 + QX→Loon 兼容层）
│   ├── compat/qx-compat.js      兼容层模板
│   └── sources.json             上游来源清单
├── scripts/          转换脚本
└── build.sh          一键重建全部产物
```

---

## 📡 订阅地址速查表

> 所有地址把 `raw.githubusercontent.com/yishisanren/proxy-rulesets/main/` 作为前缀。
> 国内慢可换 jsDelivr 镜像：`cdn.jsdelivr.net/gh/yishisanren/proxy-rulesets@main/`。

### 🛡️ 去广告 adblock（出站选 REJECT / 拒绝 / block）

| 客户端 | 格式 | 订阅地址（拼在上述前缀后） |
|---|---|---|
| **Karing** / 新版 sing-box | Binary | `adblock/ad-reject.srs` |
| **NekoBox / NekoRay** | Binary | `adblock/ad-reject-nekobox.srs` |
| NekoBox（core 太旧，兜底） | Source | `adblock/ad-reject-nekobox.json` |
| sing-box / homeproxy | Source | `adblock/ad-reject.json` |
| 其它客户端 / 人工核对 | 明文 | `adblock/domains.txt` |

### 🤖 AI 聚合（出站选代理节点）

覆盖 OpenAI / Groq / Gemini / Meta AI / Copilot / Perplexity / Claude。

| 客户端 | 格式 | 订阅地址（拼在上述前缀后） |
|---|---|---|
| **Karing** / 新版 sing-box | Binary | `ai/ai-all-karing.srs` |
| **NekoBox / NekoRay** | Binary | `ai/ai-all.srs` |
| NekoBox（兜底）/ homeproxy | Source | `ai/ai-all.json` |

### 📈 券商分流 broker（出站选你的**香港节点**，不是 REJECT）

| 客户端 | 格式 | 订阅地址（拼在上述前缀后） |
|---|---|---|
| **Karing** / 新版 sing-box | Binary | `broker/broker-hk-karing.srs` |
| **NekoBox / NekoRay** | Binary | `broker/broker-hk.srs` |
| NekoBox（兜底）/ homeproxy | Source | `broker/broker-hk.json` |
| **Loon / Surge / Clash** | 原生 list | `broker/broker-hk.list` |

**完整 URL 示例**（Karing AI 聚合二进制版）：
```
https://raw.githubusercontent.com/yishisanren/proxy-rulesets/main/ai/ai-all-karing.srs
```

券商规则覆盖富途 / moomoo 25 个、老虎 25 个域名后缀，包含根域与子域。
来源包括 [v2fly 富途规则](https://github.com/v2fly/domain-list-community/blob/master/data/futu)、[老虎规则](https://github.com/v2fly/domain-list-community/blob/master/data/itiger) 及两家券商的官方地区站、下载、静态资源和业务站点；具体链接见 `.list` 注释。

`broker-hk` 只定义匹配范围，实际出口由客户端选择，可指定其他地区节点。

富途 App 有相当一部分连接不经过 DNS，直接连内置或下发的腾讯云海外 IP（43.x、101.32.x、119.28.x、124.156.x、129.226.x、170.106.x、49.51.x 等），只靠域名规则匹配不到。
因此 sing-box 产物（`.json` / `.srs`）额外带一条 `package_name` 规则（来自 `broker/broker-hk.packages`），按 Android 包名把两家 App 的全部连接都匹配进来，包括直连 IP：

| App | 包名 |
|---|---|
| 富途牛牛 | `cn.futu.trader.universal` |
| 老虎证券 | `com.tigerbrokers.stock` |

- 包名匹配只在 Android 上的 sing-box 系客户端（Karing、NekoBox、sing-box 官方客户端等）生效，客户端需要能识别连接来源 App（TUN 模式一般可以）；其他平台会忽略这条规则。
- `.list` 只含域名，Loon / Surge / Clash 不受影响。Clash / mihomo 在 Android 上可自行加 `PROCESS-NAME,cn.futu.trader.universal` 等规则。
- 不收录直连 IP：这些 IP 属于腾讯云共享网段，写网段会误伤其他腾讯海外服务，写单个 IP 又会随服务器调度失效。它们都不在 GeoIP CN 中，常见的"国内直连、其余代理"配置也会让它们走代理。
- 规则集要排在 `geosite-cn` / `geoip-cn` 等直连规则之前。域名匹配不代表账户地区或服务权限随之改变。

### 🧩 Loon 插件（App 净化，需开启 MITM 并信任证书）

上游为 [ZenmoFeiShi/Qx](https://github.com/ZenmoFeiShi/Qx) 和 [akaagiao1/quantumult-x-scripts](https://github.com/akaagiao1/quantumult-x-scripts) 的 Quantumult X 规则，
`.github/workflows/loon-plugins.yml` 每天自动拉取并转换。

| 插件 | 订阅地址（拼在上述前缀后） | 一键导入 |
|---|---|---|
| 美团 App 净化 | `loon/meituan.plugin` | [导入 Loon](https://www.nsloon.com/openloon/import?plugin=https%3A%2F%2Fraw.githubusercontent.com%2Fyishisanren%2Fproxy-rulesets%2Fmain%2Floon%2Fmeituan.plugin) |
| 哈啰 App 净化 | `loon/hellobike.plugin` | [导入 Loon](https://www.nsloon.com/openloon/import?plugin=https%3A%2F%2Fraw.githubusercontent.com%2Fyishisanren%2Fproxy-rulesets%2Fmain%2Floon%2Fhellobike.plugin) |
| 腾讯体育 App 净化 | `loon/txsports.plugin` | [导入 Loon](https://www.nsloon.com/openloon/import?plugin=https%3A%2F%2Fraw.githubusercontent.com%2Fyishisanren%2Fproxy-rulesets%2Fmain%2Floon%2Ftxsports.plugin) |
| 虎扑 App 净化 | `loon/hupu.plugin` | [导入 Loon](https://www.nsloon.com/openloon/import?plugin=https%3A%2F%2Fraw.githubusercontent.com%2Fyishisanren%2Fproxy-rulesets%2Fmain%2Floon%2Fhupu.plugin) |
| 腾讯视频 App 净化 | `loon/txvideo.plugin` | [导入 Loon](https://www.nsloon.com/openloon/import?plugin=https%3A%2F%2Fraw.githubusercontent.com%2Fyishisanren%2Fproxy-rulesets%2Fmain%2Floon%2Ftxvideo.plugin) |

> 哈啰插件首次使用：打开哈啰 App 后若收到"已捕获本机动态密钥"通知，重新进入首页和"我的"页面即可生效。
>
> 腾讯体育插件：开屏广告的开关是 App 启动时拉取的配置，装好插件后完全退出腾讯体育、重新打开一两次才会看到开屏广告消失。
>
> 虎扑插件：只处理 `goblin.hupu.com` 的 `interfaceAd/getOther` 接口（v3 / batch，版本号不限），清空返回体里的 `ads` 数组；信息流、开屏等其他广告位不在覆盖范围。规则文件放在 `loon/sources/`，按任意版本号匹配，虎扑升级不会导致失效。
>
> 腾讯视频插件：另外两条 `host` 规则直接 REJECT 广告域名（`iacc.stgw.qq.com`、`tacc.video.qq.com`），不过 MITM，所以断网时这两条也是立即生效的；其余四个接口靠脚本改写。开屏与底部 tap 栏的配置在 App 启动时拉取，装好后完全退出腾讯视频、重开一两次才看得到效果。

---

## ℹ️ 为什么分 v1 / v2 两种 .srs

`.srs` 是 sing-box 编译后的二进制规则集，有格式版本号（魔数第 4 字节）：

- **Karing** 及新版 sing-box 内核使用 **SRS v2**（`53 52 53 02`）。
- **NekoBox / NekoRay** 内置的 sing-box core 通常偏旧，只吃 **SRS v1**（`53 52 53 01`）；喂 v2 会加载失败。

因此每类规则都保留旧内核可用的 v1 产物；Karing 使用明确标注的 v2 产物。本仓库的规则只含 `domain` / `domain_suffix`（broker 另有 `package_name`），v1 与 v2 两版规则数据完全一致。

> 若二进制版仍加载不了（个别更旧的魔改 core），改用 **Source 格式的 `.json`**，纯文本解析不受二进制版本限制。

---

## 数据规模

| 规则集 | 精确 domain | 后缀 domain_suffix | 合计 |
|---|---|---|---|
| adblock | 15,213 | 132,102 | **147,315** |
| broker-hk | 1 | 50 | **51**（另含 2 个 App 包名） |
| AI 聚合 | 29 | 601 | **630** |

### 去广告上游来源（6 源合并去重）

| 源 | 原格式 | 语义处理 |
|---|---|---|
| [anti-AD](https://anti-ad.net/) | 裸域列表 | → domain_suffix |
| [AdvertisingLite](https://github.com/blackmatrix7/ios_rule_script)（blackmatrix7） | Clash domain yaml | `+.`→suffix，裸域→exact |
| [adhosts](https://github.com/yishisanren/adhost) + 10007 | Clash payload | → domain_suffix |
| [Block](https://github.com/liandu2024/clash)（liandu2024） | Clash classical | 按 DOMAIN-SUFFIX / DOMAIN 类型 |
| [lingeringsound/10007](https://github.com/lingeringsound/10007) | hosts | 广告域转 suffix，品牌主域白名单防误伤 |

---

## 重建

```bash
# 需要本地有 sing-box 可执行文件在 PATH
bash build.sh
```

- **broker** 规则会由 GitHub Actions 在 `broker/*.list` 或 `broker/*.packages` 改动时自动重建 v1 与 Karing v2 产物。
- **AI** 的 Karing v2 产物会在 `ai/ai-all.json` 改动时由 GitHub Actions 自动重建。
- **adblock** 规则依赖 6 个外部上游源、数据量大，不在每次 push 时自动拉取；需要刷新时本地跑 `bash build.sh`。

编译后已用 `sing-box rule-set match -f binary` 做闭环验证：广告域（含子域）、AI 服务域、券商域均按预期命中，常用正常域零误伤。

---
自用配置，按各上游许可分发。规则数据版权归各上游项目所有。
