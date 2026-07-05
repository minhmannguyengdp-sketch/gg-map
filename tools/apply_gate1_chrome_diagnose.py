# -*- coding: utf-8 -*-
"""Build-time patcher for Gate 1 Chrome/Playwright diagnostics.

This script keeps the tracked app source stable while generating a patched
entry file for PyInstaller. The built EXE includes the diagnostic gate before
browser workers are started.
"""
from __future__ import annotations

import sys
from pathlib import Path

DIAGNOSTIC_BLOCK = r'''
def get_playwright_browser_root():
    return os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or os.path.join(BASE_DIR, "ms-playwright")


def find_playwright_browser_entries(browser_root):
    if not browser_root or not os.path.isdir(browser_root):
        return []
    prefixes = (
        "chromium-",
        "chromium_headless_shell-",
        "chromium-headless-shell-",
    )
    entries = []
    try:
        for entry_name in os.listdir(browser_root):
            entry_path = os.path.join(browser_root, entry_name)
            if os.path.isdir(entry_path) and entry_name.startswith(prefixes):
                entries.append(entry_name)
    except Exception:
        return []
    return sorted(entries)


def write_browser_diagnostic_log(phase, message, details=None):
    try:
        ensure_save_data_dir()
    except Exception:
        os.makedirs(SAVE_DATA_DIR, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payload = {
        "phase": phase,
        "message": str(message or ""),
        "details": details or {},
    }
    try:
        with open(BROWSER_ERROR_LOG_PATH, "a", encoding="utf-8") as log_file:
            log_file.write(f"[{timestamp}] phase={phase}\n")
            log_file.write(str(message or "").strip() + "\n")
            if details:
                log_file.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
            log_file.write("\n")
    except Exception:
        pass


def format_browser_diagnostic_report(result):
    details = result.get("details", {}) if isinstance(result, dict) else {}
    errors = result.get("errors", []) if isinstance(result, dict) else []
    warnings = result.get("warnings", []) if isinstance(result, dict) else []

    lines = [
        "Không thể khởi động Chrome/Chromium để quét Google Maps.",
        "",
        "Thông tin kiểm tra:",
        f"- Base dir: {details.get('base_dir', BASE_DIR)}",
        f"- PLAYWRIGHT_BROWSERS_PATH: {details.get('playwright_browser_root', '')}",
        f"- Chromium bundled: {', '.join(details.get('playwright_entries', [])) or 'không thấy'}",
        f"- Chrome system: {details.get('chrome_executable') or 'không thấy'}",
        f"- Proxy hợp lệ: {details.get('valid_proxy_count', 0)} / {details.get('raw_proxy_count', 0)}",
    ]

    if errors:
        lines.extend(["", "Lỗi cần xử lý:"])
        lines.extend(f"- {item}" for item in errors)
    if warnings:
        lines.extend(["", "Cảnh báo:"])
        lines.extend(f"- {item}" for item in warnings)

    lines.extend([
        "",
        f"Log kỹ thuật: {BROWSER_ERROR_LOG_PATH}",
        "",
        "Gợi ý sửa nhanh:",
        "1. Build lại bằng build_gg_map_exe.ps1 để copy đủ thư mục ms-playwright.",
        "2. Nếu dùng bản source, chạy: python -m playwright install chromium.",
        "3. Nếu muốn chạy hiện cửa sổ, cài Google Chrome đúng path mặc định hoặc tắt proxy lỗi.",
    ])
    return "\n".join(lines)


def diagnose_browser_runtime(headless=False, raw_proxies=None, proxy_pool=None):
    raw_proxies = list(raw_proxies or [])
    browser_root = get_playwright_browser_root()
    chrome_executable = get_system_chrome_executable()
    playwright_entries = find_playwright_browser_entries(browser_root)

    result = {
        "ok": True,
        "errors": [],
        "warnings": [],
        "details": {
            "base_dir": BASE_DIR,
            "frozen": bool(getattr(sys, "frozen", False)),
            "playwright_browser_root": browser_root,
            "playwright_entries": playwright_entries,
            "chrome_executable": chrome_executable,
            "raw_proxy_count": len(raw_proxies),
            "valid_proxy_count": len(getattr(proxy_pool, "_entries", []) or []),
            "headless": bool(headless),
        },
    }

    if getattr(sys, "frozen", False):
        if not os.path.isdir(browser_root):
            result["errors"].append(
                "Thiếu thư mục ms-playwright cạnh file EXE. Playwright không có Chromium để mở trình duyệt."
            )
        elif not playwright_entries:
            result["errors"].append(
                "Thư mục ms-playwright có tồn tại nhưng không thấy chromium-* hoặc chromium_headless_shell-* bên trong."
            )

    invalid_proxies = []
    for line_no, proxy_line in enumerate(raw_proxies, start=1):
        if str(proxy_line or "").strip() and parse_proxy_line(proxy_line) is None:
            invalid_proxies.append(f"dòng {line_no}: {proxy_line}")
    if invalid_proxies:
        result["errors"].append(
            "Proxy sai định dạng: " + "; ".join(invalid_proxies[:5])
        )

    if not chrome_executable:
        result["warnings"].append(
            "Không thấy Google Chrome system theo path mặc định; app sẽ dùng Chromium bundled nếu có."
        )

    if not result["errors"]:
        try:
            with sync_playwright() as playwright:
                launch_args = {"headless": True}
                if not headless and chrome_executable:
                    launch_args["executable_path"] = chrome_executable
                browser = playwright.chromium.launch(**launch_args)
                browser.close()
        except Exception as exc:
            error_text = str(exc) or exc.__class__.__name__
            if "Executable doesn't exist" in error_text:
                result["errors"].append(
                    "Playwright báo không tìm thấy executable Chromium/Chrome. Kiểm tra lại ms-playwright hoặc cài Chrome system."
                )
            elif "proxy" in error_text.lower():
                result["errors"].append(
                    "Playwright lỗi proxy khi khởi động trình duyệt: " + error_text
                )
            else:
                result["errors"].append(
                    "Playwright không launch được Chromium/Chrome: " + error_text
                )
            result["details"]["launch_exception"] = error_text

    result["ok"] = not result["errors"]
    if not result["ok"]:
        write_browser_diagnostic_log("preflight", format_browser_diagnostic_report(result), result.get("details"))
    elif result["warnings"]:
        write_browser_diagnostic_log("preflight-warning", "Chrome/Playwright preflight OK nhưng có cảnh báo.", result)
    return result
'''.strip()

GET_CHROME_MARKER = '''def get_system_chrome_executable():
    for candidate in CHROME_EXECUTABLE_CANDIDATES:
        if candidate and os.path.exists(candidate):
            return candidate
    return ""
'''

START_APP_MARKER = '''    proxies = get_proxy_list()
    proxy_pool = ProxyPool(proxies)
    profile_manager = PersistentProfileManager(PROFILES_DIR)
    is_headless = var_headless.get()
    save_last_config()
'''

START_APP_REPLACEMENT = '''    proxies = get_proxy_list()
    proxy_pool = ProxyPool(proxies)
    profile_manager = PersistentProfileManager(PROFILES_DIR)
    is_headless = var_headless.get()

    browser_diag = diagnose_browser_runtime(
        headless=is_headless,
        raw_proxies=proxies,
        proxy_pool=proxy_pool,
    )
    if not browser_diag.get("ok"):
        report_text = format_browser_diagnostic_report(browser_diag)
        set_runtime_status(
            "Không thể mở Chrome/Chromium. Xem popup và log kỹ thuật.",
            "danger",
            "LỖI CHROME",
        )
        messagebox.showerror("Lỗi Chrome/Playwright", report_text)
        return

    save_last_config()
'''


def apply_gate1_patch(source_text: str) -> str:
    patched = source_text

    if "def diagnose_browser_runtime(" not in patched:
        if GET_CHROME_MARKER not in patched:
            raise RuntimeError("Không tìm thấy marker get_system_chrome_executable để chèn diagnostics.")
        patched = patched.replace(
            GET_CHROME_MARKER,
            GET_CHROME_MARKER + "\n\n" + DIAGNOSTIC_BLOCK + "\n",
            1,
        )

    if "diagnose_browser_runtime(\n        headless=is_headless" not in patched:
        if START_APP_MARKER not in patched:
            raise RuntimeError("Không tìm thấy marker start_app để gắn preflight diagnostics.")
        patched = patched.replace(START_APP_MARKER, START_APP_REPLACEMENT, 1)

    return patched


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("Usage: apply_gate1_chrome_diagnose.py <source_ui_cao_map.py> <output_ui_cao_map.py>", file=sys.stderr)
        return 2

    source_path = Path(argv[1]).resolve()
    output_path = Path(argv[2]).resolve()
    source_text = source_path.read_text(encoding="utf-8")
    patched_text = apply_gate1_patch(source_text)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(patched_text, encoding="utf-8", newline="\n")
    print(f"Gate 1 Chrome diagnostics source generated: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
