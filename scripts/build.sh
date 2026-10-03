#!/usr/bin/env bash
# 本地一键构建（CI 里是分步执行的，见 .github/workflows/build.yml）
#
#   1) 拉取上游 + 按生态分类      scripts/fetch_upstream.py
#   2) 合并三层 + 解析聚合组      scripts/assemble_data.py
#   3) 生成 Clash rule-provider   scripts/build_clash.py
#   4) 生成 Xray dat（纯 Python） scripts/build_xray_data.py
#   5) 生成 Pages 站点内容        scripts/build_docs.py
#   6) 真内核校验 + 变异检验      scripts/verify.sh
#
# 为什么把「组装」独立成一步：聚合组（advert.com）必须在三层合并之后才算，
# 否则会漏掉手工补进子组的域名（实测踩过：客户端只引 advert.com 却漏拦 doubleclick.net）。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ "${SKIP_FETCH:-0}" != "1" ]; then
  echo "== 1/6 拉取上游 =="
  python3 scripts/fetch_upstream.py
else
  echo "== 1/6 跳过拉取（SKIP_FETCH=1），仅做守卫检查 =="
  python3 scripts/fetch_upstream.py --check
fi

echo
echo "== 2/6 合并三层 + 解析聚合组 =="
python3 scripts/assemble_data.py

echo
echo "== 3/6 生成 Clash rule-provider =="
python3 scripts/build_clash.py

echo
echo "== 4/6 生成 Xray dat =="
python3 scripts/build_xray_data.py

echo
echo "== 5/6 生成 Pages 站点内容（文档页 + 示例片段）=="
python3 scripts/build_docs.py

if [ "${SKIP_VERIFY:-0}" = "1" ]; then
  echo
  echo "== 6/6 跳过校验（SKIP_VERIFY=1）=="
else
  echo
  echo "== 6/6 用真实内核校验 + 变异检验 =="
  bash scripts/verify.sh
fi

echo
echo "✅ 构建完成"
