# proxy-rulesets

个人自用代理规则集合仓库 —— 覆盖多种代理客户端的**去广告**与**分流**规则。
由 [`karing-ruleset`](https://github.com/yishisanren/karing-ruleset) 和 [`loon-rules`](https://github.com/yishisanren/loon-rules) 两个旧仓库整合而来。

## 目录结构

```
proxy-rulesets/
├── adblock/          去广告规则集（5 源合并去重，145,457 条）
│   ├── ad-reject.srs            SRS binary v2 — Karing / 新版 sing-box
│   ├── ad-reject.json           source v3     — 源码，可 review / 二次编译
│   ├── ad-reject-nekobox.srs    SRS binary v1 — NekoBox / NekoRay / 旧内核
│   ├── ad-reject-nekobox.json   source v1     — 最保险，任何 core 都吃
│   └── domains.txt              明文合并清单（`.`前缀=后缀匹配含子域）
├── broker/           券商分流规则（富途 + 老虎证券，走香港节点）
│   ├── broker-hk.list           Loon / Surge / Clash 源格式
│   ├── broker-hk.srs            SRS binary v1
│   └── broker-hk.json           source v1
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

### 📈 券商分流 broker（出站选你的**香港节点**，不是 REJECT）

| 客户端 | 格式 | 订阅地址（拼在上述前缀后） |
|---|---|---|
| **NekoBox / NekoRay** | Binary | `broker/broker-hk.srs` |
| NekoBox（兜底）/ homeproxy | Source | `broker/broker-hk.json` |
| **Loon / Surge / Clash** | 原生 list | `broker/broker-hk.list` |

**完整 URL 示例**（NekoBox 去广告二进制版）：
```
https://raw.githubusercontent.com/yishisanren/proxy-rulesets/main/adblock/ad-reject-nekobox.srs
```

---

## ℹ️ 为什么分 v1 / v2 两种 .srs

`.srs` 是 sing-box 编译后的二进制规则集，有格式版本号（魔数第 4 字节）：

- **Karing** 及新版 sing-box 内核吃 **SRS v2**（`53 52 53 02`）。
- **NekoBox / NekoRay** 内置的 sing-box core 通常偏旧，只吃 **SRS v1**（`53 52 53 01`）；喂 v2 会加载失败。

所以去广告规则集提供两个二进制版本，按客户端选对应的那个。本仓库的规则只含 `domain` / `domain_suffix`，SRS v1 无损支持，两版数据完全一致。

> 若二进制版仍加载不了（个别更旧的魔改 core），改用 **Source 格式的 `.json`**，纯文本解析不受二进制版本限制。

---

## 数据规模

| 规则集 | 精确 domain | 后缀 domain_suffix | 合计 |
|---|---|---|---|
| adblock | 13,959 | 131,498 | **145,457** |
| broker-hk | 1 | 14 | **15** |

### 去广告上游来源（5 源合并去重）

| 源 | 原格式 | 语义处理 |
|---|---|---|
| [anti-AD](https://anti-ad.net/) | 裸域列表 | → domain_suffix |
| [AdvertisingLite](https://github.com/blackmatrix7/ios_rule_script)（blackmatrix7） | Clash domain yaml | `+.`→suffix，裸域→exact |
| [adhosts](https://github.com/yishisanren/adhost) + 10007 | Clash payload | → domain_suffix |
| [Block](https://github.com/liandu2024/clash)（liandu2024） | Clash classical | 按 DOMAIN-SUFFIX / DOMAIN 类型 |

---

## 重建

```bash
# 需要本地有 sing-box 可执行文件在 PATH
bash build.sh
```

- **broker** 规则会由 GitHub Actions 在 `broker/*.list` 改动时自动重建（`.json` + `.srs`）。
- **adblock** 规则依赖 5 个外部上游源、数据量大，不在每次 push 时自动拉取；需要刷新时本地跑 `bash build.sh`。

编译后已用 `sing-box rule-set match -f binary` 做闭环验证：广告域（含子域）全部命中，常用正常域（github/apple/google/momcozy 等）零误伤；券商域走分流、相似域（futu.com）不误命中。

---
自用配置，按各上游许可分发。规则数据版权归各上游项目所有。
