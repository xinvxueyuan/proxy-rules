# proxy-rules

自用的分流规则仓：**一份自持数据，编译成 Clash/mihomo 与 Xray 两种内核的格式**，定时自动构建发布。

- 自持规则（域名 + IP）是本仓的**单一真相**，改规则只改 `data/`；
- 产物自动生成，**不要手改** `dist/`（CI 每次覆盖）；
- 公共规则集**不合并进产物**，以「引用并按需并用」的方式搭配（理由见下文），
  可引用的清单记录在 [`sources.yaml`](sources.yaml)。

## 产物与获取地址

| 产物 | 用途 | 地址 |
|---|---|---|
| `self-geosite.dat` | Xray 域名规则集（`ext:self-geosite.dat:<tag>`，tag 大小写不敏感） | `https://github.com/xinvxueyuan/proxy-rules/releases/latest/download/self-geosite.dat` |
| `self-geoip.dat` | Xray IP 规则集（`ext:self-geoip.dat:<tag>`） | `https://github.com/xinvxueyuan/proxy-rules/releases/latest/download/self-geoip.dat` |
| `dist/clash/*.yaml` | mihomo rule-provider | `https://raw.githubusercontent.com/xinvxueyuan/proxy-rules/main/dist/clash/<name>.yaml` |
| `dist/clash/MANIFEST.json` | 每个产物的 behavior / 条数 / sha256 | 同上目录 |

### tag / 文件名一览

| tag（Xray） | 文件（Clash） | Clash behavior | 含义 |
|---|---|---|---|
| `self-direct` | `self-direct.yaml` | `domain` | 直连域名 |
| `self-proxy` | `self-proxy.yaml` | `domain` | 强制走代理的域名 |
| `self-reject` | `self-reject.yaml` | `domain` | 广告 / 跟踪 / 统计，拒掉 |
| `self-direct` | `self-direct-ip.yaml` | `ipcidr` | 直连 IP（国内公共 DNS 等） |

> 注：Xray 侧域名与 IP 是两个维度、**同名 tag 可以并存**（`ext:self-geosite.dat:self-direct`
> 与 `ext:self-geoip.dat:self-direct`）；Clash 侧则要拆成两个文件（`behavior` 不同）。

## 用法

### Clash / mihomo

```yaml
rule-providers:
  self-direct:
    type: http
    behavior: domain
    format: yaml
    interval: 86400
    url: https://raw.githubusercontent.com/xinvxueyuan/proxy-rules/main/dist/clash/self-direct.yaml
  self-proxy:
    type: http
    behavior: domain
    format: yaml
    interval: 86400
    url: https://raw.githubusercontent.com/xinvxueyuan/proxy-rules/main/dist/clash/self-proxy.yaml
  self-reject:
    type: http
    behavior: domain
    format: yaml
    interval: 86400
    url: https://raw.githubusercontent.com/xinvxueyuan/proxy-rules/main/dist/clash/self-reject.yaml
  self-direct-ip:
    type: http
    behavior: ipcidr
    format: yaml
    interval: 86400
    url: https://raw.githubusercontent.com/xinvxueyuan/proxy-rules/main/dist/clash/self-direct-ip.yaml

rules:
  - RULE-SET,self-reject,REJECT
  # 与公共大列表并用（不合并进本仓产物）
  # - RULE-SET,category-ads-all,REJECT
  - RULE-SET,self-direct,DIRECT
  - RULE-SET,self-direct-ip,DIRECT,no-resolve
  - RULE-SET,self-proxy,PROXY
  - MATCH,PROXY
```

国内可达性差的网络里，把 `raw.githubusercontent.com` 换成 jsDelivr 镜像：
`https://cdn.jsdelivr.net/gh/xinvxueyuan/proxy-rules@main/dist/clash/<name>.yaml`。

### Xray

`ext:` 引用的文件必须放在**资源目录**（启动时的当前目录，或用 `XRAY_LOCATION_ASSET` 指定）：

```bash
XRAY_LOCATION_ASSET=/usr/local/share/xray xray run -c /etc/xray/config.json
```

```json
{
  "routing": {
    "domainStrategy": "IPIfNonMatch",
    "rules": [
      { "type": "field", "outboundTag": "blocked",
        "domain": ["ext:self-geosite.dat:self-reject", "geosite:category-ads-all"] },
      { "type": "field", "outboundTag": "direct",
        "domain": ["ext:self-geosite.dat:self-direct", "geosite:cn"],
        "ip": ["ext:self-geoip.dat:self-direct", "geoip:private"] },
      { "type": "field", "outboundTag": "proxy",
        "domain": ["ext:self-geosite.dat:self-proxy"] },
      { "type": "field", "outboundTag": "proxy", "network": "tcp,udp" }
    ]
  }
}
```

Xray 还支持**按 URL 热更新** `.dat`（不用重启、不用手动 scp）：

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

### ⚠️ 产物为什么不叫 `geosite.dat` / `geoip.dat`

Xray 的 `geosite:` / `geoip:` 内置引用读的是资源目录里**固定文件名** `geosite.dat` / `geoip.dat`。
自建产物若用这两个名字，一旦放进资源目录就会**把官方那份顶掉** —— 于是配置里并写的
`geosite:cn`、`geoip:private` 全部解析失败（实测报 `illegal ip rule: geoip:private ... EOF`）。

所以自建产物用 `self-` 前缀：与官方 dat **并存**，`ext:self-geosite.dat:<tag>` 引用自建，
`geosite:<tag>` 引用官方，两边互不遮蔽。CI 的校验步骤就是把两份同时放进资源目录跑的。

### 关于 tag 大小写与条数（实测结论）

- **tag 匹配大小写不敏感**：`self-direct` 与 `SELF-DIRECT` 都能用
  （`dlc` 生成时把 tag 存成大写，Xray 查询时统一转大写）。实测环境 Xray 26.9.9。
- **`ext:` 里写不存在的 tag 会直接报错**（`failed to check code XXX from ...`），
  所以「配置能起来」就等于「tag 真的存在」——不会静默失效。
- **两种格式的条数可能不同，但语义等价**：`dlc` 会剪掉被父域覆盖的冗余子域
  （`data/domains/self-direct` 里的 `weixin.qq.com` 被同列表的 `domain:qq.com` 覆盖，
  于是不进 dat），而 Clash 侧保留。CI 的 `scripts/verify_consistency.py` 会断言
  「dat 的每条都在 Clash 里」且「只在 Clash 里的每条都被某个父域覆盖」，
  既不允许真丢条目，也允许合理的剪枝差异。IP 列表不做剪枝，两侧必须完全相等。

## 编辑规则（唯一入口：`data/`）

```
data/domains/<name>     v2fly domain-list 语法 → geosite tag 与 Clash domain 规则
data/ip/<name>.txt     每行一个 IP/CIDR       → geoip tag 与 Clash ipcidr 规则
```

`data/domains/` 的语法（与 [domain-list-community](https://github.com/v2fly/domain-list-community) 一致）：

```
# 注释
domain:example.com        # 匹配 example.com 及其所有子域
full:a.example.com        # 仅精确匹配
keyword:xxx               # 子串匹配
regexp:^a.*\.example$     # 正则
include:other-file        # 引用同目录另一文件
```

新增一个列表 = 在 `data/domains/` 丢一个文件（文件名即 tag），**不用改脚本**。

⚠️ 两个约定：

1. **`keyword:` / `regexp:` 会让该列表整体改用 Clash `behavior: classical` 输出**
   （`<name>.classical.yaml`，`behavior: domain` 表达不了这两个语义）。构建脚本会打印提示，
   记得把 rule-provider 的 `behavior` 一起改掉，否则规则静默不生效。
2. **`data/ip/` 下不要放空列表**（只有注释也算空）：geoip 工具对零条目输入会直接失败。
   域名类拦截请放 `data/domains/self-reject`。

## 为什么公共规则不合并进产物

自持规则编译成产物、公共规则在客户端**另外并写一条引用**，是有意的取舍：

- **可复现**：上游列表怎么变都不会悄悄改变你的出口行为（排查「昨天还好今天怎么全走了代理」时这点很值钱）；
- **可切换**：换掉/停用某个公共列表只改配置，不用等重新构建；
- **体积可控**：`geosite:cn`、`category-ads-all` 这类合并进来会让 `geosite.dat` 从几十 KB 涨到数 MB，
  而客户端本来就能直接引用它们。

想真正合并时：把需要的上游 `data/` 目录一起喂给 `dlc --datapath`，并在你的列表里写
`include:那个文件名`——注意 `include` 链会牵进很多文件，产物会明显变大。

## 构建与校验（CI）

`.github/workflows/build.yml`：push / 每天定时 / 手动触发。流程：

1. `scripts/build_clash.py` 生成 `dist/clash/*.yaml` 与 `MANIFEST.json`；
2. `scripts/build_xray.sh` 用官方工具生成 `geosite.dat`（[dlc](https://github.com/v2fly/domain-list-community)）
   与 `geoip.dat`（[v2fly/geoip](https://github.com/v2fly/geoip)）；
3. **`scripts/verify.sh` 用真实内核加载产物**（下载最新 Xray 与 mihomo）：
   - Xray 侧跑 `xray run -test`，把自建 dat 与**官方 dat 一起**放进资源目录，
     既验证能加载，也验证不会遮蔽 `geosite:cn` / `geoip:private` 这类官方引用；
   - Clash 侧**真启动 mihomo** 并查 `/providers/rules` 的真实 `ruleCount`，
     与 `MANIFEST.json` 逐项对齐；
   - 两侧都跑**变异检验**（dat 缺失/损坏、rule-provider 空文件/条数不符必须报错），
     否则校验本身就是个空壳；
4. `scripts/verify_consistency.py` 断言两种格式语义等价（见下）；
4. 提交 `dist/`，并把两个 `.dat` 发布到 `rules-latest` Release（地址固定，见上表）。

本地复现：

```bash
python3 scripts/build_clash.py          # 纯标准库
bash scripts/build_xray.sh              # 需要 go（dlc + v2fly/geoip）
bash scripts/verify.sh                  # 需要 curl / unzip / python3
python3 scripts/verify_consistency.py   # 需要先有 dist/xray/*.dat
```

> ⚠️ `dist/` 由 CI 生成并提交，**本地跑构建后不要提交 dist**：
> 产物按 LF 写入（`newline="\n"`），但本地工作区可能被 git 换成 CRLF，
> 会让 `MANIFEST.json` 里的 sha256 与 CI 的不一致、天天产生无意义 diff。

## 内核版本

产物对内核的要求按当前最新版对齐：**mihomo v1.19.32**、**Xray v26.9.30**。

- Xray 的 `releases/latest` 只指到 `v26.3.27`，新版本走 **pre-release** 通道；
  CI 取的是「最新一个 release（含 pre-release）」，避免拿到半年前的版本。
- `ext:` 规则集与 `geodata` 热更新都是较新的能力，太旧的内核请先升级再用本仓产物。

## License

MIT（见 [LICENSE](LICENSE)）。规则内容为自持整理，公共来源见 `sources.yaml`。
