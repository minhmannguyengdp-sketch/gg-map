# -*- coding: utf-8 -*-
"""Build-time patcher for Gate 2 single scraper worker.

Removes legacy scraper worker implementations from the generated build source
and leaves exactly one active `scraper_worker` function.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

LEGACY_START_MARKER = "def _scraper_worker_legacy_direct("
ACTIVE_WORKER_MARKER = "def scraper_worker("


def apply_gate2_patch(source_text: str) -> str:
    patched = source_text

    start = patched.find(LEGACY_START_MARKER)
    if start != -1:
        end = patched.find(ACTIVE_WORKER_MARKER, start)
        if end == -1:
            raise RuntimeError("Không tìm thấy worker thật `def scraper_worker(` sau legacy worker.")
        patched = patched[:start].rstrip() + "\n\n" + patched[end:]

    worker_count = len(re.findall(r"^def\s+scraper_worker\s*\(", patched, flags=re.MULTILINE))
    if worker_count != 1:
        raise RuntimeError(f"Gate 2 fail: kỳ vọng đúng 1 def scraper_worker, hiện có {worker_count}.")

    if "def _scraper_worker_legacy_direct(" in patched or "def _scraper_worker_legacy_proxy(" in patched:
        raise RuntimeError("Gate 2 fail: legacy worker vẫn còn trong source build.")

    return patched


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("Usage: apply_gate2_single_worker.py <input_ui_cao_map.py> <output_ui_cao_map.py>", file=sys.stderr)
        return 2

    source_path = Path(argv[1]).resolve()
    output_path = Path(argv[2]).resolve()
    source_text = source_path.read_text(encoding="utf-8")
    patched_text = apply_gate2_patch(source_text)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(patched_text, encoding="utf-8", newline="\n")
    print(f"Gate 2 single-worker source generated: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
