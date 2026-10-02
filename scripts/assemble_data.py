#!/usr/bin/env python3
"""把三层规则按 tag 合并成扁平数据目录（build/data/），并解析聚合组。

dlc 只读 datapath 直属的文件、不递归，且**一个文件 = 一个 tag**，所以三层
（data/domains 自持、data/extra 手工补充、data/upstream 上游生成）必须先按 tag
求并集、再各写成一个文件。

为什么需要这一层：若让 build/data 里同时存在两个同名来源，后写入的会静默覆盖前者
（实测踩过：上游那份盖掉手工那份，产物里少了几条却毫无提示）。

为什么聚合组（union_of，如 advert.com）必须在这里算：
    取数阶段（fetch_upstream.py）只能看到上游内容，看不到 data/extra 的手工补充。
    实测踩过：doubleclick.net 只写在 data/extra/advert.gg 里，于是它没进 advert.com，
    客户端只引 advert.com 就漏掉了它。所以聚合要放到三层合并**之后**、按最终内容算。
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOMAIN_DIR = ROOT / "data" / "domains"
EXTRA_DIR = ROOT / "data" / "extra"
UPSTREAM_DIR = ROOT / "data" / "upstream"
OUT = ROOT / "build" / "data"
SOURCES = ROOT / "sources.json"

LAYERS = (DOMAIN_DIR, EXTRA_DIR, UPSTREAM_DIR)


def parse(path: pathlib.Path) -> list[str]:
    """取有效行（去注释、去空行），保留原始指令形态"""
    out = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        s = raw.split("#", 1)[0].strip()
        if s:
            out.append(s)
    return out


def main() -> int:
    by_tag: dict[str, list[pathlib.Path]] = {}
    for d in LAYERS:
        if not d.is_dir():
            continue
        for p in sorted(d.glob("*")):
            if p.is_file() and not p.name.startswith("."):
                by_tag.setdefault(p.name, []).append(p)

    OUT.mkdir(parents=True, exist_ok=True)
    for stale in OUT.glob("*"):
        if stale.is_file():
            stale.unlink()

    # 1) 按 tag 合并三层
    merged: dict[str, list[str]] = {}
    layers_used: dict[str, list[str]] = {}
    for tag, paths in sorted(by_tag.items()):
        lines: list[str] = []
        seen: set[str] = set()
        for p in paths:
            for item in parse(p):
                if item not in seen:
                    seen.add(item)
                    lines.append(item)
        merged[tag] = lines
        layers_used[tag] = [str(p.relative_to(ROOT)).replace("\\", "/") for p in paths]

    # 2) 解析聚合组（union_of）——必须在三层合并之后
    src = json.loads(SOURCES.read_text(encoding="utf-8")) if SOURCES.exists() else {}
    aggregates: dict[str, list[str]] = {}
    for gname, g in (src.get("groups") or {}).items():
        if gname.startswith("_") or not g.get("union_of"):
            continue
        aggregates[gname] = [m for m in g["union_of"] if m in merged]

    for gname, members in sorted(aggregates.items()):
        base = merged.setdefault(gname, [])
        seen = set(base)
        added = 0
        for m in members:
            for item in merged.get(m, []):
                if item not in seen:
                    seen.add(item)
                    base.append(item)
                    added += 1
        layers_used.setdefault(gname, []).append("聚合(" + "+".join(members) + ")")
        print(f"  聚合 {gname} ← {'+'.join(members)}  并入 {added} 条")

    # 3) 写出
    rows = []
    for tag, lines in sorted(merged.items()):
        srcs = layers_used.get(tag, [])
        header = [f"# {tag} — 由 scripts/assemble_data.py 合并 {len(srcs)} 个来源生成",
                  f"# 来源: {', '.join(srcs)}",
                  f"# 条目: {len(lines)}"]
        (OUT / tag).write_text("\n".join(header) + "\n" + "\n".join(lines) + "\n",
                               encoding="utf-8", newline="\n")
        rows.append((tag, len(lines), len(srcs)))

    print(f"合并 {len(rows)} 个 tag → {OUT.relative_to(ROOT)}/")
    for tag, n, nsrc in rows:
        print(f"  {tag:<14} {n:>7} 条  （{nsrc} 个来源）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
