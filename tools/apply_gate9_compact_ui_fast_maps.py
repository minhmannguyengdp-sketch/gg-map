# -*- coding: utf-8 -*-
"""Build-time patcher for compact UI + faster Google Maps collection.

This keeps the one-command build flow, makes the main screen closer to the
compact screenshot, keeps detailed controls in popups, opens Maps by direct
search URL first, and adds safer place-card locator fallbacks so result rows are
not silently empty.
"""
from __future__ import annotations

import sys
from pathlib import Path

OPEN_MAPS_START = "def open_maps_and_search(page, browser_context, keyword, fallback_keyword, anchor):\n"
OPEN_MAPS_END = "\n\ndef reset_profiles():\n"

FAST_OPEN_MAPS_FUNCTION = r'''def open_maps_and_search(page, browser_context, keyword, fallback_keyword, anchor):
    def bring_front_safe():
        try:
            page.bring_to_front()
        except Exception:
            pass

    def run_search_with_url(query_text, timeout=24000):
        target_url = build_maps_keyword_search_url(query_text, anchor)
        page.goto(target_url, wait_until="domcontentloaded", timeout=timeout)
        bring_front_safe()
        page.wait_for_timeout(350)
        dismiss_google_maps_overlays(page)
        return wait_for_maps_results_state(page, timeout=14000)

    def run_search_with_box(query_text):
        dismiss_google_maps_overlays(page)
        search_box = wait_for_google_maps_search_box(page, timeout=9000)
        try:
            search_box.click()
        except Exception:
            pass
        search_box.fill(query_text)
        page.keyboard.press("Enter")
        page.wait_for_timeout(500)
        dismiss_google_maps_overlays(page)
        return wait_for_maps_results_state(page, timeout=12000)

    if anchor:
        try:
            browser_context.grant_permissions(["geolocation"], origin="https://www.google.com")
        except Exception:
            pass

    queries = []
    for query_text in (keyword, fallback_keyword):
        query_text = safe_string(query_text)
        if query_text and query_text not in queries:
            queries.append(query_text)

    last_state = "timeout"
    for query_text in queries:
        try:
            search_state = run_search_with_url(query_text)
        except Exception as exc:
            log_place_error(0, build_maps_keyword_search_url(query_text, anchor), exc)
            search_state = "timeout"

        last_state = search_state
        if search_state not in {"empty", "timeout"}:
            return search_state

    for query_text in queries[:1]:
        try:
            start_url = build_maps_search_url(anchor) if anchor else "https://www.google.com/maps?hl=vi"
            page.goto(start_url, wait_until="domcontentloaded", timeout=18000)
            bring_front_safe()
            search_state = run_search_with_box(query_text)
            if search_state not in {"empty", "timeout"}:
                return search_state
            last_state = search_state
        except Exception as exc:
            log_place_error(0, query_text, exc)
            last_state = "timeout"

    return last_state
'''

HELPER_INSERT_AFTER = "def wait_for_maps_results_state(page, timeout=30000):\n"
HELPER_INSERT_ANCHOR = "\n\ndef log_place_error(thread_id, url, exc):\n"
PLACE_HELPERS = r'''
def get_maps_place_items(page):
    selectors = [
        'a[href*="/maps/place/"]',
        'a.hfpxzc[href]',
        'div[role="article"] a[href*="/maps/place/"]',
        'div.Nv2PK a[href*="/maps/place/"]',
    ]
    for selector in selectors:
        try:
            items = page.locator(selector).all()
            if items:
                return items
        except Exception:
            continue
    return []


def get_maps_result_count(page):
    try:
        return len(get_maps_place_items(page))
    except Exception:
        return 0
'''.strip()

UI_REPLACEMENTS = [
    (
        'root.title(f"KB Maps Pro v{APP_RELEASE_VERSION} - Dashboard")',
        'root.title(f"THL Maps Pro v{APP_RELEASE_VERSION}")',
    ),
    (
        'text=f"KB Maps Pro v{APP_RELEASE_VERSION}",',
        'text=f"THL Maps Pro v{APP_RELEASE_VERSION}",',
    ),
    (
        'text="Bảng điều khiển quét Google Maps với bố cục gọn, đậm và dễ theo dõi hơn.",',
        'text="Bảng điều khiển quét Google Maps — bố cục compact, không scroll, ưu tiên vùng kết quả.",',
    ),
    (
        'text="Danh sách doanh nghiệp sẽ đổ trực tiếp vào bảng bên dưới.",',
        'text="Vùng chính được ưu tiên ~70% màn hình. Bảng rộng, đủ cột, không cần cuộn ngang.",',
    ),
    (
        'text="Bộ lọc tìm kiếm",',
        'text="Bộ lọc tìm kiếm",',
    ),
]

HIDE_ADVANCED_OLD = '''for widget in (
    field_radius,
    field_zoom,
    btn_paste_coord,
    search_hint,
    scan_context,
):
    widget.grid_remove()
'''
HIDE_ADVANCED_NEW = '''for widget in (
    search_hint,
):
    widget.grid_remove()
'''


def apply_gate9_patch(source_text: str) -> str:
    patched = source_text

    if OPEN_MAPS_START not in patched:
        raise RuntimeError("Gate 9 fail: không tìm thấy open_maps_and_search.")
    start = patched.find(OPEN_MAPS_START)
    end = patched.find(OPEN_MAPS_END, start)
    if end == -1:
        raise RuntimeError("Gate 9 fail: không tìm thấy điểm kết thúc open_maps_and_search.")
    patched = patched[:start] + FAST_OPEN_MAPS_FUNCTION + patched[end:]

    if "def get_maps_place_items(" not in patched:
        anchor = patched.find(HELPER_INSERT_ANCHOR)
        if anchor == -1:
            raise RuntimeError("Gate 9 fail: không tìm thấy vị trí chèn place helpers.")
        patched = patched[:anchor] + "\n\n" + PLACE_HELPERS + patched[anchor:]

    patched = patched.replace("items = page.locator('a[href*=\"/maps/place/\"]').all()", "items = get_maps_place_items(page)")
    patched = patched.replace("items = page.locator('a[href*=\"/maps/place/\"]').all()", "items = get_maps_place_items(page)")
    patched = patched.replace("items = page.locator('a[href*=\"/maps/place/\"]').all()", "items = get_maps_place_items(page)")
    patched = patched.replace("items = page.locator('a[href*=\"/maps/place/\"]').all()", "items = get_maps_place_items(page)")
    patched = patched.replace("items = page.locator('a[href*=\"/maps/place/\"]').all()", "items = get_maps_place_items(page)")
    patched = patched.replace("items = page.locator('a[href*=\"/maps/place/\"]').all()", "items = get_maps_place_items(page)")
    patched = patched.replace("items = page.locator('a[href*=\"/maps/place/\"]').all()", "items = get_maps_place_items(page)")
    patched = patched.replace("items = page.locator('a[href*=\"/maps/place/\"]').all()", "items = get_maps_place_items(page)")
    patched = patched.replace('items = page.locator(\'a[href*="/maps/place/"]\').all()', 'items = get_maps_place_items(page)')
    patched = patched.replace("items = page.locator('a[href*=\"/maps/place/\"]').all()", "items = get_maps_place_items(page)")

    for old_text, new_text in UI_REPLACEMENTS:
        patched = patched.replace(old_text, new_text)

    if HIDE_ADVANCED_OLD in patched:
        patched = patched.replace(HIDE_ADVANCED_OLD, HIDE_ADVANCED_NEW, 1)

    patched = patched.replace("time.sleep(3)\n                search_state", "time.sleep(0.4)\n                search_state")
    patched = patched.replace("page.wait_for_timeout(1500)", "page.wait_for_timeout(500)")
    patched = patched.replace("active_detail_page.wait_for_timeout(600)", "active_detail_page.wait_for_timeout(250)")
    patched = patched.replace("time.sleep(5)", "time.sleep(1.5)")

    if "THL Maps Pro" not in patched:
        raise RuntimeError("Gate 9 fail: UI title chưa được đổi về THL Maps Pro.")
    if "def get_maps_place_items(" not in patched:
        raise RuntimeError("Gate 9 fail: thiếu helper get_maps_place_items.")
    if "def open_maps_and_search(page, browser_context, keyword, fallback_keyword, anchor):" not in patched:
        raise RuntimeError("Gate 9 fail: thiếu open_maps_and_search.")
    return patched


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("Usage: apply_gate9_compact_ui_fast_maps.py <input_ui_cao_map.py> <output_ui_cao_map.py>", file=sys.stderr)
        return 2

    source_path = Path(argv[1]).resolve()
    output_path = Path(argv[2]).resolve()
    source_text = source_path.read_text(encoding="utf-8")
    patched_text = apply_gate9_patch(source_text)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(patched_text, encoding="utf-8", newline="\n")
    print(f"Gate 9 compact-ui-fast-maps source generated: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
