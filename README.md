# proxy-rules

自用分流规则仓。**一份组装结果，编译成 Clash/mihomo 与 Xray 两种内核的格式**，定时自动构建发布。

## 分流模型

```
商业广告 / 追踪 ──► REJECT      （advert.com：通用广告网络 ∪ 下列各生态子组）
中文互联网追踪 ──► REJECT      （advert.cn）
自持强制代理 ───► PROXY        （self-proxy，用来覆盖下面两条的误判）
国内域名 ──────► DIRECT        （site.cn，约 11.1 万条）
  └ 九类保底 ──► DIRECT        （site.cn.{gov,media,edu,med,fin,life,map,travel,shop}）
国内 IP ───────► DIRECT        （self-direct-ip + geoip:cn）
其余一切 ──────► PROXY         ← 兜底
```

- **兜底是代理**，「没被任何规则命中」= 走代理。所以：

  | 情况 | 后果 | 怎么管 |
  |---|---|---|
  | 国内站漏在名单外 | 走代理（能用，稍慢） | 补进 `data/domains/self-direct` |
  | 国外站误在名单内 | 走直连（可能连不上） | 补进 `data/domains/self-proxy` 覆盖 |
  | 误拦了要用的域名 | 打不开 | 删掉对应组里的条目，或另引白名单组 |

- `data/domains/self-*` 是**手写覆盖层**，永远优先于上游名单。

## 组一览

| tag | Clash 文件 | 条数 | 含义 | 来源 |
|---|---|---|---|---|
| `site.cn` | `site.cn.yaml` | ~111,470 | **国内域名直连**（上游大名单 ∪ 下面 9 个手工分类组） | 上游 + 手工 |
| `site.cn.gov` | `site.cn.gov.yaml` | 15 | **中国政务**（含 `gov.cn` 通配） | 手工保底 |
| `site.cn.media` | `site.cn.media.yaml` | 60 | **中国媒体** | 手工保底 |
| `site.cn.edu` | `site.cn.edu.yaml` | 33 | **中国教育**（含 `edu.cn` / `ac.cn` 通配） | 手工保底 |
| `site.cn.med` | `site.cn.med.yaml` | 24 | **中国医疗** | 手工保底 |
| `site.cn.fin` | `site.cn.fin.yaml` | 78 | **中国金融** | 手工保底 |
| `site.cn.life` | `site.cn.life.yaml` | 61 | **中国生活服务** | 手工保底 |
| `site.cn.map` | `site.cn.map.yaml` | 12 | **中国地图** | 手工保底 |
| `site.cn.travel` | `site.cn.travel.yaml` | 49 | **中国出行** | 手工保底 |
| `site.cn.shop` | `site.cn.shop.yaml` | 48 | **中国购物** | 手工保底 |
| `advert.com` | `advert.com.yaml` | ~50,990 | **商业广告**（通用广告网络 ∪ 下面 6 个子组） | 上游分类 + 手工补充 |
| `advert.gg` | `advert.gg.yaml` | 45 | 谷歌隐私与广告 | 上游分类 + 手工补充 |
| `advert.ms` | `advert.ms.yaml` | 396 | 微软隐私与广告 | 上游分类 + 设备遥测表 |
| `advert.fb` | `advert.fb.yaml` | 6 | Meta（Facebook/Instagram/WhatsApp） | 上游分类 |
| `advert.x` | `advert.x.yaml` | 10 | 推特（X）广告与分析 | 手工（公共列表无源） |
| `advert.tg` | `advert.tg.yaml` | 3 | Telegram 推广与统计 | 手工（公共列表无源） |
| `advert.org` | `advert.org.yaml` | 1 | 公益 / 非盈利广告 | 手工（公共列表无源） |
| `advert.cn` | `advert.cn.yaml` | ~1,740 | **中文互联网隐私与追踪** | 上游分类 + 国内遥测表 + 手工 |
| `self-direct` | `self-direct.yaml` | 38 | 手写直连补充 | 自持 |
| `self-proxy` | `self-proxy.yaml` | 83 | 手写强制代理（**覆盖**上面的误判） | 自持 |
| `self-direct-ip` | `self-direct-ip.yaml` | 9 | 直连 IP（国内公共 DNS） | 自持 |

> ⚠️ **`advert.cn` 不在 `advert.com` 的聚合里**（按你的原始定义：`advert.com` 只并入
> `advert.org/gg/ms/fb/x/tg`）。所以客户端要拦全广告与追踪，**两条都要引**：
> `advert.com` + `advert.cn`。

## 产物与获取地址

| 产物 | 用途 | 地址 |
|---|---|---|
| `self-geosite.dat` | Xray 域名规则集 | `https://github.com/xinvxueyuan/proxy-rules/releases/latest/download/self-geosite.dat` |
| `self-geoip.dat` | Xray IP 规则集 | `https://github.com/xinvxueyuan/proxy-rules/releases/latest/download/self-geoip.dat` |
| `clash/*.yaml` | mihomo rule-provider | `https://raw.githubusercontent.com/xinvxueyuan/proxy-rules/dist/clash/<tag>.yaml` |
| `MANIFEST.json` | 每个产物的 behavior / 条数 / sha256 | `.../dist/clash/MANIFEST.json` |
| `PROVENANCE.json` | 上游来源 / sha256 / 条数 / 分类明细 | `https://github.com/xinvxueyuan/proxy-rules/releases/latest/download/PROVENANCE.json` |

> 产物在 **`dist` 分支** + **Release**，**不在 `main`**：产物每天变（几 MB），提交进 main
> 会把历史撑爆。`dist` 分支每次构建**单快照强推**，历史永远只有 1 个提交。

## 客户端配置

### Clash / mihomo

```yaml
rule-providers:
  advert.com:
    type: http
    behavior: domain
    format: yaml
    interval: 86400
    url: https://raw.githubusercontent.com/xinvxueyuan/proxy-rules/dist/clash/advert.com.yaml
  advert.cn:
    type: http
    behavior: domain
    format: yaml
    interval: 86400
    url: https://raw.githubusercontent.com/xinvxueyuan/proxy-rules/dist/clash/advert.cn.yaml
  self-proxy:
    type: http
    behavior: domain
    format: yaml
    interval: 86400
    url: https://raw.githubusercontent.com/xinvxueyuan/proxy-rules/dist/clash/self-proxy.yaml
  site.cn:
    type: http
    behavior: domain
    format: yaml
    interval: 86400
    url: https://raw.githubusercontent.com/xinvxueyuan/proxy-rules/dist/clash/site.cn.yaml
  self-direct:
    type: http
    behavior: domain
    format: yaml
    interval: 86400
    url: https://raw.githubusercontent.com/xinvxueyuan/proxy-rules/dist/clash/self-direct.yaml
  self-direct-ip:
    type: http
    behavior: ipcidr
    format: yaml
    interval: 86400
    url: https://raw.githubusercontent.com/xinvxueyuan/proxy-rules/dist/clash/self-direct-ip.yaml

rules:
  - RULE-SET,advert.com,REJECT
  - RULE-SET,advert.cn,REJECT
  - RULE-SET,self-proxy,PROXY
  - RULE-SET,site.cn,DIRECT
  - RULE-SET,self-direct,DIRECT
  - RULE-SET,self-direct-ip,DIRECT,no-resolve
  - GEOIP,CN,DIRECT,no-resolve          # 国内 IP 直连（mihomo 内置，需 geoip 数据）
  - MATCH,PROXY                         # 兜底
```

> 只想要粗粒度拦截就把 `advert.com` + `advert.cn` 换成细分的
> `advert.gg` / `advert.ms` / `advert.fb` / `advert.x` / `advert.tg` / `advert.org`。
>
> 国内可达性差的网络里，把 `raw.githubusercontent.com` 换成 jsDelivr：
> `https://cdn.jsdelivr.net/gh/xinvxueyuan/proxy-rules@dist/clash/<tag>.yaml`

### Xray

`ext:` 引用的文件要放在**资源目录**（启动时的当前目录，或用 `XRAY_LOCATION_ASSET` 指定）：

```bash
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
  }
}
```

Xray 支持**按 URL 热更新** `.dat`（不用重启、不用手动放文件）：

```json
{
  "geodata": {
    "cron": "@daily",
    "assets": [
      { "url": "https://github.com/xinvxueyuan/proxy-rules/releases/latest/download/self-geosite.dat",
        "file": "self-geosite.dat" },
      { "url": "https://github.com/xinvxueyuan/proxy-rules/releases/latest/download/self-geoip.dat",
        "file": "self-geoip.dat" }
    ]
  }
}
```

## 九类中国站点保底直连（`site.cn.*`）

`site.cn` 的上游部分来自「能解析到中国大陆 IP 的域名」表（约 11.1 万条），
它**每天随上游变化**。为了让政务、媒体、教育、医疗、金融、生活服务、地图、出行、购物
这些站点**永远不被漏掉**，另外用手工整理的根域名做成 9 个子组，并由 `site.cn` 聚合它们。

### 通配根域名语义（这一组的设计核心）

`domain:X` 匹配 X **及其所有子域**（DNS 树意义），所以**只写根域就够**：

| 写的 | 覆盖 |
|---|---|
| `domain:gov.cn` | `www.gov.cn`、`moe.gov.cn`、`beijing.gov.cn` …… 全部 `*.gov.cn` |
| `domain:edu.cn` | `pku.edu.cn`、`tsinghua.edu.cn` …… 全部 `*.edu.cn` |
| `domain:ac.cn` | `cas.ac.cn` 等科研机构 |
| `domain:taobao.com` | `item.taobao.com`、`gw.alicdn.com` 等 |
| `domain:12306.cn` | `www.12306.cn`、`kyfw.12306.cn` 等 |

所以**不需要**逐个列省部级站点或子服务——一个 `gov.cn` 就顶掉全部。这也让清单能保持很短。

### 条目的来源与核实

- 全部**手工整理**（你选的方案），没有拉公共列表：v2fly 的 `category-*-cn` 里
  **政务/地图/购物/出行四类根本不存在**、医疗只有 11 行，且这些分类**没进官方 dat**；
  而 `site.cn` 上游那 11 万条已经覆盖了大量国内长尾域名，本组只需保住知名的。
- **每个条目都经 DNS 实测**（apex 或 `www.` 至少一个可解析，在服务器上跑的）。
  ⚠️ 测的时候不能只测 apex：`gov.cn` / `edu.cn` / `pbc.gov.cn` 这类**apex 本来就没有
  A 记录**（只有 `www.` 有），只测 apex 会把最有价值的条目误杀。
- 少数 apex 与 `www.` 都无 A 记录、但站点确实存在（只用深层子域）的根域，经人工确认后保留
  （如 `mof.gov.cn`、`unionpay.com`、`sf-express.com` 等）。
- **只收大陆站点**，港澳台不在本组范围。

### 聚合与守卫

`site.cn` = 上游大名单 **∪** 这 9 个子组（`sources.json` 的 `union_of`）。
所以**客户端无需改配置**——照旧引 `site.cn` 就已经包含这九类；
想单独审计/开关某类时，再单独引对应的 `site.cn.<分类>` 即可。

两道守卫防止「少一整个分类却没人发现」：

1. `sources.json` 里这些组标了 `hand: true`，`fetch_upstream.py --check` 会要求它们非空；
2. `assemble_data.py` 解析 `union_of` 时，**成员缺失直接失败**（不再静默跳过）。

两者都做过实证（临时改掉 `site.cn.gov` → 一个退出码 1、一个退出码 2）。

## 三个实测确认的坑（都有决定性证据）

### 1. 产物不能叫 `geosite.dat` / `geoip.dat`（会遮蔽官方同名文件）

Xray 的 `geosite:` / `geoip:` 内置引用读的是资源目录里**固定文件名**。自建产物若同名，
放进资源目录就会把官方那份顶掉，配置里并写的 `geosite:cn`、`geoip:private`、`geoip:cn`
会全部解析失败（实测报 `illegal ip rule: geoip:private ... EOF`）。所以自建产物带 `self-` 前缀。

### 2. 一条规则里 `domain` 与 `ip` 是 **AND**（必须拆成两条）

真 xray 26.9.9 实测：用「域名命中、IP 不命中」的目标探测一条同时带 `domain` 与 `ip` 的规则，
结果落到下一条兜底规则 → 证明是 AND。混写会让整条规则**永不命中**，而 `run -test` 依然通过
（配置合法），属于最难看出来的失效。

```
✅ { "outboundTag": "direct", "domain": [...] }
   { "outboundTag": "direct", "ip": [...] }
❌ { "outboundTag": "direct", "domain": [...], "ip": [...] }   # 永不命中
```

### 3. tag 名带点可用，但官方 dlc 生成不出来

- **Xray 接受**带点的 tag：`ext:self-geosite.dat:advert.com` 与 `:SITE.CN` 都能用
  （大小写不敏感），写不存在的 tag 会直接报错（好事：能起来就等于 tag 真存在）。
- 但官方 [dlc](https://github.com/v2fly/domain-list-community) 的 tag 名校验只允许
  `[A-Z0-9!-]`、**不含点**（见其 `validateSiteName`），实测报 `invalid list name: "ADVERT.CN"`
  后直接退出。所以本项目**自己用纯 Python 编码 `geosite.dat` / `geoip.dat`**
  （`scripts/build_xray_data.py`），顺带去掉了 Go 与 dlc 依赖，并带往返校验（写完立刻反解比对）。

## 编辑规则

```
data/domains/<tag>     自持列表（手写，进 git）
data/extra/<tag>       对上游组的手工补充 / 手工分类组（手写，进 git）
                       例：site.cn.{gov,media,edu,med,fin,life,map,travel,shop}
data/upstream/<tag>    上游拉取并分类的结果（.gitignore，构建时生成）
build/data/<tag>       三层合并 + 聚合解析后的最终数据（构建中间产物）
```

**按 tag 合并**：同名的三层会并成一份（去重）。所以「上游打底 + 手工补」不会互相覆盖 ——
这一点是实测踩坑后加的：早先三层各自出产物时，上游那份会**静默盖掉**手工那份。

`data/domains/self-*` 与 `data/extra/*` 的语法与 [dlc](https://github.com/v2fly/domain-list-community) 一致：

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
3. **想改上游那份名单**：不要改 `data/upstream/*`（构建时被覆盖）——
   要么改 `sources.json` 换来源/分类规则，要么在 `data/extra/<同名>` 里补。

### 从上游域名到生态组的分类方式

`advert.gg` / `.ms` / `.fb` / `.x` / `.tg` / `.cn` 的成员是**从广告底座里按域名后缀挑出来的**
（不是「把整个谷歌/微软/腾讯都拦掉」）：底座里只有广告/追踪域，后缀只是用来判断
「这条属于哪个生态」。例如底座里的 `adservice.google.com` → `advert.gg`；
`ad.pos.baidu.com` → `advert.cn`。所以**不会**因为 `advert.gg` 就拦掉 `google.com` 本身。

分类规则声明在 `sources.json` 的 `groups.<组名>.from_suffixes`，改规则不用改代码。

## 数据来源与许可证

声明在 [`sources.json`](sources.json)（机器可读），每次实际用的内容记在产物的 `PROVENANCE.json`。

| 用途 | 来源 | 许可证 | 实际条数 |
|---|---|---|---|
| 国内域名直连 | [Loyalsoldier/clash-rules](https://github.com/Loyalsoldier/clash-rules) `direct.txt` | GPL-3.0 | 111,304 |
| 广告/追踪底座 | [hagezi/dns-blocklists](https://github.com/hagezi/dns-blocklists) `light-onlydomains` | GPL-3.0 | 50,628 |
| 设备遥测（微软/国内/苹果等） | 同上 `native.*` | GPL-3.0 | 2,713 |
| 九类中国站点保底 | **手工整理**（每个条目经 DNS 实测） | 本仓自持 | 380 |

**本仓以 GPL-3.0 发布**（见 [LICENSE](LICENSE)）—— 产物由 GPL-3.0 的上游数据构建。

未采用的候选（含原因）也记在 `sources.json` 的 `catalog` 里：

| 候选 | 条数 | 为什么不用 |
|---|---|---|
| `geosite:cn`（v2fly） | 6,624 | 实测 88.8% 被 site.cn 包含，是精选子集 |
| `geosite:category-ads-all` | 911 | 分类后生态桶只剩个位数（gg 23 / ms 3 / fb 6 / x 1 / tg 0） |
| 1Hosts Lite | 202,955 | 约 5.2MB、误杀概率明显更高（生态桶确实厚，但代价大） |
| hagezi pro / normal | 227,572 / 199,122 | 同上，体积换拦截率的取舍选了 light |
| Loyalsoldier `cncidr` | 9,649 | mihomo 有内置 `GEOIP,CN`、Xray 有内置 `geoip:cn` |

## 构建与校验

本地一键（CI 里是分步执行的，见 `.github/workflows/build.yml`）：

```bash
bash scripts/build.sh                 # fetch → assemble → clash → dat → verify
SKIP_FETCH=1 SKIP_VERIFY=1 bash scripts/build.sh   # 复用已有上游数据、只出产物
```

分步（各脚本也能单独跑）：

```bash
python3 scripts/fetch_upstream.py     # 1) 拉上游并分类（写 data/upstream + PROVENANCE）
python3 scripts/assemble_data.py      # 2) 合并三层 + 解析聚合组（写 build/data）
python3 scripts/build_clash.py        # 3) 出 Clash rule-provider（写 dist/clash）
python3 scripts/build_xray_data.py    # 4) 出 geosite.dat / geoip.dat（写 dist/xray）
bash scripts/verify.sh                # 5) 真内核校验 + 变异检验 + 一致性
```

**校验为什么必须用真实内核**（而不是 `mihomo -t`）：实测 `mihomo -t` 只校验配置语法、
**不加载 `type: file` 的 rule-provider** —— 文件写成非法 YAML、甚至直接删掉，它都输出
`test is successful`、退出码 0。所以校验改成**真启动 mihomo 并查 `/providers/rules`
的 `ruleCount`**（与 `MANIFEST.json` 逐项对齐），Xray 侧跑 `xray run -test` 加载 `ext:`
引用的 dat，两侧都跑**变异检验**（缺文件/坏内容/空规则集/条数不符必须报错）。

另外两个必做保护：

- **`type: file` 是异步加载的**：API 一就绪就查会拿到 `ruleCount=0`，必须轮询等条数对齐。
- **启动前检查 API 端口是否被占用**：被残留进程占用时 API 会由它回答，会拿上一轮的好数据
  把这次校验伪装成通过。

### `main` 与 `dist` 两个分支

| 分支 | 内容 | 历史 |
|---|---|---|
| `main` | 只有源码：`data/`、`scripts/`、`verify/`、工作流、文档 | 正常提交 |
| `dist` | 只有产物：`clash/*.yaml`、`xray/*.dat`、两个 MANIFEST、PROVENANCE | 每次构建**强推**，永远 1 个提交 |

`.github/workflows/cleanup-history.yml`（每月 1 日 + 手动）是兜底：用 `git filter-repo`
清掉历史上误入 main 的产物/草稿并强推。正常不触发（main 本就不提交产物）。
⚠️ 它重写 main 的提交 SHA，跑完本地 clone 需重新拉取。

## 已知限制

- **`advert.org` 只有 1 条**（`adcouncil.org`）：公共列表里**没有**「公益/非盈利广告」
  这个类别，纯自持占位，价值有限，嫌碍事就删掉 `data/extra/advert.org`（构建会自动跳过空组）。
- **`advert.tg` 只有 3 条**（`ads/promote/stats.telegram.org`）：Telegram 没有独立的
  第三方广告域清单，实测从底座里分类得到 **0 条**。刻意**不含** `telegram.org` / `t.me`
  本体 —— 那是电报服务与链接域名，拦了会断掉电报。
- **`advert.x` 只有 10 条**：Twitter 在 v2fly / MetaCubeX 都没有独立广告表。同样刻意不含
  `twitter.com` / `x.com` / `t.co` 本体（会断掉推特与站外推文链接）。
- **`advert.fb` 只有 6 条**：底座里 Meta 系的广告域本来就少。
- **`site.cn` 与 `advert.*` 会有重叠**：国内域名直连表里也可能有广告域（该表由「解析到
  大陆 IP 的域名」汇总而来）。规则顺序把 REJECT 放在 DIRECT 之前，所以**广告优先被拦**。

## 内核版本

产物对齐当前最新版：**mihomo v1.19.32**、**Xray v26.9.30**（实测环境 Xray 26.9.9 校验通过）。

Xray 的 `releases/latest` 只指到 `v26.3.27`，新版本走 **pre-release** 通道；
CI 取的是「最新一个 release（含 pre-release）」。

## License

**GPL-3.0**（见 [LICENSE](LICENSE)）。上游来源与各自许可证见 [`sources.json`](sources.json)。
