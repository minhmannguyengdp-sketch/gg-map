# -*- coding: utf-8 -*-
"""Build-time patcher for Gate 3 async geocode.

Removes the synchronous `resolve_location_anchor(...)` call from `start_app()`
so the UI can respond immediately, then resolves geocode inside the existing
background launch thread before workers start.
"""
from __future__ import annotations

import sys
from pathlib import Path

SYNC_ANCHOR_START = '    set_runtime_status("Đang chuẩn bị mở Chrome và nạp luồng quét...", "info", "KHỞI ĐỘNG")\n'
SEARCH_KEYWORD_COMMENT = "    # Ưu tiên bám sát khu vực người dùng nhập ngay từ query đầu.\n"
LAUNCH_SESSION_MARKER = '''    def launch_scan_session():
        anchor, anchor_warning = resolve_location_anchor(loc, lat_text, lng_text, zoom_text, radius_text)
'''
LAUNCH_SESSION_REPLACEMENT = '''    def launch_scan_session():
        root.after(
            0,
            lambda: set_runtime_status(
                "Đang định vị khu vực...",
                "info",
                "ĐỊNH VỊ",
            ),
        )
        anchor, anchor_warning = resolve_location_anchor(loc, lat_text, lng_text, zoom_text, radius_text)
'''
QUICK_STATUS = '''    set_runtime_status(
        "Đã nhận lệnh quét, đang chuẩn bị cấu hình...",
        "info",
        "KHỞI ĐỘNG",
    )
'''


def apply_gate3_patch(source_text: str) -> str:
    patched = source_text

    start = patched.find(SYNC_ANCHOR_START)
    if start != -1:
        end = patched.find(SEARCH_KEYWORD_COMMENT, start)
        if end == -1:
            raise RuntimeError("Không tìm thấy marker search keyword sau block geocode sync.")
        patched = patched[:start] + QUICK_STATUS + patched[end:]

    if '"Đang định vị khu vực..."' not in patched:
        if LAUNCH_SESSION_MARKER not in patched:
            raise RuntimeError("Không tìm thấy marker launch_scan_session để chuyển geocode sang thread nền.")
        patched = patched.replace(LAUNCH_SESSION_MARKER, LAUNCH_SESSION_REPLACEMENT, 1)

    sync_count = patched.count("anchor, anchor_warning = resolve_location_anchor(loc, lat_text, lng_text, zoom_text, radius_text)")
    if sync_count != 1:
        raise RuntimeError(
            f"Gate 3 fail: kỳ vọng chỉ còn 1 resolve_location_anchor trong launch thread, hiện có {sync_count}."
        )
    if SYNC_ANCHOR_START in patched:
        raise RuntimeError("Gate 3 fail: block geocode đồng bộ vẫn còn trong start_app.")

    return patched


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("Usage: apply_gate3_async_geocode.py <input_ui_cao_map.py> <output_ui_cao_map.py>", file=sys.stderr)
        return 2

    source_path = Path(argv[1]).resolve()
    output_path = Path(argv[2]).resolve()
    source_text = source_path.read_text(encoding="utf-8")
    patched_text = apply_gate3_patch(source_text)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(patched_text, encoding="utf-8", newline="\n")
    print(f"Gate 3 async-geocode source generated: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
