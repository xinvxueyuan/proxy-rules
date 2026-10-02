#!/usr/bin/env python3
"""一致性校验：**同一份自持数据**编译出的两种格式必须语义等价。

这是本仓最核心的不变式 —— 它唯一能发现「某个列表在某一种格式里静默少了东西」
（比如某个 tag 没被 dlc 收进去、某个 IP 列表没进 geoip.dat）。

断言：
  1. dat 里的 tag 与 Clash 产物一一对应（不允许多、也不允许少）
  2. dat 里的每条域名都必须出现在对应 Clash 产物里
  3. 只出现在 Clash 里的条目，必须被同列表的某个父域覆盖
     （dlc 会剪掉被 `domain:` 父域覆盖的冗余子域，属预期、语义等价）
  4. geosite 的条数不得多于 Clash（多于说明 Clash 侧漏了）
  5. geoip 的条数必须与对应 Clash ipcidr 产物**完全相等**（IP 不做剪枝）

为什么纯 Python 手写 protobuf 读取：不想为了校验引入 protobuf 依赖，
geosite.dat/geoip.dat 的 schema 很窄（见下方注释），几十行足够。
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CLASH_DIR = ROOT / "dist" / "clash"
XRAY_DIR = ROOT / "dist" / "xray"


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


def parse_geosite(buf: bytes) -> dict[str, set[str]]:
    """GeoSiteList{1: GeoSite}; GeoSite{1: country_code, 2: Domain};
    Domain{1: type(0=keyword,1=regexp,2=domain,3=full), 2: value}"""
    out: dict[str, set[str]] = {}
    for fno, wt, val in fields(buf):
        if fno != 1 or wt != 2:
            continue
        code, values = "", set()
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
                if dtype == 2 and value:
                    values.add(value)
        if code:
            out[code] = values
    return out


def parse_geoip(buf: bytes) -> dict[str, int]:
    """GeoIPList{1: GeoIP}; GeoIP{1: country_code, 2: CIDR}"""
    out: dict[str, int] = {}
    for fno, wt, val in fields(buf):
        if fno != 1 or wt != 2:
            continue
        code, n = "", 0
        for f2, w2, v2 in fields(val):
            if f2 == 1 and w2 == 2:
                code = v2.decode("utf-8", "replace").lower()
            elif f2 == 2 and w2 == 2:
                n += 1
        if code:
            out[code] = n
    return out


def clash_payload(path: pathlib.Path) -> list[str]:
    """读 Clash rule-provider 的 payload 列表（容忍两种引号写法）"""
    items: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line.startswith("- "):
            continue
        v = line[2:].strip().strip("'\"")
        if v:
            items.append(v)
    return items


def main() -> int:
    for f in (XRAY_DIR / "self-geosite.dat", XRAY_DIR / "self-geoip.dat",
              CLASH_DIR / "MANIFEST.json"):
        if not f.exists():
            print(f"❌ 缺产物 {f.relative_to(ROOT)}（先跑 build_clash.py / build_xray.sh）")
            return 2

    geosite = parse_geosite((XRAY_DIR / "self-geosite.dat").read_bytes())
    geoip = parse_geoip((XRAY_DIR / "self-geoip.dat").read_bytes())
    manifest = json.loads((CLASH_DIR / "MANIFEST.json").read_text(encoding="utf-8"))
    clash = {a["name"]: a for a in manifest["artifacts"]}

    problems: list[str] = []

    # ── 1. tag 一一对应 ────────────────────────────────────────────────
    print("== 1) tag 对应关系 ==")
    domain_names = {n for n, a in clash.items() if a["behavior"] in ("domain", "classical")}
    for tag in sorted(set(geosite) | domain_names):
        gs, cl = tag in geosite, tag in domain_names
        mark = "✅" if (gs and cl) else "❌"
        if not (gs and cl):
            problems.append(f"{tag}: geosite={gs} clash={cl}（tag 未一一对应）")
        print(f"  {mark} {tag:<16} geosite={gs!s:<5} clash={cl}")
    # Clash 侧 IP 产物的名字是 <tag>-ip，比较时要先剥掉后缀，否则会比对成
    # self-direct-ip-ip（这个双后缀 bug 第一版就踩到了）
    ip_bases = {n[:-3] for n in clash if n.endswith("-ip")}
    for tag in sorted(set(geoip) | ip_bases):
        gi, cl = tag in geoip, tag in ip_bases
        mark = "✅" if (gi and cl) else "❌"
        if not (gi and cl):
            problems.append(f"{tag}: geoip={gi} clash-ip={cl}（IP tag 未一一对应）")
        print(f"  {mark} {tag:<16} geoip={gi!s:<5} clash[{tag}-ip]={cl}")

    # ── 2/3/4. 域名集包含关系 ──────────────────────────────────────────
    print("\n== 2) 域名集合包含关系（dat 必须被 Clash 覆盖）==")
    for tag, dat_values in sorted(geosite.items()):
        entry = clash.get(tag)
        if not entry:
            continue
        payload = clash_payload(CLASH_DIR / entry["file"])
        # Clash 侧 domain behavior 里 '+.x' 表示含子域，等价 dat 的 domain:x
        clash_domains = {p[2:] if p.startswith("+.") else p for p in payload}
        missing = sorted(dat_values - clash_domains)      # dat 有、Clash 没有 → 真问题
        pruned = sorted(clash_domains - dat_values)       # Clash 有、dat 剪掉 → 预期
        if missing:
            problems.append(f"{tag}: dat 有而 Clash 没有 → {missing}")
            print(f"  ❌ {tag}: dat 有而 Clash 没有 → {missing}")
        uncovered = []
        for v in pruned:
            if not any(v.endswith("." + d) for d in dat_values):
                uncovered.append(v)
        if uncovered:
            problems.append(f"{tag}: 这些条目既不在 dat、也不被任何父域覆盖 → {uncovered}")
            print(f"  ❌ {tag}: 未被父域覆盖的差异 → {uncovered}")
        if not missing and not uncovered:
            print(f"  ✅ {tag:<16} dat={len(dat_values):<4} clash={len(clash_domains):<4} "
                  f"（其中 {len(pruned)} 条是被父域覆盖的冗余子域，dlc 已剪、语义等价）")

    # ── 5. IP 必须完全相等 ────────────────────────────────────────────
    print("\n== 3) IP 集合必须完全相等（IP 不做剪枝）==")
    for tag, n in sorted(geoip.items()):
        entry = clash.get(f"{tag}-ip")
        if not entry:
            continue
        payload = clash_payload(CLASH_DIR / entry["file"])
        same = len(payload) == n
        if not same:
            problems.append(f"{tag}: geoip={n} 但 clash ipcidr={len(payload)}（应完全相等）")
        print(f"  {'✅' if same else '❌'} {tag:<16} geoip={n:<4} clash={len(payload)}")

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
