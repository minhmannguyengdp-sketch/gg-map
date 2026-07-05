# -*- coding: utf-8 -*-
"""Build-time audit for Gate 7 MST tab.

Fails the build if MST tab button bindings or handlers are missing. It also
checks that MST lookup code stays independent from Playwright/Chrome runtime.
"""
from __future__ import annotations

import sys
from pathlib import Path

TAX_LABELS_REQUIRED = [
    "TRA CỨU",
    "DÁN NHANH",
    "XÓA FORM",
    "CHẠY HÀNG LOẠT",
    "DỪNG",
    "TẢI FILE MẪU",
    "XUẤT EXCEL",
]

TAX_HANDLER_MARKERS = [
    "run_single_tax_lookup",
    "paste_tax_lookup_quick",
    "clear_tax_lookup_form",
    "start_tax_batch_lookup",
    "stop_tax_batch_lookup",
    "download_tax_template",
    "export_tax_results_to_excel",
]

TAX_CODE_START_MARKER = "def execute_tax_lookup("
TAX_UI_END_MARKER = "def handle_main_close("


def apply_gate7_audit(source_text: str) -> str:
    missing_labels = [label for label in TAX_LABELS_REQUIRED if f'"{label}"' not in source_text]
    if missing_labels:
        raise RuntimeError("Gate 7 fail: thiếu label nút MST: " + ", ".join(missing_labels))

    missing_handlers = [marker for marker in TAX_HANDLER_MARKERS if marker not in source_text]
    if missing_handlers:
        raise RuntimeError("Gate 7 fail: thiếu handler MST: " + ", ".join(missing_handlers))

    if "def run_ui_button_command(" not in source_text:
        raise RuntimeError("Gate 7 fail: button safety wrapper chưa được gắn trước khi audit MST.")

    tax_start = source_text.find(TAX_CODE_START_MARKER)
    tax_end = source_text.find(TAX_UI_END_MARKER, tax_start)
    if tax_start == -1 or tax_end == -1:
        raise RuntimeError("Gate 7 fail: không khoanh được vùng code MST để audit độc lập Chrome.")

    tax_block = source_text[tax_start:tax_end]
    chrome_markers = ["sync_playwright", "launch_playwright", "chromium.launch", "browser_context"]
    found_chrome_markers = [marker for marker in chrome_markers if marker in tax_block]
    if found_chrome_markers:
        raise RuntimeError(
            "Gate 7 fail: code MST đang phụ thuộc Chrome/Playwright: " + ", ".join(found_chrome_markers)
        )

    return source_text


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("Usage: apply_gate7_mst_audit.py <input_ui_cao_map.py> <output_ui_cao_map.py>", file=sys.stderr)
        return 2

    source_path = Path(argv[1]).resolve()
    output_path = Path(argv[2]).resolve()
    source_text = source_path.read_text(encoding="utf-8")
    audited_text = apply_gate7_audit(source_text)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(audited_text, encoding="utf-8", newline="\n")
    print(f"Gate 7 MST audit passed: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
