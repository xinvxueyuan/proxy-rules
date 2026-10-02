#!/usr/bin/env python3
"""用**真实 mihomo 内核**验证 dist/clash/*.yaml 真的能被加载。

为什么不能用 `mihomo -t`（实测教训）：
    `-t` 只做配置语法校验，**完全不加载 `type: file` 的 rule-provider**。
    把 provider 文件写成非法 YAML、甚至直接删掉，`-t` 依然输出
    "configuration file ... test is successful"、退出码 0。
    用它当 CI 闸门 = 假绿灯（文件根本没人读）。

改成：真正把内核跑起来 → 查 `GET /providers/rules` 的 `ruleCount` →
    与 build_clash.py 的 MANIFEST 逐项对齐 → 再杀掉进程。
    这样「规则文件存在但内容为空/解析失败」也逃不掉。

用法：
    python3 scripts/verify_clash.py --mihomo /path/to/mihomo
环境变量（CI 用）：MIHOMO_BIN
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
CONFIG = ROOT / "verify" / "mihomo-test.yaml"
MANIFEST = ROOT / "dist" / "clash" / "MANIFEST.json"
API = "http://127.0.0.1:19090"
SECRET = "ci-verify-only"


def api_get(path: str, timeout: float = 5.0):
    req = urllib.request.Request(API + path, headers={"Authorization": f"Bearer {SECRET}"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mihomo", default=os.environ.get("MIHOMO_BIN", "mihomo"))
    ap.add_argument("--timeout", type=float, default=30.0, help="等待内核就绪的秒数")
    args = ap.parse_args()

    if not CONFIG.exists() or not MANIFEST.exists():
        print(f"❌ 缺输入：{CONFIG.name} / {MANIFEST.name}（先跑 build_clash.py）")
        return 2

    expected = {a["name"]: a for a in json.loads(MANIFEST.read_text(encoding="utf-8"))["artifacts"]}

    print(f"启动内核：{args.mihomo}")
    proc = subprocess.Popen(
        [args.mihomo, "-d", str(ROOT), "-f", str(CONFIG)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        encoding="utf-8", errors="replace",
    )

    try:
        # 等 API 就绪
        deadline = time.time() + args.timeout
        providers = None
        while time.time() < deadline:
            if proc.poll() is not None:
                out = proc.stdout.read() if proc.stdout else ""
                print("❌ 内核启动即退出，输出：")
                print("\n".join("   " + ln for ln in out.splitlines()[-25:]))
                return 1
            try:
                providers = api_get("/providers/rules")
                break
            except (urllib.error.URLError, OSError, json.JSONDecodeError):
                time.sleep(0.4)

        if providers is None:
            print(f"❌ {args.timeout}s 内未能连上内核 API {API}")
            return 1

        # mihomo 的 /providers/rules 返回形状随版本变过：
        #   {"providers": {"<name>": {...}}}  或  {"providers": [{...}]}  或  {"<name>": {...}}
        # 两种都归一成一个 {name: info} 字典，别假定是数组。
        raw = providers.get("providers", providers) if isinstance(providers, dict) else providers
        if isinstance(raw, dict):
            got = {}
            for name, info in raw.items():
                if isinstance(info, dict):
                    got[name] = {"name": name, **info}
                else:
                    got[name] = {"name": name, "ruleCount": info}
        else:
            got = {p["name"]: p for p in raw}

        print(f"\n内核报告的 rule-provider（{len(got)} 个）：")
        for name, info in sorted(got.items()):
            print(f"  {name:<18} ruleCount={info.get('ruleCount', 0):<6} "
                  f"type={info.get('vehicleType', '?')} updatedAt={info.get('updatedAt', '')}")

        failures: list[str] = []
        print("\n与 MANIFEST 对齐：")
        for name, meta in sorted(expected.items()):
            info = got.get(name)
            if info is None:
                failures.append(f"{name}: 内核里没有这个 provider（配置里少写了？）")
                print(f"  ❌ {name:<18} 内核未报告")
                continue
            actual = info.get("ruleCount", 0)
            want = meta["entries"]
            if actual != want:
                failures.append(f"{name}: ruleCount={actual}，期望 {want}")
                print(f"  ❌ {name:<18} ruleCount={actual} ≠ {want}")
            else:
                print(f"  ✅ {name:<18} ruleCount={actual}")

        # 空 provider 也是失败（文件被清空的样子）
        for name, info in got.items():
            if info.get("ruleCount", 0) == 0:
                failures.append(f"{name}: ruleCount=0（规则集为空，等于没生效）")

        if failures:
            print("\n❌ 校验失败：")
            for f in failures:
                print(f"   - {f}")
            return 1

        print("\n✅ mihomo 真实加载校验通过")
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())
