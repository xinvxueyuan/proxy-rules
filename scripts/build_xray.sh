#!/usr/bin/env bash
# 用 v2fly 官方工具把自持规则编译成 Xray 可消费的 .dat
#
#   geosite.dat  ← dlc   读 data/domains/（一个文件 = 一个 tag）
#   geoip.dat    ← geoip 读 data/ip/（scripts/geoip.config.json 指定 text 输入）
#
# Xray 只认 geosite.dat / geoip.dat 同款 protobuf（`ext:file:tag`），不认纯文本，
# 所以这里必须构建二进制 .dat。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
mkdir -p dist/xray

echo "== 构建 geosite.dat（dlc）=="
DLC_DIR="${DLC_DIR:-/tmp/dlc-src}"
if [ ! -d "$DLC_DIR" ]; then
  git clone --depth 1 https://github.com/v2fly/domain-list-community "$DLC_DIR"
fi
( cd "$DLC_DIR" && go run ./ \
    --datapath="$ROOT/data/domains" \
    --outputdir="$ROOT/dist/xray" \
    --outputname=geosite.dat )
ls -l dist/xray/geosite.dat

echo
echo "== 构建 geoip.dat（geoip）=="
if ! command -v geoip >/dev/null 2>&1; then
  go install -v github.com/v2fly/geoip@latest
  export PATH="$PATH:$(go env GOPATH)/bin"
fi
geoip -c scripts/geoip.config.json
ls -l dist/xray/geoip.dat

echo
echo "== 产物校验（非空 + sha256）=="
for f in dist/xray/geosite.dat dist/xray/geoip.dat; do
  size=$(stat -c%s "$f" 2>/dev/null || stat -f%z "$f")
  if [ "$size" -lt 50 ]; then
    echo "  ❌ $f 过小（$size 字节），构建可能失败"; exit 1
  fi
  printf "  %-26s %8s 字节  sha256=%s\n" "$f" "$size" "$(sha256sum "$f" | cut -c1-16)"
done
