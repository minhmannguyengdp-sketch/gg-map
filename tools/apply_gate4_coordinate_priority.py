# -*- coding: utf-8 -*-
"""Build-time patcher for Gate 4 coordinate priority.

Makes valid latitude/longitude override the location text, and requires either
coordinates or a location before scanning.
"""
from __future__ import annotations

import sys
from pathlib import Path

START_LOCATION_FALLBACK = '''    elif has_location:
        lat_text = ""
        lng_text = ""
    else:
        lat_text = ""
        lng_text = ""
'''
START_LOCATION_REQUIRED = '''    elif has_location:
        lat_text = ""
        lng_text = ""
    else:
        messagebox.showwarning("Thiếu thông tin", "Hãy nhập khu vực hoặc dán đủ vĩ độ/kinh độ trước khi quét.")
        return
'''

SEARCH_KEYWORD_OLD = '''    search_keyword = f"{kw} tại {loc}".strip() if loc else kw
    fallback_keyword = kw if loc else kw
'''
SEARCH_KEYWORD_NEW = '''    if has_manual_coordinates:
        search_keyword = kw
        fallback_keyword = f"{kw} tại {loc}".strip() if loc else kw
    else:
        search_keyword = f"{kw} tại {loc}".strip() if loc else kw
        fallback_keyword = kw
'''

AREA_OLD = '''    if loc:
        if manual_ok:
            area_text = f"{loc} (ưu tiên khu vực, tọa độ nhập tay hiện có sẽ không được dùng)"
        else:
            area_text = loc
    elif manual_ok:
        area_text = "Theo tọa độ nhập tay"
    elif selected_start:
        area_text = f"Đang chọn điểm tuyến: {selected_start}"
    else:
        area_text = "Chưa có khu vực"
'''
AREA_NEW = '''    if manual_ok:
        area_text = "Theo tọa độ nhập tay" if not loc else f"Theo tọa độ nhập tay (khu vực '{loc}' chỉ dùng làm dự phòng)"
    elif loc:
        area_text = loc
    elif selected_start:
        area_text = f"Đang chọn điểm tuyến: {selected_start}"
    else:
        area_text = "Chưa có khu vực"
'''

PRIORITY_OLD = '''    if loc:
        priority_text = "khu vực nhập tay"
    elif manual_ok:
        priority_text = "tọa độ nhập tay"
    elif selected_start:
        priority_text = "điểm tuyến đã chọn"
    else:
        priority_text = "chưa có mốc"
'''
PRIORITY_NEW = '''    if manual_ok:
        priority_text = "tọa độ nhập tay"
    elif loc:
        priority_text = "khu vực nhập tay"
    elif selected_start:
        priority_text = "điểm tuyến đã chọn"
    else:
        priority_text = "chưa có mốc"
'''

QUERY_OLD = '''    if loc:
        query_main = f"{kw} tại {loc}".strip() if kw else loc
        query_fallback = kw or loc
    else:
        query_main = kw
        query_fallback = kw
'''
QUERY_NEW = '''    if manual_ok:
        query_main = kw
        query_fallback = f"{kw} tại {loc}".strip() if loc and kw else (kw or loc)
    elif loc:
        query_main = f"{kw} tại {loc}".strip() if kw else loc
        query_fallback = kw or loc
    else:
        query_main = kw
        query_fallback = kw
'''


def replace_required(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"Không tìm thấy marker Gate 4: {label}")
    return text.replace(old, new, 1)


def apply_gate4_patch(source_text: str) -> str:
    patched = source_text
    patched = replace_required(patched, START_LOCATION_FALLBACK, START_LOCATION_REQUIRED, "start_app require location/coords")
    patched = replace_required(patched, SEARCH_KEYWORD_OLD, SEARCH_KEYWORD_NEW, "search keyword coordinate priority")
    patched = replace_required(patched, AREA_OLD, AREA_NEW, "UI area priority")
    patched = replace_required(patched, PRIORITY_OLD, PRIORITY_NEW, "UI priority text")
    patched = replace_required(patched, QUERY_OLD, QUERY_NEW, "UI query preview")

    if "ưu tiên khu vực, tọa độ nhập tay hiện có sẽ không được dùng" in patched:
        raise RuntimeError("Gate 4 fail: UI vẫn báo khu vực ghi đè tọa độ.")
    if SEARCH_KEYWORD_OLD in patched:
        raise RuntimeError("Gate 4 fail: search keyword vẫn ưu tiên khu vực khi có tọa độ.")
    if START_LOCATION_FALLBACK in patched:
        raise RuntimeError("Gate 4 fail: vẫn cho chạy khi thiếu cả khu vực và tọa độ.")
    return patched


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("Usage: apply_gate4_coordinate_priority.py <input_ui_cao_map.py> <output_ui_cao_map.py>", file=sys.stderr)
        return 2

    source_path = Path(argv[1]).resolve()
    output_path = Path(argv[2]).resolve()
    source_text = source_path.read_text(encoding="utf-8")
    patched_text = apply_gate4_patch(source_text)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(patched_text, encoding="utf-8", newline="\n")
    print(f"Gate 4 coordinate-priority source generated: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
