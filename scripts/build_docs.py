#!/usr/bin/env python3
"""生成 GitHub Pages 站点内容（放进 dist/，与产物同目录）。

为什么把站点建在 dist 分支：
    Pages 一个仓库只能有一个站点。产物在 dist 分支，把文档页也放进同一个分支，
    这样「订阅链接」与「文档」同源同域，客户端与人都只记一个地址：
        https://xinvxueyuan.github.io/proxy-rules/
        https://xinvxueyuan.github.io/proxy-rules/clash/site.cn.yaml
        https://xinvxueyuan.github.io/proxy-rules/xray/self-geosite.dat

产出：
    dist/index.html          文档/导航页（自包含，无外部依赖）
    dist/.nojekyll           关掉 Jekyll —— 否则 Pages 会处理/过滤我们的文件
    dist/examples/clash.yaml 可直接复制的 Clash 片段
    dist/examples/xray.json  可直接复制的 Xray 片段
    dist/index.json          机器可读的产物索引（给脚本用）

内容里的规则示例必须与 verify/ 下的配置保持一致（尤其 Xray 的 domain/ip 必须拆两条
—— 同一条规则里两者是 AND，混写会永不命中，而 run -test 照样通过）。
"""

from __future__ import annotations

import html
import json
import pathlib
import sys
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
CLASH_DIR = DIST / "clash"
SOURCES = ROOT / "sources.json"
PROVENANCE = DIST / "PROVENANCE.json"

# Pages 站点根（无尾斜杠）。改名/换域名时只改这里。
PAGES_BASE = "https://xinvxueyuan.github.io/proxy-rules"
REPO_URL = "https://github.com/xinvxueyuan/proxy-rules"

# 不在 sources.json groups 里的组的手写说明
EXTRA_LABELS = {
    "self-direct": ("自持直连补充", "手写覆盖层，优先级高于上游大名单"),
    "self-proxy": ("自持强制代理", "用来覆盖上游大名单的误判（该走代理的域名）"),
    "self-direct-ip": ("自持直连 IP", "国内公共 DNS 等按 IP 直连"),
}


def build_index_json(manifest: dict) -> dict:
    """机器可读索引：标签、行为、条数、直链。"""
    items = []
    for a in manifest["artifacts"]:
        items.append({
            "tag": a["name"],
            "behavior": a["behavior"],
            "entries": a["entries"],
            "file": a["file"],
            # 唯一订阅基址下的一条直链（不再给 raw / Release 备用地址：
            # 多一个渠道就多一处要同步的文档，也容易让客户端配到不同来源）
            "url": f"{PAGES_BASE}/clash/{a['file']}",
        })
    return {
        "generated_by": "scripts/build_docs.py",
        "pages_base": PAGES_BASE,
        "repo": REPO_URL,
        "artifacts": items,
    }


def cf_snippet() -> str:
    """Clash rule-providers + rules 片段（域名与 IP 各自成条）。"""
    providers = [
        ("advert.com", "domain"), ("advert.cn", "domain"),
        ("self-proxy", "domain"), ("site.cn", "domain"),
        ("self-direct", "domain"), ("self-direct-ip", "ipcidr"),
    ]
    lines = ["rule-providers:"]
    for tag, behavior in providers:
        lines += [
            f"  {tag}:",
            "    type: http",
            f"    behavior: {behavior}",
            "    format: yaml",
            "    interval: 86400",
            f"    url: {PAGES_BASE}/clash/{tag}.yaml",
        ]
    lines += [
        "",
        "rules:",
        "  - RULE-SET,advert.com,REJECT",
        "  - RULE-SET,advert.cn,REJECT",
        "  - RULE-SET,self-proxy,PROXY",
        "  - RULE-SET,site.cn,DIRECT",
        "  - RULE-SET,self-direct,DIRECT",
        "  - RULE-SET,self-direct-ip,DIRECT,no-resolve",
        "  - GEOIP,CN,DIRECT,no-resolve",
        "  - MATCH,PROXY",
        "",
    ]
    return "\n".join(lines)


def xray_snippet() -> str:
    """Xray routing 片段：domain 与 ip **必须**拆成两条规则。"""
    return json.dumps({
        "_comment": "domain 与 ip 必须拆成两条规则：同一条规则里两者是 AND，混写会永不命中（而 run -test 照样通过）。",
        "routing": {
            "domainStrategy": "IPIfNonMatch",
            "rules": [
                {"type": "field", "outboundTag": "blocked",
                 "domain": [f"ext:self-geosite.dat:advert.com",
                            f"ext:self-geosite.dat:advert.cn"]},
                {"type": "field", "outboundTag": "proxy",
                 "domain": ["ext:self-geosite.dat:self-proxy"]},
                {"type": "field", "outboundTag": "direct",
                 "domain": ["ext:self-geosite.dat:site.cn",
                            "ext:self-geosite.dat:self-direct"]},
                {"type": "field", "outboundTag": "direct",
                 "ip": ["ext:self-geoip.dat:self-direct", "geoip:private", "geoip:cn"]},
                {"type": "field", "outboundTag": "proxy", "network": "tcp,udp"},
            ],
        },
        "_bootstrap": "首次部署必须先手动下载一次 self-*.dat 放到资源目录："
                      "geodata 是「配置校验通过后才下载」，不能做首次引导（文件不存在时校验直接失败）。"
                      "例：curl -fsSLO https://xinvxueyuan.github.io/proxy-rules/xray/self-geosite.dat",
        "geodata": {
            "cron": "@daily",
            "assets": [
                {"url": f"{PAGES_BASE}/xray/self-geosite.dat", "file": "self-geosite.dat"},
                {"url": f"{PAGES_BASE}/xray/self-geoip.dat", "file": "self-geoip.dat"},
            ],
        },
    }, ensure_ascii=False, indent=2) + "\n"


def render_html(labels: dict[str, str], manifest: dict, built_at: str) -> str:
    e = html.escape
    rows = []
    for a in sorted(manifest["artifacts"], key=lambda x: x["name"]):
        tag = a["name"]
        label = labels.get(tag, "")
        behavior = a["behavior"]
        entries = f"{a['entries']:,}"
        url = f"{PAGES_BASE}/clash/{a['file']}"
        rows.append(
            f'<tr><td><code>{e(tag)}</code></td><td>{e(label)}</td>'
            f'<td class="num">{e(behavior)}</td><td class="num">{entries}</td>'
            f'<td><a href="{e(url)}">yaml</a></td></tr>'
        )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>proxy-rules — 自用分流规则（Clash / Xray）</title>
<meta name="description" content="自用分流规则：一份自持数据编译成 mihomo rule-provider 与 Xray geosite/geoip dat，定时构建并发布。">
<style>
  :root {{ color-scheme: light dark; --fg:#1f2328; --muted:#59636e; --line:#d8dee4;
           --bg:#fff; --code-bg:#f6f8fa; --accent:#0969da; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --fg:#e6edf3; --muted:#9198a1; --line:#30363d; --bg:#0d1117;
             --code-bg:#161b22; --accent:#4493f8; }}
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; padding:2rem 1.25rem 4rem; background:var(--bg); color:var(--fg);
          font:16px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans SC",sans-serif; }}
  main {{ max-width: 60rem; margin: 0 auto; }}
  h1 {{ font-size:1.9rem; margin:0 0 .35rem; }}
  h2 {{ font-size:1.25rem; margin:2.4rem 0 .8rem; padding-bottom:.35rem;
        border-bottom:1px solid var(--line); }}
  p.lead {{ color:var(--muted); margin:0 0 1.6rem; }}
  a {{ color:var(--accent); text-decoration:none; }}
  a:hover {{ text-decoration:underline; }}
  code {{ background:var(--code-bg); padding:.15em .35em; border-radius:4px;
          font:0.9em ui-monospace,SFMono-Regular,Consolas,monospace; }}
  pre {{ background:var(--code-bg); padding:.9rem 1rem; border-radius:8px; overflow-x:auto;
         border:1px solid var(--line); }}
  pre code {{ background:none; padding:0; }}
  table {{ border-collapse:collapse; width:100%; font-size:.94rem; }}
  th,td {{ text-align:left; padding:.45rem .6rem; border-bottom:1px solid var(--line); }}
  th {{ color:var(--muted); font-weight:600; }}
  td.num {{ white-space:nowrap; font-variant-numeric:tabular-nums; }}
  .meta {{ display:flex; flex-wrap:wrap; gap:.4rem .6rem; margin:0 0 1.2rem; padding:0; list-style:none; }}
  .meta li {{ font-size:.85rem; color:var(--muted); border:1px solid var(--line);
              border-radius:999px; padding:.15rem .7rem; }}
  .note {{ border-left:3px solid var(--accent); padding:.5rem .9rem; margin:1rem 0;
           background:var(--code-bg); border-radius:0 6px 6px 0; }}
  footer {{ margin-top:3rem; padding-top:1rem; border-top:1px solid var(--line);
            color:var(--muted); font-size:.85rem; }}
</style>
</head>
<body>
<main>
  <h1>proxy-rules</h1>
  <p class="lead">自用分流规则：一份自持数据，编译成 <strong>mihomo（Clash.Meta）</strong> 与
     <strong>Xray</strong> 两种格式，定时构建并发布。</p>
  <ul class="meta">
    <li>站点：<a href="{e(REPO_URL)}">仓库</a></li>
    <li><a href="{e(REPO_URL)}/actions/workflows/build.yml">构建状态</a></li>
    <li><a href="{e(REPO_URL)}/tree/dist">产物分支</a></li>
    <li>最后构建：{e(built_at)}</li>
  </ul>

  <div class="note">
    <strong>分流模型</strong>：广告/追踪 → 拒绝 ｜ 自持强制代理 → 代理 ｜
    国内域名与 IP → 直连 ｜ <strong>其余一切 → 代理（兜底）</strong>。
  </div>

  <h2>订阅地址</h2>
  <p><strong>唯一订阅基址</strong>（每日构建后单快照覆盖，没有历史版本，任何时刻取到的都是最新一次构建）：</p>
  <pre><code>{e(PAGES_BASE)}/</code></pre>
  <p>在该基址下按 tag 取文件：</p>
  <table>
    <tr><th>用途</th><th>路径</th></tr>
    <tr><td>Clash / mihomo rule-provider</td>
        <td><code>{e(PAGES_BASE)}/clash/&lt;tag&gt;.yaml</code></td></tr>
    <tr><td>Xray 域名规则集</td>
        <td><code>{e(PAGES_BASE)}/xray/self-geosite.dat</code></td></tr>
    <tr><td>Xray IP 规则集</td>
        <td><code>{e(PAGES_BASE)}/xray/self-geoip.dat</code></td></tr>
    <tr><td>产物索引（机器可读）</td>
        <td><code>{e(PAGES_BASE)}/index.json</code></td></tr>
  </table>
  <div class="note">
    客户端仍按 tag 引多个 rule-provider（拦截 / 直连 / 代理是不同动作，必须分开），
    但<strong>地址只有一个前缀</strong>。本页由构建流程自动生成，与产物一起发布，
    所以站点上的文件与订阅内容永远同一次构建、不会错位。
  </div>

  <h2>Clash / mihomo</h2>
  <pre><code>{e(cf_snippet())}</code></pre>

  <h2>Xray</h2>
  <pre><code>{e(xray_snippet())}</code></pre>
  <div class="note">
    <strong>首次部署必须先放一次 dat</strong>：<code>geodata</code> 是「配置校验通过后才下载」，
    <strong>不能</strong>做首次引导 —— 文件不存在时配置校验直接失败退出
    （<code>failed to open self-geosite.dat</code>）。先执行：
    <pre><code>mkdir -p /usr/local/share/xray &amp;&amp; cd /usr/local/share/xray
curl -fsSLO {e(PAGES_BASE)}/xray/self-geosite.dat
curl -fsSLO {e(PAGES_BASE)}/xray/self-geoip.dat
curl -fsSLo geosite.dat https://github.com/v2fly/domain-list-community/releases/latest/download/dlc.dat
curl -fsSLo geoip.dat   https://github.com/v2fly/geoip/releases/latest/download/geoip.dat</code></pre>
    之后 <code>geodata</code> 的 cron 才会接管更新。
  </div>
  <div class="note">
    自建产物命名为 <code>self-geosite.dat</code> / <code>self-geoip.dat</code>，
    避免与官方同名文件互相遮蔽（同名会让并写的 <code>geosite:cn</code>、
    <code>geoip:private</code> 解析失败）。引用时用 <code>ext:self-geosite.dat:&lt;tag&gt;</code>。
  </div>

  <h2>规则组（共 {len(manifest['artifacts'])} 个）</h2>
  <table>
    <tr><th>tag</th><th>说明</th><th>behavior</th><th>条数</th><th>Clash 文件</th></tr>
    {''.join(rows)}
  </table>
  <p>另外两个 Xray 专用二进制（不进上面的表）：
     <a href="{e(PAGES_BASE)}/xray/self-geosite.dat"><code>self-geosite.dat</code></a>（域名规则集）、
     <a href="{e(PAGES_BASE)}/xray/self-geoip.dat"><code>self-geoip.dat</code></a>（IP 规则集）。</p>

  <h2>校验与保证</h2>
  <p>每次构建都会：</p>
  <ul>
    <li>用<strong>真实内核</strong>加载产物 —— mihomo 启动后查 <code>/providers/rules</code>
        的真实规则条数并与清单逐项对齐；Xray 用 <code>run -test</code> 加载
        <code>ext:</code> 引用的 dat（并与官方 dat 同目录，验证不遮蔽）。</li>
    <li>做<strong>变异检验</strong>：故意删文件 / 写坏内容 / 清空规则集，校验必须报错，
        否则说明校验本身是空壳。</li>
    <li>断言<strong>两种格式语义等价</strong>（同一份组装结果）。</li>
  </ul>

  <footer>
    <p>上游来源与其许可证记录在产物里的 <code>PROVENANCE.json</code>，
       声明在仓库的 <code>sources.json</code>。本仓以 GPL-3.0 发布。</p>
    <p>产物索引（机器可读）：<a href="./index.json"><code>index.json</code></a>。</p>
  </footer>
</main>
</body>
</html>
"""


def main() -> int:
    manifest_path = CLASH_DIR / "MANIFEST.json"
    if not manifest_path.exists():
        print(f"❌ 缺 {manifest_path.relative_to(ROOT)}（先跑 scripts/build_clash.py）")
        return 2

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # 组说明：优先取 sources.json 的 label，再补手写的
    labels: dict[str, str] = {}
    if SOURCES.exists():
        src = json.loads(SOURCES.read_text(encoding="utf-8"))
        for name, g in (src.get("groups") or {}).items():
            if name.startswith("_"):
                continue
            if g.get("label"):
                labels[name] = g["label"]
    for name, (label, note) in EXTRA_LABELS.items():
        labels[name] = f"{label} —— {note}" if name not in labels else labels[name]

    built_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    if PROVENANCE.exists():
        try:
            prov = json.loads(PROVENANCE.read_text(encoding="utf-8"))
            built_at = prov.get("built_at") or built_at
        except Exception:
            pass

    # .nojekyll：关掉 Jekyll，否则 Pages 会处理/过滤文件（含以 _ 开头或含特殊字符的）
    (DIST / ".nojekyll").write_text("", encoding="utf-8", newline="\n")

    (DIST / "index.html").write_text(render_html(labels, manifest, built_at),
                                     encoding="utf-8", newline="\n")
    (DIST / "index.json").write_text(
        json.dumps(build_index_json(manifest), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8", newline="\n")

    ex = DIST / "examples"
    ex.mkdir(parents=True, exist_ok=True)
    (ex / "clash.yaml").write_text(cf_snippet(), encoding="utf-8", newline="\n")
    (ex / "xray.json").write_text(xray_snippet(), encoding="utf-8", newline="\n")

    print(f"生成 Pages 站点内容 → {DIST.relative_to(ROOT)}/")
    print("  index.html        文档/导航页")
    print("  .nojekyll         关闭 Jekyll")
    print("  index.json        机器可读产物索引")
    print("  examples/clash.yaml  examples/xray.json")
    print(f"  站点根: {PAGES_BASE}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
