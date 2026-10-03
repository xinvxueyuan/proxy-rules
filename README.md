# proxy-rules

[![build](https://github.com/xinvxueyuan/proxy-rules/actions/workflows/build.yml/badge.svg)](https://github.com/xinvxueyuan/proxy-rules/actions/workflows/build.yml)
[![license](https://img.shields.io/badge/license-GPL--3.0-blue.svg)](LICENSE)
[![pages](https://img.shields.io/badge/docs-GitHub%20Pages-222.svg)](https://xinvxueyuan.github.io/proxy-rules/)
[![last commit](https://img.shields.io/github/last-commit/xinvxueyuan/proxy-rules)](https://github.com/xinvxueyuan/proxy-rules/commits/main)

> 自用分流规则：**一份自持数据**，编译成 **mihomo（Clash.Meta）** 与 **Xray** 两种格式，每日定时构建并发布。

- 📖 **文档与订阅地址**：<https://xinvxueyuan.github.io/proxy-rules/>
- 📦 **产物分支**：[dist](https://github.com/xinvxueyuan/proxy-rules/tree/dist)（单快照，无历史版本）
- ⚙️ **每日构建**：UTC 19:00（北京时间 03:00），也可手动触发

---

## 目录

- [快速开始](#快速开始)
- [订阅地址](#订阅地址)
- [分流模型](#分流模型)
- [规则组](#规则组)
- [九类中国站点保底直连](#九类中国站点保底直连)
- [必读：四个实测确认的坑](#必读四个实测确认的坑)
- [编辑规则](#编辑规则)
- [构建与校验](#构建与校验)
- [目录结构](#目录结构)
- [数据来源与许可证](#数据来源与许可证)
- [常见问题](#常见问题)

---

## 快速开始

### Clash / mihomo

在配置里加 `rule-providers` 与 `rules`（完整片段见
[`examples/clash.yaml`](https://xinvxueyuan.github.io/proxy-rules/examples/clash.yaml)）：

```yaml
rule-providers:
  advert.com:
    type: http
    behavior: domain
    format: yaml
    interval: 86400
    url: https://xinvxueyuan.github.io/proxy-rules/clash/advert.com.yaml
  advert.cn:
    type: http
    behavior: domain
    format: yaml
    interval: 86400
    url: https://xinvxueyuan.github.io/proxy-rules/clash/advert.cn.yaml
  self-proxy:
    type: http
    behavior: domain
    format: yaml
    interval: 86400
    url: https://xinvxueyuan.github.io/proxy-rules/clash/self-proxy.yaml
  site.cn:
    type: http
    behavior: domain
    format: yaml
    interval: 86400
    url: https://xinvxueyuan.github.io/proxy-rules/clash/site.cn.yaml
  self-direct-ip:
    type: http
    behavior: ipcidr
    format: yaml
    interval: 86400
    url: https://xinvxueyuan.github.io/proxy-rules/clash/self-direct-ip.yaml

rules:
  - RULE-SET,advert.com,REJECT
  - RULE-SET,advert.cn,REJECT
  - RULE-SET,self-proxy,PROXY
  - RULE-SET,site.cn,DIRECT
  - RULE-SET,self-direct-ip,DIRECT,no-resolve
  - GEOIP,CN,DIRECT,no-resolve
  - MATCH,PROXY
```

### Xray

**首次部署必须先放一次 dat**（`geodata` 是「配置校验通过后才下载」，不能做首次引导 ——
文件不存在时配置校验会直接失败退出，详见[必读](#必读四个实测确认的坑)）：

```bash
mkdir -p /usr/local/share/xray && cd /usr/local/share/xray

# 自建规则集
curl -fsSLO https://xinvxueyuan.github.io/proxy-rules/xray/self-geosite.dat
curl -fsSLO https://xinvxueyuan.github.io/proxy-rules/xray/self-geoip.dat

# 官方 dat 也要在（geoip:cn / geoip:private 等内置引用需要）
curl -fsSLo geosite.dat https://github.com/v2fly/domain-list-community/releases/latest/download/dlc.dat
curl -fsSLo geoip.dat   https://github.com/v2fly/geoip/releases/latest/download/geoip.dat

XRAY_LOCATION_ASSET=/usr/local/share/xray xray run -c /etc/xray/config.json
```

```json
{
  "routing": {
    "domainStrategy": "IPIfNonMatch",
    "rules": [
      { "type": "field", "outboundTag": "blocked",
        "domain": ["ext:self-geosite.dat:advert.com", "ext:self-geosite.dat:advert.cn"] },
      { "type": "field", "outboundTag": "proxy",
        "domain": ["ext:self-geosite.dat:self-proxy"] },
      { "type": "field", "outboundTag": "direct",
        "domain": ["ext:self-geosite.dat:site.cn", "ext:self-geosite.dat:self-direct"] },
      { "type": "field", "outboundTag": "direct",
        "ip": ["ext:self-geoip.dat:self-direct", "geoip:private", "geoip:cn"] },
      { "type": "field", "outboundTag": "proxy", "network": "tcp,udp" }
    ]
  },
  "geodata": {
    "cron": "@daily",
    "assets": [
      { "url": "https://xinvxueyuan.github.io/proxy-rules/xray/self-geosite.dat",
        "file": "self-geosite.dat" },
      { "url": "https://xinvxueyuan.github.io/proxy-rules/xray/self-geoip.dat",
        "file": "self-geoip.dat" }
    ]
  }
}
```

完整片段见 [`examples/xray.json`](https://xinvxueyuan.github.io/proxy-rules/examples/xray.json)。

> **`domain` 与 `ip` 必须拆成两条规则** —— 同一条规则里两者是 AND，混写会永不命中
> 而 `xray run -test` 照样通过；另外 `geodata` **不能**做首次引导。详见[必读](#必读四个实测确认的坑)。

---

## 订阅地址

**唯一订阅基址**（每日构建后单快照覆盖，**没有历史版本**，任何时刻取到的都是最新一次构建）：

```
https://xinvxueyuan.github.io/proxy-rules/
```

在该基址下按 tag 取文件：

| 用途 | 路径 |
|---|---|
| Clash / mihomo rule-provider | `<基址>/clash/<tag>.yaml` |
| Xray 域名规则集 | `<基址>/xray/self-geosite.dat` |
| Xray IP 规则集 | `<基址>/xray/self-geoip.dat` |
| 产物索引（机器可读） | `<基址>/index.json` |
| 产物校验和 | `<基址>/MANIFEST.sha256` |
| 上游来源与构建时间 | `<基址>/PROVENANCE.json` |

> 客户端仍按 tag 引多个 rule-provider（拦截 / 直连 / 代理是不同动作，必须分开），
> 但**地址只有一个前缀** —— 不再提供 raw 直链或 Release 资产这样的第二渠道，
> 避免客户端配到不同来源却在文档里看起来一样。
>
> 站点由构建流程自动生成、与产物一起发布，所以**页面上的文件与订阅内容永远同一次构建**。
> Pages 有 CDN 缓存，更新可能滞后几分钟。

---

## 分流模型

```
广告 / 追踪 ────────► REJECT    （advert.com = 通用广告网络 ∪ 各生态子组；advert.cn）
自持强制代理 ───────► PROXY     （self-proxy，用来覆盖下面的误判）
国内域名 ──────────► DIRECT    （site.cn，约 11.1 万条）
  └ 九类保底 ──────► DIRECT    （site.cn.{gov,media,edu,med,fin,life,map,travel,shop}）
国内 IP ────────────► DIRECT    （self-direct-ip + GEOIP,CN / geoip:cn）
其余一切 ──────────► PROXY     ← 兜底
```

**兜底是代理**，所以「没被任何规则命中」= 走代理。由此：

| 情况 | 后果 | 怎么处理 |
|---|---|---|
| 国内站漏在名单外 | 走代理（能用，稍慢） | 补进 `data/domains/self-direct` |
| 国外站误在名单内 | 走直连（可能连不上） | 补进 `data/domains/self-proxy` 覆盖 |
| 误拦了要用的域名 | 打不开 | 删掉对应组里的条目，或另引白名单 |

`data/domains/self-*` 是**手写覆盖层**，永远优先于上游大名单。

---

## 规则组

| tag | 说明 | behavior | 条数 |
|---|---|---|---|
| `site.cn` | 国内域名直连（上游大名单 ∪ 九类保底） | `domain` | 111,466 |
| `site.cn.gov` | 中国政务（含 `gov.cn` 通配） | `domain` | 15 |
| `site.cn.media` | 中国媒体 | `domain` | 60 |
| `site.cn.edu` | 中国教育（含 `edu.cn` / `ac.cn` 通配） | `domain` | 33 |
| `site.cn.med` | 中国医疗 | `domain` | 24 |
| `site.cn.fin` | 中国金融 | `domain` | 78 |
| `site.cn.life` | 中国生活服务 | `domain` | 61 |
| `site.cn.map` | 中国地图 | `domain` | 12 |
| `site.cn.travel` | 中国出行（含 `12306.cn` 通配） | `domain` | 49 |
| `site.cn.shop` | 中国购物 | `domain` | 48 |
| `advert.com` | 商业广告（通用广告网络 ∪ `org/gg/ms/fb/x/tg`） | `domain` | 50,993 |
| `advert.cn` | 中文互联网隐私与追踪 | `domain` | 1,741 |
| `advert.gg` / `.ms` / `.fb` / `.x` / `.tg` / `.org` | 各生态隐私与广告 | `domain` | 45 / 396 / 6 / 10 / 3 / 1 |
| `self-direct` | 手写直连补充 | `domain` | 38 |
| `self-proxy` | 手写强制代理（覆盖误判） | `domain` | 83 |
| `self-direct-ip` | 直连 IP（国内公共 DNS 等） | `ipcidr` | 9 |

> **`advert.cn` 不在 `advert.com` 的聚合里**（`advert.com` 只并入 `org/gg/ms/fb/x/tg`）。
> 要同时拦广告与中文互联网追踪，**两条都要引**：`advert.com` + `advert.cn`。
>
> `site.cn.*` 同理是 `site.cn` 的子集；**客户端照旧只引 `site.cn` 即可**，
> 单独引子组是为了审计或按类开关。

---

## 九类中国站点保底直连

`site.cn` 的上游部分来自「能解析到中国大陆 IP 的域名」表，**每天随上游变化**。
为了让政务、媒体、教育、医疗、金融、生活服务、地图、出行、购物这些站点**永远不被漏掉**，
另外用手工整理的根域名做成 9 个子组，由 `site.cn` 聚合。

### 通配根域名语义（这一组的设计核心）

`domain:X` 匹配 X **及其所有子域**，所以**只写根域就够**：

| 写的 | 覆盖 |
|---|---|
| `domain:gov.cn` | `www.gov.cn`、`moe.gov.cn`、`beijing.gov.cn` …… 全部 `*.gov.cn` |
| `domain:edu.cn` | `pku.edu.cn`、`tsinghua.edu.cn` …… 全部 `*.edu.cn` |
| `domain:ac.cn` | `cas.ac.cn` 等科研机构 |
| `domain:12306.cn` | `www.12306.cn`、`kyfw.12306.cn` 等 |

所以**不需要**逐个列省部级站点或子服务 —— 一个 `gov.cn` 就顶掉全部，清单才能保持很短。

### 来源与核实

- 全部**手工整理**（未拉公共列表）：v2fly 的 `category-*-cn` 里政务/地图/购物/出行**四类不存在**、
  医疗只有 11 行，且这些分类**没进官方 dat**；而上游那 11 万条已覆盖大量国内长尾，本组只需保住知名的。
- **每个条目都经 DNS 实测**（apex 或 `www.` 至少一个可解析）。
  ⚠️ 不能只测 apex：`gov.cn` / `edu.cn` / `pbc.gov.cn` 这类**apex 本来就没有 A 记录**
  （只有 `www.` 有），只测 apex 会把最有价值的条目误杀。
- 少数 apex 与 `www.` 都无 A 记录、但站点确实存在（只用深层子域）的根域，人工确认后保留。
- **只收大陆站点**，港澳台不在本组范围。

---

## 必读：四个实测确认的坑

### 1. 自建产物不能叫 `geosite.dat` / `geoip.dat`

Xray 的 `geosite:` / `geoip:` 内置引用读的是资源目录里**固定文件名**。自建产物若同名，
放进资源目录就会把官方那份顶掉，配置里并写的 `geosite:cn`、`geoip:private`、`geoip:cn`
会全部解析失败（实测报 `illegal ip rule: geoip:private ... EOF`）。
所以自建产物带 `self-` 前缀，与官方**并存**。

### 2. 一条规则里 `domain` 与 `ip` 是 **AND**

真 xray 26.9.9 实测：用「域名命中、IP 不命中」的目标探测一条同时带 `domain` 与 `ip` 的规则，
结果落到下一条兜底规则 → 证明是 AND。混写会让这条规则**永不命中**，
而 `run -test` 依然通过（配置合法），属最难看出来的失效。

### 3. Xray 的 `geodata` 不能做首次引导

实测：`geodata` 是**先校验路由规则、后下载资产**。首次部署时 `ext:` 引用的 dat 还不存在，
配置校验就失败、进程退出：

```
infra/conf: illegal domain rule: ext:self-geosite.dat:advert.com >
common/geodata: failed to open self-geosite.dat > no such file or directory
```

所以**必须先手动下载一次**（见上面的快速开始），之后 `geodata` 的 `cron` 才能接管更新
（日志会打印 `scheduled geodata reload with cron: @daily`）。
用 `curl -fsSLO` 做这一步即可，Pages 地址稳定可直接写进运维脚本。

### 4. tag 名带点可用，但官方 dlc 生成不出来

- **Xray 接受**带点的 tag（`ext:self-geosite.dat:advert.com` 与 `:SITE.CN` 都能用，大小写不敏感）；
  写不存在的 tag 会直接报错 —— 好事：能起来就等于 tag 真存在。
- 但官方 [dlc](https://github.com/v2fly/domain-list-community) 的 tag 名校验只允许 `[A-Z0-9!-]`、
  **不含点**（实测 `invalid list name: "ADVERT.CN"` 后退出）。所以本项目用
  [`scripts/build_xray_data.py`](scripts/build_xray_data.py) **纯 Python 编码** dat，
  顺带去掉了 Go 与 dlc 依赖，并带「写完立刻反解一遍」的往返校验。

---

## 编辑规则

```
data/domains/<tag>     自持列表（手写，进 git）—— self-direct / self-proxy
data/extra/<tag>       手工补充 / 手工分类组（手写，进 git）
                       例：site.cn.{gov,media,edu,med,fin,life,map,travel,shop}
data/upstream/<tag>    上游拉取并分类的结果（.gitignore，构建时生成）
data/ip/<name>.txt     自持 IP（每行 IP 或 CIDR）
build/data/<tag>       三层合并 + 聚合解析后的最终数据（构建中间产物）
```

**按 tag 合并三层**：同名的三层会并成一份（去重），所以「上游打底 + 手工补充」不会互相覆盖。

语法与 [dlc](https://github.com/v2fly/domain-list-community) 一致：

```
# 注释
domain:example.com        # 匹配 example.com 及其所有子域
full:a.example.com        # 仅精确匹配
keyword:xxx               # 子串匹配
regexp:^a\.example$       # 正则
include:other-file        # 引用同目录另一文件
```

⚠️ 三个约定：

1. **`keyword:` / `regexp:` 会让该列表整体改用 Clash `behavior: classical` 输出**
   （`<tag>.classical.yaml`）。构建会打印提示，记得把 rule-provider 的 `behavior` 一起改。
2. **`data/ip/` 下不要放空列表**（只有注释也算空）。
3. **不要改 `data/upstream/*`**（构建时会被覆盖）：要么改 `sources.json` 换来源/分类规则，
   要么在 `data/extra/<同名>` 里补。

### 从上游域名到生态组的分类方式

`advert.gg` / `.ms` / `.fb` / `.x` / `.tg` / `.cn` 的成员是**从广告底座里按域名后缀挑出来的**，
不是「把整个厂商都拦掉」：底座里只有广告/追踪域，后缀只用来判断归属。
例如 `adservice.google.com` → `advert.gg`，`ad.pos.baidu.com` → `advert.cn`。
所以**不会**因为 `advert.gg` 就拦掉 `google.com` 本身。

分类规则声明在 [`sources.json`](sources.json) 的 `groups.<组名>.from_suffixes`，改规则不用改代码。

---

## 构建与校验

本地一键：

```bash
bash scripts/build.sh                              # 全流程
SKIP_FETCH=1 SKIP_VERIFY=1 bash scripts/build.sh   # 复用已有上游数据、只出产物
```

流水线（CI 里分步执行，见 [`.github/workflows/build.yml`](.github/workflows/build.yml)）：

| # | 脚本 | 作用 |
|---|---|---|
| 1 | `scripts/fetch_upstream.py` | 拉上游、按生态分类、写 `PROVENANCE.json` |
| 2 | `scripts/assemble_data.py` | 合并三层 + 解析聚合组 → `build/data/` |
| 3 | `scripts/build_clash.py` | 出 Clash rule-provider → `dist/clash/` |
| 4 | `scripts/build_xray_data.py` | 出 `geosite.dat` / `geoip.dat` → `dist/xray/` |
| 5 | `scripts/build_docs.py` | 出 Pages 站点内容（文档页 + 示例 + 索引） |
| 6 | `scripts/verify.sh` | 真内核校验 + 变异检验 + 一致性 |

**校验为什么必须用真实内核**（而不是 `mihomo -t`）：实测 `mihomo -t` 只校验配置语法、
**不加载 `type: file` 的 rule-provider** —— 文件写成非法 YAML、甚至直接删掉，它都输出
`test is successful`、退出码 0。所以校验改成**真启动 mihomo 并查 `/providers/rules`
的真实 `ruleCount`**（与 `MANIFEST.json` 逐项对齐），Xray 侧跑 `run -test` 加载
`ext:` 引用的 dat，两侧都跑**变异检验**（缺文件/坏内容/空规则集/条数不符必须报错）。

另有两个必做保护：`type: file` 是**异步加载**的（必须轮询等条数对齐）；
启动前要检查 API 端口**没被占用**（否则 API 由残留进程回答，会拿上一轮的好数据伪装通过）。

### 产物发布

| 位置 | 内容 | 历史 |
|---|---|---|
| `main` | 只有源码：`data/`、`scripts/`、`verify/`、工作流、文档 | 正常提交 |
| `dist` | 产物 + Pages 站点（`clash/`、`xray/`、`index.html`、`.nojekyll`、两个 MANIFEST、PROVENANCE） | 每次构建**强推单快照**，永远 1 个提交 |
| GitHub Pages | 从 `dist` 分支根发布 | 随 `dist` 更新 |

> **不保留任何历史构建**：每次构建直接覆盖上一次（`dist` 强推、无 Release、无归档），
> 所以任何时刻取到的都是最新版本。
>
> 产物不进 `main`：每天几 MB，提交进 main 一年能把仓库历史撑爆。
>
> [`.github/workflows/cleanup-history.yml`](.github/workflows/cleanup-history.yml)（每月 1 日 + 手动）
> 是兜底，用 `git filter-repo` 清掉历史上误入 main 的产物/草稿并强推。
> ⚠️ 它会重写 main 的提交 SHA，跑完本地 clone 需重新拉取。

---

## 目录结构

```
.
├── data/
│   ├── domains/          自持列表（手写）
│   ├── extra/            手工补充 / 手工分类组（手写）
│   ├── ip/               自持 IP
│   └── upstream/         上游拉取结果（.gitignore）
├── scripts/
│   ├── build.sh              一键构建
│   ├── fetch_upstream.py     拉上游 + 分类
│   ├── assemble_data.py      合并三层 + 聚合
│   ├── build_clash.py        出 Clash rule-provider
│   ├── build_xray_data.py    出 Xray dat（纯 Python）
│   ├── build_docs.py         出 Pages 站点内容
│   ├── verify.sh             真内核校验 + 变异检验
│   ├── verify_clash.py       mihomo 加载校验（查真实 ruleCount）
│   └── verify_consistency.py 两种格式语义等价断言
├── verify/               CI 用校验配置（mihomo / xray）
├── sources.json          来源与分类声明（机器可读）
└── dist/                 产物（构建生成，不进 main）
```

---

## 数据来源与许可证

声明在 [`sources.json`](sources.json)；每次实际用的内容记在产物的 `PROVENANCE.json`
（源 URL + sha256 + 条数 + 抓取时间）。

| 用途 | 来源 | 许可证 | 条数 |
|---|---|---|---|
| 国内域名直连 | [Loyalsoldier/clash-rules](https://github.com/Loyalsoldier/clash-rules) `direct.txt` | GPL-3.0 | 111,304 |
| 广告/追踪底座 | [hagezi/dns-blocklists](https://github.com/hagezi/dns-blocklists) `light-onlydomains` | GPL-3.0 | 50,628 |
| 设备遥测（微软/国内/苹果等） | 同上 `native.*` | GPL-3.0 | 2,713 |
| 九类中国站点保底 | **手工整理**（每个条目经 DNS 实测） | 本仓自持 | 380 |

未采用的候选（含原因）也记在 `sources.json` 的 `catalog` 里：`geosite:cn`（6,624 条，
88.8% 被上游包含）、`geosite:category-ads-all`（911 条，分类后生态桶只剩个位数）、
1Hosts Lite（202,955 条 / 约 5.2MB，误杀概率明显更高）、Loyalsoldier `cncidr`
（mihomo 有内置 `GEOIP,CN`、Xray 有内置 `geoip:cn`）。

**本仓以 GPL-3.0 发布**（见 [LICENSE](LICENSE)）—— 产物由 GPL-3.0 的上游数据构建。

---

## 常见问题

**Q：为什么订阅里没有节点？**
A：本仓只提供**规则**，不含节点。节点由你自己的面板/订阅提供，规则用于决定「走直连还是走代理」。

**Q：`advert.x` / `.tg` / `.org` 怎么只有几条？**
A：公共列表里**根本没有**这些类别（Telegram 与「公益广告」实测分类得到 0 条），只能纯手工。
这三组都**刻意不含本体域**（`twitter.com` / `x.com` / `t.me` / `telegram.org`）——
拦了会直接断掉服务。删掉 `data/extra/advert.org` 即可停用该组（构建会跳过空组）。

**Q：Pages 上的文件多久更新一次？**
A：每天 03:00（北京时间）构建一次，也可手动触发 workflow。Pages 有 CDN 缓存，
更新可能滞后几分钟；要绝对即时请用 raw 直链。

**Q：误拦了某个域名怎么办？**
A：改 `data/extra/<组名>`（或 `data/domains/self-*`）提交即可，下次构建生效。
想立刻生效就自己 fork 后改 `dist` 分支。

**Q：`site.cn` 与 `advert.*` 有重叠怎么办？**
A：国内直连表里也可能出现广告域。规则顺序把 REJECT 放在 DIRECT 之前，所以**广告优先被拦**。

---

## 内核版本

产物对齐当前最新版：**mihomo v1.19.32**、**Xray v26.9.30**（实测环境 Xray 26.9.9 校验通过）。

Xray 的 `releases/latest` 只指到 `v26.3.27`，新版本走 **pre-release** 通道；
CI 取的是「最新一个 release（含 pre-release）」。

---

## License

[GPL-3.0](LICENSE)。上游来源与各自许可证见 [`sources.json`](sources.json)。
