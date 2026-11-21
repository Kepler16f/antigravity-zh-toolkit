#!/usr/bin/env python3
"""Restore AG Link / model-merge patches on top of upstream Antigrative Dashboard
0.9.11 for Antigravity Desktop 2.34.0+.

Beyond the model-merge/budget/staging patches, 0.9.11 on this machine needs one
extra fix: discovery's CIM/PowerShell enumeration budget is 8 s upstream, but
CIM on this Windows-on-ARM box inherently takes 5.5-10 s, so every discovery
pass ends in "读取 Antigravity 进程信息超时" (state limited / offline). This
script raises those budgets to 30 s (marker PULSE_CIM_TIMEOUT_V1).

Idempotent. Usage:
    python patch_pulse_0911.py [plugin_dir]
"""
import sys
from pathlib import Path

MARKER = "PULSE_CIM_TIMEOUT_V1"


def patch_cim_timeout(root: Path) -> str:
    path = root / "sidecars" / "panel" / "discovery.mjs"
    if not path.is_file():
        return "discovery.mjs not found"
    src = path.read_text(encoding="utf-8")
    if MARKER in src:
        return "already patched"
    n = src.count("timeout:8000")
    if not n:
        return "no 8s budgets found (upstream changed?)"
    src = src.replace("timeout:8000", "timeout:30000")
    path.write_text(src, encoding="utf-8")
    return f"raised {n} x 8s -> 30s"


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / ".gemini" / "config" / "plugins" / "antigravity-pulse"
    print("discovery.mjs: " + patch_cim_timeout(root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
