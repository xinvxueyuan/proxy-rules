# proxy-rules

自用的分流规则仓：**一份自持数据，编译成 Clash/mihomo 与 Xray 两种内核的格式**，定时自动构建发布。

- 自持规则（域名 + IP）是本仓的**单一真相**，改规则只改 `data/`；
- 产物自动生成，**不要手改** `dist/`（CI 每次覆盖）；
- 公共规则集**不合并进产物**，以「引用并按需并用」的方式搭配（理由见下文），
  可引用的清单记录在 [`sources.yaml`](sources.yaml)。

## 产物与获取地址

| 产物 | 用途 | 地址 |
|---|---|---|
| `geosite.dat` | Xray 域名规则集（`ext:geosite.dat:<tag>`） | `https://github.com/xinvxueyuan/proxy-rules/releases/latest/download/geosite.dat` |
| `geoip.dat` | Xray IP 规则集（`ext:geoip.dat:<tag>`） | `https://github.com/xinvxueyuan/proxy-rules/releases/latest/download/geoip.dat` |
| `dist/clash/*.yaml` | mihomo rule-provider | `https://raw.githubusercontent.com/xinvxueyuan/proxy-rules/main/dist/clash/<name>.yaml` |
| `dist/clash/MANIFEST.json` | 每个产物的 behavior / 条数 / sha256 | 同上目录 |

### tag / 文件名一览

| tag（Xray） | 文件（Clash） | Clash behavior | 含义 |
|---|---|---|---|
| `self-direct` | `self-direct.yaml` | `domain` | 直连域名 |
| `self-proxy` | `self-proxy.yaml` | `domain` | 强制走代理的域名 |
| `self-reject` | `self-reject.yaml` | `domain` | 广告 / 跟踪 / 统计，拒掉 |
| `self-direct` | `self-direct-ip.yaml` | `ipcidr` | 直连 IP（国内公共 DNS 等） |

> 注：Xray 侧域名与 IP 是两个维度、**同名 tag 可以并存**（`ext:geosite.dat:self-direct`
> 与 `ext:geoip.dat:self-direct`）；Clash 侧则要拆成两个文件（`behavior` 不同）。

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
        "domain": ["ext:geosite.dat:self-reject", "geosite:category-ads-all"] },
      { "type": "field", "outboundTag": "direct",
        "domain": ["ext:geosite.dat:self-direct", "geosite:cn"],
        "ip": ["ext:geoip.dat:self-direct", "geoip:private"] },
      { "type": "field", "outboundTag": "proxy",
        "domain": ["ext:geosite.dat:self-proxy"] },
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
      { "url": "https://github.com/xinvxueyuan/proxy-rules/releases/latest/download/geosite.dat",
        "file": "geosite.dat" },
      { "url": "https://github.com/xinvxueyuan/proxy-rules/releases/latest/download/geoip.dat",
        "file": "geoip.dat" }
    ]
  }
}
```

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
3. **`scripts/verify.sh` 用真实内核加载产物**（下载最新 Xray 与 mihomo，跑
   `xray run -test` 与 `mihomo -t`）——文件存在不等于规则能用；
4. 提交 `dist/`，并把两个 `.dat` 发布到 `rules-latest` Release（地址固定，见上表）。

本地复现：

```bash
python3 scripts/build_clash.py          # 只需 PyYAML 之外的标准库
bash scripts/build_xray.sh              # 需要 go
bash scripts/verify.sh                  # 需要 curl/unzip/python3
```

## 内核版本

产物对内核的要求按当前最新版对齐：**mihomo v1.19.32**、**Xray v26.9.30**。

- Xray 的 `releases/latest` 只指到 `v26.3.27`，新版本走 **pre-release** 通道；
  CI 取的是「最新一个 release（含 pre-release）」，避免拿到半年前的版本。
- `ext:` 规则集与 `geodata` 热更新都是较新的能力，太旧的内核请先升级再用本仓产物。

## License

MIT（见 [LICENSE](LICENSE)）。规则内容为自持整理，公共来源见 `sources.yaml`。
