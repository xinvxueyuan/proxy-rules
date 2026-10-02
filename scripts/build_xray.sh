#!/usr/bin/env bash
# 用 v2fly 官方工具把自持 + 上游规则编译成 Xray 可消费的 .dat
#
#   geosite.dat  ← dlc   读 <数据目录>（一个文件 = 一个 tag）
#   geoip.dat    ← geoip 读 data/ip/（scripts/geoip.config.json 指定 text 输入）
#
# Xray 只认 geosite.dat / geoip.dat 同款 protobuf（`ext:file:tag`），不认纯文本，
# 所以这里必须构建二进制 .dat。
#
# 数据目录要「扁平」：dlc 只读 datapath 直属的文件，不递归。所以先把
# data/domains/（自持）与 data/upstream/（拉取）拷进 build/data/。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
mkdir -p dist/xray
DATA="$ROOT/build/data"

# 路径兼容垫片：本机是 Windows（git-bash）时，原生程序（git / go）不认 MSYS 的
# /c/... 形式（bash 内建 cd 会翻译，但原生程序不会 —— 曾被 clone 到 C:\c\Users\...）。
# cygpath -m 给出 C:/... 形式，两边都能用；Linux（CI）上没有 cygpath，原样透传。
topath() { command -v cygpath >/dev/null 2>&1 && cygpath -m "$1" || printf '%s' "$1"; }

echo "== 组装数据目录 =="
rm -rf "$DATA" && mkdir -p "$DATA"
cp data/domains/* "$DATA/"
if [ -d data/upstream ]; then
  cp data/upstream/* "$DATA/"
fi
echo "  数据文件："
ls -l "$DATA" | awk 'NR>1 {printf "    %10s  %s\n", $5, $9}'

# 守卫：sources.json 声明要拉的上游列表必须在（否则静默少 11 万条）
python3 - <<'PY'
import json, pathlib, sys
root = pathlib.Path(".")
src = json.loads((root / "sources.json").read_text(encoding="utf-8"))
bad = []
for item in src.get("upstream", []):
    p = root / "data" / "upstream" / item["tag"]
    n = sum(1 for ln in p.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.strip().startswith("#")) if p.exists() else 0
    if n < 100:
        bad.append(f"{item['tag']}: {n} 条")
if bad:
    print("❌ 上游数据异常：" + "; ".join(bad)); sys.exit(2)
print(f"  ✅ 上游列表齐备（{len(src.get('upstream', []))} 个）")
PY

echo
echo "== 构建 geosite.dat（dlc）=="
# 放在仓库内（build/ 已 gitignore）：/tmp 这种 MSYS 路径在 Windows 上
# 会被原生 git 当成字面量目录名、clone 完找不到，本地复现直接挂。
DLC_DIR="${DLC_DIR:-$ROOT/build/dlc-src}"
DLC_NATIVE="$(topath "$DLC_DIR")"
if [ ! -d "$DLC_DIR" ]; then
  git clone --depth 1 https://github.com/v2fly/domain-list-community "$DLC_NATIVE"
fi
( cd "$DLC_DIR" && go run ./ \
    --datapath="$(topath "$DATA")" \
    --outputdir="$(topath "$ROOT/dist/xray")" \
    --outputname=self-geosite.dat )
ls -l dist/xray/self-geosite.dat

echo
echo "== 构建 geoip.dat（geoip）=="
if ! command -v geoip >/dev/null 2>&1; then
  go install -v github.com/v2fly/geoip@latest
  export PATH="$PATH:$(go env GOPATH)/bin"
fi
geoip -c scripts/geoip.config.json
ls -l dist/xray/self-geoip.dat

echo
echo "== 产物校验（非空 + sha256）=="
for f in dist/xray/self-geosite.dat dist/xray/self-geoip.dat; do
  size=$(stat -c%s "$f" 2>/dev/null || stat -f%z "$f")
  if [ "$size" -lt 50 ]; then
    echo "  ❌ $f 过小（$size 字节），构建可能失败"; exit 1
  fi
  printf "  %-26s %8s 字节  sha256=%s\n" "$f" "$size" "$(sha256sum "$f" | cut -c1-16)"
done
