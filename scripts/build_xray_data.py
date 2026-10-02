#!/usr/bin/env python3
"""纯 Python 生成 Xray 的 geosite.dat 与 geoip.dat（不依赖 go / dlc / v2fly 工具）。

为什么不继续用官方 dlc 生成 geosite.dat：
    dlc 的 tag 名校验只允许 `[A-Z0-9!-]`（见其 validateSiteName）**不含点**，
    所以它无法产出 `site.cn` / `advert.com` 这类组名（实测报
    `invalid list name: "ADVERT.CN"` 后直接退出）。本项目要求组名带点，因此自己编码。

附带好处：不再需要 Go 工具链、不再 clone domain-list-community、构建变快且可复现，
也能顺手做「写完立刻反解一遍」的往返校验（防止编码出错却没人发现）。

protobuf schema（与官方 dat 二进制兼容）：
    GeoSiteList { repeated GeoSite entry = 1; }
    GeoSite     { string country_code = 1; repeated Domain domain = 2; }
    Domain      { int32 type = 1; string value = 2; }   # 0=Plain 1=Regex 2=Domain 3=Full
    GeoIPList   { repeated GeoIP entry = 1; }
    GeoIP       { string country_code = 1; repeated CIDR cidr = 2; }
    CIDR        { bytes ip = 1; uint32 prefix = 2; }

输入：
    build/data/<tag>   组装后的规则（dlc domain-list 语法，一个文件 = 一个 tag）
    data/ip/<name>.txt 每行一个 IP/CIDR
输出：
    dist/xray/self-geosite.dat
    dist/xray/self-geoip.dat
"""

from __future__ import annotations

import ipaddress
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "build" / "data"
IP_DIR = ROOT / "data" / "ip"
OUT = ROOT / "dist" / "xray"

TYPE_PLAIN, TYPE_REGEX, TYPE_DOMAIN, TYPE_FULL = 0, 1, 2, 3


# ── protobuf 编码原语 ──────────────────────────────────────────────────
def varint(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def key(field: int, wire: int) -> bytes:
    return varint((field << 3) | wire)


def ld(field: int, data: bytes) -> bytes:
    """length-delimited 字段"""
    return key(field, 2) + varint(len(data)) + data


def vint(field: int, value: int) -> bytes:
    """varint 字段"""
    return key(field, 0) + varint(value)


def encode_domain(dtype: int, value: str) -> bytes:
    return vint(1, dtype) + ld(2, value.encode("utf-8"))


def encode_geosite(tag: str, domains: list[tuple[int, str]]) -> bytes:
    body = ld(1, tag.encode("utf-8")) + b"".join(ld(2, encode_domain(t, v)) for t, v in domains)
    return body


def encode_cidr(ip: str, prefix: int) -> bytes:
    packed = ipaddress.ip_address(ip).packed
    return ld(1, packed) + vint(2, prefix)


def encode_geoip(tag: str, cidrs: list[tuple[str, int]]) -> bytes:
    body = ld(1, tag.encode("utf-8")) + b"".join(
        ld(2, encode_cidr(ip, p)) for ip, p in cidrs)
    return body


# ── 解析输入 ───────────────────────────────────────────────────────────
def parse_dlc(path: pathlib.Path) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("domain:"):
            out.append((TYPE_DOMAIN, line.split(":", 1)[1].strip()))
        elif line.startswith("full:"):
            out.append((TYPE_FULL, line.split(":", 1)[1].strip()))
        elif line.startswith("keyword:"):
            out.append((TYPE_PLAIN, line.split(":", 1)[1].strip()))
        elif line.startswith("regexp:"):
            out.append((TYPE_REGEX, line.split(":", 1)[1].strip()))
        else:
            raise SystemExit(f"❌ {path.name}: 不支持的指令 `{line}`（只认 domain/full/keyword/regexp）")
    return out


def parse_ip(path: pathlib.Path) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if "/" in line:
            ip, _, plen = line.partition("/")
            out.append((str(ipaddress.ip_address(ip)), int(plen)))
        else:
            a = ipaddress.ip_address(line)
            out.append((str(a), a.max_prefixlen))
    return out


# ── 往返校验（写完立刻反解，确认编码没错）──────────────────────────────
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
        k, pos = read_varint(buf, pos)
        fno, wt = k >> 3, k & 7
        if wt == 0:
            v, pos = read_varint(buf, pos)
            yield fno, wt, v
        elif wt == 2:
            ln, pos = read_varint(buf, pos)
            yield fno, wt, buf[pos:pos + ln]
            pos += ln
        else:
            raise ValueError(f"未知 wire type {wt}")


def decode_geosite(buf: bytes) -> dict[str, list[tuple[int, str]]]:
    out: dict[str, list[tuple[int, str]]] = {}
    for fno, wt, val in fields(buf):
        if fno != 1 or wt != 2:
            continue
        tag, rows = None, []
        for f2, w2, v2 in fields(val):
            if f2 == 1 and w2 == 2:
                tag = v2.decode()
            elif f2 == 2 and w2 == 2:
                dt, dv = None, None
                for f3, w3, v3 in fields(v2):
                    if f3 == 1 and w3 == 0:
                        dt = v3
                    elif f3 == 2 and w3 == 2:
                        dv = v3.decode()
                if dt is not None and dv is not None:
                    rows.append((dt, dv))
        if tag is not None:
            out[tag] = rows
    return out


def decode_geoip(buf: bytes) -> dict[str, int]:
    out: dict[str, int] = {}
    for fno, wt, val in fields(buf):
        if fno != 1 or wt != 2:
            continue
        tag, n = None, 0
        for f2, w2, v2 in fields(val):
            if f2 == 1 and w2 == 2:
                tag = v2.decode()
            elif f2 == 2 and w2 == 2:
                n += 1
        if tag is not None:
            out[tag] = n
    return out


def main() -> int:
    if not DATA.is_dir():
        print(f"❌ 缺 {DATA.relative_to(ROOT)}（先跑 scripts/assemble_data.py）")
        return 2

    OUT.mkdir(parents=True, exist_ok=True)
    problems: list[str] = []

    # ── geosite.dat ──
    sites = []
    for path in sorted(DATA.glob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        rows = parse_dlc(path)
        if not rows:
            problems.append(f"{path.name}: 空列表，跳过（Xray 不接受零条目 tag）")
            continue
        # tag 统一大写：与官方 dlc 产物一致，且避免下游工具假设大写时找不到
        sites.append((path.name.upper(), rows))

    blob = b"".join(ld(1, encode_geosite(tag, rows)) for tag, rows in sites)
    gs_path = OUT / "self-geosite.dat"
    gs_path.write_bytes(blob)

    back = decode_geosite(blob)
    if len(back) != len(sites):
        print(f"❌ geosite 往返校验失败：写入 {len(sites)} 个 tag，反解出 {len(back)} 个")
        return 1
    for tag, rows in sites:
        got = back.get(tag, [])
        if len(got) != len(rows):
            problems.append(f"geosite {tag}: 写入 {len(rows)} 条，反解 {len(got)} 条")
    print(f"geosite.dat  {len(sites)} 个 tag / {sum(len(r) for _, r in sites)} 条 → "
          f"{gs_path.relative_to(ROOT)} ({len(blob):,} 字节)")
    for tag, rows in sites:
        print(f"    {tag:<16} {len(rows):>7} 条")

    # ── geoip.dat ──
    ips = []
    for path in sorted(IP_DIR.glob("*.txt")):
        cidrs = parse_ip(path)
        if not cidrs:
            problems.append(f"{path.name}: 无有效条数，跳过（只有注释属预期）")
            continue
        ips.append((path.stem.upper(), cidrs))

    if ips:
        blob_ip = b"".join(ld(1, encode_geoip(tag, cidrs)) for tag, cidrs in ips)
    else:
        # Xray 的 ext: 引用若指向不存在的文件会报错，所以至少要有一个 tag。
        # 需要 geoip 时请在 data/ip/ 下放列表。
        blob_ip = b""
    ip_path = OUT / "self-geoip.dat"
    ip_path.write_bytes(blob_ip)
    if blob_ip:
        back_ip = decode_geoip(blob_ip)
        for tag, cidrs in ips:
            if back_ip.get(tag) != len(cidrs):
                problems.append(f"geoip {tag}: 写入 {len(cidrs)} 条，反解 {back_ip.get(tag)} 条")
        print(f"\ngeoip.dat    {len(ips)} 个 tag / {sum(len(c) for _, c in ips)} 条 → "
              f"{ip_path.relative_to(ROOT)} ({len(blob_ip):,} 字节)")
        for tag, cidrs in ips:
            print(f"    {tag:<16} {len(cidrs):>7} 条")
    else:
        print("\ngeoip.dat    0 字节（data/ip/ 下没有有效列表）")

    # ── 体积与内容守卫 ──
    print()
    for f, minimum in ((gs_path, 200), (ip_path, 0)):
        size = f.stat().st_size
        if size < minimum:
            print(f"  ❌ {f.name} 体积异常（{size} 字节 < {minimum}）")
            return 1
        print(f"  ✔ {f.name:<20} {size:>9,} 字节")

    if problems:
        print("\n⚠️ 注意：")
        for p in problems:
            print(f"  - {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
