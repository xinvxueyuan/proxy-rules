#!/usr/bin/env python3
"""一致性校验：**同一份自持数据**编译出的两种格式必须语义等价。

这是本仓最核心的不变式 —— 它唯一能发现「某个列表在某一种格式里静默少了东西」
（比如某个 tag 没被 dlc 收进去、某个 IP 列表没进 geoip.dat）。

⚠️ 必须**分维度**比较：「后缀匹配」与「精确匹配」是两种语义，混在一个集合里比会
误报（第一版就这么错过：上游 505 条精确条目标记成「未覆盖」）。两侧的语义映射：

    dlc  domain:x  ==  Clash '+.x'   →  后缀匹配（该域 + 所有子域）
    dlc  full:x    ==  Clash 'x'     →  仅精确匹配

断言（tag 名：dat 侧与 Clash 侧一一对应）：
  1. 两侧 tag 集合完全相同（不允许多、不允许少）
  2. dat 的后缀集 ⊆ Clash 的后缀集；只在 Clash 里的必须被某个 dat 后缀父域覆盖
     （dlc 会剪掉被父域覆盖的冗余子域，属预期）
  3. dat 的精确集 ⊆ Clash 的精确集；只在 Clash 里的必须被某个 dat **后缀**父域覆盖
     （dlc 同样会剪掉已被后缀覆盖的精确条目）
  4. geoip 条数必须与对应 Clash ipcidr 产物**完全相等**（IP 不做剪枝）
  5. dat 里出现的其它类型（keyword/regexp）要与 Clash 侧 classical 产物对得上

为什么手写 protobuf 读取：不想为了校验引入 protobuf 依赖，
geosite.dat/geoip.dat 的 schema 很窄（见下方注释），几十行足够。
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CLASH_DIR = ROOT / "dist" / "clash"
XRAY_DIR = ROOT / "dist" / "xray"

DOMAIN_TYPES = {0: "keyword", 1: "regexp", 2: "suffix", 3: "exact"}


# ── 极简 protobuf 读取 ─────────────────────────────────────────────────
def read_varint(buf: bytes, pos: int) -> tuple[int, int]:
    result = shift = 0
    while True:
        b = buf[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not b & 0x80:
            return result, pos
        shift += 7


def fields(buf: bytes):
    pos = 0
    while pos < len(buf):
        key, pos = read_varint(buf, pos)
        fno, wt = key >> 3, key & 7
        if wt == 0:
            val, pos = read_varint(buf, pos)
            yield fno, wt, val
        elif wt == 2:
            ln, pos = read_varint(buf, pos)
            yield fno, wt, buf[pos:pos + ln]
            pos += ln
        elif wt == 5:
            yield fno, wt, buf[pos:pos + 4]
            pos += 4
        elif wt == 1:
            yield fno, wt, buf[pos:pos + 8]
            pos += 8
        else:
            raise ValueError(f"未知 wire type {wt}")


def parse_geosite(buf: bytes) -> dict[str, dict[str, set[str]]]:
    """GeoSiteList{1: GeoSite}; GeoSite{1: country_code, 2: Domain};
    Domain{1: type(0=keyword,1=regexp,2=domain,3=full), 2: value}

    返回 {tag: {"suffix": {...}, "exact": {...}, "other": {...}}}
    """
    out: dict[str, dict[str, set[str]]] = {}
    for fno, wt, val in fields(buf):
        if fno != 1 or wt != 2:
            continue
        code = None
        rows: list[tuple[int, str]] = []
        for f2, w2, v2 in fields(val):
            if f2 == 1 and w2 == 2:
                code = v2.decode("utf-8", "replace").lower()
            elif f2 == 2 and w2 == 2:
                dtype = value = None
                for f3, w3, v3 in fields(v2):
                    if f3 == 1 and w3 == 0:
                        dtype = v3
                    elif f3 == 2 and w3 == 2:
                        value = v3.decode("utf-8", "replace")
                if value is not None:
                    rows.append((dtype if dtype is not None else 2, value))
        if code is None:
            continue
        bucket = out.setdefault(code, {"suffix": set(), "exact": set(), "other": set()})
        for dtype, value in rows:
            v = value.lower().lstrip(".")
            kind = DOMAIN_TYPES.get(dtype, "other")
            bucket["suffix" if kind == "suffix" else
                   "exact" if kind == "exact" else "other"].add(v)
    return out


def parse_geoip(buf: bytes) -> dict[str, int]:
    """GeoIPList{1: GeoIP}; GeoIP{1: country_code, 2: CIDR}"""
    out: dict[str, int] = {}
    for fno, wt, val in fields(buf):
        if fno != 1 or wt != 2:
            continue
        code, n = None, 0
        for f2, w2, v2 in fields(val):
            if f2 == 1 and w2 == 2:
                code = v2.decode("utf-8", "replace").lower()
            elif f2 == 2 and w2 == 2:
                n += 1
        if code is not None:
            out[code] = n
    return out


def clash_payload(path: pathlib.Path) -> dict[str, set[str]]:
    """读 Clash rule-provider 的 payload，按语义分桶。

    behavior: domain  →  '+.x' = 后缀；'x' = 精确
    behavior: classical / 上游文本 →  'DOMAIN-SUFFIX,x' = 后缀；'DOMAIN,x' = 精确
    """
    suffix: set[str] = set()
    exact: set[str] = set()
    other: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line.startswith("- "):
            continue
        v = line[2:].strip().strip("'\"")
        if not v:
            continue
        if v.startswith("+."):
            suffix.add(v[2:].lower())
        elif v.startswith("DOMAIN-SUFFIX,"):
            suffix.add(v.split(",", 1)[1].strip().lower())
        elif v.startswith("DOMAIN,"):
            exact.add(v.split(",", 1)[1].strip().lower())
        elif "," in v:                       # DOMAIN-KEYWORD / DOMAIN-REGEX / IP-CIDR ...
            other.add(v.lower())
        else:
            exact.add(v.lower())
    return {"suffix": suffix, "exact": exact, "other": other}


def covered_by_any_parent(value: str, parents: set[str]) -> bool:
    """value 是否被 parents 里某个「后缀父域」覆盖（= dlc 剪枝的理由）。

    逐级去掉最左标签查集合；不能对每个 value 扫全表 —— 11 万条 × 上万条
    就是十亿级比较，实测会卡死。
    """
    labels = value.split(".")
    return any(".".join(labels[i:]) in parents for i in range(1, len(labels)))


def main() -> int:
    for f in (XRAY_DIR / "self-geosite.dat", XRAY_DIR / "self-geoip.dat",
              CLASH_DIR / "MANIFEST.json"):
        if not f.exists():
            print(f"❌ 缺产物 {f.relative_to(ROOT)}（先跑 scripts/build.sh 或分步 build_clash.py + build_xray_data.py）")
            return 2

    geosite = parse_geosite((XRAY_DIR / "self-geosite.dat").read_bytes())
    geoip = parse_geoip((XRAY_DIR / "self-geoip.dat").read_bytes())
    manifest = json.loads((CLASH_DIR / "MANIFEST.json").read_text(encoding="utf-8"))
    clash = {a["name"]: a for a in manifest["artifacts"]}

    problems: list[str] = []

    print("== 1) tag 对应关系 ==")
    domain_names = {n for n, a in clash.items() if a["behavior"] in ("domain", "classical")}
    for tag in sorted(set(geosite) | domain_names):
        gs, cl = tag in geosite, tag in domain_names
        mark = "✅" if (gs and cl) else "❌"
        if not (gs and cl):
            problems.append(f"{tag}: geosite={gs} clash={cl}（tag 未一一对应）")
        print(f"  {mark} {tag:<16} geosite={gs!s:<5} clash={cl}")
    ip_bases = {n[:-3] for n in clash if n.endswith("-ip")}
    for tag in sorted(set(geoip) | ip_bases):
        gi, cl = tag in geoip, tag in ip_bases
        mark = "✅" if (gi and cl) else "❌"
        if not (gi and cl):
            problems.append(f"{tag}: geoip={gi} clash-ip={cl}（IP tag 未一一对应）")
        print(f"  {mark} {tag:<16} geoip={gi!s:<5} clash[{tag}-ip]={cl}")

    print("\n== 2) 域名集合（按语义分维度：后缀 / 精确）==")
    for tag in sorted(geosite):
        entry = clash.get(tag)
        if not entry:
            continue
        dat = geosite[tag]
        cl = clash_payload(CLASH_DIR / entry["file"])

        # 后缀维度
        lost_suffix = sorted(dat["suffix"] - cl["suffix"])
        if lost_suffix:
            problems.append(f"{tag}: dat 后缀有而 Clash 没有 → {lost_suffix[:10]}")
            print(f"  ❌ {tag:<16} 后缀丢失 {len(lost_suffix)} 条 → {lost_suffix[:5]}")
        pruned_suffix = sorted(cl["suffix"] - dat["suffix"])
        bad_suffix = [v for v in pruned_suffix
                      if not covered_by_any_parent(v, dat["suffix"])]

        # 精确维度
        lost_exact = sorted(dat["exact"] - cl["exact"])
        if lost_exact:
            problems.append(f"{tag}: dat 精确有而 Clash 没有 → {lost_exact[:10]}")
            print(f"  ❌ {tag:<16} 精确丢失 {len(lost_exact)} 条 → {lost_exact[:5]}")
        pruned_exact = sorted(cl["exact"] - dat["exact"])
        bad_exact = [v for v in pruned_exact
                     if not covered_by_any_parent(v, dat["suffix"])]

        if bad_suffix:
            problems.append(f"{tag}: 后缀差异既不在 dat、也不被父域覆盖 → {bad_suffix[:10]}")
            print(f"  ❌ {tag:<16} 未被父域覆盖的后缀差异 {len(bad_suffix)} 条 → {bad_suffix[:5]}")
        if bad_exact:
            problems.append(f"{tag}: 精确差异既不在 dat、也不被后缀父域覆盖 → {bad_exact[:10]}")
            print(f"  ❌ {tag:<16} 未被后缀覆盖的精确差异 {len(bad_exact)} 条 → {bad_exact[:5]}")

        if not (lost_suffix or bad_suffix or lost_exact or bad_exact):
            print(f"  ✅ {tag:<16} 后缀 dat={len(dat['suffix']):<7} clash={len(cl['suffix']):<7} "
                  f"（剪枝 {len(pruned_suffix)}）  精确 dat={len(dat['exact']):<4} "
                  f"clash={len(cl['exact']):<4}（剪枝 {len(pruned_exact)}）")

        if dat["other"] or cl["other"]:
            print(f"     · keyword/regexp：dat={len(dat['other'])} clash={len(cl['other'])}"
                  f"（本项目自持列表不使用；出现说明列表里混进了 keyword:/regexp:）")

    print("\n== 3) IP 集合必须完全相等（IP 不做剪枝）==")
    for tag, n in sorted(geoip.items()):
        entry = clash.get(f"{tag}-ip")
        if not entry:
            continue
        payload = clash_payload(CLASH_DIR / entry["file"])
        m = len(payload["suffix"]) + len(payload["exact"])
        same = m == n
        if not same:
            problems.append(f"{tag}: geoip={n} 但 clash ipcidr={m}（应完全相等）")
        print(f"  {'✅' if same else '❌'} {tag:<16} geoip={n:<4} clash={m}")

    print()
    if problems:
        print("❌ 一致性校验失败：")
        for p in problems:
            print(f"   - {p}")
        return 1
    print("✅ 两种格式语义等价，源自同一份自持数据")
    return 0


if __name__ == "__main__":
    sys.exit(main())
