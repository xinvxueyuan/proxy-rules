#!/usr/bin/env python3
"""按 sources.json 拉取上游规则并**按生态分类**，生成各组的数据文件。

为什么要有这一步：
  「国内直连」需要约 11 万条国内域名；「广告拦截」需要按生态（谷歌/微软/Meta/推特/Telegram/
  中文互联网）分开的组。手工维护不现实，所以从上游拉取、规范成与自持规则同一种语法
  （dlc domain-list），这样 Clash 与 Xray 两侧的编译脚本都不需要知道上游格式。

分类模型（声明在 sources.json 的 groups 里）：
  - from_suffixes   从底座（advert.base）里按域名后缀挑本组成员
  - from_substrings 同上，但按子串匹配（用于 "goog"、"firebase" 这类）
  - plus            直接并入某个 internal 来源的全部条目（如 native.winoffice → advert.ms）
  - rest_of         底座里**没被任何组挑走**的剩余（= 通用广告网络）
  - union_of        聚合组（advert.com = 通用 ∪ 各生态子组）

关键设计：
  - 抓下来的文件写进 data/upstream/<tag>，被 .gitignore 排除
    → 仓库里不存每日变动的数据，只有产物（在 dist 分支与 Release）。
  - 手工补充不写这里，写 data/extra/<tag>（进 git）；构建时按 tag 合并三个目录，
    这样「上游打底 + 手工补」不会互相覆盖。
  - 记录 provenance（源 URL / sha256 / 条数 / 分类明细）到 dist/PROVENANCE.json。

用法：
    python3 scripts/fetch_upstream.py            # 全量拉取并分类
    python3 scripts/fetch_upstream.py --check    # 只检查本地是否齐备，不联网
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
UPSTREAM_DIR = ROOT / "data" / "upstream"
PROVENANCE = ROOT / "dist" / "PROVENANCE.json"
UA = "proxy-rules-fetch/1.0 (+https://github.com/xinvxueyuan/proxy-rules)"


def load_sources() -> dict:
    return json.loads(SOURCES.read_text(encoding="utf-8"))


def download(url: str, timeout: int = 180) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def parse_clash_domain(text: str) -> tuple[list[str], list[str], dict]:
    """Loyalsoldier 的 direct.txt 之类：每行 `- 'x'` / `- '+.x'`（可能带缩进与引号）。

    语义（实测确认）：
        '+.x' = 该域及子域 → dlc 'domain:x'
        'x'   = 仅精确匹配 → dlc 'full:x'
    """
    suffix: list[str] = []
    exact: list[str] = []
    stats = {"plus": 0, "bare": 0, "skipped": 0}
    for raw in text.splitlines():
        s = raw.strip()
        if not s or s.startswith("#") or s == "payload:":
            continue
        if s.startswith("- "):
            s = s[2:].strip()
        s = s.strip().strip("'\"")
        if not s:
            continue
        s = s.lower()
        if s.startswith(("+.", "*.")):
            suffix.append(s[2:])
            stats["plus"] += 1
        elif any(c in s for c in ":,/"):
            stats["skipped"] += 1
        elif "*" in s or "?" in s:
            stats["skipped"] += 1
        else:
            exact.append(s)
            stats["bare"] += 1
    return suffix, exact, stats


def parse_domains(text: str) -> tuple[list[str], list[str], dict]:
    """纯域名 / hosts 表（hagezi 的 *-onlydomains.txt、1Hosts 等）。

    这些表的语义是「拦该域及其子域」，所以一律按后缀（dlc domain:）处理。
    兼容 hosts 格式（`0.0.0.0 domain`）与通配格式（`*.domain`）。
    """
    suffix: list[str] = []
    stats = {"domains": 0, "skipped": 0}
    for raw in text.splitlines():
        s = raw.strip()
        if not s or s.startswith(("#", "!")):
            continue
        parts = s.split()
        # hosts 格式：首列是 IP；其它格式：只有一列（或末列是域名）
        if len(parts) > 1 and (parts[0][0].isdigit() or ":" in parts[0]):
            cand = parts[1]
        else:
            cand = parts[0]
        cand = cand.strip().lower().rstrip(".")
        if cand.startswith(("*", "+")):
            cand = cand.lstrip("*+").lstrip(".")
        if not cand or cand in ("localhost", "localhost.localdomain", "local", "broadcasthost",
                                "0.0.0.0", "127.0.0.1", "::1", "ip6-localhost", "ip6-loopback"):
            stats["skipped"] += 1
            continue
        if "/" in cand or ":" in cand or "*" in cand or not cand.count("."):
            stats["skipped"] += 1
            continue
        suffix.append(cand)
        stats["domains"] += 1
    return suffix, [], stats


PARSERS = {"clash-domain": parse_clash_domain, "domains": parse_domains}


def matches(domain: str, suffixes: list[str], substrings: list[str]) -> bool:
    for p in suffixes:
        if domain == p or domain.endswith("." + p):
            return True
    for k in substrings:
        if k in domain:
            return True
    return False


def write_domain_list(path: pathlib.Path, suffix: list[str], exact: list[str],
                      header_lines: list[str]) -> dict:
    """输出 dlc 语法：后缀用 domain:、精确用 full:（排序去重，保证可复现）"""
    sd = sorted(set(suffix))
    ed = sorted(set(exact) - set(sd))
    body = [f"domain:{d}" for d in sd] + [f"full:{d}" for d in ed]
    text = "\n".join(header_lines) + "\n" + "\n".join(body) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")
    return {"suffix": len(sd), "exact": len(ed), "total": len(sd) + len(ed)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只检查本地是否齐备，不联网")
    args = ap.parse_args()

    src = load_sources()
    upstream = src.get("upstream", [])
    groups_cfg = {k: v for k, v in (src.get("groups") or {}).items() if not k.startswith("_")}

    if args.check:
        expected = [u["tag"] for u in upstream if not u.get("internal")]
        for gname, g in groups_cfg.items():
            if g.get("from_suffixes") or g.get("from_substrings") or g.get("plus") \
                    or g.get("union_of") or g.get("rest_of"):
                expected.append(gname)
        missing = []
        manual = [ROOT / "data" / "domains", ROOT / "data" / "extra"]
        for tag in sorted(set(expected)):
            n_up = 0
            up = UPSTREAM_DIR / tag
            if up.exists():
                n_up = sum(1 for ln in up.read_text(encoding="utf-8").splitlines()
                           if ln.strip() and not ln.strip().startswith("#"))
            n_manual = 0
            for d in manual:
                f = d / tag
                if f.exists():
                    n_manual += sum(1 for ln in f.read_text(encoding="utf-8").splitlines()
                                    if ln.strip() and not ln.strip().startswith("#"))
            total = n_up + n_manual
            note = f"上游 {n_up} + 手工 {n_manual}" if n_up or n_manual else "缺失"
            print(f"  {tag:<18} {total:>7} 条  （{note}）")
            if total < 1:
                missing.append(tag)
        if missing:
            print(f"\n❌ 缺失/异常：{missing}（先跑 scripts/fetch_upstream.py）")
            return 1
        print("\n✅ 上游数据齐备")
        return 0

    UPSTREAM_DIR.mkdir(parents=True, exist_ok=True)
    record: dict = {"fetched_by": "scripts/fetch_upstream.py", "sources": [], "groups": {}}
    problems: list[str] = []

    # ── 1. 拉取所有来源 ────────────────────────────────────────────────
    fetched: dict[str, dict] = {}
    for item in upstream:
        tag, url, fmt = item["tag"], item["url"], item["format"]
        parser = PARSERS.get(fmt)
        if parser is None:
            print(f"❌ {tag}: 不支持的 format={fmt}")
            return 2
        print(f"== 拉取 {tag} ==")
        print(f"   来源: {url}")
        try:
            raw = download(url)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            print(f"   ❌ 下载失败：{e}")
            problems.append(f"{tag}: {e}")
            continue
        suffix, exact, stats = parser(raw.decode("utf-8", "replace"))
        fetched[tag] = {"suffix": suffix, "exact": exact, "stats": stats}
        sha = hashlib.sha256(raw).hexdigest()
        print(f"   {len(raw):,} 字节 sha256={sha[:16]}  {stats}")
        record["sources"].append({
            "tag": tag, "url": url, "format": fmt, "repo": item.get("repo"),
            "license": item.get("license"), "purpose": item.get("purpose"),
            "internal": bool(item.get("internal")), "raw_bytes": len(raw), "raw_sha256": sha,
            "entries": {"suffix": len(set(suffix)), "exact": len(set(exact))},
        })

    if problems:
        print("\n❌ 有来源拉取失败，拒绝继续（否则会产出缺内容的组）：")
        for p in problems:
            print(f"   - {p}")
        return 1

    # ── 2. 非 internal 来源直接出产物 ─────────────────────────────────
    for item in upstream:
        tag = item["tag"]
        if item.get("internal") or tag not in fetched:
            continue
        f = fetched[tag]
        counts = write_domain_list(
            UPSTREAM_DIR / tag, f["suffix"], f["exact"],
            [f"# ⚠️ 自动生成，请勿手改（要补条目请写 data/extra/{tag}）",
             f"# 来源: {item['url']}",
             f"# 许可: {item.get('license')}   用途: {item.get('purpose')}"])
        print(f"\n  → {tag}: {counts}")
        record["groups"][tag] = {"role": "source", "entries": counts,
                                 "origin": item["url"], "license": item.get("license")}
        if counts["total"] < 1000:
            problems.append(f"{tag}: 仅 {counts['total']} 条，疑似上游结构变了")

    base_set = set(fetched.get("advert.base", {}).get("suffix", []))

    # ── 3. 分类：先叶子组，再聚合组 ───────────────────────────────────
    classified: dict[str, set[str]] = {}
    taken: set[str] = set()
    for name, g in groups_cfg.items():
        if g.get("union_of"):
            continue
        suf, sub = g.get("from_suffixes") or [], g.get("from_substrings") or []
        picked = {d for d in base_set if matches(d, suf, sub)} if (suf or sub) else set()
        members = set(picked)
        for extra_tag in g.get("plus") or []:
            members |= set(fetched.get(extra_tag, {}).get("suffix", []))
        classified[name] = members
        taken |= picked

    for name, g in groups_cfg.items():
        if not g.get("union_of"):
            continue
        members: set[str] = set()
        for other in g["union_of"]:
            members |= classified.get(other, set())
        if g.get("rest_of"):
            members |= (base_set - taken)
        for extra_tag in g.get("plus") or []:
            members |= set(fetched.get(extra_tag, {}).get("suffix", []))
        classified[name] = members

    # ── 4. 写出各组 ───────────────────────────────────────────────────
    print()
    for name in sorted(classified):
        g = groups_cfg[name]
        members = classified[name]
        if not members:
            print(f"  → {name:<12} 0 条（公共源无内容，靠手工层 data/domains|extra 提供）")
            record["groups"][name] = {"role": "group", "label": g.get("label"),
                                      "entries": {"suffix": 0, "exact": 0, "total": 0},
                                      "note": "公共来源无内容，由手工层提供"}
            continue
        counts = write_domain_list(
            UPSTREAM_DIR / name, sorted(members), [],
            [f"# ⚠️ 自动生成，请勿手改（要补条目请写 data/extra/{name}）",
             f"# 组: {g.get('label') or name}",
             f"# 由 scripts/fetch_upstream.py 依 sources.json 的分类规则生成",
             f"# 内容: from_suffixes={'有' if g.get('from_suffixes') else '无'}"
             f"  from_substrings={g.get('from_substrings') or []}"
             f"  plus={g.get('plus') or []}"
             f"  union_of={g.get('union_of') or []}"
             f"  rest_of={g.get('rest_of') or '无'}"])
        print(f"  → {name:<12} {counts['total']:>6} 条   {g.get('label') or ''}")
        record["groups"][name] = {"role": "group", "label": g.get("label"), "entries": counts}

    PROVENANCE.parent.mkdir(parents=True, exist_ok=True)
    PROVENANCE.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n",
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
