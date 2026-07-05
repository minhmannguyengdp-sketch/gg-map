# -*- coding: utf-8 -*-
"""Build-time patcher for Gate 6 Maps button audit.

Adds a safe command wrapper to every Tk button created through `make_button` so
Maps buttons never fail silently. The wrapper writes a technical log, updates
status labels when available, and shows a popup for uncaught exceptions.
"""
from __future__ import annotations

import sys
from pathlib import Path

INSERT_BEFORE = "def make_button(parent, text, command, bg, hover_bg, width=14):\n"
OLD_COMMAND_LINE = "        command=command,\n"
NEW_COMMAND_LINE = "        command=lambda: run_ui_button_command(text, command),\n"

BUTTON_SAFETY_BLOCK = r'''
MAPS_BUTTON_AUDIT_LABELS = {
    "BẮT ĐẦU QUÉT",
    "DỪNG NGAY",
    "DÁN TỌA ĐỘ",
    "DỌN BẢNG",
    "XUẤT EXCEL",
    "TICK CHỌN",
    "BỎ TICK",
    "SẮP XẾP TUYẾN",
    "XEM TRƯỚC TUYẾN",
    "MỞ TUYẾN MAPS",
}

TAX_BUTTON_AUDIT_LABELS = {
    "TRA CỨU",
    "DÁN NHANH",
    "XÓA FORM",
    "CHẠY HÀNG LOẠT",
    "DỪNG",
    "TẢI FILE MẪU",
    "XUẤT EXCEL",
}


def log_ui_button_error(button_label, exc):
    try:
        ensure_save_data_dir()
    except Exception:
        try:
            os.makedirs(SAVE_DATA_DIR, exist_ok=True)
        except Exception:
            pass

    error_text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)).strip()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payload = f"[{timestamp}] button={safe_string(button_label)}\n{error_text}\n\n"
    try:
        with open(os.path.join(SAVE_DATA_DIR, "ui_button_errors.log"), "a", encoding="utf-8") as log_file:
            log_file.write(payload)
    except Exception:
        try:
            with open(BROWSER_ERROR_LOG_PATH, "a", encoding="utf-8") as log_file:
                log_file.write(payload)
        except Exception:
            print(payload)


def run_ui_button_command(button_label, command):
    label = safe_string(button_label) or "Nút không tên"
    try:
        if not callable(command):
            raise RuntimeError(f"Nút '{label}' chưa có command hợp lệ.")
        return command()
    except Exception as exc:
        log_ui_button_error(label, exc)
        error_text = str(exc) or exc.__class__.__name__
        if label in TAX_BUTTON_AUDIT_LABELS and "tax_lbl_status" in globals():
            try:
                tax_lbl_status.config(text=f"Lỗi nút {label}: {error_text}", fg=color_for("danger"))
            except Exception:
                pass
        elif "set_runtime_status" in globals():
            try:
                set_runtime_status(f"Lỗi nút {label}: {error_text}", "danger", "LỖI NÚT")
            except Exception:
                pass
        try:
            messagebox.showerror(
                f"Lỗi nút {label}",
                f"Nút {label} gặp lỗi và đã ghi log kỹ thuật.\n\n{error_text}",
            )
        except Exception:
            pass
        return None
'''.strip()

MAPS_LABELS_REQUIRED = [
    "BẮT ĐẦU QUÉT",
    "DỪNG NGAY",
    "DÁN TỌA ĐỘ",
    "DỌN BẢNG",
    "XUẤT EXCEL",
    "TICK CHỌN",
    "BỎ TICK",
    "SẮP XẾP TUYẾN",
    "XEM TRƯỚC TUYẾN",
    "MỞ TUYẾN MAPS",
]

MAPS_HANDLER_MARKERS = [
    "start_app",
    "stop_app",
    "paste_coordinates_from_clipboard",
    "clear_results",
    "export_to_excel",
    "set_route_pick_for_targets(True)",
    "set_route_pick_for_targets(False)",
    "sort_route_for_sales",
    "preview_route_plan",
    "open_route_on_google_maps",
]


def apply_gate6_patch(source_text: str) -> str:
    patched = source_text

    missing_labels = [label for label in MAPS_LABELS_REQUIRED if f'"{label}"' not in patched]
    if missing_labels:
        raise RuntimeError("Gate 6 fail: thiếu label nút Maps: " + ", ".join(missing_labels))

    missing_handlers = [marker for marker in MAPS_HANDLER_MARKERS if marker not in patched]
    if missing_handlers:
        raise RuntimeError("Gate 6 fail: thiếu handler nút Maps: " + ", ".join(missing_handlers))

    if "def run_ui_button_command(" not in patched:
        if INSERT_BEFORE not in patched:
            raise RuntimeError("Không tìm thấy make_button để gắn safety wrapper.")
        patched = patched.replace(INSERT_BEFORE, BUTTON_SAFETY_BLOCK + "\n\n\n" + INSERT_BEFORE, 1)

    if NEW_COMMAND_LINE not in patched:
        if OLD_COMMAND_LINE not in patched:
            raise RuntimeError("Không tìm thấy command=command trong make_button.")
        patched = patched.replace(OLD_COMMAND_LINE, NEW_COMMAND_LINE, 1)

    if "command=lambda: run_ui_button_command(text, command)" not in patched:
        raise RuntimeError("Gate 6 fail: make_button chưa được bọc safety wrapper.")
    return patched


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("Usage: apply_gate6_maps_buttons.py <input_ui_cao_map.py> <output_ui_cao_map.py>", file=sys.stderr)
        return 2

    source_path = Path(argv[1]).resolve()
    output_path = Path(argv[2]).resolve()
    source_text = source_path.read_text(encoding="utf-8")
    patched_text = apply_gate6_patch(source_text)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(patched_text, encoding="utf-8", newline="\n")
    print(f"Gate 6 Maps button-audit source generated: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
