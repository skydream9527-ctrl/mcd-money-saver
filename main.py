#!/usr/bin/env python3
"""入口：python main.py ... 或 python -m mcd_money_saver ..."""

from __future__ import annotations

import sys
from pathlib import Path

# 保证未 pip install 时也能从源码运行
_SRC = Path(__file__).resolve().parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from mcd_money_saver.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
