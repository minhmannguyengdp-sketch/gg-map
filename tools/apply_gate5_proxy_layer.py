# -*- coding: utf-8 -*-
"""Build-time patcher for Gate 5 proxy-layer diagnostics.

Adds explicit proxy format validation and a small Playwright IP check before
starting scan workers. Proxy failures are reported as proxy failures instead of
being mixed into generic Chrome launch errors.
"""
from __future__ import annotations

import sys
from pathlib import Path

INSERT_AFTER = '''def format_proxy_display(proxy_value):
    if not proxy_value:
        return "direct"
    if isinstance(proxy_value, dict):
        return proxy_value.get("server") or proxy_value.get("raw") or "direct"
    return safe_string(proxy_value)
'''

PROXY_DIAGNOSTIC_BLOCK = r'''
def validate_proxy_lines_for_scan(proxy_lines):
    valid = []
    invalid = []
    for line_no, proxy_line in enumerate(proxy_lines or [], start=1):
        raw = safe_string(proxy_line)
        if not raw:
            continue
        parsed = parse_proxy_line(raw)
        if parsed:
            valid.append(parsed)
        else:
            invalid.append(f"dòng {line_no}: {raw}")
    return valid, invalid


def test_proxy_ip_with_playwright(proxy_entry, headless=True, timeout_ms=18000):
    proxy_config = build_playwright_proxy(proxy_entry)
    if not proxy_config:
        return False, "Proxy không chuyển được sang cấu hình Playwright.", ""

    browser = None
    try:
        with sync_playwright() as playwright:
            browser = launch_playwright_browser(playwright, headless=True, proxy=proxy_config)
            page = browser.new_page()
            page.set_default_timeout(timeout_ms)
            page.goto(PUBLIC_IP_CHECK_URL, wait_until="domcontentloaded", timeout=timeout_ms)
            body_text = safe_string(page.locator("body").inner_text(timeout=6000))
            browser.close()
            browser = None
            if not body_text:
                return False, "Proxy mở được browser nhưng không đọc được IP public.", ""
            return True, "OK", body_text[:300]
    except Exception as exc:
        error_text = str(exc) or exc.__class__.__name__
        if "ERR_PROXY" in error_text or "proxy" in error_text.lower() or "407" in error_text:
            return False, "Proxy không kết nối/xác thực được: " + error_text, ""
        return False, "Không test được IP qua proxy: " + error_text, ""
    finally:
        if browser:
            try:
                browser.close()
            except Exception:
                pass


def diagnose_proxy_runtime(proxy_pool, raw_proxies=None, headless=True, max_tests=3):
    raw_proxies = list(raw_proxies or [])
    valid, invalid = validate_proxy_lines_for_scan(raw_proxies)
    result = {
        "ok": True,
        "errors": [],
        "warnings": [],
        "details": {
            "raw_proxy_count": len(raw_proxies),
            "valid_proxy_count": len(valid),
            "invalid_proxies": invalid[:10],
            "tested": [],
        },
    }

    if invalid:
        result["errors"].append("Proxy sai định dạng: " + "; ".join(invalid[:5]))

    if raw_proxies and not valid:
        result["errors"].append("Có nhập proxy nhưng không proxy nào đúng định dạng.")

    if result["errors"]:
        result["ok"] = False
        write_browser_diagnostic_log("proxy-preflight", "Proxy format validation failed.", result)
        return result

    if not proxy_pool or not proxy_pool.has_proxies:
        return result

    tested = 0
    passed = None
    max_tests = max(1, int(max_tests or 1))
    while tested < max_tests:
        proxy_entry = proxy_pool.acquire()
        if not proxy_entry:
            break
        tested += 1
        ok, message, public_ip_payload = test_proxy_ip_with_playwright(proxy_entry, headless=headless)
        result["details"]["tested"].append(
            {
                "server": proxy_entry.get("server"),
                "ok": ok,
                "message": message,
                "public_ip_payload": public_ip_payload,
            }
        )
        if ok:
            proxy_pool.report_success(proxy_entry)
            passed = proxy_entry
            break
        proxy_pool.report_failure(proxy_entry)

    if passed:
        result["warnings"].append(f"Proxy đã qua test IP: {passed.get('server')}")
        write_browser_diagnostic_log("proxy-preflight", "Proxy preflight OK.", result)
        return result

    result["ok"] = False
    result["errors"].append(
        "Không proxy nào qua được bước test IP riêng. Kiểm tra proxy chết, sai user/pass, hết hạn hoặc bị chặn kết nối."
    )
    write_browser_diagnostic_log("proxy-preflight", "Proxy connectivity validation failed.", result)
    return result


def format_proxy_diagnostic_report(result):
    details = result.get("details", {}) if isinstance(result, dict) else {}
    errors = result.get("errors", []) if isinstance(result, dict) else []
    tested = details.get("tested", []) or []
    lines = [
        "Proxy không qua kiểm tra trước khi quét.",
        "",
        f"- Proxy nhập vào: {details.get('raw_proxy_count', 0)}",
        f"- Proxy hợp lệ định dạng: {details.get('valid_proxy_count', 0)}",
    ]
    if details.get("invalid_proxies"):
        lines.append("- Proxy sai định dạng: " + "; ".join(details.get("invalid_proxies", [])[:5]))
    if tested:
        lines.append("")
        lines.append("Proxy đã test IP:")
        for item in tested:
            lines.append(f"- {item.get('server')}: {'OK' if item.get('ok') else 'FAIL'} - {item.get('message')}")
    if errors:
        lines.append("")
        lines.append("Lỗi cần xử lý:")
        lines.extend(f"- {item}" for item in errors)
    lines.extend(["", f"Log kỹ thuật: {BROWSER_ERROR_LOG_PATH}"])
    return "\n".join(lines)
'''.strip()

BROWSER_DIAG_BLOCK = '''    browser_diag = diagnose_browser_runtime(
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

BROWSER_AND_PROXY_DIAG_BLOCK = '''    browser_diag = diagnose_browser_runtime(
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

    proxy_diag = diagnose_proxy_runtime(
        proxy_pool,
        raw_proxies=proxies,
        headless=is_headless,
        max_tests=min(3, max(1, len(proxies) or 1)),
    )
    if not proxy_diag.get("ok"):
        report_text = format_proxy_diagnostic_report(proxy_diag)
        set_runtime_status(
            "Proxy không qua kiểm tra. Xem popup và log kỹ thuật.",
            "danger",
            "LỖI PROXY",
        )
        messagebox.showerror("Lỗi proxy", report_text)
        return

    save_last_config()
'''


def apply_gate5_patch(source_text: str) -> str:
    patched = source_text
    if "def diagnose_proxy_runtime(" not in patched:
        if INSERT_AFTER not in patched:
            raise RuntimeError("Không tìm thấy marker format_proxy_display để chèn proxy diagnostics.")
        patched = patched.replace(INSERT_AFTER, INSERT_AFTER + "\n\n" + PROXY_DIAGNOSTIC_BLOCK + "\n", 1)

    if "proxy_diag = diagnose_proxy_runtime(" not in patched:
        if BROWSER_DIAG_BLOCK not in patched:
            raise RuntimeError("Không tìm thấy block Chrome diagnose của Gate 1 để gắn proxy preflight.")
        patched = patched.replace(BROWSER_DIAG_BLOCK, BROWSER_AND_PROXY_DIAG_BLOCK, 1)

    if "def diagnose_proxy_runtime(" not in patched or "proxy_diag = diagnose_proxy_runtime(" not in patched:
        raise RuntimeError("Gate 5 fail: proxy diagnostics chưa được gắn đủ.")
    return patched


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("Usage: apply_gate5_proxy_layer.py <input_ui_cao_map.py> <output_ui_cao_map.py>", file=sys.stderr)
        return 2

    source_path = Path(argv[1]).resolve()
    output_path = Path(argv[2]).resolve()
    source_text = source_path.read_text(encoding="utf-8")
    patched_text = apply_gate5_patch(source_text)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(patched_text, encoding="utf-8", newline="\n")
    print(f"Gate 5 proxy-layer source generated: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
