# -*- coding: utf-8 -*-
from __future__ import annotations
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("Usage: apply_gate3_async_geocode.py <input> <output>", file=sys.stderr)
        return 2
    source_path = Path(argv[1]).resolve()
    output_path = Path(argv[2]).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    text = source_path.read_text(encoding="utf-8")
    text = text.replace('page.wait_for_timeout(1500)', 'page.wait_for_timeout(500)')
    text = text.replace('time.sleep(3)\n                search_state', 'time.sleep(0.4)\n                search_state')
    output_path.write_text(text, encoding="utf-8")
    print(f"Gate 3 fast-start source generated: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
