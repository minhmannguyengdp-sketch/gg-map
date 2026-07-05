# -*- coding: utf-8 -*-
from __future__ import annotations
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("Usage: apply_gate4_coordinate_priority.py <input> <output>", file=sys.stderr)
        return 2
    src = Path(argv[1]).resolve()
    dst = Path(argv[2]).resolve()
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"Gate 4 source generated: {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
