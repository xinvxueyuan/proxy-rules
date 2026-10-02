#!/usr/bin/env bash
# 用**真实内核**验证产物，并做变异检验证明校验不是空壳。
#
#   Clash 侧：真启动 mihomo + 查 /providers/rules 的 ruleCount。
#             ⚠️ 不能用 `mihomo -t`：它只校验配置语法，**不加载 type: file 的
#             rule-provider** —— 文件写成非法 YAML、甚至直接删掉，`-t` 都输出
#             "test is successful" 退出码 0（实测）。拿它当闸门 = 假绿灯。
#   Xray  侧：xray run -test 加载 ext: 引用的 .dat；并验证「文件缺失/内容损坏
#             时必须报错」，证明 -test 真的在读文件。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
TMP="$ROOT/build/verify"
mkdir -p "$TMP"
FAIL=0

# 取仓库最新一个 release（含 pre-release）里匹配指定 asset 的下载地址
latest_asset() { # $1=repo $2=asset 正则
  python3 - "$1" "$2" <<'PY'
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

echo "======== 准备：取 Xray 内核（最新 release，含 pre-release）========"
readarray -t XR < <(latest_asset "XTLS/Xray-core" '^Xray-linux-64\.zip$')
echo "Xray 版本: ${XR[0]}"
curl -fsSL -o "$TMP/xray.zip" "${XR[1]}"
rm -rf "$TMP/xray" && mkdir -p "$TMP/xray"
unzip -oq "$TMP/xray.zip" -d "$TMP/xray"
# 资源目录要「自建 dat + 官方 dat 并存」，才与真实部署一致：
# 自建产物若与官方同名会互相遮蔽，这里名字已分开（self-*.dat），顺便验证不会被遮蔽。
ASSET="$TMP/asset"
rm -rf "$ASSET" && mkdir -p "$ASSET"
cp "$ROOT/dist/xray/"*.dat "$ASSET/"
curl -fsSL -o "$ASSET/geosite.dat" \
  "https://github.com/v2fly/domain-list-community/releases/latest/download/dlc.dat"
curl -fsSL -o "$ASSET/geoip.dat" \
  "https://github.com/v2fly/geoip/releases/latest/download/geoip.dat"
export XRAY_LOCATION_ASSET="$ASSET"
DAT="$ASSET/self-geosite.dat"

echo
echo "-- 1) 正向：ext: 引用的 .dat 应能加载 --"
if "$TMP/xray/xray" run -test -c "$ROOT/verify/xray-test.json"; then
  echo "   ✅ xray 成功加载 ext: 规则集"
else
  echo "   ❌ xray 加载失败"; FAIL=1
fi

echo
echo "-- 2) 变异：把 geosite.dat 移走，必须报错 --"
mv "$DAT" "$TMP/geosite.dat.hold"
if "$TMP/xray/xray" run -test -c "$ROOT/verify/xray-test.json" >/dev/null 2>&1; then
  echo "   ❌ 漏过：dat 不存在仍通过，校验有盲区"; FAIL=1
else
  echo "   ✅ 被抓到"
fi
mv "$TMP/geosite.dat.hold" "$DAT"

echo
echo "-- 3) 变异：破坏 geosite.dat 内容，必须报错 --"
cp "$DAT" "$TMP/geosite.dat.bak"
printf 'not a protobuf at all, garbage bytes to break parsing' > "$DAT"
if "$TMP/xray/xray" run -test -c "$ROOT/verify/xray-test.json" >/dev/null 2>&1; then
  echo "   ❌ 漏过：内容损坏仍通过"; FAIL=1
else
  echo "   ✅ 被抓到"
fi
cp "$TMP/geosite.dat.bak" "$DAT"

echo
echo "-- 4) 恢复后复测 --"
if "$TMP/xray/xray" run -test -c "$ROOT/verify/xray-test.json" >/dev/null 2>&1; then
  echo "   ✅ 恢复后正常"
else
  echo "   ❌ 恢复后仍失败"; FAIL=1
fi

echo
echo "======== 准备：取 mihomo 内核 ========"
readarray -t MH < <(latest_asset "MetaCubeX/mihomo" '^mihomo-linux-amd64.*\.gz$')
echo "mihomo 版本: ${MH[0]}"
curl -fsSL -o "$TMP/mihomo.gz" "${MH[1]}"
gunzip -f "$TMP/mihomo.gz"
chmod +x "$TMP/mihomo"

echo
echo "-- 5) 真启动内核 + 查 rule-provider 真实条数 --"
if python3 scripts/verify_clash.py --mihomo "$TMP/mihomo"; then
  echo "   ✅ mihomo 真实加载校验通过"
else
  echo "   ❌ mihomo 校验失败"; FAIL=1
fi

echo
echo "-- 6) 变异：把一个 rule-provider 清空，必须被抓到 --"
cp "$ROOT/dist/clash/self-reject.yaml" "$TMP/self-reject.yaml.bak"
printf 'payload: []\n' > "$ROOT/dist/clash/self-reject.yaml"
if python3 scripts/verify_clash.py --mihomo "$TMP/mihomo" --timeout 12 >/dev/null 2>&1; then
  echo "   ❌ 漏过：空规则集仍通过"; FAIL=1
else
  echo "   ✅ 被抓到"
fi
cp "$TMP/self-reject.yaml.bak" "$ROOT/dist/clash/self-reject.yaml"

echo
echo "======== 结论 ========"
if [ "$FAIL" -eq 0 ]; then
  echo "✅ 两种内核均成功加载产物，且全部变异被抓到"
else
  echo "❌ 存在失败项，见上"
fi
exit "$FAIL"
