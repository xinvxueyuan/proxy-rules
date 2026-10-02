#!/usr/bin/env bash
# 用**真实内核**验证产物，并做变异检验证明校验不是空壳。
#
#   Clash 侧：真启动 mihomo + 查 /providers/rules 的 ruleCount。
#             ⚠️ 不能用 `mihomo -t`：它只校验配置语法，**不加载 type: file 的
#             rule-provider** —— 文件写成非法 YAML、甚至直接删掉，`-t` 都输出
#             "test is successful" 退出码 0（实测）。拿它当闸门 = 假绿灯。
#   Xray  侧：xray run -test 加载 ext: 引用的 .dat；并验证「文件缺失/内容损坏
#             时必须报错」，证明 -test 真的在读文件。资源目录里同时放**官方 dat**，
#             验证自建产物不会遮蔽 geosite:cn / geoip:private 这类内置引用。
#
# 三个本机（Windows / git-bash）的坑，都在下面处理掉了：
#   1) python 写 stdout 是 CRLF → readarray 会把 \r 带进元素，URL 变成 "...zip\r"；
#   2) curl / unzip / xray / mihomo 是**原生程序**，不认 MSYS 的 /c/... 路径
#      （实测 curl -o /c/... 直接报 error 23）。给原生程序的路径统一过 topath；
#   3) 内核要按平台取对应资产 —— 拿 Linux 版在内核在 Windows 上跑会报
#      `不是有效的 Win32 应用程序`。所以按 uname 选 windows/linux 构建。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

topath() { command -v cygpath >/dev/null 2>&1 && cygpath -m "$1" || printf '%s' "$1"; }
WROOT="$(topath "$ROOT")"

TMP="$ROOT/build/verify"
WTMP="$WROOT/build/verify"
mkdir -p "$TMP"
FAIL=0

case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*)
    PLAT=windows
    XR_PAT='^Xray-windows-64\.zip$'  ; XR_BIN=xray.exe
    MH_PAT='^mihomo-windows-amd64-compatible.*\.zip$' ; MH_BIN=mihomo.exe
    ;;
  *)
    PLAT=linux
    XR_PAT='^Xray-linux-64\.zip$'    ; XR_BIN=xray
    MH_PAT='^mihomo-linux-amd64-compatible.*\.gz$'    ; MH_BIN=mihomo
    ;;
esac
echo "平台: $PLAT（内核取对应平台的构建）"

# 取仓库最新一个 release（含 pre-release）里匹配指定 asset 的下载地址，
# 输出两行：版本号、下载地址（末尾 tr -d '\r' 解决上述 CRLF 问题）。
latest_asset() {
  python3 - "$1" "$2" <<'PY' | tr -d '\r'
import json, re, sys, urllib.request
repo, pat = sys.argv[1], re.compile(sys.argv[2])
def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "proxy-rules-ci"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)
rels = get(f"https://api.github.com/repos/{repo}/releases")
if not rels:
    sys.exit("no releases")
tag = rels[0]["tag_name"]
for a in rels[0].get("assets", []):
    if pat.search(a["name"]):
        print(tag)
        print(a["browser_download_url"])
        sys.exit(0)
sys.exit(f"no asset matching {pat.pattern} in {tag}")
PY
}

echo
echo "======== 准备：Xray 内核 ========"
readarray -t XR < <(latest_asset "XTLS/Xray-core" "$XR_PAT")
echo "Xray 版本: ${XR[0]}"
curl -fsSL --retry 4 --retry-delay 2 --retry-all-errors -o "$WTMP/xray.zip" "${XR[1]}"
rm -rf "$TMP/xray" && mkdir -p "$TMP/xray"
unzip -oq "$WTMP/xray.zip" -d "$WTMP/xray"
XR_FOUND="$(find "$TMP/xray" -type f -name "xray*" 2>/dev/null | head -1)"
if [ -z "$XR_FOUND" ]; then
  echo "   ❌ 未在解压目录里找到 xray 可执行文件"; ls -l "$TMP/xray" | sed 's/^/      /'; exit 1
fi
chmod +x "$XR_FOUND" 2>/dev/null || true
XBIN="$(topath "$XR_FOUND")"

# 资源目录：自建 dat + 官方 dat 并存（与真实部署一致）
ASSET="$ROOT/build/verify/asset"
WASSET="$WTMP/asset"
rm -rf "$ASSET" && mkdir -p "$ASSET"
cp "$ROOT/dist/xray/"*.dat "$ASSET/"
curl -fsSL --retry 4 --retry-delay 2 --retry-all-errors -o "$WASSET/geosite.dat" \
  "https://github.com/v2fly/domain-list-community/releases/latest/download/dlc.dat"
curl -fsSL --retry 4 --retry-delay 2 --retry-all-errors -o "$WASSET/geoip.dat" \
  "https://github.com/v2fly/geoip/releases/latest/download/geoip.dat"
export XRAY_LOCATION_ASSET="$WASSET"
DAT="$ASSET/self-geosite.dat"
echo "资源目录: $(ls -1 "$ASSET" | tr '\n' ' ')"

echo
echo "-- 1) 正向：ext: 引用的 .dat 应能加载（且与官方 dat 并存不遮蔽）--"
if "$XBIN" run -test -c "$WROOT/verify/xray-test.json"; then
  echo "   ✅ xray 成功加载 ext: 规则集"
else
  echo "   ❌ xray 加载失败"; FAIL=1
fi

echo
echo "-- 2) 变异：把自建 geosite.dat 移走，必须报错 --"
mv "$DAT" "$TMP/geosite.dat.hold"
if "$XBIN" run -test -c "$WROOT/verify/xray-test.json" >/dev/null 2>&1; then
  echo "   ❌ 漏过：dat 不存在仍通过，校验有盲区"; FAIL=1
else
  echo "   ✅ 被抓到"
fi
mv "$TMP/geosite.dat.hold" "$DAT"

echo
echo "-- 3) 变异：破坏自建 geosite.dat 内容，必须报错 --"
cp "$DAT" "$TMP/geosite.dat.bak"
printf 'not a protobuf at all, garbage bytes to break parsing' > "$DAT"
if "$XBIN" run -test -c "$WROOT/verify/xray-test.json" >/dev/null 2>&1; then
  echo "   ❌ 漏过：内容损坏仍通过"; FAIL=1
else
  echo "   ✅ 被抓到"
fi
cp "$TMP/geosite.dat.bak" "$DAT"

echo
echo "-- 4) 恢复后复测 --"
if "$XBIN" run -test -c "$WROOT/verify/xray-test.json" >/dev/null 2>&1; then
  echo "   ✅ 恢复后正常"
else
  echo "   ❌ 恢复后仍失败"; FAIL=1
fi

echo
echo "======== 准备：mihomo 内核 ========"
readarray -t MH < <(latest_asset "MetaCubeX/mihomo" "$MH_PAT")
echo "mihomo 版本: ${MH[0]}"
if [ "$PLAT" = windows ]; then
  curl -fsSL --retry 4 --retry-delay 2 --retry-all-errors -o "$WTMP/mihomo.zip" "${MH[1]}"
  rm -rf "$TMP/mihomo-dir" && mkdir -p "$TMP/mihomo-dir"
  unzip -oq "$WTMP/mihomo.zip" -d "$WTMP/mihomo-dir"
else
  curl -fsSL --retry 4 --retry-delay 2 --retry-all-errors -o "$WTMP/mihomo.gz" "${MH[1]}"
  gunzip -f "$WTMP/mihomo.gz"
fi
# 两个平台解出来的形态不同：Windows 是 zip → 解压出目录；Linux 是 .gz → 单个文件。
# 资产名还带版本后缀（mihomo-windows-amd64-compatible-alpha-9f053c4.exe），
# 所以按通配找。找不到就直接失败，**不要**回退到别的文件
# （曾回退到残留的 Linux 二进制 → WinError 193，把排查方向带偏）。
if [ "$PLAT" = windows ]; then
  MH_FOUND="$(find "$TMP/mihomo-dir" -type f -name "mihomo*" 2>/dev/null | head -1)"
  MH_DIRSHOW="$TMP/mihomo-dir"
else
  MH_FOUND="$TMP/mihomo"
  MH_DIRSHOW="$TMP"
fi
if [ -z "$MH_FOUND" ] || [ ! -f "$MH_FOUND" ]; then
  echo "   ❌ 未找到 mihomo 可执行文件"; ls -l "$MH_DIRSHOW" 2>/dev/null | sed 's/^/      /'; exit 1
fi
chmod +x "$MH_FOUND" 2>/dev/null || true
MBIN="$(topath "$MH_FOUND")"
echo "   mihomo 可执行: $(basename "$MH_FOUND")"

echo
echo "-- 5) 真启动内核 + 查 rule-provider 真实条数 --"
if python3 scripts/verify_clash.py --mihomo "$MBIN" --timeout 60; then
  echo "   ✅ mihomo 真实加载校验通过"
else
  echo "   ❌ mihomo 校验失败"; FAIL=1
fi

echo
echo "-- 6) 变异：把一个 rule-provider 清空，必须被抓到 --"
cp "$ROOT/dist/clash/advert.gg.yaml" "$TMP/advert.gg.yaml.bak"
printf 'payload: []\n' > "$ROOT/dist/clash/advert.gg.yaml"
if python3 scripts/verify_clash.py --mihomo "$MBIN" --timeout 15 >/dev/null 2>&1; then
  echo "   ❌ 漏过：空规则集仍通过"; FAIL=1
else
  echo "   ✅ 被抓到"
fi
cp "$TMP/advert.gg.yaml.bak" "$ROOT/dist/clash/advert.gg.yaml"

echo
echo "-- 7) 一致性：两种格式必须语义等价（同一份组装结果）--"
if python3 scripts/verify_consistency.py; then
  echo "   ✅ 一致性校验通过"
else
  echo "   ❌ 一致性校验失败"; FAIL=1
fi

echo
echo "======== 结论 ========"
if [ "$FAIL" -eq 0 ]; then
  echo "✅ 两种内核均成功加载产物，且全部变异被抓到"
else
  echo "❌ 存在失败项，见上"
fi
exit "$FAIL"
