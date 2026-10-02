#!/usr/bin/env python3
"""拉取 sources.json 里声明的上游域名列表，规范化成 dlc domain-list 语法。

为什么要有这一步：
    「国内域名直连」需要一份覆盖足够全的国内域名表（约 11 万条），
    手工维护不现实，所以从上游拉取并**规范成与自持规则同一种语法**，
    这样 Clash 与 Xray 两侧的编译脚本都不需要知道上游格式。

关键设计：
  - 抓下来的文件写进 data/domains/<tag>，并被 .gitignore 排除
    → 仓库里不存 2MB 的每日变动数据，只有产物（在 dist 分支与 Release）。
  - 规范化时保留「精确 / 后缀」的区别（实测确认过语义）：
        Clash '+.x'  = 该域及子域  →  dlc 'domain:x'
        Clash 'x'    = 仅精确匹配  →  dlc 'full:x'
    mihomo 实测：bare 写法不匹配子域、'+.' 写法匹配自身与子域。
  - 记录 provenance（源 URL / sha256 / 条数 / 时间）到 dist/PROVENANCE.json，
    让每个产物都能追溯回上游那一刻的内容。

用法：
    python3 scripts/fetch_upstream.py            # 按 sources.json 全量拉取
    python3 scripts/fetch_upstream.py --check    # 只检查声明与本地文件是否齐备
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCES = ROOT / "sources.json"
# 上游数据独立成目录（整目录被 .gitignore 排除）：与自持规则分开放，
# 既避免误把 2MB 的每日变动文件提交进 main，也让「哪些是自有的、哪些是拉来的」一目了然。
UPSTREAM_DIR = ROOT / "data" / "upstream"
PROVENANCE = ROOT / "dist" / "PROVENANCE.json"
UA = "proxy-rules-fetch/1.0 (+https://github.com/xinvxueyuan/proxy-rules)"


def load_sources() -> dict:
    return json.loads(SOURCES.read_text(encoding="utf-8"))


def download(url: str, timeout: int = 180) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


# ── 各上游格式 → dlc domain-list 语法 ───────────────────────────────────
def parse_clash_domain(text: str) -> tuple[list[str], list[str], dict]:
    """Loyalsoldier 的 direct.txt 之类：每行 `- 'x'` 或 `- '+.x'`（可能带缩进/引号）。"""
    suffix: list[str] = []
    exact: list[str] = []
    stats = {"bare": 0, "plus": 0, "skipped": 0}
    for raw in text.splitlines():
        s = raw.strip()
        if not s or s.startswith("#") or s in ("payload:",):
            continue
        if s.startswith("- "):
            s = s[2:].strip()
        s = s.strip().strip("'\"")
        if not s:
            continue
        s = s.lower()
        if s.startswith("+."):
            suffix.append(s[2:])
            stats["plus"] += 1
        elif s.startswith("*."):
            suffix.append(s[2:])
            stats["plus"] += 1
        elif any(c in s for c in ":,/"):
            # DOMAIN-KEYWORD,xxx / IP-CIDR 之类本仓不处理的形态
            stats["skipped"] += 1
        elif "*" in s or "?" in s:
            stats["skipped"] += 1
        else:
            exact.append(s)
            stats["bare"] += 1
    return suffix, exact, stats


PARSERS = {"clash-domain": parse_clash_domain}


def to_domain_list(suffix: list[str], exact: list[str]) -> tuple[str, dict]:
    """输出 dlc 语法文本；后缀用 domain:，精确用 full:；排序去重保证可复现。"""
    sd = sorted(set(suffix))
    ed = sorted(set(exact) - set(sd))     # 已是后缀的不必再写精确
    body = [f"domain:{d}" for d in sd] + [f"full:{d}" for d in ed]
    header = (
        f"# ⚠️ 本文件由 scripts/fetch_upstream.py 自动生成，**请勿手改**\n"
        f"# 来源与许可证见 sources.json；要改规则请改 data/domains/self-*。\n"
        f"# domain: 后缀匹配（含子域）{len(sd)} 条；full: 精确匹配 {len(ed)} 条\n"
    )
    return header + "\n".join(body) + "\n", {"suffix": len(sd), "exact": len(ed),
                                             "total": len(sd) + len(ed)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只检查本地是否齐备，不联网")
    args = ap.parse_args()

    src = load_sources()
    upstream = src.get("upstream", [])
    if not upstream:
        print("sources.json 里没有 upstream 声明")
        return 0

    if args.check:
        missing = []
        for item in upstream:
            p = UPSTREAM_DIR / item["tag"]
            n = sum(1 for _ in p.open(encoding="utf-8")) if p.exists() else 0
            state = f"{n} 行" if p.exists() else "缺失"
            print(f"  {item['tag']:<16} {state}")
            if not p.exists() or n < 10:
                missing.append(item["tag"])
        if missing:
            print(f"\n❌ 缺失/异常：{missing}（先跑 scripts/fetch_upstream.py）")
            return 1
        print("\n✅ 上游数据齐备")
        return 0

    UPSTREAM_DIR.mkdir(parents=True, exist_ok=True)
    record = {"fetched_by": "scripts/fetch_upstream.py", "sources": []}
    problems: list[str] = []

    for item in upstream:
        tag, url, fmt = item["tag"], item["url"], item["format"]
        parser = PARSERS.get(fmt)
        if parser is None:
            print(f"❌ {tag}: 不支持的 format={fmt}")
            return 2
        print(f"== {tag} ==")
        print(f"   来源: {url}")
        try:
            raw = download(url)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            print(f"   ❌ 下载失败：{e}")
            problems.append(f"{tag}: {e}")
            continue

        suffix, exact, stats = parser(raw.decode("utf-8", "replace"))
        text, counts = to_domain_list(suffix, exact)
        out = UPSTREAM_DIR / tag
        out.write_text(text, encoding="utf-8", newline="\n")

        sha_raw = hashlib.sha256(raw).hexdigest()
        sha_norm = hashlib.sha256(text.encode("utf-8")).hexdigest()
        print(f"   原始 {len(raw):,} 字节 sha256={sha_raw[:16]}")
        print(f"   {stats}")
        print(f"   规范化 {counts} → {out.relative_to(ROOT)} ({len(text):,} 字节)")
        record["sources"].append({
            "tag": tag,
            "url": url,
            "format": fmt,
            "repo": item.get("repo"),
            "license": item.get("license"),
            "purpose": item.get("purpose"),
            "raw_bytes": len(raw),
            "raw_sha256": sha_raw,
            "normalized_sha256": sha_norm,
            "entries": counts,
            "parse_stats": stats,
        })

        if counts["total"] < 1000:
            problems.append(f"{tag}: 规范化后仅 {counts['total']} 条，疑似上游结构变了")

    PROVENANCE.parent.mkdir(parents=True, exist_ok=True)
    PROVENANCE.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8", newline="\n")
    print(f"\nprovenance → {PROVENANCE.relative_to(ROOT)}")

    if problems:
        print("\n❌ 有问题：")
        for p in problems:
            print(f"   - {p}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
