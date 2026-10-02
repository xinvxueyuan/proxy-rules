# proxy-rules

自用分流规则仓。**一份自持数据，编译成 Clash/mihomo 与 Xray 两种内核的格式**，定时自动构建发布。

## 分流模型：国内直连，其余走代理兜底

```
拦截广告/跟踪 ──────────► REJECT
强制代理（覆盖用） ─────► PROXY
国内域名 ──────────────► DIRECT
国内 IP ───────────────► DIRECT
其余一切 ──────────────► PROXY        ← 兜底
```

- **「国内直连」那份名单不是手写的**，而是从上游拉取的 **11 万条**（见「上游来源」），
  覆盖足够全，长尾国内站不会漏。
- **兜底是代理**，所以「没被任何规则命中」= 走代理。这意味着：

  | 情况 | 后果 | 怎么管 |
  |---|---|---|
  | 国内站漏在名单外 | 走代理（能用，稍慢） | 补进 `data/domains/self-direct` |
  | 国外站误在名单内 | 走直连（可能连不上） | 补进 `data/domains/self-proxy` 覆盖 |

- 自持规则（`data/domains/self-*`）**永远优先于上游名单**，就是用来做上面两种修正的。

## 产物与获取地址

| 产物 | 用途 | 地址 |
|---|---|---|
| `self-geosite.dat` | Xray 域名规则集（`ext:self-geosite.dat:<tag>`） | `https://github.com/xinvxueyuan/proxy-rules/releases/latest/download/self-geosite.dat` |
| `self-geoip.dat` | Xray IP 规则集（`ext:self-geoip.dat:<tag>`） | `https://github.com/xinvxueyuan/proxy-rules/releases/latest/download/self-geoip.dat` |
| `clash/*.yaml` | mihomo rule-provider | `https://raw.githubusercontent.com/xinvxueyuan/proxy-rules/dist/clash/<name>.yaml` |
| `MANIFEST.json` | 每个产物的 behavior / 条数 / sha256 | `https://raw.githubusercontent.com/xinvxueyuan/proxy-rules/dist/clash/MANIFEST.json` |
| `PROVENANCE.json` | 上游来源 / sha256 / 条数 / 抓取时间 | `https://github.com/xinvxueyuan/proxy-rules/releases/latest/download/PROVENANCE.json` |

> 产物在 **`dist` 分支** + **Release**，**不在 `main`**。原因：产物每天变（上游 11 万条），
> 若提交进 main，每天 +2.8MB、一年约 1GB，会把仓库历史撑爆。`dist` 分支每次构建**单快照强推**，
> 历史永远只有 1 个提交。

### tag / 文件名一览

| tag（Xray） | 文件（Clash） | behavior | 条数 | 含义 |
|---|---|---|---|---|
| `china-direct` | `china-direct.yaml` | `domain` | ~111,000 | **国内域名直连**（上游拉取） |
| `self-direct` | `self-direct.yaml` | `domain` | 38 | 自持直连补充 |
| `self-proxy` | `self-proxy.yaml` | `domain` | 83 | 自持强制代理（**覆盖**上游名单） |
| `self-reject` | `self-reject.yaml` | `domain` | 61 | 广告 / 跟踪，拒掉 |
| `self-direct` | `self-direct-ip.yaml` | `ipcidr` | 9 | 自持直连 IP（国内公共 DNS 等） |

> Xray 侧域名与 IP 是两个维度、**tag 可同名并存**（`ext:self-geosite.dat:self-direct`
> 与 `ext:self-geoip.dat:self-direct`）；Clash 侧要拆成两个文件（behavior 不同）。

## 客户端配置

### Clash / mihomo

```yaml
rule-providers:
  self-reject:
    type: http
    behavior: domain
    format: yaml
    interval: 86400
    url: https://raw.githubusercontent.com/xinvxueyuan/proxy-rules/dist/clash/self-reject.yaml
  self-proxy:
    type: http
    behavior: domain
    format: yaml
    interval: 86400
    url: https://raw.githubusercontent.com/xinvxueyuan/proxy-rules/dist/clash/self-proxy.yaml
  china-direct:
    type: http
    behavior: domain
    format: yaml
    interval: 86400
    url: https://raw.githubusercontent.com/xinvxueyuan/proxy-rules/dist/clash/china-direct.yaml
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
  - RULE-SET,self-reject,REJECT
  - RULE-SET,self-proxy,PROXY           # 覆盖上游名单里想走代理的域名
  - RULE-SET,china-direct,DIRECT
  - RULE-SET,self-direct,DIRECT
  - RULE-SET,self-direct-ip,DIRECT,no-resolve
  - GEOIP,CN,DIRECT,no-resolve          # 国内 IP 直连（mihomo 内置，需 geoip 数据）
  - MATCH,PROXY                         # 兜底
```

> `GEOIP,CN` 需要 mihomo 的 geoip 数据（Clash Verge 一般自带）。不想依赖它就删掉那行 ——
> 只靠域名规则也能工作，只是纯 IP 场景（某些 App 直连 IP）会走代理。
>
> 国内可达性差的网络里，把 `raw.githubusercontent.com` 换成 jsDelivr：
> `https://cdn.jsdelivr.net/gh/xinvxueyuan/proxy-rules@dist/clash/<name>.yaml`

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
        "domain": ["ext:self-geosite.dat:self-reject"] },
      { "type": "field", "outboundTag": "proxy",
        "domain": ["ext:self-geosite.dat:self-proxy"] },
      { "type": "field", "outboundTag": "direct",
        "domain": ["ext:self-geosite.dat:china-direct", "ext:self-geosite.dat:self-direct"] },
      { "type": "field", "outboundTag": "direct",
        "ip": ["ext:self-geoip.dat:self-direct", "geoip:private", "geoip:cn"] },
      { "type": "field", "outboundTag": "proxy", "network": "tcp,udp" }
    ]
  }
}
```

最后一条 `network: tcp,udp` 就是**兜底走代理**。

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

### ⚠️ `domain` 与 `ip` 必须拆成两条规则（实测）

Xray 的一条规则里同时给 `domain` 和 `ip` 时，两者是 **AND** —— 必须同时命中才算命中该规则
（真 xray 26.9.9 实测：用「域名命中、IP 不命中」的目标探测这条规则，结果落到下一条兜底规则）。
把「域名直连」与「IP 直连」混写在一条里，这条规则就**永不命中**。

```
✅ 正确：两条规则
  { "outboundTag": "direct", "domain": ["ext:self-geosite.dat:china-direct"] }
  { "outboundTag": "direct", "ip": ["ext:self-geoip.dat:self-direct","geoip:private","geoip:cn"] }

❌ 错误：混在一条里 → 永不命中
  { "outboundTag": "direct",
    "domain": ["ext:self-geosite.dat:china-direct"],
    "ip": ["geoip:cn"] }
```

（`domain` 数组内部、`ip` 数组内部各自是 OR：任一命中即算该维度命中。）

### ⚠️ 产物为什么不叫 `geosite.dat` / `geoip.dat`

Xray 的 `geosite:` / `geoip:` 内置引用读的是资源目录里**固定文件名**。
自建产物若用这两个名字，放进资源目录就会**把官方那份顶掉** —— 配置里并写的
`geosite:cn`、`geoip:private`、`geoip:cn` 会全部解析失败（实测报
`illegal ip rule: geoip:private ... EOF`）。所以自建产物带 `self-` 前缀，与官方**并存**。

## 编辑规则（唯一入口：`data/`）

```
data/domains/self-*    自持规则，v2fly domain-list 语法（会被提交）
data/ip/*.txt          自持 IP（会被提交）
data/upstream/         上游拉取的名单（.gitignore 排除，构建前自动生成）
```

`data/domains/self-*` 的语法（与 [domain-list-community](https://github.com/v2fly/domain-list-community) 一致）：

```
# 注释
domain:example.com        # 匹配 example.com 及其所有子域
full:a.example.com        # 仅精确匹配
keyword:xxx               # 子串匹配
regexp:^a.*\.example$     # 正则
include:other-file        # 引用同目录另一文件
```

新增一个列表 = 丢一个文件（文件名即 tag），**不用改脚本**。

⚠️ 三个约定：

1. **`keyword:` / `regexp:` 会让该列表整体改用 Clash `behavior: classical` 输出**
   （`<name>.classical.yaml`）。构建会打印提示，记得把 rule-provider 的 `behavior` 一起改，
   否则规则静默不生效。
2. **`data/ip/` 下不要放空列表**（只有注释也算空）：geoip 工具对零条目输入会直接失败。
3. **想改「国内直连」那份名单**：不要改 `data/upstream/china-direct`（构建时被覆盖）——
   要么改 `sources.json` 换上游，要么用 `self-direct` / `self-proxy` 做修正。

### 关于 tag 大小写与条数（实测结论）

- **tag 匹配大小写不敏感**：`self-direct` 与 `SELF-DIRECT` 都能用（Xray 26.9.9 实测）。
- **`ext:` 写不存在的 tag 会直接报错** → 「配置能起来」就等于「tag 真存在」，不会静默失效。
- **dat 条数可能少于 Clash 条数，但语义等价**：`dlc` 会剪掉被父域覆盖的冗余子域
  （`data/domains/self-direct` 里的 `weixin.qq.com` 被同列表 `domain:qq.com` 覆盖）。
  `scripts/verify_consistency.py` 断言「dat 的每条都在 Clash 里」且「只在 Clash 里的每条
  都被某个父域覆盖」；IP 列表不剪枝，两侧必须完全相等。

### Clash 侧两种写法的语义（实测）

| payload 写法 | 匹配自身 | 匹配子域 |
|---|---|---|
| `example.com` | ✅ | ❌（精确） |
| `+.example.com` | ✅ | ✅（后缀） |

所以从上游转换时 `+.x` → dlc `domain:x`、裸 `x` → dlc `full:x`，两边语义严格对应。

## 上游来源与许可证

声明在 [`sources.json`](sources.json)（机器可读），构建前由 `scripts/fetch_upstream.py` 拉取。
每次实际用的那份内容记在产物的 `PROVENANCE.json`（源 URL + sha256 + 条数 + 抓取时间）。

| 用途 | 来源 | 许可证 |
|---|---|---|
| 国内域名直连（~111k） | [Loyalsoldier/clash-rules](https://github.com/Loyalsoldier/clash-rules) `direct.txt` | **GPL-3.0** |
| 其它候选（记录了未采用的原因） | v2fly / MetaCubeX / felixonmars | 见 `sources.json` |

**本仓因此以 GPL-3.0 发布**（见 [LICENSE](LICENSE)）—— 分发基于 GPL-3.0 数据构建的产物，
保持同一许可证最省事。

为什么用 11 万条那份而不是 v2fly 的 `geosite:cn`（6,624 条）：后者实测 **88.8% 被前者包含**，
是精选子集；在「国内直连、其余走代理」模型下，名单不全意味着国内站白白走代理。
为什么不用 `geosite:geolocation-!cn`（25,023 条「非大陆」）：本模型兜底即代理，不需要反面名单。
IP 侧未采用上游 `cncidr`：mihomo 有内置 `GEOIP,CN`、Xray 有内置 `geoip:cn`，无需自维。

## 构建与校验

`.github/workflows/build.yml`（push / 每日 / 手动）：

1. `scripts/fetch_upstream.py` — 拉上游列表，规范成 dlc 语法，写 provenance；
2. `scripts/build_clash.py` — 生成 `dist/clash/*.yaml` + `MANIFEST.json`；
3. `scripts/build_xray.sh` — 用官方工具生成 `self-geosite.dat`（[dlc](https://github.com/v2fly/domain-list-community)）
   与 `self-geoip.dat`（[v2fly/geoip](https://github.com/v2fly/geoip)）；
4. `scripts/verify.sh` — **用真实内核加载产物**：
   - Xray 侧 `xray run -test`，把自建 dat 与**官方 dat 一起**放进资源目录
     （既验证能加载，也验证不遮蔽 `geosite:cn` / `geoip:private`）；
   - Clash 侧**真启动 mihomo** 并查 `/providers/rules` 的真实 `ruleCount`，与 `MANIFEST.json` 对齐；
   - 两侧都跑**变异检验**（dat 缺失/损坏、rule-provider 空文件/条数不符必须报错）；
5. `scripts/verify_consistency.py` — 断言两种格式语义等价（见上文剪枝说明）；
6. 强推 `dist` 分支 + 发 Release。

> ⚠️ **不要用 `mihomo -t` 当闸门**：它只校验配置语法、**不加载 `type: file` 的 rule-provider** ——
> 文件写成非法 YAML、甚至直接删掉，它都输出 `test is successful`、退出码 0（实测）。
> 这就是上面为什么要真启动内核 + 查 API 条数 + 做变异检验。

本地复现：

```bash
python3 scripts/fetch_upstream.py       # 拉上游（需要网络）
python3 scripts/build_clash.py          # 纯标准库
bash scripts/build_xray.sh              # 需要 go（dlc + v2fly/geoip）
bash scripts/verify.sh                  # 需要 curl / unzip / python3
python3 scripts/verify_consistency.py   # 需要先有 dist/xray/*.dat
```

### `main` 与 `dist` 两个分支

| 分支 | 内容 | 历史 |
|---|---|---|
| `main` | 只有源码：`data/`、`scripts/`、`verify/`、工作流、文档 | 正常提交 |
| `dist` | 只有产物：`clash/*.yaml`、`xray/*.dat`、两个 MANIFEST、PROVENANCE | 每次构建**强推**，永远 1 个提交 |

`.github/workflows/cleanup-history.yml`（每月 1 日 + 手动）是**兜底**：把历史上误入 main 的
产物 / 草稿文件用 `git filter-repo` 清掉并强推。正常情况下不会触发清理（main 本就不提交产物）。

> ⚠️ 它重写 main 的提交 SHA，跑完本地 clone 需重新拉取。

## 内核版本

产物对齐当前最新版：**mihomo v1.19.32**、**Xray v26.9.30**。

- Xray 的 `releases/latest` 只指到 `v26.3.27`，新版本走 **pre-release** 通道；
  CI 取的是「最新一个 release（含 pre-release）」。
- `ext:` 规则集与 `geodata` 热更新都是较新的能力，太旧的内核请先升级。

## License

**GPL-3.0**（见 [LICENSE](LICENSE)）。理由：产物由 GPL-3.0 的上游名单构建。
上游来源与各自许可证见 [`sources.json`](sources.json)。
