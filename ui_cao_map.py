# -*- coding: utf-8 -*-
import hashlib
import json
import math
import os
import platform
import queue
import random
import re
import shutil
import sys
import threading
import time
import traceback
import tkinter as tk
import unicodedata
import uuid
import webbrowser
import xml.etree.ElementTree as ET
from datetime import datetime
from dataclasses import dataclass
from difflib import SequenceMatcher
from tkinter import filedialog, messagebox, simpledialog, ttk
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

import pandas as pd
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

try:
    import winreg
except ImportError:
    winreg = None


def get_app_base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSww2D28Ci0ECLGKAi_tVG3GvaWKIVryruJKuZGza9j0yM1GV6_Lgj2iKXC9i_WDjMGCclQr3EYNcoK/pub?output=csv"
BASE_DIR = get_app_base_dir()
SAVE_DATA_DIR = os.path.join(BASE_DIR, "Save_data")
BUILD_VERSION_PATH = os.path.join(BASE_DIR, "build_version.txt")
LAST_CONFIG_PATH = os.path.join(SAVE_DATA_DIR, "ui_cao_map_last_config.json")
LICENSE_STATE_PATH = os.path.join(SAVE_DATA_DIR, "ui_cao_map_license.json")
LICENSE_SERVER_CONFIG_PATH = os.path.join(SAVE_DATA_DIR, "ui_cao_map_license_server.json")
PROXY_HEALTH_PATH = os.path.join(SAVE_DATA_DIR, "proxy_health.json")
PROFILES_DIR = os.path.join(SAVE_DATA_DIR, "browser_profiles")
LOCATION_ANCHOR_CACHE_PATH = os.path.join(SAVE_DATA_DIR, "location_anchor_cache.json")
BROWSER_ERROR_LOG_PATH = os.path.join(SAVE_DATA_DIR, "browser_worker_errors.log")
PUBLIC_IP_CHECK_URL = "https://api64.ipify.org?format=json"
LICENSE_STATUS_ACTIVE = "active"
LICENSE_APP_NAME = "THL Maps Pro"
LICENSE_APP_VERSION = "7.9"
LICENSE_SERVER_TIMEOUT = 20
MAX_PROXY_COOLDOWN_SECONDS = 1800
CHROME_EXECUTABLE_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Google\Chrome\Application\chrome.exe"),
]


def load_release_version():
    try:
        with open(BUILD_VERSION_PATH, "r", encoding="utf-8-sig") as handle:
            version = handle.read().strip()
            if version:
                return version
    except Exception:
        pass
    return "7.9.1"


APP_RELEASE_VERSION = load_release_version()

if getattr(sys, "frozen", False):
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(BASE_DIR, "ms-playwright")


def get_system_chrome_executable():
    for candidate in CHROME_EXECUTABLE_CANDIDATES:
        if candidate and os.path.exists(candidate):
            return candidate
    return ""


def launch_playwright_browser(playwright, headless=True, proxy=None):
    launch_args = {
        "headless": headless,
        "proxy": proxy,
    }
    try:
        return playwright.chromium.launch(**launch_args)
    except Exception as exc:
        if "Executable doesn't exist" not in str(exc):
            raise
        chrome_executable = get_system_chrome_executable()
        if not chrome_executable:
            raise
        launch_args["executable_path"] = chrome_executable
        return playwright.chromium.launch(**launch_args)


def launch_playwright_persistent_context(playwright, context_args):
    try:
        return playwright.chromium.launch_persistent_context(**context_args)
    except Exception as exc:
        if "Executable doesn't exist" not in str(exc):
            raise
        chrome_executable = get_system_chrome_executable()
        if not chrome_executable:
            raise
        fallback_args = dict(context_args)
        fallback_args["executable_path"] = chrome_executable
        return playwright.chromium.launch_persistent_context(**fallback_args)

APP_THEME = {
    "bg": "#0B1220",
    "surface": "#111A2D",
    "panel": "#16213A",
    "panel_alt": "#1C2A46",
    "border": "#2A3A59",
    "text": "#F8FAFC",
    "muted": "#93A4BD",
    "accent": "#22C55E",
    "accent_hover": "#16A34A",
    "info": "#38BDF8",
    "danger": "#EF4444",
    "danger_hover": "#DC2626",
    "warning": "#F59E0B",
    "violet": "#8B5CF6",
}

STATUS_COLORS = {
    "muted": APP_THEME["muted"],
    "info": APP_THEME["info"],
    "success": APP_THEME["accent"],
    "danger": APP_THEME["danger"],
    "warning": APP_THEME["warning"],
}

FONT_FAMILY = "Segoe UI"

login_success = False
final_data = []
seen_urls = set()
data_lock = threading.Lock()
is_running = False
active_threads = 0
_machine_identity_cache = None
next_row_id = 1
route_source_lookup = {}
tax_results_data = []
tax_results_lock = threading.Lock()
tax_batch_runner = None
tax_batch_file_path = ""
tax_batch_dataframe = None

TREE_COLUMNS = (
    "pick",
    "stt",
    "route_order",
    "route_cluster",
    "name",
    "phone",
    "address",
    "lat",
    "lng",
    "route_distance",
    "route_time",
    "route_note",
)

ROUTE_OUTPUT_COLUMNS = [
    "STT",
    "Tên",
    "SĐT",
    "Địa chỉ",
    "latitude",
    "longitude",
    "thu_tu_tuyen",
    "cum_tuyen",
    "khoang_cach_uoc_tinh",
    "thoi_gian_uoc_tinh",
    "ghi_chu_tuyen",
]

ROUTE_MODE_SPEED_KMH = {
    "Tiết kiệm": 24.0,
    "Cân bằng": 30.0,
    "Nhanh": 36.0,
}


@dataclass
class LocationAnchor:
    query_text: str
    lat: float
    lng: float
    zoom: int = 14
    radius_km: float = 5.0
    resolved_address: str = ""
    source: str = "manual"
    resolved_at: int = 0


def color_for(kind):
    return STATUS_COLORS.get(kind, APP_THEME["muted"])


def set_app_icon(window):
    # No-op: logo branding has been intentionally removed.
    return


def ensure_save_data_dir():
    os.makedirs(SAVE_DATA_DIR, exist_ok=True)


def load_json_file(path):
    if not os.path.exists(path):
        return {}

    try:
        with open(path, "r", encoding="utf-8") as json_file:
            data = json.load(json_file)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_json_file(path, payload):
    ensure_save_data_dir()
    with open(path, "w", encoding="utf-8") as json_file:
        json.dump(payload, json_file, ensure_ascii=False, indent=2)


def normalize_lookup_text(value, keep_spaces=False):
    text = unicodedata.normalize("NFKC", str(value or "")).lower().strip()
    text = text.replace("đ", "d")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[_/\\|]+", " ", text)
    text = re.sub(r"[-]+", " ", text)

    abbreviations = {
        r"\bcty\b": "cong ty",
        r"\btnhh\b": "trach nhiem huu han",
        r"\bcp\b": "co phan",
        r"\bdntn\b": "doanh nghiep tu nhan",
        r"\bhkd\b": "ho kinh doanh",
    }
    for pattern, replacement in abbreviations.items():
        text = re.sub(pattern, replacement, text)

    location_aliases = {
        r"\btp\.?\s*hcm\b": "thanh pho ho chi minh",
        r"\btphcm\b": "thanh pho ho chi minh",
        r"\bhcm\b": "thanh pho ho chi minh",
        r"\bho chi minh\b": "thanh pho ho chi minh",
        r"\bq\.\b": "quan ",
        r"\bp\.\b": "phuong ",
        r"\bkp\b": "khu pho",
        r"\bap\b": "ap",
        r"\bd\.\b": "duong ",
    }
    for pattern, replacement in location_aliases.items():
        text = re.sub(pattern, replacement, text)

    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if keep_spaces:
        return text
    return re.sub(r"\s+", "", text)


def resolve_column_name(dataframe, *candidates):
    normalized_columns = {}
    for column in dataframe.columns:
        normalized_columns.setdefault(normalize_lookup_text(column), column)

    for candidate in candidates:
        column_name = normalized_columns.get(normalize_lookup_text(candidate))
        if column_name:
            return column_name
    return None


def safe_string(value):
    if pd.isna(value):
        return ""
    return str(value).strip()


def get_windows_machine_guid():
    if winreg is None:
        return ""

    access_flags = winreg.KEY_READ
    if hasattr(winreg, "KEY_WOW64_64KEY"):
        access_flags |= winreg.KEY_WOW64_64KEY

    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
            0,
            access_flags,
        ) as registry_key:
            machine_guid, _ = winreg.QueryValueEx(registry_key, "MachineGuid")
        return str(machine_guid).strip()
    except Exception:
        return ""


def build_fallback_machine_id():
    return "|".join(
        part
        for part in [
            os.environ.get("COMPUTERNAME", "").strip(),
            platform.node().strip(),
            f"{uuid.getnode():012x}",
            platform.platform(),
        ]
        if part
    )


def get_machine_identity():
    global _machine_identity_cache

    if _machine_identity_cache is not None:
        return _machine_identity_cache

    raw_id = get_windows_machine_guid() or build_fallback_machine_id()
    fingerprint = hashlib.sha256(raw_id.encode("utf-8")).hexdigest()
    _machine_identity_cache = {
        "raw_id": raw_id,
        "fingerprint": fingerprint,
        "display_id": fingerprint[:12].upper(),
    }
    return _machine_identity_cache


def load_saved_license():
    return load_json_file(LICENSE_STATE_PATH)


def save_license_state(license_key, customer_name, machine_identity, server_machine_id=""):
    payload = {
        "version": 1,
        "license_key": license_key,
        "customer_name": customer_name,
        "machine_fingerprint": machine_identity["fingerprint"],
        "machine_display_id": machine_identity["display_id"],
        "server_machine_id": server_machine_id,
        "activated_at": int(time.time()),
    }
    save_json_file(LICENSE_STATE_PATH, payload)


def get_saved_license_status():
    saved_license = load_saved_license()
    if not saved_license:
        return False, {}, ""

    saved_key = safe_string(saved_license.get("license_key"))
    if not saved_key:
        return False, {}, ""

    current_machine = get_machine_identity()
    if safe_string(saved_license.get("machine_fingerprint")) != current_machine["fingerprint"]:
        return False, saved_license, "License đã lưu không khớp ID máy hiện tại."

    return True, saved_license, ""


def load_license_server_config():
    return load_json_file(LICENSE_SERVER_CONFIG_PATH)


def save_license_server_config(api_url):
    payload = load_license_server_config()
    payload["license_api_url"] = safe_string(api_url)
    save_json_file(LICENSE_SERVER_CONFIG_PATH, payload)


def get_license_api_url():
    env_url = safe_string(os.environ.get("THL_LICENSE_API_URL"))
    if env_url:
        return env_url

    config = load_license_server_config()
    return safe_string(config.get("license_api_url") or config.get("web_app_url"))


def looks_like_activation_url(url):
    cleaned_url = safe_string(url)
    if not cleaned_url.startswith(("http://", "https://")):
        return False

    if cleaned_url.startswith("https://script.google.com/macros/s/") and "/exec" in cleaned_url:
        return True

    parsed_url = urllib_parse.urlsplit(cleaned_url)
    normalized_path = parsed_url.path.lower()
    return bool(parsed_url.netloc) and normalized_path.startswith("/api/apps/") and normalized_path.endswith("/activate")


def prompt_license_api_url(parent=None):
    current_url = get_license_api_url()
    api_url = simpledialog.askstring(
        "Cấu hình server kích hoạt",
        "Dán URL server kích hoạt (hỗ trợ link /exec cũ hoặc /api/apps/.../activate):",
        initialvalue=current_url,
        parent=parent,
    )
    if api_url is None:
        return False

    api_url = safe_string(api_url)
    if not api_url:
        messagebox.showwarning("Thiếu URL", "Vui lòng nhập URL server kích hoạt.", parent=parent)
        return False

    if not looks_like_activation_url(api_url):
        messagebox.showwarning(
            "Kiểm tra URL",
            "URL này chưa giống endpoint kích hoạt hợp lệ. Hãy kiểm tra lại trước khi lưu.",
            parent=parent,
        )

    save_license_server_config(api_url)
    return True


def post_json_request(url, payload, timeout=LICENSE_SERVER_TIMEOUT):
    request_body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    parsed_url = urllib_parse.urlsplit(url)
    request_headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json",
        "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Chrome/137.0.0.0 Safari/537.36 THLMaps/{APP_RELEASE_VERSION}"
        ),
    }
    if parsed_url.scheme in {"http", "https"} and parsed_url.netloc:
        origin = f"{parsed_url.scheme}://{parsed_url.netloc}"
        request_headers["Origin"] = origin
        request_headers["Referer"] = f"{origin}/"

    request_obj = urllib_request.Request(
        url,
        data=request_body,
        headers=request_headers,
        method="POST",
    )

    try:
        with urllib_request.urlopen(request_obj, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            raw_response = response.read().decode(charset, errors="replace")
    except urllib_error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace").strip()
        message = error_body[:250] if error_body else "Không có nội dung phản hồi."
        raise RuntimeError(f"Máy chủ kích hoạt trả về HTTP {exc.code}: {message}") from exc
    except urllib_error.URLError as exc:
        raise RuntimeError(f"Không kết nối được máy chủ kích hoạt: {exc.reason}") from exc
    except Exception as exc:
        raise RuntimeError(f"Lỗi gọi máy chủ kích hoạt: {exc}") from exc

    try:
        data = json.loads(raw_response)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Máy chủ kích hoạt không trả về JSON hợp lệ.") from exc

    if not isinstance(data, dict):
        raise RuntimeError("Máy chủ kích hoạt trả về dữ liệu không đúng định dạng.")
    return data


def activate_license_with_server(license_key, machine_identity):
    api_url = get_license_api_url()
    if not api_url:
        raise RuntimeError(
            f"Chưa cấu hình server kích hoạt.\nHãy tạo file {LICENSE_SERVER_CONFIG_PATH} "
            "với license_api_url sau khi cấp endpoint kích hoạt."
        )

    response_data = post_json_request(
        api_url,
        {
            "action": "activate_license",
            "license_key": safe_string(license_key),
            "machine_id": machine_identity["fingerprint"],
            "machine_display_id": machine_identity["display_id"],
            "app_name": LICENSE_APP_NAME,
            "app_version": LICENSE_APP_VERSION,
        },
    )

    return {
        "ok": bool(response_data.get("ok")),
        "code": safe_string(response_data.get("code")).lower(),
        "message": safe_string(response_data.get("message")),
        "status": safe_string(response_data.get("status")).lower(),
        "customer_name": safe_string(response_data.get("customer_name")),
        "machine_id": safe_string(response_data.get("machine_id")),
    }


def machine_matches_lock(locked_machine_id, machine_identity):
    locked_token = normalize_lookup_text(locked_machine_id)
    if not locked_token:
        return True

    candidates = {
        normalize_lookup_text(machine_identity["fingerprint"]),
        normalize_lookup_text(machine_identity["display_id"]),
        normalize_lookup_text(machine_identity["raw_id"]),
    }
    return locked_token in candidates


def fetch_license_record(license_key):
    df = pd.read_csv(SHEET_CSV_URL)

    key_column = resolve_column_name(df, "Mã Kích Hoạt", "Ma Kich Hoat", "License Key", "License")
    status_column = resolve_column_name(df, "Trạng Thái", "Trang Thai", "Status")
    customer_column = resolve_column_name(df, "Khách hàng", "Khach hang", "Customer")
    machine_column = resolve_column_name(
        df,
        "Machine ID",
        "MachineID",
        "ID Máy",
        "Id May",
        "Fingerprint",
        "Machine Fingerprint",
    )

    if not key_column or not status_column:
        raise ValueError("Google Sheet đang thiếu cột Mã Kích Hoạt hoặc Trạng Thái.")

    normalized_key = safe_string(license_key)
    license_series = df[key_column].apply(safe_string)
    matched_rows = df[license_series == normalized_key]
    if matched_rows.empty:
        return None

    row = matched_rows.iloc[0]
    return {
        "status": safe_string(row[status_column]).lower(),
        "customer_name": safe_string(row[customer_column]) if customer_column else "",
        "machine_id": safe_string(row[machine_column]) if machine_column else "",
    }


def create_brand_logo(parent):
    # Kept for compatibility with older code paths, no logo rendering now.
    return tk.Frame(parent, width=1, height=1, bg=APP_THEME["bg"])


def center_window(window, width, height):
    window.update_idletasks()
    screen_w = window.winfo_screenwidth()
    screen_h = window.winfo_screenheight()
    pos_x = max((screen_w - width) // 2, 0)
    pos_y = max((screen_h - height) // 2, 0)
    window.geometry(f"{width}x{height}+{pos_x}+{pos_y}")


def style_entry(widget, justify="left"):
    widget.configure(
        bg=APP_THEME["panel"],
        fg=APP_THEME["text"],
        insertbackground=APP_THEME["text"],
        relief="flat",
        bd=0,
        justify=justify,
        highlightthickness=1,
        highlightbackground=APP_THEME["border"],
        highlightcolor=APP_THEME["accent"],
        font=(FONT_FAMILY, 9),
    )


def style_text_widget(widget):
    widget.configure(
        bg=APP_THEME["panel"],
        fg=APP_THEME["text"],
        insertbackground=APP_THEME["text"],
        relief="flat",
        bd=0,
        wrap=tk.WORD,
        highlightthickness=1,
        highlightbackground=APP_THEME["border"],
        highlightcolor=APP_THEME["accent"],
        font=(FONT_FAMILY, 10),
        padx=10,
        pady=10,
    )


def style_spinbox(widget):
    widget.configure(
        bg=APP_THEME["panel"],
        fg=APP_THEME["text"],
        insertbackground=APP_THEME["text"],
        relief="flat",
        bd=0,
        justify="center",
        highlightthickness=1,
        highlightbackground=APP_THEME["border"],
        highlightcolor=APP_THEME["accent"],
        font=(FONT_FAMILY, 9),
        buttonbackground=APP_THEME["panel_alt"],
        buttonuprelief="flat",
        buttondownrelief="flat",
        disabledbackground=APP_THEME["panel"],
        disabledforeground=APP_THEME["muted"],
        readonlybackground=APP_THEME["panel"],
    )


def make_button(parent, text, command, bg, hover_bg, width=14):
    button = tk.Button(
        parent,
        text=text,
        command=command,
        bg=bg,
        fg="white",
        activebackground=hover_bg,
        activeforeground="white",
        relief="flat",
        bd=0,
        cursor="hand2",
        font=(FONT_FAMILY, 9, "bold"),
        padx=10,
        pady=8,
        width=width,
        disabledforeground="#CFD8E3",
    )

    def on_enter(_event):
        if str(button["state"]) != str(tk.DISABLED):
            button.configure(bg=hover_bg)

    def on_leave(_event):
        if str(button["state"]) != str(tk.DISABLED):
            button.configure(bg=bg)

    button.bind("<Enter>", on_enter)
    button.bind("<Leave>", on_leave)
    return button


def make_card(parent, title, subtitle="", accent=None):
    accent = accent or APP_THEME["accent"]
    card = tk.Frame(
        parent,
        bg=APP_THEME["surface"],
        highlightbackground=APP_THEME["border"],
        highlightthickness=1,
        bd=0,
    )
    tk.Frame(card, bg=accent, height=4).pack(fill=tk.X)

    header = tk.Frame(card, bg=APP_THEME["surface"])
    header.pack(fill=tk.X, padx=18, pady=(14, 10))
    tk.Label(
        header,
        text=title,
        font=(FONT_FAMILY, 13, "bold"),
        bg=APP_THEME["surface"],
        fg=APP_THEME["text"],
    ).pack(anchor="w")
    if subtitle:
        tk.Label(
            header,
            text=subtitle,
            font=(FONT_FAMILY, 9),
            bg=APP_THEME["surface"],
            fg=APP_THEME["muted"],
            justify="left",
            wraplength=700,
        ).pack(anchor="w", pady=(4, 0))

    body = tk.Frame(card, bg=APP_THEME["surface"])
    body.pack(fill=tk.BOTH, expand=True, padx=18, pady=(0, 18))
    return card, body


def make_stat_tile(parent, label_text, value="--", accent=None):
    tile = tk.Frame(
        parent,
        bg=APP_THEME["panel"],
        highlightbackground=APP_THEME["border"],
        highlightthickness=1,
        bd=0,
    )
    tk.Label(
        tile,
        text=label_text.upper(),
        font=(FONT_FAMILY, 8, "bold"),
        bg=APP_THEME["panel"],
        fg=APP_THEME["muted"],
    ).pack(anchor="w", padx=12, pady=(10, 2))
    value_label = tk.Label(
        tile,
        text=value,
        font=(FONT_FAMILY, 15, "bold"),
        bg=APP_THEME["panel"],
        fg=accent or APP_THEME["text"],
    )
    value_label.pack(anchor="w", padx=12, pady=(0, 10))
    return tile, value_label


def setup_ttk_styles():
    style = ttk.Style()
    style.theme_use("clam")

    style.configure(
        "Treeview",
        background=APP_THEME["panel"],
        fieldbackground=APP_THEME["panel"],
        foreground=APP_THEME["text"],
        rowheight=30,
        borderwidth=0,
        relief="flat",
        font=(FONT_FAMILY, 10),
    )
    style.map(
        "Treeview",
        background=[("selected", "#1D4ED8")],
        foreground=[("selected", APP_THEME["text"])],
    )

    style.configure(
        "Treeview.Heading",
        background=APP_THEME["panel_alt"],
        foreground=APP_THEME["text"],
        borderwidth=0,
        relief="flat",
        font=(FONT_FAMILY, 10, "bold"),
        padding=(10, 8),
    )
    style.map("Treeview.Heading", background=[("active", APP_THEME["panel_alt"])])

    style.configure(
        "Vertical.TScrollbar",
        background=APP_THEME["panel_alt"],
        troughcolor=APP_THEME["bg"],
        arrowcolor=APP_THEME["muted"],
        bordercolor=APP_THEME["bg"],
        relief="flat",
    )

    style.configure(
        "Horizontal.TScrollbar",
        background=APP_THEME["panel_alt"],
        troughcolor=APP_THEME["bg"],
        arrowcolor=APP_THEME["muted"],
        bordercolor=APP_THEME["bg"],
        relief="flat",
    )

    style.configure(
        "Modern.TCheckbutton",
        background=APP_THEME["surface"],
        foreground=APP_THEME["text"],
        font=(FONT_FAMILY, 10),
    )
    style.map(
        "Modern.TCheckbutton",
        background=[("active", APP_THEME["surface"])],
        foreground=[("disabled", APP_THEME["muted"])],
    )

    style.configure(
        "Dashboard.TNotebook",
        background=APP_THEME["bg"],
        borderwidth=0,
        tabmargins=(0, 0, 0, 0),
    )
    style.configure(
        "Dashboard.TNotebook.Tab",
        background=APP_THEME["panel"],
        foreground=APP_THEME["text"],
        padding=(18, 8),
        font=(FONT_FAMILY, 10, "bold"),
        borderwidth=0,
    )
    style.map(
        "Dashboard.TNotebook.Tab",
        background=[("selected", APP_THEME["panel_alt"]), ("active", APP_THEME["panel_alt"])],
        foreground=[("selected", APP_THEME["accent"]), ("active", APP_THEME["text"])],
    )


def set_runtime_status(message, tone="muted", badge_text=None):
    if "lbl_stt" in globals():
        lbl_stt.config(text=message, fg=color_for(tone))
    if "lbl_state_badge" in globals():
        if badge_text:
            lbl_state_badge.config(text=badge_text)
        lbl_state_badge.config(fg=color_for(tone))


def log_browser_worker_error(thread_id, phase, proxy_entry, exc):
    ensure_save_data_dir()
    proxy_text = format_proxy_display(proxy_entry)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    error_text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)).strip()
    with open(BROWSER_ERROR_LOG_PATH, "a", encoding="utf-8") as log_file:
        log_file.write(
            f"[{timestamp}] thread={thread_id} phase={phase} proxy={proxy_text}\n"
            f"{error_text}\n\n"
        )


def notify_browser_worker_error(thread_id, phase, proxy_entry, exc):
    error_text = safe_string(exc) or exc.__class__.__name__
    proxy_text = format_proxy_display(proxy_entry)
    message = f"Luồng {thread_id} lỗi ở bước {phase} ({proxy_text}): {error_text}"
    log_browser_worker_error(thread_id, phase, proxy_entry, exc)
    print(message)
    root.after(0, lambda msg=message: set_runtime_status(msg, "danger", "LỖI CHROME"))


def normalize_phone_number(phone_text):
    text = safe_string(phone_text)
    if not text or text.upper() == "N/A":
        return ""
    digits = "".join(char for char in text if char.isdigit() or char == "+")
    if digits.startswith("+84"):
        digits = "0" + digits[3:]
    digits = "".join(char for char in digits if char.isdigit())
    if digits.startswith("84") and len(digits) >= 10:
        digits = "0" + digits[2:]
    return digits


def format_nullable_coordinate(value):
    numeric_value = safe_float(value)
    if numeric_value is None:
        return ""
    return format_coordinate_value(numeric_value)


def format_estimated_distance(distance_km):
    value = safe_float(distance_km)
    if value is None:
        return ""
    return f"{value:.2f} km"


def format_estimated_time(minutes_value):
    value = safe_float(minutes_value)
    if value is None:
        return ""
    if value < 60:
        return f"{int(round(value))} phút"
    hours = int(value // 60)
    minutes = int(round(value % 60))
    return f"{hours} giờ {minutes} phút" if minutes else f"{hours} giờ"


def default_route_values(row_data):
    row_data.setdefault("thu_tu_tuyen", "")
    row_data.setdefault("cum_tuyen", "")
    row_data.setdefault("khoang_cach_uoc_tinh", "")
    row_data.setdefault("thoi_gian_uoc_tinh", "")
    row_data.setdefault("ghi_chu_tuyen", "")
    row_data.setdefault("lat", "")
    row_data.setdefault("lng", "")
    row_data.setdefault("_route_selected", False)
    return row_data


def build_tree_row_values(row_data):
    default_route_values(row_data)
    return (
        "☑" if bool(row_data.get("_route_selected")) else "☐",
        row_data.get("STT", ""),
        safe_string(row_data.get("thu_tu_tuyen")),
        safe_string(row_data.get("cum_tuyen")),
        safe_string(row_data.get("Tên")),
        safe_string(row_data.get("SĐT")),
        safe_string(row_data.get("Địa chỉ")),
        format_nullable_coordinate(row_data.get("lat")),
        format_nullable_coordinate(row_data.get("lng")),
        format_estimated_distance(row_data.get("khoang_cach_uoc_tinh")),
        format_estimated_time(row_data.get("thoi_gian_uoc_tinh")),
        safe_string(row_data.get("ghi_chu_tuyen")),
    )


def make_row_tag(index_number):
    return "evenrow" if index_number % 2 == 0 else "oddrow"


def rebuild_tree_from_final_data():
    selected_ids = set(tree.selection())
    tree.delete(*tree.get_children())
    for idx, row_data in enumerate(final_data, start=1):
        row_data["STT"] = idx
        row_id = str(row_data.get("_row_id", idx))
        tree.insert("", "end", iid=row_id, values=build_tree_row_values(row_data), tags=(make_row_tag(idx),))
    keep_selection = [item_id for item_id in selected_ids if tree.exists(item_id)]
    if keep_selection:
        tree.selection_set(keep_selection)
    refresh_route_source_options()
    update_route_summary_labels()


def find_row_by_id(row_id):
    for row_data in final_data:
        if str(row_data.get("_row_id")) == str(row_id):
            return row_data
    return None


def toggle_route_pick_for_row(row_id):
    row_data = find_row_by_id(row_id)
    if not row_data:
        return
    row_data["_route_selected"] = not bool(row_data.get("_route_selected"))
    rebuild_tree_from_final_data()
    if tree.exists(str(row_id)):
        tree.selection_set((str(row_id),))


def set_route_pick_for_targets(selected_state):
    targets = tree.selection() or tree.get_children()
    if not targets:
        return
    for item_id in targets:
        row_data = find_row_by_id(item_id)
        if row_data:
            row_data["_route_selected"] = bool(selected_state)
    rebuild_tree_from_final_data()


def handle_tree_click_toggle(event):
    region = tree.identify("region", event.x, event.y)
    if region != "cell":
        return None

    column = tree.identify_column(event.x)
    row_id = tree.identify_row(event.y)
    if not row_id:
        return None

    # Cột đầu tiên là tick chọn tuyến.
    if column == "#1":
        toggle_route_pick_for_row(row_id)
        return "break"
    return None


def insert_result_row(row_data):
    default_route_values(row_data)
    row_id = str(row_data.get("_row_id", ""))
    if not row_id:
        return
    row_tag = make_row_tag(int(row_data.get("STT", 0) or 0))
    tree.insert("", "end", iid=row_id, values=build_tree_row_values(row_data), tags=(row_tag,))
    refresh_route_source_options()
    update_route_summary_labels()


def clear_results():
    targets = tree.selection() or tree.get_children()
    if not targets:
        set_runtime_status("Bảng kết quả đang trống.", "warning", "CHỜ DỮ LIỆU")
        return

    target_ids = {str(item_id) for item_id in targets}
    with data_lock:
        final_data[:] = [row for row in final_data if str(row.get("_row_id")) not in target_ids]
    rebuild_tree_from_final_data()
    set_runtime_status("Đã dọn sạch dữ liệu hiển thị trên bảng.", "muted", "SẴN SÀNG")


def collect_route_export_rows():
    rows = []
    for row_data in final_data:
        default_route_values(row_data)
        rows.append(
            {
                "STT": row_data.get("STT", ""),
                "Tên": safe_string(row_data.get("Tên")),
                "SĐT": normalize_phone_number(row_data.get("SĐT")),
                "Địa chỉ": safe_string(row_data.get("Địa chỉ")),
                "latitude": format_nullable_coordinate(row_data.get("lat")),
                "longitude": format_nullable_coordinate(row_data.get("lng")),
                "thu_tu_tuyen": safe_string(row_data.get("thu_tu_tuyen")),
                "cum_tuyen": safe_string(row_data.get("cum_tuyen")),
                "khoang_cach_uoc_tinh": safe_string(row_data.get("khoang_cach_uoc_tinh")),
                "thoi_gian_uoc_tinh": safe_string(row_data.get("thoi_gian_uoc_tinh")),
                "ghi_chu_tuyen": safe_string(row_data.get("ghi_chu_tuyen")),
            }
        )
    return rows


def export_route_data(file_path, grouped=False):
    export_rows = collect_route_export_rows()
    if not export_rows:
        messagebox.showwarning("Thiếu dữ liệu", "Chưa có dữ liệu để xuất file.")
        return False

    export_df = pd.DataFrame(export_rows, columns=ROUTE_OUTPUT_COLUMNS)
    if grouped:
        export_df["_sort_cluster"] = export_df["cum_tuyen"].astype(str)
        export_df["_sort_route"] = pd.to_numeric(export_df["thu_tu_tuyen"], errors="coerce").fillna(10**9)
        export_df["_sort_stt"] = pd.to_numeric(export_df["STT"], errors="coerce").fillna(10**9)
        export_df = export_df.sort_values(by=["_sort_cluster", "_sort_route", "_sort_stt"], na_position="last")
        export_df = export_df.drop(columns=["_sort_cluster", "_sort_route", "_sort_stt"])

    lower_path = file_path.lower()
    if lower_path.endswith(".csv"):
        export_df.to_csv(file_path, index=False, encoding="utf-8-sig")
    else:
        export_df.to_excel(file_path, index=False)

    return True


def export_to_excel():
    if not final_data:
        messagebox.showwarning("Thiếu dữ liệu", "Chưa có dữ liệu để xuất Excel.")
        return

    save_path = filedialog.asksaveasfilename(
        title="Lưu file Excel",
        defaultextension=".xlsx",
        filetypes=[("Excel Workbook", "*.xlsx")],
    )
    if not save_path:
        return

    if export_route_data(save_path, grouped=False):
        set_runtime_status(f"Đã xuất {len(final_data)} dòng dữ liệu ra file Excel.", "success", "XUẤT FILE")


def safe_float(value):
    try:
        return float(str(value).strip())
    except Exception:
        return None


def safe_int(value, default=0):
    try:
        return int(str(value).strip())
    except Exception:
        return default


def clamp(value, min_value, max_value):
    return max(min_value, min(max_value, value))


def get_entry_clean_value(entry):
    if getattr(entry, "_placeholder_active", False):
        return ""
    return entry.get().strip()


def set_entry_value(entry, value):
    text = safe_string(value)
    entry.configure(fg=APP_THEME["text"])
    entry.delete(0, tk.END)
    if text:
        entry.insert(0, text)
        entry._placeholder_active = False
        return

    if hasattr(entry, "_show_placeholder"):
        entry._show_placeholder()
    else:
        entry._placeholder_active = False


def attach_entry_placeholder(entry, placeholder_text):
    entry._placeholder_text = placeholder_text

    def show_placeholder():
        if entry.get().strip():
            entry.configure(fg=APP_THEME["text"])
            entry._placeholder_active = False
            return
        entry.configure(fg=APP_THEME["muted"])
        entry.delete(0, tk.END)
        entry.insert(0, placeholder_text)
        entry._placeholder_active = True

    def clear_placeholder(_event=None):
        if getattr(entry, "_placeholder_active", False):
            entry.delete(0, tk.END)
            entry.configure(fg=APP_THEME["text"])
            entry._placeholder_active = False

    def restore_placeholder(_event=None):
        if not entry.get().strip():
            show_placeholder()
        else:
            entry.configure(fg=APP_THEME["text"])
            entry._placeholder_active = False

    entry._show_placeholder = show_placeholder
    entry.bind("<FocusIn>", clear_placeholder, add="+")
    entry.bind("<FocusOut>", restore_placeholder, add="+")
    show_placeholder()


def normalize_coordinate_number(value):
    token = safe_string(value).replace(" ", "")
    if not token:
        return None

    if "," in token and "." in token:
        if token.rfind(",") > token.rfind("."):
            token = token.replace(".", "")
            token = token.replace(",", ".")
        else:
            token = token.replace(",", "")
    elif "," in token:
        token = token.replace(",", ".")
    return safe_float(token)


def validate_coordinate_range(latitude, longitude):
    if latitude is None or longitude is None:
        return False, "Không đọc được đủ cặp vĩ độ/kinh độ."
    if not (-90 <= latitude <= 90):
        return False, "Vĩ độ phải nằm trong khoảng [-90, 90]."
    if not (-180 <= longitude <= 180):
        return False, "Kinh độ phải nằm trong khoảng [-180, 180]."
    return True, ""


def format_coordinate_value(value):
    return f"{value:.6f}".rstrip("0").rstrip(".")


def parse_coordinates_from_text(raw_text):
    text = safe_string(raw_text)
    if not text:
        return None, None

    maps_match = re.search(r"@\s*(-?\d+(?:[.,]\d+)?),\s*(-?\d+(?:[.,]\d+)?)", text)
    if maps_match:
        tokens = [maps_match.group(1), maps_match.group(2)]
    else:
        tokens = re.findall(r"-?\d+(?:[.,]\d+)?", text)
        if len(tokens) < 2:
            return None, None
        tokens = tokens[:2]

    latitude = normalize_coordinate_number(tokens[0])
    longitude = normalize_coordinate_number(tokens[1])
    return latitude, longitude


def parse_google_maps_url_coordinates(raw_text):
    text = safe_string(raw_text)
    if not text:
        return None, None, "Clipboard đang trống."

    url_text = text.splitlines()[0].strip()
    parsed_url = urllib_parse.urlparse(url_text)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        return None, None, "Nội dung dán không phải URL hợp lệ."

    host = parsed_url.netloc.lower()
    if host.startswith("www."):
        host = host[4:]

    short_google_hosts = {"maps.app.goo.gl", "goo.gl", "g.co"}
    if host in short_google_hosts:
        try:
            request_obj = urllib_request.Request(
                url_text,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    )
                },
                method="GET",
            )
            with urllib_request.urlopen(request_obj, timeout=8) as response:
                redirected_url = safe_string(response.geturl())
                if redirected_url:
                    url_text = redirected_url
                    parsed_url = urllib_parse.urlparse(url_text)
                    host = parsed_url.netloc.lower()
                    if host.startswith("www."):
                        host = host[4:]
        except Exception:
            pass

    if "google." not in host and host not in {"maps.google.com", "google.com"}:
        return None, None, "URL không phải Google Maps."

    decoded_url = urllib_parse.unquote(url_text)
    is_maps_context = ("maps" in host) or ("/maps" in parsed_url.path) or ("maps" in decoded_url.lower())
    if not is_maps_context:
        return None, None, "URL không thuộc trang Google Maps."

    coord_match = re.search(r"@\s*(-?\d+(?:[.,]\d+)?),\s*(-?\d+(?:[.,]\d+)?)", decoded_url)
    if coord_match:
        latitude = normalize_coordinate_number(coord_match.group(1))
        longitude = normalize_coordinate_number(coord_match.group(2))
        return latitude, longitude, ""

    query_dict = urllib_parse.parse_qs(parsed_url.query)
    for key in ("q", "query", "ll", "sll", "center", "destination", "origin"):
        for token in query_dict.get(key, []):
            token_match = re.search(r"(-?\d+(?:[.,]\d+)?)\s*,\s*(-?\d+(?:[.,]\d+)?)", token)
            if token_match:
                latitude = normalize_coordinate_number(token_match.group(1))
                longitude = normalize_coordinate_number(token_match.group(2))
                return latitude, longitude, ""

    return None, None, "URL Google Maps chưa chứa tọa độ @lat,lng rõ ràng."


def parse_coordinates_or_maps_url(raw_text):
    text = safe_string(raw_text)
    if not text:
        return None, None, "Clipboard đang trống."

    if text.lower().startswith(("http://", "https://")):
        latitude, longitude, parse_error = parse_google_maps_url_coordinates(text)
        if latitude is not None and longitude is not None:
            return latitude, longitude, ""

        latitude = normalize_coordinate_number(text)
        longitude = None
        if latitude is not None:
            match = re.search(r"(-?\d+(?:[.,]\d+)?)\s*,\s*(-?\d+(?:[.,]\d+)?)", text)
            if match:
                longitude = normalize_coordinate_number(match.group(2))
        if latitude is not None and longitude is not None:
            is_valid, warning_text = validate_coordinate_range(latitude, longitude)
            if is_valid:
                return latitude, longitude, ""
            return None, None, warning_text

        return None, None, parse_error

    latitude, longitude = parse_coordinates_from_text(text)
    if latitude is not None and longitude is not None:
        is_valid, warning_text = validate_coordinate_range(latitude, longitude)
        if is_valid:
            return latitude, longitude, ""
        return None, None, warning_text

    latitude, longitude, parse_error = parse_google_maps_url_coordinates(text)
    if latitude is not None and longitude is not None:
        return latitude, longitude, ""

    return None, None, parse_error


def set_coordinate_entries(latitude, longitude):
    set_entry_value(ent_lat, format_coordinate_value(latitude))
    set_entry_value(ent_lng, format_coordinate_value(longitude))


def handle_coordinate_paste(_event=None):
    try:
        clipboard_text = root.clipboard_get()
    except Exception:
        return None

    latitude, longitude, parse_error = parse_coordinates_or_maps_url(clipboard_text)
    if latitude is None or longitude is None:
        if parse_error:
            messagebox.showwarning("Tọa độ không hợp lệ", parse_error)
        return None

    set_coordinate_entries(latitude, longitude)
    update_runtime_badges()
    set_runtime_status(
        f"Đã dán tọa độ: {format_coordinate_value(latitude)}, {format_coordinate_value(longitude)}",
        "info",
        "ANCHOR",
    )
    return "break"


def paste_coordinates_from_clipboard():
    try:
        clipboard_text = root.clipboard_get()
    except Exception:
        messagebox.showwarning("Thiếu dữ liệu", "Clipboard hiện không có URL Google Maps để dán.")
        return

    latitude, longitude, parse_error = parse_coordinates_or_maps_url(clipboard_text)
    if latitude is None or longitude is None:
        messagebox.showwarning(
            "URL Google Maps không hợp lệ",
            f"{parse_error}\nHãy dán link Google Maps có tọa độ, ví dụ: https://www.google.com/maps/@10.8231,106.6297,15z",
        )
        return

    set_coordinate_entries(latitude, longitude)
    update_runtime_badges()
    set_runtime_status(
        f"Đã dán tọa độ từ URL Maps: {format_coordinate_value(latitude)}, {format_coordinate_value(longitude)}",
        "info",
        "ANCHOR",
    )


def extract_coordinates_from_maps_text(*raw_candidates):
    patterns = [
        r"@\s*(-?\d+(?:[.,]\d+)?),\s*(-?\d+(?:[.,]\d+)?)",
        r"!3d(-?\d+(?:[.,]\d+)?)!4d(-?\d+(?:[.,]\d+)?)",
        r"ll=(-?\d+(?:[.,]\d+)?),\s*(-?\d+(?:[.,]\d+)?)",
        r"query=(-?\d+(?:[.,]\d+)?),\s*(-?\d+(?:[.,]\d+)?)",
    ]
    for candidate in raw_candidates:
        text = safe_string(candidate)
        if not text:
            continue
        decoded = urllib_parse.unquote(text)
        for pattern in patterns:
            match = re.search(pattern, decoded)
            if not match:
                continue
            latitude = normalize_coordinate_number(match.group(1))
            longitude = normalize_coordinate_number(match.group(2))
            is_valid, _warning = validate_coordinate_range(latitude, longitude)
            if is_valid:
                return latitude, longitude
    return None, None


def haversine_km(lat1, lng1, lat2, lng2):
    if None in {lat1, lng1, lat2, lng2}:
        return None

    radius_km = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)

    hav_a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * (math.sin(d_lambda / 2) ** 2)
    hav_c = 2 * math.atan2(math.sqrt(hav_a), math.sqrt(1 - hav_a))
    return radius_km * hav_c


def estimate_minutes_from_distance(distance_km, optimize_mode):
    speed_kmh = ROUTE_MODE_SPEED_KMH.get(optimize_mode, ROUTE_MODE_SPEED_KMH["Cân bằng"])
    if distance_km is None:
        return None
    return (distance_km / max(speed_kmh, 1.0)) * 60.0


def route_distance_delta(points, start_anchor, i, j):
    lat_start, lng_start = start_anchor
    a_lat, a_lng = (lat_start, lng_start) if i == 0 else (points[i - 1]["lat"], points[i - 1]["lng"])
    b_lat, b_lng = points[i]["lat"], points[i]["lng"]
    c_lat, c_lng = points[j]["lat"], points[j]["lng"]

    old_distance = haversine_km(a_lat, a_lng, b_lat, b_lng) or 0.0
    new_distance = haversine_km(a_lat, a_lng, c_lat, c_lng) or 0.0

    if j < len(points) - 1:
        d_lat, d_lng = points[j + 1]["lat"], points[j + 1]["lng"]
        old_distance += haversine_km(c_lat, c_lng, d_lat, d_lng) or 0.0
        new_distance += haversine_km(b_lat, b_lng, d_lat, d_lng) or 0.0

    return new_distance - old_distance


def refine_route_two_opt(points, start_anchor, optimize_mode):
    total_points = len(points)
    if total_points < 4:
        return points

    pass_by_mode = {"Nhanh": 1, "Cân bằng": 2, "Tiết kiệm": 3}
    max_points = 120
    iterations = pass_by_mode.get(optimize_mode, 2)
    if total_points > max_points:
        iterations = min(iterations, 1)

    refined = list(points)
    for _ in range(iterations):
        improved = False
        for i in range(total_points - 2):
            for j in range(i + 2, total_points):
                delta = route_distance_delta(refined, start_anchor, i, j)
                if delta < -0.001:
                    refined[i : j + 1] = reversed(refined[i : j + 1])
                    improved = True
        if not improved:
            break
    return refined


class BaseRoutePlanner:
    engine_name = "base"

    def sort_points(self, points, start_anchor, sort_type, optimize_mode):
        raise NotImplementedError


class LocalHeuristicRoutePlanner(BaseRoutePlanner):
    engine_name = "local_heuristic_v1"

    def sort_points(self, points, start_anchor, sort_type, optimize_mode):
        if not points:
            return []

        remaining = list(points)
        ordered = []
        current_lat, current_lng = start_anchor

        while remaining:
            nearest = min(
                remaining,
                key=lambda item: haversine_km(current_lat, current_lng, item["lat"], item["lng"]) or float("inf"),
            )
            ordered.append(nearest)
            remaining.remove(nearest)
            current_lat, current_lng = nearest["lat"], nearest["lng"]

        if sort_type in {"Thuận tuyến", "Tối ưu thời gian đi"}:
            ordered = refine_route_two_opt(ordered, start_anchor, optimize_mode)
        return ordered


ROUTE_PLANNER = LocalHeuristicRoutePlanner()


def refresh_route_source_options():
    global route_source_lookup
    if "cmb_route_start_pick" not in globals():
        return

    route_source_lookup = {}
    options = []
    for row_data in final_data:
        label = f"{row_data.get('STT', '')}. {safe_string(row_data.get('Tên'))} | {safe_string(row_data.get('Địa chỉ'))}"
        route_source_lookup[label] = row_data
        options.append(label)

    cmb_route_start_pick["values"] = options
    current_value = cmb_route_start_pick.get().strip()
    if current_value and current_value not in route_source_lookup:
        cmb_route_start_pick.set("")


def resolve_start_anchor_from_controls():
    start_input = get_entry_clean_value(ent_route_start) if "ent_route_start" in globals() else ""
    selected_label = safe_string(cmb_route_start_pick.get()) if "cmb_route_start_pick" in globals() else ""

    if start_input:
        lat_text, lng_text = parse_coordinates_from_text(start_input)
        is_valid, _warning = validate_coordinate_range(lat_text, lng_text)
        if is_valid:
            return lat_text, lng_text, f"Tọa độ nhập tay: {format_coordinate_value(lat_text)}, {format_coordinate_value(lng_text)}"

    if start_input:
        lat_text, lng_text, _error = parse_google_maps_url_coordinates(start_input)
        is_valid, _warning = validate_coordinate_range(lat_text, lng_text)
        if is_valid:
            return lat_text, lng_text, f"URL Maps: {format_coordinate_value(lat_text)}, {format_coordinate_value(lng_text)}"

    picked_row = route_source_lookup.get(selected_label)
    if picked_row:
        lat_value = safe_float(picked_row.get("lat"))
        lng_value = safe_float(picked_row.get("lng"))
        is_valid, _warning = validate_coordinate_range(lat_value, lng_value)
        if is_valid:
            return lat_value, lng_value, f"Điểm trong danh sách: {safe_string(picked_row.get('Tên'))}"

    if start_input:
        lowered = normalize_lookup_text(start_input)
        for row_data in final_data:
            haystack = f"{safe_string(row_data.get('Tên'))} {safe_string(row_data.get('Địa chỉ'))}"
            if lowered and lowered in normalize_lookup_text(haystack):
                lat_value = safe_float(row_data.get("lat"))
                lng_value = safe_float(row_data.get("lng"))
                is_valid, _warning = validate_coordinate_range(lat_value, lng_value)
                if is_valid:
                    return lat_value, lng_value, f"Khớp theo địa chỉ/tên: {safe_string(row_data.get('Tên'))}"

    lat_entry = normalize_coordinate_number(get_entry_clean_value(ent_lat))
    lng_entry = normalize_coordinate_number(get_entry_clean_value(ent_lng))
    is_valid, _warning = validate_coordinate_range(lat_entry, lng_entry)
    if is_valid:
        return lat_entry, lng_entry, "Lấy từ vĩ độ/kinh độ bộ lọc"

    return None, None, ""


def get_rows_by_scope(scope_text):
    if scope_text == "Chỉ các dòng đã chọn":
        selected_ids = {str(row.get("_row_id")) for row in final_data if bool(row.get("_route_selected"))}
        if not selected_ids:
            selected_ids = {str(item_id) for item_id in tree.selection()}
        if not selected_ids:
            return [], []
        indices = [idx for idx, row in enumerate(final_data) if str(row.get("_row_id")) in selected_ids]
    else:
        indices = list(range(len(final_data)))

    rows = [final_data[idx] for idx in indices]
    return rows, indices


def choose_cluster_size(total_points):
    if total_points <= 18:
        return 6
    if total_points <= 40:
        return 10
    if total_points <= 80:
        return 15
    return 20


def update_route_summary_labels():
    if "lbl_route_start_value" not in globals():
        return

    sorted_rows = [row for row in final_data if safe_string(row.get("thu_tu_tuyen"))]
    sorted_rows.sort(key=lambda row: safe_int(row.get("thu_tu_tuyen"), 0))
    total_distance = sum(safe_float(row.get("khoang_cach_uoc_tinh")) or 0.0 for row in sorted_rows)

    selected_start = get_entry_clean_value(ent_route_start) if "ent_route_start" in globals() else ""
    picked_start = safe_string(cmb_route_start_pick.get()) if "cmb_route_start_pick" in globals() else ""
    start_text = selected_start or picked_start or "Chưa chọn"

    lbl_route_start_value.config(text=start_text)
    lbl_route_order_value.config(text=str(len(sorted_rows)))
    lbl_route_total_points_value.config(text=str(len(final_data)))
    lbl_route_total_distance_value.config(text=f"{total_distance:.2f} km")


def apply_route_sort_result(sorted_rows, missing_rows, affected_indices, scope_text, start_anchor, optimize_mode):
    points_total = len(sorted_rows)
    cluster_size = choose_cluster_size(points_total)
    current_lat, current_lng = start_anchor

    for route_order, row_data in enumerate(sorted_rows, start=1):
        distance_km = haversine_km(current_lat, current_lng, row_data["lat"], row_data["lng"]) or 0.0
        time_minutes = estimate_minutes_from_distance(distance_km, optimize_mode) or 0.0
        row_data["thu_tu_tuyen"] = route_order
        row_data["cum_tuyen"] = f"Cụm {(route_order - 1) // cluster_size + 1}"
        row_data["khoang_cach_uoc_tinh"] = round(distance_km, 2)
        row_data["thoi_gian_uoc_tinh"] = round(time_minutes, 1)
        row_data["ghi_chu_tuyen"] = "Điểm bắt đầu chặng" if route_order == 1 else "Theo tuyến tối ưu cục bộ"
        current_lat, current_lng = row_data["lat"], row_data["lng"]

    for row_data in missing_rows:
        row_data["thu_tu_tuyen"] = ""
        row_data["cum_tuyen"] = ""
        row_data["khoang_cach_uoc_tinh"] = ""
        row_data["thoi_gian_uoc_tinh"] = ""
        row_data["ghi_chu_tuyen"] = "Thiếu tọa độ, cần kiểm tra lại dữ liệu"

    ordered_scope_rows = sorted_rows + missing_rows
    if scope_text == "Chỉ các dòng đã chọn":
        for index, row_data in zip(affected_indices, ordered_scope_rows):
            final_data[index] = row_data
    else:
        final_data[:] = ordered_scope_rows


def sort_route_for_sales():
    if not final_data:
        messagebox.showwarning("Thiếu dữ liệu", "Chưa có dữ liệu để sắp xếp tuyến.")
        return

    sort_type = safe_string(cmb_route_sort_type.get()) if "cmb_route_sort_type" in globals() else "Gần nhất trước"
    optimize_mode = safe_string(cmb_route_optimize.get()) if "cmb_route_optimize" in globals() else "Cân bằng"
    scope_text = safe_string(cmb_route_scope.get()) if "cmb_route_scope" in globals() else "Toàn bộ kết quả"

    start_lat, start_lng, start_text = resolve_start_anchor_from_controls()
    is_valid, warning_text = validate_coordinate_range(start_lat, start_lng)
    if not is_valid:
        messagebox.showwarning("Thiếu điểm bắt đầu", f"{warning_text}\nHãy nhập tọa độ hoặc chọn điểm bắt đầu từ danh sách.")
        return

    rows_in_scope, affected_indices = get_rows_by_scope(scope_text)
    if not rows_in_scope:
        messagebox.showwarning("Thiếu dòng dữ liệu", "Phạm vi đang chọn không có điểm để tối ưu tuyến.")
        return

    available_rows = []
    missing_rows = []
    for row_data in rows_in_scope:
        lat_value = safe_float(row_data.get("lat"))
        lng_value = safe_float(row_data.get("lng"))
        valid_pair, _warning = validate_coordinate_range(lat_value, lng_value)
        if valid_pair:
            available_rows.append(
                {
                    "row": row_data,
                    "lat": lat_value,
                    "lng": lng_value,
                }
            )
        else:
            missing_rows.append(row_data)

    if not available_rows:
        messagebox.showwarning("Thiếu tọa độ", "Không có điểm nào đủ vĩ độ/kinh độ để sắp xếp tuyến.")
        return

    sorted_nodes = ROUTE_PLANNER.sort_points(
        available_rows,
        start_anchor=(start_lat, start_lng),
        sort_type=sort_type,
        optimize_mode=optimize_mode,
    )
    sorted_rows = [node["row"] for node in sorted_nodes]
    apply_route_sort_result(sorted_rows, missing_rows, affected_indices, scope_text, (start_lat, start_lng), optimize_mode)
    rebuild_tree_from_final_data()

    total_distance = sum(safe_float(row.get("khoang_cach_uoc_tinh")) or 0.0 for row in sorted_rows)
    set_runtime_status(
        (
            f"Đã sắp xếp {len(sorted_rows)} điểm theo tuyến. "
            f"Tổng quãng đường ước tính: {total_distance:.2f} km. "
            f"Điểm bắt đầu: {start_text}"
        ),
        "success",
        "TUYẾN SALES",
    )


def preview_route_plan():
    route_rows = [row for row in final_data if safe_string(row.get("thu_tu_tuyen"))]
    if not route_rows:
        messagebox.showinfo("Xem trước tuyến", "Chưa có tuyến sắp xếp. Hãy bấm 'Sắp xếp tuyến' trước.")
        return

    route_rows.sort(key=lambda row: safe_int(row.get("thu_tu_tuyen"), 0))
    preview_lines = []
    for row_data in route_rows[:20]:
        preview_lines.append(
            f"{safe_string(row_data.get('thu_tu_tuyen'))}. {safe_string(row_data.get('Tên'))} | "
            f"{safe_string(row_data.get('Địa chỉ'))} | {format_estimated_distance(row_data.get('khoang_cach_uoc_tinh'))}"
        )

    total_distance = sum(safe_float(row.get("khoang_cach_uoc_tinh")) or 0.0 for row in route_rows)
    messagebox.showinfo(
        "Xem trước tuyến",
        (
            f"Tổng số điểm theo tuyến: {len(route_rows)}\n"
            f"Tổng quãng đường ước tính: {total_distance:.2f} km\n\n"
            f"{chr(10).join(preview_lines)}"
        ),
    )


def export_route_sorted_list():
    if not final_data:
        messagebox.showwarning("Thiếu dữ liệu", "Chưa có dữ liệu để xuất danh sách theo tuyến.")
        return

    save_path = filedialog.asksaveasfilename(
        title="Xuất danh sách theo tuyến",
        defaultextension=".xlsx",
        filetypes=[("Excel Workbook", "*.xlsx"), ("CSV UTF-8", "*.csv")],
    )
    if not save_path:
        return

    grouped = bool(var_route_group_cluster.get()) if "var_route_group_cluster" in globals() else False
    if export_route_data(save_path, grouped=grouped):
        set_runtime_status("Đã xuất danh sách tuyến cho sales.", "success", "XUẤT TUYẾN")
        messagebox.showinfo("Xuất dữ liệu", "Đã xuất danh sách theo tuyến thành công.")


def open_route_on_google_maps():
    ticked_rows = [row for row in final_data if bool(row.get("_route_selected"))]
    selected_ids = {str(item_id) for item_id in tree.selection()}
    selected_rows = [row for row in final_data if str(row.get("_row_id")) in selected_ids]

    if len(ticked_rows) >= 2:
        route_rows = ticked_rows
    elif len(selected_rows) >= 2:
        route_rows = selected_rows
    else:
        route_rows = [row for row in final_data if safe_string(row.get("thu_tu_tuyen"))]

    if len(route_rows) < 2:
        messagebox.showwarning(
            "Thiếu dữ liệu",
            "Hãy tick hoặc chọn tối thiểu 2 điểm trên bảng, hoặc sắp xếp tuyến trước rồi mở Maps.",
        )
        return

    if all(safe_string(row.get("thu_tu_tuyen")) for row in route_rows):
        route_rows.sort(key=lambda row: safe_int(row.get("thu_tu_tuyen"), 0))
    else:
        route_rows.sort(key=lambda row: safe_int(row.get("STT"), 0))

    start_lat, start_lng, _start_text = resolve_start_anchor_from_controls()
    start_ok, _warn = validate_coordinate_range(start_lat, start_lng)
    if not start_ok:
        first_row = route_rows[0]
        start_lat = safe_float(first_row.get("lat"))
        start_lng = safe_float(first_row.get("lng"))
    start_ok, _warn = validate_coordinate_range(start_lat, start_lng)
    if not start_ok:
        messagebox.showwarning("Thiếu tọa độ", "Không xác định được điểm bắt đầu hợp lệ để mở tuyến Maps.")
        return

    destination = route_rows[-1]
    destination_lat = safe_float(destination.get("lat"))
    destination_lng = safe_float(destination.get("lng"))
    if destination_lat is None or destination_lng is None:
        messagebox.showwarning("Thiếu tọa độ", "Điểm cuối tuyến chưa có tọa độ để mở bản đồ.")
        return

    waypoint_limit = 8
    waypoint_rows = route_rows[:waypoint_limit]
    waypoint_tokens = [
        f"{format_coordinate_value(safe_float(row.get('lat')))},"
        f"{format_coordinate_value(safe_float(row.get('lng')))}"
        for row in waypoint_rows
        if safe_float(row.get("lat")) is not None and safe_float(row.get("lng")) is not None
    ]
    query_params = {
        "api": "1",
        "origin": f"{format_coordinate_value(start_lat)},{format_coordinate_value(start_lng)}",
        "destination": f"{format_coordinate_value(destination_lat)},{format_coordinate_value(destination_lng)}",
        "travelmode": "driving",
    }
    if waypoint_tokens:
        query_params["waypoints"] = "|".join(waypoint_tokens)
    maps_url = "https://www.google.com/maps/dir/?" + urllib_parse.urlencode(query_params, safe="|,")
    webbrowser.open(maps_url)
    set_runtime_status("Đã mở tuyến trên Google Maps.", "info", "MAPS")


def parse_proxy_line(proxy_line):
    raw = safe_string(proxy_line)
    if not raw:
        return None

    working = raw
    if "://" not in working:
        if working.count(":") == 3:
            host, port, username, password = working.split(":", 3)
            if not host or not port:
                return None
            working = f"http://{host}:{port}"
            parsed = urllib_parse.urlparse(working)
            return {
                "raw": raw,
                "server": f"{parsed.scheme}://{parsed.hostname}:{parsed.port}",
                "username": username,
                "password": password,
            }
        if working.count(":") >= 1:
            working = f"http://{working}"
        else:
            return None

    parsed = urllib_parse.urlparse(working)
    if not parsed.scheme or not parsed.hostname or not parsed.port:
        return None

    if parsed.scheme.lower() not in {"http", "https", "socks5", "socks5h"}:
        return None

    return {
        "raw": raw,
        "server": f"{parsed.scheme.lower()}://{parsed.hostname}:{parsed.port}",
        "username": urllib_parse.unquote(parsed.username or ""),
        "password": urllib_parse.unquote(parsed.password or ""),
    }


def build_playwright_proxy(proxy_value):
    if not proxy_value:
        return None

    parsed = proxy_value
    if isinstance(proxy_value, str):
        parsed = parse_proxy_line(proxy_value)
    elif isinstance(proxy_value, dict):
        if "server" not in proxy_value:
            parsed = parse_proxy_line(proxy_value.get("raw", ""))
    else:
        parsed = None

    if not parsed or not parsed.get("server"):
        return None

    proxy_config = {"server": parsed["server"]}
    if parsed.get("username"):
        proxy_config["username"] = parsed["username"]
    if parsed.get("password"):
        proxy_config["password"] = parsed["password"]
    return proxy_config


def format_proxy_display(proxy_value):
    if not proxy_value:
        return "direct"
    if isinstance(proxy_value, dict):
        return proxy_value.get("server") or proxy_value.get("raw") or "direct"
    return safe_string(proxy_value)


def load_proxy_health():
    if not os.path.exists(PROXY_HEALTH_PATH):
        save_json_file(PROXY_HEALTH_PATH, {})
        return {}
    payload = load_json_file(PROXY_HEALTH_PATH)
    return payload if isinstance(payload, dict) else {}


def save_proxy_health(payload):
    save_json_file(PROXY_HEALTH_PATH, payload if isinstance(payload, dict) else {})


class ProxyPool:
    def __init__(self, proxy_lines):
        self._lock = threading.Lock()
        self._health_store = load_proxy_health()
        self._entries = []
        seen_raw = set()

        for line in proxy_lines:
            parsed = parse_proxy_line(line)
            if not parsed:
                continue
            if parsed["raw"] in seen_raw:
                continue
            seen_raw.add(parsed["raw"])
            self._entries.append(self._build_entry(parsed))

        # Ensure health file exists for review/ops visibility even before first success/failure.
        save_proxy_health(self._health_store)

    @property
    def has_proxies(self):
        return bool(self._entries)

    def _build_entry(self, parsed):
        historic = self._health_store.get(parsed["raw"], {})
        entry = {
            "raw": parsed["raw"],
            "server": parsed["server"],
            "username": parsed["username"],
            "password": parsed["password"],
            "success_count": safe_int(historic.get("success_count"), 0),
            "fail_count": safe_int(historic.get("fail_count"), 0),
            "fail_streak": safe_int(historic.get("fail_streak"), 0),
            "last_used_at": float(historic.get("last_used_at") or 0),
            "cooldown_until": float(historic.get("cooldown_until") or 0),
            "health_score": float(historic.get("health_score") or 70),
        }
        entry["health_score"] = float(clamp(entry["health_score"], 1, 100))
        return entry

    def _persist_locked(self):
        for entry in self._entries:
            self._health_store[entry["raw"]] = {
                "server": entry["server"],
                "success_count": entry["success_count"],
                "fail_count": entry["fail_count"],
                "fail_streak": entry["fail_streak"],
                "last_used_at": entry["last_used_at"],
                "cooldown_until": entry["cooldown_until"],
                "health_score": round(float(entry["health_score"]), 2),
                "updated_at": int(time.time()),
            }
        save_proxy_health(self._health_store)

    def acquire(self):
        with self._lock:
            if not self._entries:
                return None

            now_ts = time.time()
            available = [entry for entry in self._entries if entry["cooldown_until"] <= now_ts]
            if not available:
                return None

            weights = [max(1.0, float(entry["health_score"])) for entry in available]
            chosen = random.choices(available, weights=weights, k=1)[0]
            chosen["last_used_at"] = now_ts
            self._persist_locked()
            return dict(chosen)

    def report_success(self, proxy_entry):
        if not proxy_entry:
            return
        raw = proxy_entry.get("raw")
        with self._lock:
            target = next((item for item in self._entries if item["raw"] == raw), None)
            if not target:
                return
            target["success_count"] += 1
            target["fail_streak"] = 0
            target["cooldown_until"] = 0
            target["health_score"] = clamp(target["health_score"] + 6, 1, 100)
            self._persist_locked()

    def report_failure(self, proxy_entry):
        if not proxy_entry:
            return 0
        raw = proxy_entry.get("raw")
        with self._lock:
            target = next((item for item in self._entries if item["raw"] == raw), None)
            if not target:
                return 0
            target["fail_count"] += 1
            target["fail_streak"] += 1
            target["health_score"] = clamp(target["health_score"] - 12, 1, 100)
            cooldown_seconds = int(min(MAX_PROXY_COOLDOWN_SECONDS, 30 * (2 ** (target["fail_streak"] - 1))))
            target["cooldown_until"] = time.time() + cooldown_seconds
            self._persist_locked()
            return cooldown_seconds


class PersistentProfileManager:
    def __init__(self, base_dir):
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)

    def get_profile_path(self, thread_slot, proxy_entry, anchor):
        proxy_key = "direct"
        if proxy_entry:
            proxy_key = proxy_entry.get("server", "direct")

        anchor_key = "no_anchor"
        if anchor:
            anchor_key = f"{round(anchor.lat, 3)}|{round(anchor.lng, 3)}"

        key_material = f"{thread_slot}|{proxy_key}|{anchor_key}"
        digest = hashlib.sha256(key_material.encode("utf-8")).hexdigest()[:18]
        profile_path = os.path.join(self.base_dir, f"profile_{thread_slot}_{digest}")
        os.makedirs(profile_path, exist_ok=True)
        return profile_path

    def reset_all(self):
        if os.path.exists(self.base_dir):
            shutil.rmtree(self.base_dir, ignore_errors=True)
        os.makedirs(self.base_dir, exist_ok=True)


def load_location_anchor_cache():
    if not os.path.exists(LOCATION_ANCHOR_CACHE_PATH):
        save_json_file(LOCATION_ANCHOR_CACHE_PATH, {})
        return {}
    payload = load_json_file(LOCATION_ANCHOR_CACHE_PATH)
    return payload if isinstance(payload, dict) else {}


def save_location_anchor_cache(payload):
    save_json_file(LOCATION_ANCHOR_CACHE_PATH, payload if isinstance(payload, dict) else {})


def resolve_location_text_to_anchor(location_text):
    query = safe_string(location_text)
    if not query:
        return None

    params = urllib_parse.urlencode({"q": query, "format": "json", "limit": 1})
    req = urllib_request.Request(
        f"https://nominatim.openstreetmap.org/search?{params}",
        headers={"User-Agent": f"THL-Maps-Pro/{APP_RELEASE_VERSION}"},
    )
    with urllib_request.urlopen(req, timeout=12) as response:
        payload = json.loads(response.read().decode("utf-8", errors="replace"))
    if not payload:
        return None
    first = payload[0]
    lat = safe_float(first.get("lat"))
    lng = safe_float(first.get("lon"))
    if lat is None or lng is None:
        return None
    return {
        "lat": lat,
        "lng": lng,
        "resolved_address": safe_string(first.get("display_name")) or query,
    }


def resolve_location_anchor(location_text, latitude_text, longitude_text, zoom_text):
    zoom = clamp(safe_int(zoom_text, 14), 3, 20)
    now_ts = int(time.time())
    query = safe_string(location_text)
    manual_lat = normalize_coordinate_number(latitude_text)
    manual_lng = normalize_coordinate_number(longitude_text)

    if query:
        query_lat, query_lng, _query_error = parse_coordinates_or_maps_url(query)
        if query_lat is not None and query_lng is not None:
            return (
                LocationAnchor(
                    query_text=query,
                    lat=query_lat,
                    lng=query_lng,
                    zoom=zoom,
                    radius_km=5.0,
                    resolved_address="Google Maps URL" if query.lower().startswith(("http://", "https://")) else query,
                    source="url" if query.lower().startswith(("http://", "https://")) else "manual",
                    resolved_at=now_ts,
                ),
                "",
            )

        if query.lower().startswith(("http://", "https://")):
            parsed_url = urllib_parse.urlparse(query)
            query_hint = extract_google_maps_text_hint(parsed_url)
            if query_hint:
                query = query_hint

        cache_key = normalize_lookup_text(query)
        cache = load_location_anchor_cache()
        cached = cache.get(cache_key)
        if isinstance(cached, dict):
            cached_lat = safe_float(cached.get("lat"))
            cached_lng = safe_float(cached.get("lng"))
            if cached_lat is not None and cached_lng is not None:
                return (
                    LocationAnchor(
                        query_text=query,
                        lat=cached_lat,
                        lng=cached_lng,
                        zoom=zoom,
                        radius_km=float(cached.get("radius_km") or 5.0),
                        resolved_address=safe_string(cached.get("resolved_address")) or query,
                        source="cache",
                        resolved_at=safe_int(cached.get("resolved_at"), now_ts),
                    ),
                    "",
                )

        try:
            resolved = resolve_location_text_to_anchor(query)
        except Exception as exc:
            return None, f"Resolve location thất bại: {exc}"

        if not resolved:
            return None, "Không geocode được location text."

        anchor = LocationAnchor(
            query_text=query,
            lat=resolved["lat"],
            lng=resolved["lng"],
            zoom=zoom,
            radius_km=5.0,
            resolved_address=resolved["resolved_address"],
            source="geocode",
            resolved_at=now_ts,
        )
        cache[cache_key] = {
            "query_text": anchor.query_text,
            "lat": anchor.lat,
            "lng": anchor.lng,
            "zoom": anchor.zoom,
            "radius_km": anchor.radius_km,
            "resolved_address": anchor.resolved_address,
            "source": anchor.source,
            "resolved_at": anchor.resolved_at,
        }
        save_location_anchor_cache(cache)
        return anchor, ""

    if safe_string(latitude_text) or safe_string(longitude_text):
        if manual_lat is None or manual_lng is None:
            return None, "Vui lòng nhập đúng cả vĩ độ và kinh độ."

        valid_range, warning_text = validate_coordinate_range(manual_lat, manual_lng)
        if not valid_range:
            return None, warning_text

        return (
            LocationAnchor(
                query_text=safe_string(location_text),
                lat=manual_lat,
                lng=manual_lng,
                zoom=zoom,
                radius_km=5.0,
                resolved_address="Manual anchor",
                source="manual",
                resolved_at=now_ts,
            ),
            "",
        )

    return None, "Thiếu khu vực và chưa có vĩ độ/kinh độ thủ công."


def extract_google_maps_text_hint(parsed_url):
    if not parsed_url or not safe_string(parsed_url.netloc):
        return ""

    query_dict = urllib_parse.parse_qs(parsed_url.query)
    for key in ("q", "query", "destination", "origin"):
        for token in query_dict.get(key, []):
            token_text = safe_string(urllib_parse.unquote(token))
            if token_text:
                return token_text

    decoded_path = urllib_parse.unquote(parsed_url.path)
    for prefix in ("/maps/place/", "/maps/search/", "/maps/dir/"):
        if prefix in decoded_path:
            hint_text = decoded_path.split(prefix, 1)[1].split("/", 1)[0]
            hint_text = safe_string(hint_text).replace("+", " ")
            if hint_text and "@" not in hint_text:
                return hint_text

    return ""


def build_maps_search_url(anchor):
    if not anchor:
        return "https://www.google.com/maps"
    return f"https://www.google.com/maps/@{anchor.lat:.6f},{anchor.lng:.6f},{anchor.zoom}z"


def build_maps_keyword_search_url(query_text, anchor=None):
    encoded_query = urllib_parse.quote_plus(safe_string(query_text))
    if anchor:
        return (
            "https://www.google.com/maps/search/"
            f"{encoded_query}/@{anchor.lat:.6f},{anchor.lng:.6f},{anchor.zoom}z"
        )
    return f"https://www.google.com/maps/search/{encoded_query}"


def dismiss_google_maps_overlays(page):
    for btn_text in ["Chấp nhận", "Đồng ý", "Accept", "Agree", "Để sau", "No thanks"]:
        try:
            button = page.get_by_role("button", name=btn_text)
            if button.is_visible(timeout=1000):
                button.click()
                page.wait_for_timeout(400)
        except Exception:
            continue


def wait_for_google_maps_search_box(page, timeout=45000):
    search_box = page.locator("input#searchboxinput").first
    try:
        search_box.wait_for(state="visible", timeout=timeout)
        return search_box
    except Exception:
        alt_box = page.locator('input[name="q"]').first
        alt_box.wait_for(state="visible", timeout=5000)
        return alt_box


def wait_for_maps_results_state(page, timeout=30000):
    deadline = time.time() + max(1, timeout / 1000)
    no_result_markers = (
        "Khong tim thay ket qua",
        "Khong co ket qua",
        "No results found",
        "did not match any locations",
    )

    while time.time() < deadline:
        try:
            if page.locator('a[href*="/maps/place/"]').count() > 0:
                return "results"
        except Exception:
            pass

        try:
            if page.locator('div[role="feed"]').count() > 0:
                return "feed"
        except Exception:
            pass

        try:
            page_text = unicodedata.normalize("NFKD", page.locator("body").inner_text(timeout=1000))
            page_text = "".join(char for char in page_text if not unicodedata.combining(char)).lower()
            if any(marker.lower() in page_text for marker in no_result_markers):
                return "empty"
        except Exception:
            pass

        page.wait_for_timeout(800)

    return "timeout"


def reset_profiles():
    if not messagebox.askyesno(
        "Reset profile",
        "Xóa toàn bộ profile trình duyệt đã lưu? Thao tác này không thể hoàn tác.",
    ):
        return
    manager = PersistentProfileManager(PROFILES_DIR)
    manager.reset_all()
    set_runtime_status("Đã reset toàn bộ browser profile.", "warning", "PROFILE")


def get_proxy_list():
    raw_text = txt_px.get("1.0", tk.END).replace("\r", "\n")
    proxies = []

    for line in raw_text.splitlines():
        cleaned = line.strip()
        if cleaned:
            proxies.append(cleaned)

    return proxies


def set_proxy_text(proxy_lines):
    txt_px.delete("1.0", tk.END)
    if not proxy_lines:
        update_runtime_badges()
        return

    if isinstance(proxy_lines, str):
        content = proxy_lines.strip()
    else:
        content = "\n".join(str(line).strip() for line in proxy_lines if str(line).strip())

    if content:
        txt_px.insert("1.0", content)
    update_runtime_badges()


def collect_current_config():
    route_start_text = get_entry_clean_value(ent_route_start) if "ent_route_start" in globals() else ""
    route_pick_text = safe_string(cmb_route_start_pick.get()) if "cmb_route_start_pick" in globals() else ""
    route_sort_type = safe_string(cmb_route_sort_type.get()) if "cmb_route_sort_type" in globals() else "Gần nhất trước"
    route_optimize = safe_string(cmb_route_optimize.get()) if "cmb_route_optimize" in globals() else "Cân bằng"
    route_scope = safe_string(cmb_route_scope.get()) if "cmb_route_scope" in globals() else "Toàn bộ kết quả"
    route_group_cluster = bool(var_route_group_cluster.get()) if "var_route_group_cluster" in globals() else False

    return {
        "location": ent_loc.get().strip(),
        "keyword": ent_kw.get().strip(),
        "latitude": get_entry_clean_value(ent_lat),
        "longitude": get_entry_clean_value(ent_lng),
        "zoom": ent_zoom.get().strip(),
        "limit": ent_lim.get().strip(),
        "threads": ent_threads.get().strip(),
        "window_width": ent_win_w.get().strip(),
        "window_height": ent_win_h.get().strip(),
        "headless": bool(var_headless.get()),
        "proxies": get_proxy_list(),
        "route_start_text": route_start_text,
        "route_start_pick": route_pick_text,
        "route_sort_type": route_sort_type,
        "route_optimize": route_optimize,
        "route_scope": route_scope,
        "route_group_cluster": route_group_cluster,
    }
def save_last_config(silent=True):
    try:
        save_json_file(LAST_CONFIG_PATH, collect_current_config())
        return True
    except Exception as exc:
        if not silent:
            messagebox.showwarning("Cảnh báo", f"Không lưu được cấu hình gần nhất.\n{exc}")
        return False


def load_last_config():
    return load_json_file(LAST_CONFIG_PATH)


def apply_last_config(config):
    if not config:
        return

    ent_loc.delete(0, tk.END)
    ent_loc.insert(0, config.get("location", "Mỹ Tho"))

    ent_kw.delete(0, tk.END)
    ent_kw.insert(0, config.get("keyword", "Salon tóc"))

    set_entry_value(ent_lat, config.get("latitude", ""))

    set_entry_value(ent_lng, config.get("longitude", ""))

    ent_zoom.delete(0, tk.END)
    ent_zoom.insert(0, config.get("zoom", "14"))

    ent_lim.delete(0, tk.END)
    ent_lim.insert(0, config.get("limit", "100"))

    ent_threads.delete(0, tk.END)
    ent_threads.insert(0, config.get("threads", "1"))

    ent_win_w.delete(0, tk.END)
    ent_win_w.insert(0, config.get("window_width", "900"))

    ent_win_h.delete(0, tk.END)
    ent_win_h.insert(0, config.get("window_height", "500"))

    var_headless.set(bool(config.get("headless", False)))
    set_proxy_text(config.get("proxies", []))

    if "ent_route_start" in globals():
        set_entry_value(ent_route_start, config.get("route_start_text", ""))
    if "cmb_route_start_pick" in globals():
        start_pick = safe_string(config.get("route_start_pick"))
        if start_pick:
            cmb_route_start_pick.set(start_pick)
    if "cmb_route_sort_type" in globals():
        sort_type = safe_string(config.get("route_sort_type")) or "Gần nhất trước"
        cmb_route_sort_type.set(sort_type)
    if "cmb_route_optimize" in globals():
        optimize_mode = safe_string(config.get("route_optimize")) or "Cân bằng"
        cmb_route_optimize.set(optimize_mode)
    if "cmb_route_scope" in globals():
        scope_mode = safe_string(config.get("route_scope")) or "Toàn bộ kết quả"
        cmb_route_scope.set(scope_mode)
    if "var_route_group_cluster" in globals():
        var_route_group_cluster.set(bool(config.get("route_group_cluster", False)))
def paste_proxies_from_clipboard():
    try:
        clipboard_text = root.clipboard_get()
    except Exception:
        messagebox.showwarning("Thiếu dữ liệu", "Clipboard hiện không có nội dung proxy để dán.")
        return

    if not str(clipboard_text).strip():
        messagebox.showwarning("Thiếu dữ liệu", "Clipboard hiện đang trống.")
        return

    set_proxy_text(clipboard_text)
    set_runtime_status("Đã dán danh sách proxy từ clipboard.", "info", "CẬP NHẬT PROXY")


def clear_proxy_box():
    set_proxy_text([])
    set_runtime_status("Đã xóa toàn bộ proxy trong ô nhập.", "muted", "CẬP NHẬT PROXY")


def import_proxy_file():
    file_path = filedialog.askopenfilename(
        title="Chọn file proxy",
        filetypes=[("Text files", "*.txt;*.csv"), ("All files", "*.*")],
    )
    if not file_path:
        return

    try:
        with open(file_path, "r", encoding="utf-8") as proxy_file:
            content = proxy_file.read()
    except UnicodeDecodeError:
        with open(file_path, "r", encoding="latin-1") as proxy_file:
            content = proxy_file.read()
    except Exception as exc:
        messagebox.showerror("Lỗi", f"Không đọc được file proxy.\n{exc}")
        return

    set_proxy_text(content)
    set_runtime_status("Đã nạp proxy từ file.", "info", "CẬP NHẬT PROXY")


def fetch_public_ip(proxy_server=None):
    proxy_config = build_playwright_proxy(proxy_server)
    with sync_playwright() as playwright:
        browser = launch_playwright_browser(
            playwright,
            headless=True,
            proxy=proxy_config,
        )
        try:
            context = browser.new_context(ignore_https_errors=True)
            page = context.new_page()
            page.goto(PUBLIC_IP_CHECK_URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(1200)
            raw_text = (page.locator("body").text_content() or "").strip()
            context.close()
        finally:
            browser.close()

    data = json.loads(raw_text)
    ip_value = str(data.get("ip", "")).strip()
    if not ip_value:
        raise ValueError("Không đọc được IP public từ dịch vụ kiểm tra.")
    return ip_value


def finish_proxy_ip_check(proxy_display, direct_ip, proxy_ip):
    btn_proxy_check.config(state=tk.NORMAL)

    if proxy_display == "direct":
        lbl_proxy_check_result.config(
            text=f"IP hiện tại không dùng proxy: {direct_ip}",
            fg=color_for("info"),
        )
        set_runtime_status(f"IP direct hiện tại: {direct_ip}", "info", "KIỂM TRA IP")
        messagebox.showinfo("Kiểm tra IP", f"Bạn chưa nhập proxy.\nIP đang ra ngoài: {direct_ip}")
        return

    if direct_ip == proxy_ip:
        lbl_proxy_check_result.config(
            text=f"IP direct và proxy đang trùng nhau: {proxy_ip}",
            fg=color_for("warning"),
        )
        set_runtime_status("IP proxy không đổi so với IP direct. Hãy kiểm tra lại proxy.", "warning", "KIỂM TRA IP")
        messagebox.showwarning(
            "Kiểm tra IP proxy",
            "IP direct và IP qua proxy đầu tiên đang trùng nhau.\n"
            f"IP direct: {direct_ip}\n"
            f"IP proxy: {proxy_ip}\n\n"
            "Kết luận: proxy có thể chưa hoạt động đúng hoặc không đổi IP ra ngoài.",
        )
        return

    lbl_proxy_check_result.config(
        text=f"Direct: {direct_ip} | Proxy đầu tiên: {proxy_ip}",
        fg=color_for("success"),
    )
    set_runtime_status("Đã xác minh IP ra ngoài qua proxy đầu tiên.", "success", "KIỂM TRA IP")
    messagebox.showinfo(
        "Kiểm tra IP proxy",
        f"IP direct: {direct_ip}\nIP qua proxy đầu tiên: {proxy_ip}\n\nKết luận: trình duyệt đang đi ra ngoài qua proxy.",
    )


def fail_proxy_ip_check(proxy_display, error_text):
    btn_proxy_check.config(state=tk.NORMAL)
    lbl_proxy_check_result.config(
        text="Kiểm tra IP thất bại. Xem thông báo lỗi để biết chi tiết.",
        fg=color_for("danger"),
    )
    set_runtime_status("Không kiểm tra được IP proxy.", "danger", "KIỂM TRA IP")

    target_proxy = proxy_display or "Không dùng proxy"
    messagebox.showerror(
        "Kiểm tra IP proxy",
        f"Không kiểm tra được kết nối IP.\nMục tiêu: {target_proxy}\nLỗi: {error_text}",
    )


def proxy_ip_check_worker(proxy_server, proxy_display):
    try:
        direct_ip = fetch_public_ip()
        proxy_ip = fetch_public_ip(proxy_server) if proxy_server else direct_ip
        root.after(0, lambda: finish_proxy_ip_check(proxy_display, direct_ip, proxy_ip))
    except Exception as exc:
        root.after(0, lambda: fail_proxy_ip_check(proxy_display, str(exc)))


def check_proxy_ip():
    proxy_list = get_proxy_list()
    first_proxy_raw = proxy_list[0] if proxy_list else None
    first_proxy = parse_proxy_line(first_proxy_raw) if first_proxy_raw else None
    proxy_display = format_proxy_display(first_proxy)

    btn_proxy_check.config(state=tk.DISABLED)
    lbl_proxy_check_result.config(
        text="Đang kiểm tra IP public bằng trình duyệt Playwright...",
        fg=color_for("info"),
    )
    set_runtime_status("Đang kiểm tra IP direct và IP qua proxy đầu tiên...", "info", "KIỂM TRA IP")

    threading.Thread(
        target=proxy_ip_check_worker,
        args=(first_proxy, proxy_display if proxy_display else "direct"),
        daemon=True,
    ).start()


def update_runtime_badges(_event=None):
    thread_text = ent_threads.get().strip() or "--"
    target_text = ent_lim.get().strip() or "--"
    proxy_count = len(get_proxy_list())
    width_text = ent_win_w.get().strip() or "--"
    height_text = ent_win_h.get().strip() or "--"

    lbl_threads_value.config(text=thread_text)
    lbl_target_value.config(text=target_text)
    lbl_proxy_value.config(text=str(proxy_count))
    lbl_mode_value.config(text="Ẩn" if var_headless.get() else "Hiện")
    lbl_window_note.config(text=f"Kích thước trình duyệt: {width_text} x {height_text} px")
    update_route_summary_labels()


def check_license():
    global login_success

    key = ent_key.get().strip()
    if not key:
        messagebox.showwarning("Lỗi", "Vui lòng nhập mã kích hoạt.")
        return

    api_url = get_license_api_url()
    if not api_url:
        configured = prompt_license_api_url(root_login)
        if not configured:
            lbl_status.config(
                text="Chưa có URL server kích hoạt. Hãy bấm CẤU HÌNH SERVER trước.",
                fg=color_for("warning"),
            )
            return

    machine_identity = get_machine_identity()
    lbl_status.config(
        text=f"Đang kiểm tra bản quyền cho ID máy {machine_identity['display_id']}...",
        fg=color_for("info"),
    )
    root_login.update()

    try:
        activation_result = activate_license_with_server(key, machine_identity)
        if not activation_result["ok"]:
            response_code = activation_result["code"]
            response_message = activation_result["message"] or "Không thể kích hoạt mã bản quyền."

            if response_code in {"license_not_found", "invalid_license"}:
                messagebox.showerror("Thất bại", response_message)
                lbl_status.config(text="Sai mã kích hoạt.", fg=color_for("danger"))
                return

            if response_code in {"inactive_license", "license_blocked", "expired_license"}:
                messagebox.showerror("Từ chối", response_message)
                lbl_status.config(text="Mã đã bị khóa hoặc hết hạn.", fg=color_for("danger"))
                return

            if response_code in {"machine_locked", "machine_mismatch"}:
                messagebox.showerror("Từ chối", response_message)
                lbl_status.config(text="Mã không khớp ID máy hiện tại.", fg=color_for("danger"))
                return

            messagebox.showerror("Kích hoạt thất bại", response_message)
            lbl_status.config(text=response_message, fg=color_for("danger"))
            return

        if activation_result["status"] and activation_result["status"] != LICENSE_STATUS_ACTIVE:
            messagebox.showerror("Từ chối", "Mã kích hoạt này đã bị khóa hoặc hết hạn.")
            lbl_status.config(text="Mã đã bị khóa hoặc hết hạn.", fg=color_for("danger"))
            return

        if not machine_matches_lock(activation_result["machine_id"], machine_identity):
            messagebox.showerror(
                "Từ chối",
                "Máy chủ trả về Machine ID không khớp với máy hiện tại.",
            )
            lbl_status.config(text="Machine ID trả về không khớp.", fg=color_for("danger"))
            return

        try:
            save_license_state(
                key,
                activation_result["customer_name"],
                machine_identity,
                activation_result["machine_id"] or machine_identity["fingerprint"],
            )
        except Exception as exc:
            messagebox.showerror(
                "Lỗi lưu kích hoạt",
                f"License hợp lệ nhưng không thể lưu trạng thái kích hoạt trên máy.\n{exc}",
            )
            lbl_status.config(text="Không lưu được trạng thái kích hoạt cục bộ.", fg=color_for("danger"))
            return

        customer_name = activation_result["customer_name"] or "Khách hàng"
        messagebox.showinfo(
            "Thành công",
            f"Kích hoạt thành công cho ID máy {machine_identity['display_id']}.\nChào mừng: {customer_name}",
        )
        login_success = True
        root_login.destroy()
    except RuntimeError as exc:
        messagebox.showerror("Lỗi kích hoạt", str(exc))
        lbl_status.config(text="Không thể xác thực license với máy chủ kích hoạt.", fg=color_for("danger"))
    except Exception:
        messagebox.showerror(
            "Lỗi mạng",
            "Không thể kết nối máy chủ kích hoạt. Hãy kiểm tra mạng hoặc URL server kích hoạt.",
        )
        lbl_status.config(text="Không kết nối được máy chủ.", fg=color_for("danger"))


def configure_license_server_from_login():
    if prompt_license_api_url(root_login):
        lbl_status.config(
            text="Đã lưu URL server kích hoạt. Anh có thể nhập mã và kích hoạt ngay.",
            fg=color_for("success"),
        )


def scraper_worker(thread_id, keyword, fallback_keyword, proxy_pool, profile_manager, anchor, target_limit, headless, win_w, win_h, pos_x, pos_y):
    global active_threads, final_data, is_running, seen_urls, next_row_id

    attempts_limit = 3 if proxy_pool and proxy_pool.has_proxies else 1
    attempt = 0
    worker_success = False
    last_error = ""

    while is_running and attempt < attempts_limit and not worker_success:
        proxy_entry = proxy_pool.acquire() if proxy_pool and proxy_pool.has_proxies else None
        if proxy_pool and proxy_pool.has_proxies and not proxy_entry:
            time.sleep(1)
            attempt += 1
            continue

        profile_path = profile_manager.get_profile_path(thread_id, proxy_entry, anchor)
        proxy_config = build_playwright_proxy(proxy_entry)

        if proxy_entry:
            root.after(
                0,
                lambda p=proxy_entry: set_runtime_status(
                    f"Luong {thread_id} dung {p['server']} (score {int(p.get('health_score', 0))})",
                    "info",
                    "DANG CHAY",
                ),
            )

        browser_context = None
        try:
            with sync_playwright() as playwright:
                context_args = {
                    "user_data_dir": profile_path,
                    "headless": headless,
                    "proxy": proxy_config,
                    "locale": "vi-VN",
                    "timezone_id": "Asia/Ho_Chi_Minh",
                    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "viewport": {"width": 1280, "height": 720},
                    "args": [
                        f"--window-position={pos_x},{pos_y}",
                        f"--window-size={win_w},{win_h}",
                        "--disable-blink-features=AutomationControlled",
                        "--force-device-scale-factor=0.8",
                    ],
                }
                if anchor:
                    context_args["geolocation"] = {"latitude": anchor.lat, "longitude": anchor.lng}
                    context_args["permissions"] = ["geolocation"]

                browser_context = launch_playwright_persistent_context(playwright, context_args)
                page = browser_context.new_page()
                if not is_running:
                    browser_context.close()
                    return

                maps_url = build_maps_search_url(anchor)
                page.goto(maps_url, timeout=60000)
                if anchor:
                    try:
                        browser_context.grant_permissions(["geolocation"], origin="https://www.google.com")
                    except Exception:
                        pass

                time.sleep(2)
                for btn_text in ["Chấp nhận", "Đồng ý", "Accept", "Agree", "Để sau", "No thanks"]:
                    try:
                        button = page.get_by_role("button", name=btn_text)
                        if button.is_visible(timeout=1000):
                            button.click()
                    except Exception:
                        continue

                search_box = page.locator('input#searchboxinput, input[name="q"]').first
                search_box.wait_for(state="visible", timeout=30000)

                def submit_search(query_text):
                    search_box.fill(query_text)
                    page.keyboard.press("Enter")
                    page.wait_for_timeout(1500)

                submit_search(keyword)
                page.wait_for_selector('div[role="feed"]', timeout=30000)

                fallback_used = False
                empty_rounds = 0

                while is_running and len(final_data) < target_limit:
                    feed = page.locator('div[role="feed"]')
                    items = page.locator('a[href*="/maps/place/"]').all()

                    if not items:
                        empty_rounds += 1
                        if not fallback_used and fallback_keyword and empty_rounds >= 2:
                            submit_search(fallback_keyword)
                            fallback_used = True
                            empty_rounds = 0
                            continue
                        feed.evaluate("el => el.scrollTop += 1000")
                        time.sleep(2)
                        continue

                    empty_rounds = 0
                    for item in items:
                        if not is_running or len(final_data) >= target_limit:
                            break

                        url = item.get_attribute("href")
                        if not url:
                            continue

                        with data_lock:
                            if url in seen_urls:
                                continue
                            seen_urls.add(url)

                        try:
                            if page.locator("text='Đăng nhập'").is_visible(timeout=500):
                                page.keyboard.press("Escape")

                            item.click()
                            time.sleep(2.5)

                            soup = BeautifulSoup(page.content(), "html.parser")
                            name = item.get_attribute("aria-label") or "N/A"

                            addr_tag = soup.find("button", {"data-item-id": "address"})
                            addr = addr_tag.get_text(strip=True) if addr_tag else "N/A"

                            phone_tag = soup.find(
                                "button",
                                {"data-item-id": lambda value: value and "phone" in value},
                            )
                            phone = phone_tag.get_text(strip=True) if phone_tag else "N/A"
                            latitude, longitude = extract_coordinates_from_maps_text(url, page.url)

                            with data_lock:
                                if url in seen_urls:
                                    continue
                                seen_urls.add(url)
                                row_id = next_row_id
                                next_row_id += 1
                                row_idx = len(final_data) + 1
                                row_data = {
                                    "_row_id": row_id,
                                    "STT": row_idx,
                                    "Tên": name,
                                    "SĐT": phone,
                                    "Địa chỉ": addr,
                                    "lat": latitude if latitude is not None else "",
                                    "lng": longitude if longitude is not None else "",
                                    "thu_tu_tuyen": "",
                                    "cum_tuyen": "",
                                    "khoang_cach_uoc_tinh": "",
                                    "thoi_gian_uoc_tinh": "",
                                    "ghi_chu_tuyen": "",
                                }
                                final_data.append(row_data)

                            root.after(0, lambda row=row_data: insert_result_row(row))
                            root.after(
                                0,
                                lambda current=row_idx, total=target_limit: set_runtime_status(
                                    f"Tien do hien tai: {current}/{total} doanh nghiep.",
                                    "info",
                                    "DANG QUET",
                                ),
                            )
                        except Exception:
                            continue

                    feed.evaluate("el => el.scrollTop += 5000")
                    time.sleep(3)

                    page_content = page.content()
                    if "Bạn đã đi đến cuối danh sách" in page_content or "Không tìm thấy kết quả nào khác" in page_content:
                        break

                browser_context.close()
                if proxy_pool and proxy_entry:
                    proxy_pool.report_success(proxy_entry)
                worker_success = True
        except Exception as exc:
            last_error = str(exc)
            notify_browser_worker_error(thread_id, "khởi tạo/truy cập Maps", proxy_entry, exc)
            if proxy_pool and proxy_entry:
                cooldown = proxy_pool.report_failure(proxy_entry)
                root.after(
                    0,
                    lambda p=proxy_entry, cd=cooldown: set_runtime_status(
                        f"Proxy {p['server']} loi, cooldown {cd}s",
                        "warning",
                        "PROXY RETRY",
                    ),
                )
            if browser_context and not headless:
                time.sleep(5)
            attempt += 1
            time.sleep(1.2)
        finally:
            if browser_context:
                try:
                    browser_context.close()
                except Exception:
                    pass

    if not worker_success and last_error:
        print(f"Luong {thread_id} ket thuc voi loi: {last_error}")

    with data_lock:
        active_threads -= 1
        if active_threads <= 0:
            root.after(0, reset_ui)


def scraper_worker(thread_id, keyword, fallback_keyword, proxy_pool, profile_manager, anchor, target_limit, headless, win_w, win_h, pos_x, pos_y):
    global active_threads, final_data, is_running, seen_urls, next_row_id

    attempts_limit = 3 if proxy_pool and proxy_pool.has_proxies else 1
    attempt = 0
    worker_success = False
    last_error = ""

    def run_session(proxy_entry):
        nonlocal last_error

        profile_path = profile_manager.get_profile_path(thread_id, proxy_entry, anchor)
        proxy_config = build_playwright_proxy(proxy_entry)
        browser_context = None
        session_has_results = False

        try:
            if proxy_entry:
                root.after(
                    0,
                    lambda p=proxy_entry: set_runtime_status(
                        f"Luong {thread_id} dung {p['server']} (score {int(p.get('health_score', 0))})",
                        "info",
                        "DANG CHAY",
                    ),
                )

            with sync_playwright() as playwright:
                context_args = {
                    "user_data_dir": profile_path,
                    "headless": headless,
                    "proxy": proxy_config,
                    "locale": "vi-VN",
                    "timezone_id": "Asia/Ho_Chi_Minh",
                    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "viewport": {"width": 1280, "height": 720},
                    "args": [
                        f"--window-position={pos_x},{pos_y}",
                        f"--window-size={win_w},{win_h}",
                        "--disable-blink-features=AutomationControlled",
                        "--force-device-scale-factor=0.8",
                    ],
                }
                if anchor:
                    context_args["geolocation"] = {"latitude": anchor.lat, "longitude": anchor.lng}
                    context_args["permissions"] = ["geolocation"]

                browser_context = launch_playwright_persistent_context(playwright, context_args)
                page = browser_context.pages[0] if browser_context.pages else browser_context.new_page()
                page.set_default_timeout(15000)
                page.set_default_navigation_timeout(30000)
                if not is_running:
                    browser_context.close()
                    return False

                maps_url = build_maps_search_url(anchor)
                page.goto(maps_url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(2000)
                if anchor:
                    try:
                        browser_context.grant_permissions(["geolocation"], origin="https://www.google.com")
                    except Exception:
                        pass

                dismiss_google_maps_overlays(page)
                wait_for_google_maps_search_box(page, timeout=45000)

                def submit_search(query_text):
                    page.goto(
                        build_maps_keyword_search_url(query_text, anchor),
                        wait_until="domcontentloaded",
                        timeout=60000,
                    )
                    page.wait_for_timeout(2000)
                    dismiss_google_maps_overlays(page)
                    return wait_for_maps_results_state(page, timeout=30000)

                search_state = submit_search(keyword)
                if search_state in {"empty", "timeout"} and fallback_keyword and fallback_keyword != keyword:
                    search_state = submit_search(fallback_keyword)

                if search_state == "empty":
                    last_error = f"Khong tim thay ket qua cho tu khoa '{keyword}'."
                    root.after(
                        0,
                        lambda: set_runtime_status(
                            "Khong tim thay ket qua tren Google Maps voi bo loc hien tai.",
                            "warning",
                            "KHONG CO DU LIEU",
                        ),
                    )
                    return False

                if search_state == "timeout":
                    last_error = "Google Maps khong tra ve danh sach ket qua dung han."
                    root.after(
                        0,
                        lambda: set_runtime_status(
                            "Google Maps tai qua lau hoac khong mo duoc danh sach ket qua.",
                            "danger",
                            "LOI CHROME",
                        ),
                    )
                    return False

                fallback_used = False
                empty_rounds = 0
                stall_rounds = 0
                stall_limit = 6

                while is_running and len(final_data) < target_limit:
                    feed = page.locator('div[role="feed"]')
                    items = page.locator('a[href*="/maps/place/"]').all()

                    if not items:
                        empty_rounds += 1
                        stall_rounds += 1
                        if not fallback_used and fallback_keyword and empty_rounds >= 2:
                            submit_search(fallback_keyword)
                            fallback_used = True
                            empty_rounds = 0
                            continue
                        if stall_rounds >= stall_limit:
                            root.after(
                                0,
                                lambda: set_runtime_status(
                                    "Không còn dữ liệu mới sau nhiều lần cuộn, tự dừng để tránh quay vô hạn.",
                                    "warning",
                                    "DUNG QUET",
                                ),
                            )
                            break
                        try:
                            feed.evaluate("el => el.scrollTop += 1000")
                        except Exception:
                            page.mouse.wheel(0, 1000)
                        time.sleep(2)
                        continue

                    empty_rounds = 0
                    new_rows_this_round = 0
                    for item in items:
                        if not is_running or len(final_data) >= target_limit:
                            break

                        url = item.get_attribute("href")
                        if not url:
                            continue

                        with data_lock:
                            if url in seen_urls:
                                continue

                        place_name = item.get_attribute("aria-label") or "N/A"

                        try:
                            if page.locator("text='Đăng nhập'").is_visible(timeout=500):
                                page.keyboard.press("Escape")

                            try:
                                item.click(timeout=5000)
                            except Exception:
                                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                            time.sleep(2.5)

                            soup = BeautifulSoup(page.content(), "html.parser")
                            name = place_name

                            addr_tag = soup.find("button", {"data-item-id": "address"})
                            addr = addr_tag.get_text(strip=True) if addr_tag else "N/A"

                            phone_tag = soup.find(
                                "button",
                                {"data-item-id": lambda value: value and "phone" in value},
                            )
                            phone = phone_tag.get_text(strip=True) if phone_tag else "N/A"
                            latitude, longitude = extract_coordinates_from_maps_text(url, page.url)

                            with data_lock:
                                if url in seen_urls:
                                    continue
                                seen_urls.add(url)
                                row_id = next_row_id
                                next_row_id += 1
                                row_idx = len(final_data) + 1
                                row_data = {
                                    "_row_id": row_id,
                                    "STT": row_idx,
                                    "Tên": name,
                                    "SĐT": phone,
                                    "Địa chỉ": addr,
                                    "lat": latitude if latitude is not None else "",
                                    "lng": longitude if longitude is not None else "",
                                    "thu_tu_tuyen": "",
                                    "cum_tuyen": "",
                                    "khoang_cach_uoc_tinh": "",
                                    "thoi_gian_uoc_tinh": "",
                                    "ghi_chu_tuyen": "",
                                }
                                final_data.append(row_data)
                                new_rows_this_round += 1
                                session_has_results = True

                            root.after(0, lambda row=row_data: insert_result_row(row))
                            root.after(
                                0,
                                lambda current=row_idx, total=target_limit: set_runtime_status(
                                    f"Tien do hien tai: {current}/{total} doanh nghiep.",
                                    "info",
                                    "DANG QUET",
                                ),
                            )
                        except Exception:
                            continue

                    if new_rows_this_round:
                        stall_rounds = 0
                    else:
                        stall_rounds += 1
                        if stall_rounds >= stall_limit:
                            root.after(
                                0,
                                lambda: set_runtime_status(
                                    "Không còn kết quả mới sau nhiều lần quét, tự dừng để tránh quay vô hạn.",
                                    "warning",
                                    "DUNG QUET",
                                ),
                            )
                            break

                    try:
                        feed.evaluate("el => el.scrollTop += 5000")
                    except Exception:
                        page.mouse.wheel(0, 5000)
                    time.sleep(3)

                    page_content = page.content()
                    if "Bạn đã đi đến cuối danh sách" in page_content or "Không tìm thấy kết quả nào khác" in page_content:
                        break

                if not session_has_results:
                    last_error = "Da mo Google Maps nhung khong thu duoc doanh nghiep nao."
                    root.after(
                        0,
                        lambda: set_runtime_status(
                            "Da mo Google Maps nhung khong lay duoc doanh nghiep nao. Hay doi bo loc hoac vi tri.",
                            "warning",
                            "KHONG CO DU LIEU",
                        ),
                    )
                    return False

                if proxy_pool and proxy_entry:
                    proxy_pool.report_success(proxy_entry)
                return True
        except Exception as exc:
            last_error = str(exc)
            notify_browser_worker_error(thread_id, "khởi tạo/truy cập Maps", proxy_entry, exc)
            if proxy_pool and proxy_entry:
                cooldown = proxy_pool.report_failure(proxy_entry)
                root.after(
                    0,
                    lambda p=proxy_entry, cd=cooldown: set_runtime_status(
                        f"Proxy {p['server']} loi, cooldown {cd}s",
                        "warning",
                        "PROXY RETRY",
                    ),
                )
            if browser_context and not headless:
                time.sleep(5)
            return False
        finally:
            if browser_context:
                try:
                    browser_context.close()
                except Exception:
                    pass

    if is_running:
        root.after(
            0,
            lambda: set_runtime_status(
                "Dang thu ket noi truc tiep truoc khi dung proxy.",
                "info",
                "DIRECT",
            ),
        )
        worker_success = run_session(None)
        if not worker_success:
            attempt += 1
            time.sleep(1.0)

    while is_running and proxy_pool and proxy_pool.has_proxies and attempt < attempts_limit and not worker_success:
        proxy_entry = proxy_pool.acquire() if proxy_pool and proxy_pool.has_proxies else None
        if proxy_pool and proxy_pool.has_proxies and not proxy_entry:
            time.sleep(1)
            attempt += 1
            continue

        worker_success = run_session(proxy_entry)
        if not worker_success:
            attempt += 1
            time.sleep(1.2)

    if not worker_success and proxy_pool and proxy_pool.has_proxies and is_running:
        root.after(
            0,
            lambda: set_runtime_status(
                "Tat ca proxy deu that bai, thu lai theo che do direct de khoanh vung loi.",
                "warning",
                "DIRECT FALLBACK",
            ),
        )
        worker_success = run_session(None)

    if not worker_success and last_error:
        print(f"Luong {thread_id} ket thuc voi loi: {last_error}")

    with data_lock:
        active_threads -= 1
        if active_threads <= 0:
            root.after(0, reset_ui)


def reset_ui():
    global is_running
    is_running = False
    btn_run.config(state=tk.NORMAL)
    btn_stop.config(state=tk.DISABLED)
    if final_data:
        set_runtime_status("Đã dừng hoặc hoàn thành phiên quét.", "success", "SẴN SÀNG")
    else:
        set_runtime_status("Phiên quét kết thúc nhưng chưa thu được dữ liệu nào.", "warning", "KHÔNG CÓ DỮ LIỆU")


def start_app():
    global active_threads, final_data, is_running, seen_urls, next_row_id

    loc = ent_loc.get().strip()
    kw = ent_kw.get().strip()
    lat_text = get_entry_clean_value(ent_lat)
    lng_text = get_entry_clean_value(ent_lng)
    zoom_text = ent_zoom.get().strip()

    try:
        limit = int(ent_lim.get())
        num_threads = int(ent_threads.get())
        win_w = int(ent_win_w.get())
        win_h = int(ent_win_h.get())
    except ValueError:
        messagebox.showerror("Lỗi", "Các giá trị cấu hình phải là số hợp lệ.")
        return

    if not kw:
        messagebox.showwarning("Thiếu thông tin", "Hãy nhập từ khóa tìm kiếm.")
        return

    has_location = bool(loc)
    has_manual_coordinates = bool(lat_text) or bool(lng_text)
    manual_lat = normalize_coordinate_number(lat_text) if has_manual_coordinates else None
    manual_lng = normalize_coordinate_number(lng_text) if has_manual_coordinates else None

    if has_location:
        lat_text = ""
        lng_text = ""
    elif has_manual_coordinates:
        if manual_lat is None or manual_lng is None:
            messagebox.showwarning("Thiếu thông tin", "Nếu dùng tọa độ thì phải nhập đủ cả vĩ độ và kinh độ.")
            return
        valid_range, warning_text = validate_coordinate_range(manual_lat, manual_lng)
        if not valid_range:
            messagebox.showwarning("Tọa độ không hợp lệ", warning_text)
            return
        lat_text = format_coordinate_value(manual_lat)
        lng_text = format_coordinate_value(manual_lng)
    else:
        messagebox.showwarning("Thiếu thông tin", "Nhập khu vực hoặc cấp lat/lng thủ công.")
        return

    if min(limit, num_threads, win_w, win_h) <= 0:
        messagebox.showwarning("Không hợp lệ", "Các thông số phải lớn hơn 0.")
        return

    anchor, anchor_warning = resolve_location_anchor(loc, lat_text, lng_text, zoom_text)
    if anchor:
        if anchor.source == "manual":
            set_runtime_status(
                f"Manual anchor: {anchor.lat:.6f}, {anchor.lng:.6f} (zoom {anchor.zoom})",
                "info",
                "ANCHOR",
            )
        else:
            set_runtime_status(
                f"Anchor: {loc} -> {anchor.lat:.6f}, {anchor.lng:.6f} (zoom {anchor.zoom})",
                "info",
                "ANCHOR",
            )
    else:
        if has_location:
            set_runtime_status(
                f"Không định vị được khu vực '{loc}', app sẽ chạy theo từ khóa.",
                "info",
                "ANCHOR FALLBACK",
            )
        else:
            set_runtime_status(
                f"Anchor fallback về cách cũ: {anchor_warning}",
                "warning",
                "ANCHOR FALLBACK",
            )

    search_keyword = kw if anchor else f"{kw} tại {loc}".strip()
    fallback_keyword = f"{kw} tại {loc}".strip() if loc else kw

    proxies = get_proxy_list()
    proxy_pool = ProxyPool(proxies)
    profile_manager = PersistentProfileManager(PROFILES_DIR)
    is_headless = var_headless.get()
    save_last_config()

    final_data, seen_urls = [], set()
    next_row_id = 1
    is_running, active_threads = True, num_threads

    for item in tree.get_children():
        tree.delete(item)
    refresh_route_source_options()
    update_route_summary_labels()

    btn_run.config(state=tk.DISABLED)
    btn_stop.config(state=tk.NORMAL)
    set_runtime_status(
        f"Khởi động {num_threads} luồng với từ khóa '{search_keyword}'.",
        "info",
        "ĐANG CHẠY",
    )
    update_runtime_badges()

    screen_w = root.winfo_screenwidth()
    max_cols = screen_w // win_w if screen_w > win_w else 1

    for idx in range(num_threads):
        pos_x = (idx % max_cols) * win_w
        pos_y = (idx // max_cols) * (win_h + 40)

        threading.Thread(
            target=scraper_worker,
            args=(
                idx + 1,
                search_keyword,
                fallback_keyword,
                proxy_pool,
                profile_manager,
                anchor,
                limit,
                is_headless,
                win_w,
                win_h,
                pos_x,
                pos_y,
            ),
            daemon=True,
        ).start()
        time.sleep(1.0)


def stop_app():
    global is_running

    is_running = False
    btn_stop.config(state=tk.DISABLED)
    set_runtime_status("Đang yêu cầu dừng các luồng. Vui lòng chờ...", "danger", "ĐANG DỪNG")
    root.after(4000, lambda: btn_run.config(state=tk.NORMAL) if not is_running else None)


def handle_main_close():
    save_last_config(silent=False)
    stop_tax_batch_lookup()
    root.destroy()


@dataclass
class TaxLookupInput:
    query_name: str
    query_address: str = ""
    object_type: str = "Tất cả"
    max_results: int = 5
    prefer_official: bool = True
    allow_fallback: bool = True
    merge_by_address: bool = True


@dataclass
class TaxLookupResult:
    stt: int
    query_name: str
    query_address: str
    tax_code: str
    matched_name: str
    matched_address: str
    object_type: str
    status: str
    source: str
    score: float
    note: str = ""


class TaxProviderBase:
    provider_name = "base"

    def __init__(self, timeout=12, retry=2):
        self.timeout = timeout
        self.retry = max(1, int(retry))

    def search(self, lookup_input):
        return []

    def _request_text(self, url):
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
        }
        last_error = ""
        for attempt in range(self.retry):
            try:
                req = urllib_request.Request(url, headers=headers, method="GET")
                with urllib_request.urlopen(req, timeout=self.timeout) as resp:
                    charset = resp.headers.get_content_charset() or "utf-8"
                    return resp.read().decode(charset, errors="replace")
            except Exception as exc:
                last_error = str(exc)
                time.sleep(0.4 * (attempt + 1))
        raise RuntimeError(last_error or "Không thể lấy dữ liệu từ nguồn tra cứu.")

    def _request_json(self, url):
        raw_text = self._request_text(url)
        try:
            return json.loads(raw_text)
        except Exception as exc:
            raise RuntimeError(f"Nguồn trả JSON không hợp lệ: {exc}") from exc


def guess_object_type(name_text):
    normalized = normalize_lookup_text(name_text, keep_spaces=True)
    if "ho kinh doanh" in normalized:
        return "Hộ kinh doanh"
    if "cong ty" in normalized or "doanh nghiep" in normalized:
        return "Doanh nghiệp"
    return "Cá nhân"


def parse_tax_status(raw_text):
    normalized = normalize_lookup_text(raw_text, keep_spaces=True)
    if "ngung hoat dong" in normalized or "tam ngung" in normalized:
        return "Ngừng hoạt động"
    if "dang hoat dong" in normalized or "hoat dong" in normalized:
        return "Đang hoạt động"
    return "Không rõ"


TAX_CODE_PATTERN = re.compile(r"\b\d{10}(?:-?\d{3})?\b")


def normalize_tax_code(value):
    digits = re.sub(r"\D", "", safe_string(value))
    if len(digits) == 13:
        return f"{digits[:10]}-{digits[10:]}"
    if len(digits) >= 10:
        return digits[:10]
    return ""


def get_tax_code_base(value):
    normalized = normalize_tax_code(value)
    if not normalized:
        return ""
    return normalized.split("-", 1)[0]


def extract_tax_codes(text):
    found = []
    seen = set()
    for match in TAX_CODE_PATTERN.findall(safe_string(text)):
        normalized = normalize_tax_code(match)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        found.append(normalized)
    return found


class OfficialTaxProvider(TaxProviderBase):
    provider_name = "official"

    def search(self, lookup_input):
        query_name = safe_string(lookup_input.query_name)
        query_address = safe_string(lookup_input.query_address)
        query_text = f"{query_name} {query_address}".strip()
        if not query_text:
            return []

        explicit_codes = extract_tax_codes(query_text)
        if explicit_codes:
            return self._lookup_candidates_from_codes(explicit_codes)

        candidates = []
        try:
            search_url = f"https://masothue.com/Search/?q={urllib_parse.quote_plus(query_text)}"
            html_text = self._request_text(search_url)
            candidates.extend(self._parse_masothue_html(html_text))
        except Exception:
            # masothue có thể chặn theo IP/UA, để fallback xử lý nguồn khác.
            pass
        return self._deduplicate_candidates(candidates)

    def search_by_bing_discovery(self, lookup_input):
        query_name = safe_string(lookup_input.query_name)
        query_address = safe_string(lookup_input.query_address)
        if not query_name:
            return []

        query_keywords = [
            token
            for token in normalize_lookup_text(query_name, keep_spaces=True).split()
            if len(token) >= 3 and token not in NAME_MATCH_STOPWORDS
        ][:6]

        discovered_codes = []
        source_map = {}
        queries = [f"mst {query_name}"]
        if query_address:
            queries.insert(0, f"mst {query_name} {query_address}")
            queries.append(f"\"{query_name}\" \"{query_address}\" \"mã số thuế\"")
        queries.append(f"\"{query_name}\" \"mã số thuế\"")

        for query in queries:
            try:
                discovered_items = self._extract_tax_codes_from_bing_rss(query)
            except Exception:
                discovered_items = []
            for tax_code, source_url, source_blob in discovered_items:
                if query_keywords:
                    blob_norm = normalize_lookup_text(source_blob, keep_spaces=True)
                    if not any(keyword in blob_norm for keyword in query_keywords):
                        continue
                normalized = normalize_tax_code(tax_code)
                if not normalized or normalized in source_map:
                    continue
                source_map[normalized] = source_url
                discovered_codes.append(normalized)
                if len(discovered_codes) >= 15:
                    break
            if len(discovered_codes) >= 15:
                break

        if not discovered_codes:
            return []

        candidates = self._lookup_candidates_from_codes(discovered_codes, source_map=source_map)
        for candidate in candidates:
            source_text = safe_string(candidate.get("source"))
            candidate["source"] = f"{source_text}+bing" if source_text else "bing"
        return candidates

    def _extract_tax_codes_from_bing_rss(self, query_text):
        feed_url = f"https://www.bing.com/search?format=rss&q={urllib_parse.quote_plus(query_text)}"
        xml_text = self._request_text(feed_url)
        results = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return results

        for item in root.findall("./channel/item"):
            title = safe_string(item.findtext("title", ""))
            link = safe_string(item.findtext("link", ""))
            description = safe_string(item.findtext("description", ""))
            source_blob = " ".join([title, link, description]).strip()
            if not source_blob:
                continue
            for tax_code in extract_tax_codes(source_blob):
                results.append((tax_code, link, source_blob))
        return results

    def _lookup_candidates_from_codes(self, tax_codes, source_map=None):
        candidates = []
        for tax_code in tax_codes:
            normalized = normalize_tax_code(tax_code)
            if not normalized:
                continue
            try:
                candidate = self._lookup_candidate_by_tax_code(normalized)
            except Exception:
                candidate = None
            if not candidate:
                continue

            external_source = safe_string((source_map or {}).get(normalized))
            if external_source:
                current_note = safe_string(candidate.get("source_url"))
                candidate["source_url"] = external_source if not current_note else f"{current_note} | {external_source}"

            candidates.append(candidate)
        return self._deduplicate_candidates(candidates)

    def _lookup_candidate_by_tax_code(self, tax_code):
        base_tax_code = get_tax_code_base(tax_code)
        if not base_tax_code:
            return None

        try:
            esgoo_candidate = self._fetch_esgoo(base_tax_code)
        except Exception:
            esgoo_candidate = None

        try:
            vietqr_candidate = self._fetch_vietqr(base_tax_code)
        except Exception:
            vietqr_candidate = None

        if not vietqr_candidate and not esgoo_candidate:
            return None

        merged = vietqr_candidate or esgoo_candidate
        if vietqr_candidate and esgoo_candidate:
            merged = self._merge_candidates(vietqr_candidate, esgoo_candidate)

        if tax_code != base_tax_code and merged.get("tax_code") == base_tax_code:
            merged["tax_code"] = tax_code
        return merged

    def _fetch_vietqr(self, tax_code):
        url = f"https://api.vietqr.io/v2/business/{urllib_parse.quote_plus(tax_code)}"
        payload = self._request_json(url)
        if safe_string(payload.get("code")) != "00":
            return None
        data = payload.get("data") or {}
        company_name = safe_string(data.get("name") or data.get("shortName"))
        if not company_name:
            return None
        return {
            "tax_code": safe_string(data.get("id") or tax_code),
            "matched_name": company_name,
            "matched_address": safe_string(data.get("address")),
            "object_type": guess_object_type(company_name),
            "status": parse_tax_status(data.get("status")),
            "source": "vietqr.io",
            "source_url": url,
        }

    def _fetch_esgoo(self, tax_code):
        url = f"https://esgoo.net/api-mst/{urllib_parse.quote_plus(tax_code)}.htm"
        payload = self._request_json(url)
        if safe_int(payload.get("error"), 1) != 0:
            return None
        data = payload.get("data") or {}
        company_name = safe_string(data.get("ten"))
        if not company_name:
            return None
        return {
            "tax_code": safe_string(data.get("mst") or tax_code),
            "matched_name": company_name,
            "matched_address": safe_string(data.get("dc")),
            "object_type": guess_object_type(company_name),
            "status": parse_tax_status(data.get("tinhtrang")),
            "source": "esgoo.net",
            "source_url": url,
        }

    def _merge_candidates(self, preferred, fallback):
        merged = dict(preferred)
        for field in ("tax_code", "matched_name", "matched_address", "object_type", "status", "source_url"):
            if not safe_string(merged.get(field)):
                merged[field] = fallback.get(field)

        preferred_source = safe_string(preferred.get("source"))
        fallback_source = safe_string(fallback.get("source"))
        source_list = [source for source in (preferred_source, fallback_source) if source]
        merged["source"] = "+".join(dict.fromkeys(source_list))

        fallback_status = safe_string(fallback.get("status"))
        if safe_string(merged.get("status")) in {"", "Không rõ"} and fallback_status:
            merged["status"] = fallback_status
        return merged

    def _deduplicate_candidates(self, candidates):
        deduped = {}
        for candidate in candidates:
            tax_code = normalize_tax_code(candidate.get("tax_code"))
            name = normalize_lookup_text(candidate.get("matched_name"), keep_spaces=True)
            key = (tax_code, name)
            if key not in deduped:
                deduped[key] = candidate
        return list(deduped.values())

    def _parse_masothue_html(self, html_text):
        soup = BeautifulSoup(html_text, "html.parser")
        candidates = []
        seen_codes = set()
        page_text = normalize_lookup_text(soup.get_text(" ", strip=True), keep_spaces=True)
        if "forbidden" in page_text or "access denied" in page_text:
            return candidates

        possible_blocks = soup.select("tr, li")
        for block in possible_blocks:
            anchor = block.find("a", href=True)
            if not anchor:
                continue

            block_text = block.get_text(" ", strip=True)
            if not block_text or len(block_text) < 12:
                continue

            tax_match = TAX_CODE_PATTERN.search(block_text) or TAX_CODE_PATTERN.search(safe_string(anchor.get("href")))
            if not tax_match:
                continue

            tax_code = normalize_tax_code(tax_match.group(0))
            if tax_code in seen_codes:
                continue

            matched_name = safe_string(anchor.get_text(" ", strip=True)) if anchor else ""
            if not matched_name:
                matched_name = block_text[:200]

            matched_address = ""
            address_match = re.search(
                r"(?:dia chi|địa chỉ)\s*[:\-]?\s*(.+?)(?:ma so thue|mst|$)",
                normalize_lookup_text(block_text, keep_spaces=True),
            )
            if address_match:
                matched_address = safe_string(address_match.group(1))
            if not matched_address:
                matched_address = block_text

            source_url = ""
            if anchor and anchor.get("href"):
                source_url = urllib_parse.urljoin("https://masothue.com", anchor.get("href"))

            status_text = parse_tax_status(block_text)
            candidates.append(
                {
                    "tax_code": tax_code,
                    "matched_name": matched_name,
                    "matched_address": matched_address,
                    "object_type": guess_object_type(matched_name),
                    "status": status_text,
                    "source": "masothue.com",
                    "source_url": source_url,
                }
            )
            seen_codes.add(tax_code)

            if len(candidates) >= 50:
                break

        return candidates


class FallbackTaxProvider(TaxProviderBase):
    provider_name = "fallback"

    def __init__(self, timeout=10, retry=1):
        super().__init__(timeout=timeout, retry=retry)
        self.adapters = []

    def register_adapter(self, adapter_callable):
        if callable(adapter_callable):
            self.adapters.append(adapter_callable)

    def search(self, lookup_input):
        results = []
        for adapter in self.adapters:
            try:
                payload = adapter(lookup_input)
                if isinstance(payload, list):
                    results.extend(payload)
            except Exception:
                continue
        return results


def detect_city_bucket(address_text):
    normalized = normalize_lookup_text(address_text, keep_spaces=True)
    if not normalized:
        return ""
    city_tokens = [
        "thanh pho ho chi minh",
        "ha noi",
        "da nang",
        "hai phong",
        "can tho",
        "dong nai",
        "binh duong",
        "khanh hoa",
        "nghe an",
        "thua thien hue",
        "quang ninh",
        "lam dong",
    ]
    for token in city_tokens:
        if token in normalized:
            return token
    return ""


def ratio_similarity(text_a, text_b):
    if not text_a or not text_b:
        return 0.0
    return SequenceMatcher(None, text_a, text_b).ratio()


def token_similarity(text_a, text_b):
    tokens_a = set(safe_string(text_a).split())
    tokens_b = set(safe_string(text_b).split())
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / max(len(tokens_a | tokens_b), 1)


def get_name_match_score(query_name, candidate_name):
    query_norm = normalize_lookup_text(query_name, keep_spaces=True)
    candidate_norm = normalize_lookup_text(candidate_name, keep_spaces=True)
    if not query_norm or not candidate_norm:
        return 0.0
    return max(ratio_similarity(query_norm, candidate_norm), token_similarity(query_norm, candidate_norm)) * 100


NAME_MATCH_STOPWORDS = {
    "cong",
    "ty",
    "tnhh",
    "co",
    "phan",
    "doanh",
    "nghiep",
    "ho",
    "kinh",
    "doanh",
    "chi",
    "nhanh",
    "viet",
    "nam",
    "tap",
    "doan",
}


def has_significant_name_overlap(query_name, candidate_name):
    query_tokens = [
        token
        for token in normalize_lookup_text(query_name, keep_spaces=True).split()
        if len(token) >= 2 and token not in NAME_MATCH_STOPWORDS
    ]
    candidate_tokens = {
        token
        for token in normalize_lookup_text(candidate_name, keep_spaces=True).split()
        if len(token) >= 2 and token not in NAME_MATCH_STOPWORDS
    }
    if not query_tokens:
        return True
    strong_tokens = [token for token in query_tokens if len(token) >= 4]
    if strong_tokens and not any(token in candidate_tokens for token in strong_tokens):
        return False
    overlap_count = sum(1 for token in query_tokens if token in candidate_tokens)
    return overlap_count >= max(1, int(math.ceil(len(query_tokens) * 0.25)))


def score_tax_match(query_name, query_address, candidate):
    query_blob = f"{safe_string(query_name)} {safe_string(query_address)}"
    query_codes = extract_tax_codes(query_blob)
    query_base_codes = {get_tax_code_base(code) for code in query_codes if get_tax_code_base(code)}
    candidate_tax_code = normalize_tax_code(candidate.get("tax_code"))
    candidate_base_code = get_tax_code_base(candidate_tax_code)

    if candidate_tax_code and candidate_tax_code in query_codes:
        return 100.0
    if candidate_base_code and candidate_base_code in query_base_codes:
        return 98.0

    query_name_norm = normalize_lookup_text(query_name, keep_spaces=True)
    query_address_norm = normalize_lookup_text(query_address, keep_spaces=True)
    candidate_name_norm = normalize_lookup_text(candidate.get("matched_name"), keep_spaces=True)
    candidate_address_norm = normalize_lookup_text(candidate.get("matched_address"), keep_spaces=True)

    name_score = get_name_match_score(query_name, candidate.get("matched_name"))
    address_score = max(ratio_similarity(query_address_norm, candidate_address_norm), token_similarity(query_address_norm, candidate_address_norm)) * 100
    score = name_score * 0.6 + address_score * 0.4 if query_address_norm else name_score

    query_city = detect_city_bucket(query_address_norm)
    candidate_city = detect_city_bucket(candidate_address_norm)
    if query_city and candidate_city:
        if query_city == candidate_city:
            score += 8
        else:
            score -= 12

    status_norm = normalize_lookup_text(candidate.get("status"), keep_spaces=True)
    if "dang hoat dong" in status_norm or status_norm == "hoat dong":
        score += 5
    if "ngung hoat dong" in status_norm:
        score -= 8

    return round(float(clamp(score, 0, 100)), 2)


def build_tax_lookup_result(lookup_input, candidate, score_value, source_name, note_text=""):
    return TaxLookupResult(
        stt=0,
        query_name=lookup_input.query_name,
        query_address=lookup_input.query_address,
        tax_code=safe_string(candidate.get("tax_code")),
        matched_name=safe_string(candidate.get("matched_name")),
        matched_address=safe_string(candidate.get("matched_address")),
        object_type=safe_string(candidate.get("object_type") or lookup_input.object_type or "Tất cả"),
        status=safe_string(candidate.get("status") or "Không rõ"),
        source=safe_string(candidate.get("source") or source_name),
        score=score_value,
        note=note_text,
    )


def tax_result_to_values(result):
    return (
        result.stt,
        result.query_name,
        result.query_address,
        result.tax_code,
        result.matched_name,
        result.matched_address,
        result.object_type,
        result.status,
        result.source,
        result.score,
        result.note,
    )


def clear_tax_results():
    with tax_results_lock:
        tax_results_data.clear()
    if "tax_tree" in globals():
        for item in tax_tree.get_children():
            tax_tree.delete(item)
    if "tax_lbl_summary" in globals():
        tax_lbl_summary.config(text="Tổng dòng kết quả: 0")


def append_tax_results(results):
    if not results:
        return

    with tax_results_lock:
        for result in results:
            result.stt = len(tax_results_data) + 1
            tax_results_data.append(result)
            if "tax_tree" in globals():
                tax_tree.insert("", "end", values=tax_result_to_values(result))
        total_rows = len(tax_results_data)

    if "tax_lbl_summary" in globals():
        tax_lbl_summary.config(text=f"Tổng dòng kết quả: {total_rows}")


def export_tax_results_to_excel():
    with tax_results_lock:
        if not tax_results_data:
            messagebox.showwarning("Thiếu dữ liệu", "Chưa có kết quả tra cứu MST để xuất file.")
            return
        export_rows = [
            {
                "STT": result.stt,
                "Tên truy vấn": result.query_name,
                "Địa chỉ truy vấn": result.query_address,
                "MST": result.tax_code,
                "Tên khớp": result.matched_name,
                "Địa chỉ khớp": result.matched_address,
                "Loại": result.object_type,
                "Trạng thái": result.status,
                "Nguồn": result.source,
                "Điểm": result.score,
                "Ghi chú": result.note,
            }
            for result in tax_results_data
        ]

    default_name = f"tra_cuu_mst_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    save_path = filedialog.asksaveasfilename(
        title="Xuất kết quả tra cứu MST",
        defaultextension=".xlsx",
        initialfile=default_name,
        filetypes=[("Excel Workbook", "*.xlsx")],
    )
    if not save_path:
        return

    try:
        pd.DataFrame(export_rows).to_excel(save_path, index=False)
        if "tax_lbl_status" in globals():
            tax_lbl_status.config(text=f"Đã xuất file: {os.path.basename(save_path)}", fg=color_for("success"))
    except Exception as exc:
        messagebox.showerror("Lỗi xuất file", f"Không xuất được Excel.\n{exc}")


def filter_candidates_by_object_type(candidates, object_type):
    normalized_type = normalize_lookup_text(object_type, keep_spaces=True)
    if not normalized_type or normalized_type == "tat ca":
        return candidates

    filtered = []
    for candidate in candidates:
        candidate_type = normalize_lookup_text(candidate.get("object_type"), keep_spaces=True)
        if normalized_type in candidate_type or candidate_type in normalized_type:
            filtered.append(candidate)
    return filtered


def merge_candidates(candidates, merge_by_address):
    merged = {}
    for candidate in candidates:
        code = safe_string(candidate.get("tax_code"))
        name = normalize_lookup_text(candidate.get("matched_name"), keep_spaces=True)
        address = normalize_lookup_text(candidate.get("matched_address"), keep_spaces=True) if merge_by_address else ""
        key = (code, name, address)
        if key not in merged:
            merged[key] = candidate
    return list(merged.values())


def execute_tax_lookup(lookup_input):
    provider_chain = []
    if lookup_input.prefer_official:
        provider_chain.append(("official", tax_provider_official))
    if lookup_input.allow_fallback:
        provider_chain.append(("fallback", tax_provider_fallback))
    if not provider_chain:
        provider_chain.append(("official", tax_provider_official))

    query_contains_tax_code = bool(extract_tax_codes(f"{lookup_input.query_name} {lookup_input.query_address}"))
    candidates = []
    for provider_name, provider_obj in provider_chain:
        try:
            provider_candidates = provider_obj.search(lookup_input)
        except Exception as exc:
            if "tax_lbl_status" in globals():
                root.after(
                    0,
                    lambda m=f"Nguồn {provider_name} lỗi: {exc}": tax_lbl_status.config(text=m, fg=color_for("warning")),
                )
            provider_candidates = []
        if provider_candidates:
            for item in provider_candidates:
                item.setdefault("source", provider_name)
            candidates.extend(provider_candidates)
            if provider_name == "official":
                break

    candidates = filter_candidates_by_object_type(candidates, lookup_input.object_type)
    candidates = merge_candidates(candidates, lookup_input.merge_by_address)
    if not query_contains_tax_code:
        min_name_score = 40.0 if lookup_input.query_address else 34.0
        candidates = [
            candidate
            for candidate in candidates
            if has_significant_name_overlap(lookup_input.query_name, candidate.get("matched_name"))
            and get_name_match_score(lookup_input.query_name, candidate.get("matched_name")) >= min_name_score
        ]

    scored_results = []
    for candidate in candidates:
        score_value = score_tax_match(lookup_input.query_name, lookup_input.query_address, candidate)
        note_text = safe_string(candidate.get("source_url"))
        scored_results.append(
            build_tax_lookup_result(
                lookup_input=lookup_input,
                candidate=candidate,
                score_value=score_value,
                source_name=safe_string(candidate.get("source") or "official"),
                note_text=note_text,
            )
        )

    scored_results.sort(key=lambda item: item.score, reverse=True)
    if not query_contains_tax_code and scored_results:
        min_score = 42.0 if lookup_input.query_address else 34.0
        scored_results = [item for item in scored_results if item.score >= min_score]

    max_items = max(1, safe_int(lookup_input.max_results, 5))
    return scored_results[:max_items]


def build_not_found_tax_result(lookup_input, note_text):
    return TaxLookupResult(
        stt=0,
        query_name=lookup_input.query_name,
        query_address=lookup_input.query_address,
        tax_code="",
        matched_name="",
        matched_address="",
        object_type=lookup_input.object_type,
        status="Không tìm thấy",
        source="",
        score=0.0,
        note=note_text,
    )


class TaxLookupBatchRunner:
    def __init__(self, lookup_executor, on_result, on_progress, on_finish):
        self.lookup_executor = lookup_executor
        self.on_result = on_result
        self.on_progress = on_progress
        self.on_finish = on_finish
        self.stop_event = threading.Event()
        self.thread = None
        self.running = False

    def start(self, tasks):
        if self.running:
            return False
        self.stop_event.clear()
        self.running = True
        self.thread = threading.Thread(target=self._run, args=(list(tasks),), daemon=True)
        self.thread.start()
        return True

    def stop(self):
        self.stop_event.set()

    def _run(self, tasks):
        processed = 0
        total = len(tasks)
        for lookup_input in tasks:
            if self.stop_event.is_set():
                break
            try:
                results = self.lookup_executor(lookup_input)
                chosen = results[0] if results else build_not_found_tax_result(lookup_input, "Không có dữ liệu phù hợp.")
            except Exception as exc:
                chosen = build_not_found_tax_result(lookup_input, f"Lỗi xử lý: {exc}")
            processed += 1
            self.on_result(chosen)
            self.on_progress(processed, total)

        stopped = self.stop_event.is_set()
        self.running = False
        self.on_finish(processed, total, stopped)


def collect_tax_lookup_input_from_form():
    name_text = get_entry_clean_value(tax_ent_name)
    if not name_text:
        raise ValueError("Vui lòng nhập tên cần tra cứu.")

    address_text = get_entry_clean_value(tax_ent_address)
    object_type = safe_string(tax_cmb_type.get()) or "Tất cả"
    max_results = safe_int(tax_ent_limit.get(), 5)
    max_results = clamp(max_results, 1, 50)

    return TaxLookupInput(
        query_name=name_text,
        query_address=address_text,
        object_type=object_type,
        max_results=max_results,
        prefer_official=bool(tax_var_prefer_official.get()),
        allow_fallback=bool(tax_var_allow_fallback.get()),
        merge_by_address=bool(tax_var_merge_address.get()),
    )


def run_single_tax_lookup():
    try:
        lookup_input = collect_tax_lookup_input_from_form()
    except ValueError as exc:
        messagebox.showwarning("Thiếu thông tin", str(exc))
        return

    tax_btn_lookup.config(state=tk.DISABLED)
    tax_lbl_status.config(text="Đang tra cứu dữ liệu MST...", fg=color_for("info"))

    def worker():
        try:
            results = execute_tax_lookup(lookup_input)
            if not results:
                results = [
                    build_not_found_tax_result(
                        lookup_input,
                        "Không tìm thấy kết quả phù hợp. Gợi ý: nhập đầy đủ tên + địa chỉ hoặc dán trực tiếp mã số thuế.",
                    )
                ]
            root.after(0, lambda: append_tax_results(results))
            root.after(0, lambda: tax_lbl_status.config(text=f"Tra cứu xong: {lookup_input.query_name}", fg=color_for("success")))
        except Exception as exc:
            root.after(0, lambda: tax_lbl_status.config(text=f"Lỗi tra cứu: {exc}", fg=color_for("danger")))
        finally:
            root.after(0, lambda: tax_btn_lookup.config(state=tk.NORMAL))

    threading.Thread(target=worker, daemon=True).start()


def paste_tax_lookup_quick():
    try:
        clip_text = root.clipboard_get()
    except Exception:
        messagebox.showwarning("Thiếu dữ liệu", "Clipboard đang trống.")
        return

    lines = [safe_string(line) for line in str(clip_text).splitlines() if safe_string(line)]
    if not lines:
        return

    set_entry_value(tax_ent_name, lines[0])
    if len(lines) >= 2:
        set_entry_value(tax_ent_address, lines[1])
    elif "," in lines[0]:
        parts = [safe_string(part) for part in lines[0].split(",", 1)]
        if len(parts) == 2 and len(parts[0]) > 2 and len(parts[1]) > 2:
            set_entry_value(tax_ent_name, parts[0])
            set_entry_value(tax_ent_address, parts[1])


def clear_tax_lookup_form():
    set_entry_value(tax_ent_name, "")
    set_entry_value(tax_ent_address, "")
    tax_cmb_type.set("Tất cả")
    tax_ent_limit.delete(0, tk.END)
    tax_ent_limit.insert(0, "5")
    tax_var_prefer_official.set(True)
    tax_var_allow_fallback.set(True)
    tax_var_merge_address.set(True)


def load_tax_batch_file():
    global tax_batch_file_path, tax_batch_dataframe

    file_path = filedialog.askopenfilename(
        title="Chọn file dữ liệu tra cứu MST",
        filetypes=[("Excel/CSV", "*.xlsx;*.csv"), ("Excel", "*.xlsx"), ("CSV", "*.csv")],
    )
    if not file_path:
        return

    try:
        if file_path.lower().endswith(".csv"):
            df = pd.read_csv(file_path, encoding="utf-8")
        else:
            df = pd.read_excel(file_path)
    except UnicodeDecodeError:
        df = pd.read_csv(file_path, encoding="latin-1")
    except Exception as exc:
        messagebox.showerror("Lỗi đọc file", f"Không đọc được file dữ liệu.\n{exc}")
        return

    if df is None or df.empty:
        messagebox.showwarning("Thiếu dữ liệu", "File đang trống hoặc không có dòng dữ liệu.")
        return

    tax_batch_file_path = file_path
    tax_batch_dataframe = df.fillna("")
    tax_lbl_batch_file.config(text=f"File: {os.path.basename(file_path)} ({len(df)} dòng)")
    tax_lbl_batch_progress.config(text="Tiến độ: 0/0")

    columns = list(tax_batch_dataframe.columns)
    tax_batch_col_name["values"] = columns
    tax_batch_col_address["values"] = columns
    tax_batch_col_type["values"] = [""] + columns

    name_col = resolve_column_name(tax_batch_dataframe, "ten_doi_tuong", "ten", "name")
    addr_col = resolve_column_name(tax_batch_dataframe, "dia_chi", "dia chi", "address")
    type_col = resolve_column_name(tax_batch_dataframe, "loai_doi_tuong", "loai", "type")
    if name_col:
        tax_batch_col_name.set(name_col)
    elif columns:
        tax_batch_col_name.set(columns[0])
    if addr_col:
        tax_batch_col_address.set(addr_col)
    elif len(columns) > 1:
        tax_batch_col_address.set(columns[1])
    if type_col:
        tax_batch_col_type.set(type_col)

    tax_lbl_status.config(text="Đã nạp file hàng loạt.", fg=color_for("success"))


def build_tax_batch_inputs():
    if tax_batch_dataframe is None:
        raise ValueError("Vui lòng nạp file hàng loạt trước.")

    name_col = safe_string(tax_batch_col_name.get())
    address_col = safe_string(tax_batch_col_address.get())
    type_col = safe_string(tax_batch_col_type.get())
    if not name_col or name_col not in tax_batch_dataframe.columns:
        raise ValueError("Chưa chọn đúng cột tên đối tượng.")
    if not address_col or address_col not in tax_batch_dataframe.columns:
        raise ValueError("Chưa chọn đúng cột địa chỉ.")

    object_type_default = safe_string(tax_cmb_type.get()) or "Tất cả"
    max_results = clamp(safe_int(tax_ent_limit.get(), 5), 1, 50)
    prefer_official = bool(tax_var_prefer_official.get())
    allow_fallback = bool(tax_var_allow_fallback.get())
    merge_by_address = bool(tax_var_merge_address.get())

    tasks = []
    for _, row in tax_batch_dataframe.iterrows():
        query_name = safe_string(row.get(name_col))
        if not query_name:
            continue
        query_address = safe_string(row.get(address_col))
        row_type = safe_string(row.get(type_col)) if type_col and type_col in tax_batch_dataframe.columns else ""
        lookup_input = TaxLookupInput(
            query_name=query_name,
            query_address=query_address,
            object_type=row_type or object_type_default,
            max_results=max_results,
            prefer_official=prefer_official,
            allow_fallback=allow_fallback,
            merge_by_address=merge_by_address,
        )
        tasks.append(lookup_input)
    return tasks


def start_tax_batch_lookup():
    global tax_batch_runner

    try:
        tasks = build_tax_batch_inputs()
    except ValueError as exc:
        messagebox.showwarning("Thiếu cấu hình", str(exc))
        return

    if not tasks:
        messagebox.showwarning("Thiếu dữ liệu", "Không có dòng dữ liệu hợp lệ để chạy hàng loạt.")
        return

    if tax_batch_runner and tax_batch_runner.running:
        messagebox.showwarning("Đang chạy", "Batch tra cứu MST đang chạy.")
        return

    clear_tax_results()
    tax_btn_batch_start.config(state=tk.DISABLED)
    tax_btn_batch_stop.config(state=tk.NORMAL)
    tax_lbl_status.config(text="Đang chạy batch tra cứu MST...", fg=color_for("info"))
    tax_lbl_batch_progress.config(text=f"Tiến độ: 0/{len(tasks)}")

    def on_result(result):
        root.after(0, lambda r=result: append_tax_results([r]))

    def on_progress(done, total):
        root.after(0, lambda: tax_lbl_batch_progress.config(text=f"Tiến độ: {done}/{total}"))

    def on_finish(processed, total, stopped):
        def finish_ui():
            tax_btn_batch_start.config(state=tk.NORMAL)
            tax_btn_batch_stop.config(state=tk.DISABLED)
            if stopped:
                tax_lbl_status.config(text=f"Đã dừng mềm batch: {processed}/{total} dòng.", fg=color_for("warning"))
            else:
                tax_lbl_status.config(text=f"Hoàn tất batch: {processed}/{total} dòng.", fg=color_for("success"))

        root.after(0, finish_ui)

    tax_batch_runner = TaxLookupBatchRunner(
        lookup_executor=execute_tax_lookup,
        on_result=on_result,
        on_progress=on_progress,
        on_finish=on_finish,
    )
    tax_batch_runner.start(tasks)


def stop_tax_batch_lookup():
    if tax_batch_runner and tax_batch_runner.running:
        tax_batch_runner.stop()
        if "tax_lbl_status" in globals():
            tax_lbl_status.config(text="Đang dừng batch...", fg=color_for("warning"))


def download_tax_template():
    save_path = filedialog.asksaveasfilename(
        title="Lưu file mẫu tra cứu MST",
        defaultextension=".xlsx",
        initialfile="mau_tra_cuu_mst.xlsx",
        filetypes=[("Excel Workbook", "*.xlsx"), ("CSV UTF-8", "*.csv")],
    )
    if not save_path:
        return

    template_df = pd.DataFrame(
        columns=["ten_doi_tuong", "dia_chi", "loai_doi_tuong"],
        data=[["Công ty TNHH ABC", "Quận 1, TP HCM", "Doanh nghiệp"]],
    )
    try:
        if save_path.lower().endswith(".csv"):
            template_df.to_csv(save_path, index=False, encoding="utf-8-sig")
        else:
            template_df.to_excel(save_path, index=False)
        tax_lbl_status.config(text=f"Đã tạo file mẫu: {os.path.basename(save_path)}", fg=color_for("success"))
    except Exception as exc:
        messagebox.showerror("Lỗi tạo file mẫu", f"Không thể tạo file mẫu.\n{exc}")


def build_tax_lookup_tab(parent):
    global tax_ent_name, tax_ent_address, tax_cmb_type, tax_ent_limit
    global tax_var_prefer_official, tax_var_allow_fallback, tax_var_merge_address
    global tax_btn_lookup, tax_lbl_status, tax_tree, tax_lbl_summary
    global tax_lbl_batch_file, tax_batch_col_name, tax_batch_col_address, tax_batch_col_type
    global tax_btn_batch_start, tax_btn_batch_stop, tax_lbl_batch_progress
    global tax_provider_official, tax_provider_fallback

    tab_shell = tk.Frame(parent, bg=APP_THEME["bg"])
    tab_shell.pack(fill=tk.BOTH, expand=True, padx=20, pady=18)
    tab_shell.grid_rowconfigure(1, weight=0, minsize=300)
    tab_shell.grid_rowconfigure(2, weight=1)
    tab_shell.grid_rowconfigure(3, weight=0)
    tab_shell.grid_columnconfigure(0, weight=1)
    tab_shell.grid_columnconfigure(1, weight=1)

    header = tk.Frame(tab_shell, bg=APP_THEME["bg"])
    header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 14))
    tk.Label(
        header,
        text="Tra cứu mã số thuế",
        font=(FONT_FAMILY, 20, "bold"),
        bg=APP_THEME["bg"],
        fg=APP_THEME["text"],
    ).pack(anchor="w")
    tk.Label(
        header,
        text="Tra đơn hoặc hàng loạt theo tên + địa chỉ, tách riêng với tab Quét Maps.",
        font=(FONT_FAMILY, 10),
        bg=APP_THEME["bg"],
        fg=APP_THEME["muted"],
    ).pack(anchor="w", pady=(4, 0))

    single_card, single_body = make_card(
        tab_shell,
        "Tra đơn",
        "Nhập tên đối tượng và địa chỉ để tra cứu nhanh.",
        accent=APP_THEME["accent"],
    )
    single_card.grid(row=1, column=0, sticky="ew", padx=(0, 8), pady=(0, 14))
    single_body.grid_columnconfigure(0, weight=1)
    single_body.grid_columnconfigure(1, weight=1)

    tk.Label(single_body, text="Tên đối tượng", bg=APP_THEME["surface"], fg=APP_THEME["text"], font=(FONT_FAMILY, 9, "bold")).grid(row=0, column=0, sticky="w")
    tax_ent_name = tk.Entry(single_body)
    style_entry(tax_ent_name, justify="left")
    tax_ent_name.grid(row=1, column=0, sticky="ew", ipady=8, pady=(6, 10), padx=(0, 6))

    tk.Label(single_body, text="Địa chỉ", bg=APP_THEME["surface"], fg=APP_THEME["text"], font=(FONT_FAMILY, 9, "bold")).grid(row=0, column=1, sticky="w")
    tax_ent_address = tk.Entry(single_body)
    style_entry(tax_ent_address, justify="left")
    tax_ent_address.grid(row=1, column=1, sticky="ew", ipady=8, pady=(6, 10), padx=(6, 0))

    tk.Label(single_body, text="Loại đối tượng", bg=APP_THEME["surface"], fg=APP_THEME["text"], font=(FONT_FAMILY, 9, "bold")).grid(row=2, column=0, sticky="w")
    tax_cmb_type = ttk.Combobox(single_body, state="readonly", values=["Tất cả", "Cá nhân", "Doanh nghiệp", "Hộ kinh doanh"])
    tax_cmb_type.grid(row=3, column=0, sticky="ew", ipady=6, pady=(6, 10), padx=(0, 6))
    tax_cmb_type.set("Tất cả")

    tk.Label(single_body, text="Số kết quả tối đa", bg=APP_THEME["surface"], fg=APP_THEME["text"], font=(FONT_FAMILY, 9, "bold")).grid(row=2, column=1, sticky="w")
    tax_ent_limit = tk.Spinbox(single_body, from_=1, to=50, increment=1)
    style_spinbox(tax_ent_limit)
    tax_ent_limit.grid(row=3, column=1, sticky="ew", ipady=6, pady=(6, 10), padx=(6, 0))
    tax_ent_limit.delete(0, tk.END)
    tax_ent_limit.insert(0, "5")

    tax_var_prefer_official = tk.BooleanVar(value=True)
    tax_var_allow_fallback = tk.BooleanVar(value=True)
    tax_var_merge_address = tk.BooleanVar(value=True)

    ttk.Checkbutton(single_body, text="Ưu tiên nguồn chính thức", variable=tax_var_prefer_official, style="Modern.TCheckbutton").grid(row=4, column=0, sticky="w")
    ttk.Checkbutton(single_body, text="Cho phép fallback", variable=tax_var_allow_fallback, style="Modern.TCheckbutton").grid(row=5, column=0, sticky="w")
    ttk.Checkbutton(single_body, text="Ghép điểm theo địa chỉ", variable=tax_var_merge_address, style="Modern.TCheckbutton").grid(row=6, column=0, sticky="w", pady=(0, 8))

    single_actions = tk.Frame(single_body, bg=APP_THEME["surface"])
    single_actions.grid(row=7, column=0, columnspan=2, sticky="ew")
    single_actions.grid_columnconfigure(0, weight=1)
    single_actions.grid_columnconfigure(1, weight=1)
    single_actions.grid_columnconfigure(2, weight=1)

    tax_btn_lookup = make_button(single_actions, "TRA CỨU", run_single_tax_lookup, APP_THEME["accent"], APP_THEME["accent_hover"], width=12)
    tax_btn_lookup.grid(row=0, column=0, sticky="ew", padx=(0, 6))
    make_button(single_actions, "DÁN NHANH", paste_tax_lookup_quick, APP_THEME["panel_alt"], "#334155", width=12).grid(row=0, column=1, sticky="ew", padx=3)
    make_button(single_actions, "XÓA FORM", clear_tax_lookup_form, APP_THEME["danger"], APP_THEME["danger_hover"], width=12).grid(row=0, column=2, sticky="ew", padx=(6, 0))

    batch_card, batch_body = make_card(
        tab_shell,
        "Tra hàng loạt",
        "Nạp file xlsx/csv và chạy nền theo queue.",
        accent=APP_THEME["warning"],
    )
    batch_card.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=(0, 14))
    batch_body.grid_columnconfigure(0, weight=1)
    batch_body.grid_columnconfigure(1, weight=1)

    tax_lbl_batch_file = tk.Label(
        batch_body,
        text="Chưa nạp file.",
        bg=APP_THEME["surface"],
        fg=APP_THEME["muted"],
        justify="left",
        wraplength=420,
        font=(FONT_FAMILY, 9),
    )
    tax_lbl_batch_file.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

    make_button(batch_body, "NẠP FILE", load_tax_batch_file, APP_THEME["panel_alt"], "#334155", width=12).grid(row=1, column=0, sticky="w", padx=(0, 8))
    tax_lbl_batch_progress = tk.Label(batch_body, text="Tiến độ: 0/0", bg=APP_THEME["surface"], fg=APP_THEME["muted"], font=(FONT_FAMILY, 9))
    tax_lbl_batch_progress.grid(row=1, column=1, sticky="e")

    tk.Label(batch_body, text="Cột tên", bg=APP_THEME["surface"], fg=APP_THEME["text"], font=(FONT_FAMILY, 9, "bold")).grid(row=2, column=0, sticky="w", pady=(10, 0))
    tk.Label(batch_body, text="Cột địa chỉ", bg=APP_THEME["surface"], fg=APP_THEME["text"], font=(FONT_FAMILY, 9, "bold")).grid(row=2, column=1, sticky="w", pady=(10, 0))
    tax_batch_col_name = ttk.Combobox(batch_body, state="readonly")
    tax_batch_col_address = ttk.Combobox(batch_body, state="readonly")
    tax_batch_col_name.grid(row=3, column=0, sticky="ew", ipady=6, pady=(6, 10), padx=(0, 6))
    tax_batch_col_address.grid(row=3, column=1, sticky="ew", ipady=6, pady=(6, 10), padx=(6, 0))

    tk.Label(batch_body, text="Cột loại đối tượng (tuỳ chọn)", bg=APP_THEME["surface"], fg=APP_THEME["text"], font=(FONT_FAMILY, 9, "bold")).grid(row=4, column=0, sticky="w")
    tax_batch_col_type = ttk.Combobox(batch_body, state="readonly")
    tax_batch_col_type.grid(row=5, column=0, sticky="ew", ipady=6, pady=(6, 10), padx=(0, 6))

    batch_actions = tk.Frame(batch_body, bg=APP_THEME["surface"])
    batch_actions.grid(row=6, column=0, columnspan=2, sticky="ew")
    batch_actions.grid_columnconfigure(0, weight=1)
    batch_actions.grid_columnconfigure(1, weight=1)
    batch_actions.grid_columnconfigure(2, weight=1)
    batch_actions.grid_columnconfigure(3, weight=1)

    tax_btn_batch_start = make_button(batch_actions, "CHẠY HÀNG LOẠT", start_tax_batch_lookup, APP_THEME["warning"], "#D97706", width=15)
    tax_btn_batch_start.grid(row=0, column=0, sticky="ew", padx=(0, 4))
    tax_btn_batch_stop = make_button(batch_actions, "DỪNG", stop_tax_batch_lookup, APP_THEME["danger"], APP_THEME["danger_hover"], width=10)
    tax_btn_batch_stop.grid(row=0, column=1, sticky="ew", padx=4)
    tax_btn_batch_stop.config(state=tk.DISABLED)
    make_button(batch_actions, "TẢI FILE MẪU", download_tax_template, APP_THEME["panel_alt"], "#334155", width=12).grid(row=0, column=2, sticky="ew", padx=4)
    make_button(batch_actions, "XUẤT EXCEL", export_tax_results_to_excel, APP_THEME["info"], "#0284C7", width=12).grid(row=0, column=3, sticky="ew", padx=(4, 0))

    results_card, results_body = make_card(
        tab_shell,
        "Bảng kết quả MST",
        "Kết quả tra cứu được tách riêng hoàn toàn với bảng Quét Maps.",
        accent=APP_THEME["info"],
    )
    results_card.grid(row=2, column=0, columnspan=2, sticky="nsew")
    results_body.grid_rowconfigure(0, weight=1)
    results_body.grid_columnconfigure(0, weight=1)

    tax_tree_frame = tk.Frame(results_body, bg=APP_THEME["surface"])
    tax_tree_frame.grid(row=0, column=0, sticky="nsew")
    tax_tree_frame.grid_rowconfigure(0, weight=1)
    tax_tree_frame.grid_columnconfigure(0, weight=1)

    tax_tree = ttk.Treeview(
        tax_tree_frame,
        columns=("stt", "query_name", "query_address", "tax_code", "match_name", "match_address", "obj_type", "status", "source", "score", "note"),
        show="headings",
        selectmode="extended",
    )
    tax_tree.heading("stt", text="STT")
    tax_tree.heading("query_name", text="Tên truy vấn")
    tax_tree.heading("query_address", text="Địa chỉ truy vấn")
    tax_tree.heading("tax_code", text="MST")
    tax_tree.heading("match_name", text="Tên khớp")
    tax_tree.heading("match_address", text="Địa chỉ khớp")
    tax_tree.heading("obj_type", text="Loại")
    tax_tree.heading("status", text="Trạng thái")
    tax_tree.heading("source", text="Nguồn")
    tax_tree.heading("score", text="Điểm")
    tax_tree.heading("note", text="Ghi chú")
    tax_tree.column("stt", width=60, anchor="center", stretch=False)
    tax_tree.column("query_name", width=180, anchor="w")
    tax_tree.column("query_address", width=220, anchor="w")
    tax_tree.column("tax_code", width=120, anchor="center")
    tax_tree.column("match_name", width=220, anchor="w")
    tax_tree.column("match_address", width=260, anchor="w")
    tax_tree.column("obj_type", width=120, anchor="center")
    tax_tree.column("status", width=130, anchor="center")
    tax_tree.column("source", width=100, anchor="center")
    tax_tree.column("score", width=80, anchor="center")
    tax_tree.column("note", width=280, anchor="w")
    tax_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    tax_scroll_y = ttk.Scrollbar(tax_tree_frame, orient="vertical", command=tax_tree.yview, style="Vertical.TScrollbar")
    tax_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
    tax_tree.configure(yscrollcommand=tax_scroll_y.set)

    tax_scroll_x = ttk.Scrollbar(tax_tree_frame, orient="horizontal", command=tax_tree.xview, style="Horizontal.TScrollbar")
    tax_scroll_x.pack(side=tk.BOTTOM, fill=tk.X, pady=(8, 0))
    tax_tree.configure(xscrollcommand=tax_scroll_x.set)

    results_footer = tk.Frame(results_body, bg=APP_THEME["surface"])
    results_footer.grid(row=1, column=0, sticky="ew", pady=(10, 0))
    results_footer.grid_columnconfigure(0, weight=1)

    tax_lbl_summary = tk.Label(results_footer, text="Tổng dòng kết quả: 0", bg=APP_THEME["surface"], fg=APP_THEME["muted"], font=(FONT_FAMILY, 9))
    tax_lbl_summary.grid(row=0, column=0, sticky="w")

    footer_actions = tk.Frame(results_footer, bg=APP_THEME["surface"])
    footer_actions.grid(row=0, column=1, sticky="e")
    make_button(footer_actions, "XÓA KẾT QUẢ", clear_tax_results, APP_THEME["panel_alt"], "#334155", width=12).pack(side=tk.LEFT, padx=(0, 8))
    make_button(footer_actions, "XUẤT EXCEL", export_tax_results_to_excel, APP_THEME["info"], "#0284C7", width=12).pack(side=tk.LEFT)

    tax_lbl_status = tk.Label(
        tab_shell,
        text="Sẵn sàng tra cứu MST.",
        bg=APP_THEME["bg"],
        fg=APP_THEME["muted"],
        font=(FONT_FAMILY, 9),
        justify="left",
    )
    tax_lbl_status.grid(row=3, column=0, columnspan=2, sticky="w", pady=(10, 0))

    tax_provider_official = OfficialTaxProvider(timeout=12, retry=2)
    tax_provider_fallback = FallbackTaxProvider(timeout=8, retry=1)
    tax_provider_fallback.register_adapter(tax_provider_official.search_by_bing_discovery)

    attach_entry_placeholder(tax_ent_name, "Ví dụ: Công ty TNHH ABC")
    attach_entry_placeholder(tax_ent_address, "Ví dụ: Quận 1, TP HCM")

saved_license_valid, _saved_license, saved_license_message = get_saved_license_status()
login_success = saved_license_valid

if not login_success:
    current_machine = get_machine_identity()
    license_api_url = get_license_api_url()
    if saved_license_message:
        login_status_text = saved_license_message
        login_status_color = color_for("warning")
    elif not license_api_url:
        login_status_text = (
            "Chưa cấu hình server kích hoạt. "
            "Bấm CẤU HÌNH SERVER để dán endpoint kích hoạt rồi tiếp tục."
        )
        login_status_color = color_for("warning")
    else:
        login_status_text = "Vui lòng nhập đúng mã kích hoạt đã được cấp."
        login_status_color = color_for("muted")

    root_login = tk.Tk()
    root_login.title("Kích hoạt bản quyền - THL Maps")
    root_login.configure(bg=APP_THEME["bg"])
    root_login.resizable(False, False)
    center_window(root_login, 470, 400)
    set_app_icon(root_login)

    login_shell = tk.Frame(root_login, bg=APP_THEME["bg"])
    login_shell.pack(fill=tk.BOTH, expand=True, padx=24, pady=24)

    login_card = tk.Frame(
        login_shell,
        bg=APP_THEME["surface"],
        highlightbackground=APP_THEME["border"],
        highlightthickness=1,
        bd=0,
    )
    login_card.pack(fill=tk.BOTH, expand=True)
    tk.Frame(login_card, bg=APP_THEME["accent"], height=5).pack(fill=tk.X)

    login_body = tk.Frame(login_card, bg=APP_THEME["surface"])
    login_body.pack(fill=tk.BOTH, expand=True, padx=28, pady=26)

    tk.Label(
        login_body,
        text="THL Maps License",
        font=(FONT_FAMILY, 18, "bold"),
        bg=APP_THEME["surface"],
        fg=APP_THEME["text"],
    ).pack(anchor="w")

    tk.Label(
        login_body,
        text="Nhập mã bản quyền để mở dashboard quét Google Maps.",
        font=(FONT_FAMILY, 10),
        bg=APP_THEME["surface"],
        fg=APP_THEME["muted"],
    ).pack(anchor="w", pady=(6, 10))

    tk.Label(
        login_body,
        text=f"ID máy hiện tại: {current_machine['display_id']}",
        font=(FONT_FAMILY, 9, "bold"),
        bg=APP_THEME["surface"],
        fg=APP_THEME["info"],
    ).pack(anchor="w", pady=(0, 14))

    tk.Label(
        login_body,
        text="Mã kích hoạt",
        font=(FONT_FAMILY, 9, "bold"),
        bg=APP_THEME["surface"],
        fg=APP_THEME["text"],
    ).pack(anchor="w")

    ent_key = tk.Entry(login_body)
    style_entry(ent_key, justify="center")
    ent_key.pack(fill=tk.X, ipady=10, pady=(8, 14))

    btn_activate = make_button(
        login_body,
        "KÍCH HOẠT NGAY",
        check_license,
        APP_THEME["accent"],
        APP_THEME["accent_hover"],
        width=22,
    )
    btn_activate.pack(fill=tk.X)

    btn_server = make_button(
        login_body,
        "CẤU HÌNH SERVER",
        configure_license_server_from_login,
        APP_THEME["info"],
        "#0EA5E9",
        width=22,
    )
    btn_server.pack(fill=tk.X, pady=(10, 0))

    lbl_status = tk.Label(
        login_body,
        text=login_status_text,
        font=(FONT_FAMILY, 9),
        bg=APP_THEME["surface"],
        fg=login_status_color,
        justify="left",
        wraplength=360,
    )
    lbl_status.pack(anchor="w", pady=(14, 0))

    tk.Label(
        login_body,
        text="Product by Khương Bình",
        font=(FONT_FAMILY, 8),
        bg=APP_THEME["surface"],
        fg=APP_THEME["muted"],
    ).pack(anchor="e", pady=(10, 0))

    ent_key.focus_set()
    root_login.bind("<Return>", lambda _event: check_license())
    root_login.mainloop()

if not login_success:
    sys.exit()


root = tk.Tk()
root.title(f"THL Maps Pro v{APP_RELEASE_VERSION} - Dashboard")
root.configure(bg=APP_THEME["bg"])
root.minsize(1120, 760)
center_window(root, 1240, 860)
set_app_icon(root)
setup_ttk_styles()

main_notebook = ttk.Notebook(root, style="Dashboard.TNotebook")
main_notebook.pack(fill=tk.BOTH, expand=True, padx=20, pady=18)

maps_tab = tk.Frame(main_notebook, bg=APP_THEME["bg"])
tax_tab = tk.Frame(main_notebook, bg=APP_THEME["bg"])
main_notebook.add(maps_tab, text="Quét Maps")
main_notebook.add(tax_tab, text="Tra cứu MST")

app_shell = tk.Frame(maps_tab, bg=APP_THEME["bg"])
app_shell.pack(fill=tk.BOTH, expand=True)

header = tk.Frame(app_shell, bg=APP_THEME["bg"])
header.pack(fill=tk.X, pady=(0, 16))

header_text = tk.Frame(header, bg=APP_THEME["bg"])
header_text.pack(side=tk.LEFT, fill=tk.X, expand=True)

tk.Label(
    header_text,
    text=f"THL Maps Pro v{APP_RELEASE_VERSION}",
    font=(FONT_FAMILY, 24, "bold"),
    bg=APP_THEME["bg"],
    fg=APP_THEME["text"],
).pack(anchor="w")

tk.Label(
    header_text,
    text="Bảng điều khiển quét Google Maps với bố cục gọn, đậm và dễ theo dõi hơn.",
    font=(FONT_FAMILY, 10),
    bg=APP_THEME["bg"],
    fg=APP_THEME["muted"],
).pack(anchor="w", pady=(4, 0))

lbl_state_badge = tk.Label(
    header,
    text="SẴN SÀNG",
    font=(FONT_FAMILY, 10, "bold"),
    bg=APP_THEME["panel"],
    fg=APP_THEME["accent"],
    padx=18,
    pady=10,
    highlightbackground=APP_THEME["border"],
    highlightthickness=1,
)
lbl_state_badge.pack(side=tk.RIGHT)

content = tk.Frame(app_shell, bg=APP_THEME["bg"])
content.pack(fill=tk.BOTH, expand=True)
content.grid_columnconfigure(0, weight=5, minsize=820)
content.grid_columnconfigure(1, weight=4, minsize=520)
content.grid_rowconfigure(0, weight=1)

left_col = tk.Frame(content, bg=APP_THEME["bg"])
left_col.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
left_col.grid_columnconfigure(0, weight=1)
left_col.grid_rowconfigure(1, weight=1)
left_col.grid_rowconfigure(2, weight=0)

right_col_wrap = tk.Frame(content, bg=APP_THEME["bg"])
right_col_wrap.grid(row=0, column=1, sticky="nsew")
right_col_wrap.grid_rowconfigure(0, weight=1)
right_col_wrap.grid_columnconfigure(0, weight=1)

right_col_canvas = tk.Canvas(
    right_col_wrap,
    bg=APP_THEME["bg"],
    highlightthickness=0,
    bd=0,
)
right_col_canvas.grid(row=0, column=0, sticky="nsew")

right_col_scroll = ttk.Scrollbar(
    right_col_wrap,
    orient="vertical",
    command=right_col_canvas.yview,
    style="Vertical.TScrollbar",
)
right_col_scroll.grid(row=0, column=1, sticky="ns")
right_col_canvas.configure(yscrollcommand=right_col_scroll.set)

right_col = tk.Frame(right_col_canvas, bg=APP_THEME["bg"])
right_col_window = right_col_canvas.create_window((0, 0), window=right_col, anchor="nw")
right_col.grid_columnconfigure(0, weight=1)
right_col.grid_rowconfigure(4, weight=1)


def _sync_right_panel_scroll_region(_event=None):
    right_col_canvas.configure(scrollregion=right_col_canvas.bbox("all"))


def _sync_right_panel_width(event):
    right_col_canvas.itemconfigure(right_col_window, width=event.width)


right_col.bind("<Configure>", _sync_right_panel_scroll_region)
right_col_canvas.bind("<Configure>", _sync_right_panel_width)


def _right_panel_mousewheel_units(event):
    if getattr(event, "num", None) == 4:
        return -1
    if getattr(event, "num", None) == 5:
        return 1

    delta = getattr(event, "delta", 0) or 0
    if not delta:
        return 0
    return -1 * int(delta / 120)


def _scroll_right_panel(event):
    units = _right_panel_mousewheel_units(event)
    if units:
        right_col_canvas.yview_scroll(units, "units")
        return "break"


def _bind_right_panel_mousewheel(widget):
    if widget is txt_px:
        return

    for sequence in ("<MouseWheel>", "<Shift-MouseWheel>", "<Button-4>", "<Button-5>"):
        widget.bind(sequence, _scroll_right_panel, add="+")

    for child in widget.winfo_children():
        _bind_right_panel_mousewheel(child)

search_card, search_body = make_card(
    left_col,
    "Bộ lọc tìm kiếm",
    "Xác định khu vực, từ khóa và số lượng doanh nghiệp cần quét.",
    accent=APP_THEME["accent"],
)
search_card.grid(row=0, column=0, sticky="ew", pady=(0, 14))
search_body.grid_columnconfigure(0, weight=4)
search_body.grid_columnconfigure(1, weight=4)
search_body.grid_columnconfigure(2, weight=2)

field_loc = tk.Frame(search_body, bg=APP_THEME["surface"])
field_loc.grid(row=0, column=0, sticky="ew", padx=(0, 10))
tk.Label(
    field_loc,
    text="Khu vực",
    font=(FONT_FAMILY, 9, "bold"),
    bg=APP_THEME["surface"],
    fg=APP_THEME["text"],
).pack(anchor="w")
ent_loc = tk.Entry(field_loc)
style_entry(ent_loc)
ent_loc.insert(0, "Mỹ Tho")
ent_loc.pack(fill=tk.X, ipady=10, pady=(8, 0))

field_kw = tk.Frame(search_body, bg=APP_THEME["surface"])
field_kw.grid(row=0, column=1, sticky="ew", padx=5)
tk.Label(
    field_kw,
    text="Từ khóa",
    font=(FONT_FAMILY, 9, "bold"),
    bg=APP_THEME["surface"],
    fg=APP_THEME["text"],
).pack(anchor="w")
ent_kw = tk.Entry(field_kw)
style_entry(ent_kw)
ent_kw.insert(0, "Salon tóc")
ent_kw.pack(fill=tk.X, ipady=10, pady=(8, 0))

field_limit = tk.Frame(search_body, bg=APP_THEME["surface"])
field_limit.grid(row=0, column=2, sticky="ew", padx=(10, 0))
tk.Label(
    field_limit,
    text="Mục tiêu",
    font=(FONT_FAMILY, 9, "bold"),
    bg=APP_THEME["surface"],
    fg=APP_THEME["text"],
).pack(anchor="w")
ent_lim = tk.Entry(field_limit)
style_entry(ent_lim, justify="center")
ent_lim.insert(0, "100")
ent_lim.pack(fill=tk.X, ipady=10, pady=(8, 0))

field_lat = tk.Frame(search_body, bg=APP_THEME["surface"])
field_lat.grid(row=1, column=0, sticky="ew", padx=(0, 10), pady=(12, 0))
tk.Label(
    field_lat,
    text="Vĩ độ",
    font=(FONT_FAMILY, 9, "bold"),
    bg=APP_THEME["surface"],
    fg=APP_THEME["text"],
).pack(anchor="w")
ent_lat = tk.Entry(field_lat)
style_entry(ent_lat, justify="left")
ent_lat.pack(fill=tk.X, ipady=10, pady=(8, 0))

field_lng = tk.Frame(search_body, bg=APP_THEME["surface"])
field_lng.grid(row=1, column=1, sticky="ew", padx=5, pady=(12, 0))
tk.Label(
    field_lng,
    text="Kinh độ",
    font=(FONT_FAMILY, 9, "bold"),
    bg=APP_THEME["surface"],
    fg=APP_THEME["text"],
).pack(anchor="w")
ent_lng = tk.Entry(field_lng)
style_entry(ent_lng, justify="left")
ent_lng.pack(fill=tk.X, ipady=10, pady=(8, 0))

field_zoom = tk.Frame(search_body, bg=APP_THEME["surface"])
field_zoom.grid(row=1, column=2, sticky="ew", padx=(10, 0), pady=(12, 0))
tk.Label(
    field_zoom,
    text="Zoom",
    font=(FONT_FAMILY, 9, "bold"),
    bg=APP_THEME["surface"],
    fg=APP_THEME["text"],
).pack(anchor="w")
ent_zoom = tk.Entry(field_zoom)
style_entry(ent_zoom, justify="left")
ent_zoom.insert(0, "14")
ent_zoom.pack(fill=tk.X, ipady=10, pady=(8, 0))

btn_paste_coord = make_button(
    field_zoom,
    "DÁN TỌA ĐỘ",
    paste_coordinates_from_clipboard,
    APP_THEME["panel_alt"],
    "#334155",
    width=12,
)
btn_paste_coord.pack(fill=tk.X, pady=(8, 0))

search_hint = tk.Frame(
    search_body,
    bg=APP_THEME["panel"],
    highlightbackground=APP_THEME["border"],
    highlightthickness=1,
    bd=0,
)
search_hint.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(14, 0))
tk.Label(
    search_hint,
    text="Gợi ý: chỉ cần nhập khu vực hoặc tọa độ, không cần cả hai. Từ khóa càng ngắn gọn và đúng ngữ cảnh địa phương thì kết quả trên Google Maps thường ổn định hơn.",
    font=(FONT_FAMILY, 9),
    bg=APP_THEME["panel"],
    fg=APP_THEME["muted"],
    justify="left",
    wraplength=760,
).pack(anchor="w", padx=14, pady=12)

results_card, results_body = make_card(
    left_col,
    "Kết quả thu thập",
    "Danh sách doanh nghiệp sẽ đổ trực tiếp vào bảng bên dưới.",
    accent=APP_THEME["info"],
)
results_card.grid(row=1, column=0, sticky="nsew")
results_body.grid_rowconfigure(0, weight=1)
results_body.grid_columnconfigure(0, weight=1)

table_frame = tk.Frame(results_body, bg=APP_THEME["surface"])
table_frame.grid(row=0, column=0, sticky="nsew")

tree = ttk.Treeview(
    table_frame,
    columns=TREE_COLUMNS,
    show="headings",
    selectmode="extended",
)
tree.heading("pick", text="Tick")
tree.heading("stt", text="STT")
tree.heading("route_order", text="Thứ tự tuyến")
tree.heading("route_cluster", text="Cụm")
tree.heading("name", text="Tên")
tree.heading("phone", text="SĐT")
tree.heading("address", text="Địa chỉ")
tree.heading("lat", text="Vĩ độ")
tree.heading("lng", text="Kinh độ")
tree.heading("route_distance", text="Khoảng cách ước tính")
tree.heading("route_time", text="Thời gian ước tính")
tree.heading("route_note", text="Ghi chú tuyến")
tree.column("pick", width=52, anchor="center", stretch=False)
tree.column("stt", width=56, anchor="center", stretch=False)
tree.column("route_order", width=88, anchor="center")
tree.column("route_cluster", width=70, anchor="center")
tree.column("name", width=210, anchor="w")
tree.column("phone", width=120, anchor="center")
tree.column("address", width=260, anchor="w")
tree.column("lat", width=100, anchor="center")
tree.column("lng", width=100, anchor="center")
tree.column("route_distance", width=160, anchor="center")
tree.column("route_time", width=150, anchor="center")
tree.column("route_note", width=220, anchor="w")
tree.tag_configure("oddrow", background=APP_THEME["panel"], foreground=APP_THEME["text"])
tree.tag_configure("evenrow", background=APP_THEME["panel_alt"], foreground=APP_THEME["text"])
tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

scrl = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview, style="Vertical.TScrollbar")
tree.configure(yscrollcommand=scrl.set)
scrl.pack(side=tk.RIGHT, fill=tk.Y)

scrl_x = ttk.Scrollbar(table_frame, orient="horizontal", command=tree.xview, style="Horizontal.TScrollbar")
tree.configure(xscrollcommand=scrl_x.set)
scrl_x.pack(side=tk.BOTTOM, fill=tk.X, pady=(8, 0))

results_footer = tk.Frame(results_body, bg=APP_THEME["surface"])
results_footer.grid(row=1, column=0, sticky="ew", pady=(14, 0))
results_footer.grid_columnconfigure(0, weight=1)

table_actions = tk.Frame(results_footer, bg=APP_THEME["surface"])
table_actions.grid(row=0, column=1, sticky="e")

btn_tick_on = make_button(
    table_actions,
    "TICK CHỌN",
    lambda: set_route_pick_for_targets(True),
    APP_THEME["panel_alt"],
    "#334155",
    width=11,
)
btn_tick_on.pack(side=tk.LEFT, padx=(0, 8))

btn_tick_off = make_button(
    table_actions,
    "BỎ TICK",
    lambda: set_route_pick_for_targets(False),
    APP_THEME["panel_alt"],
    "#334155",
    width=10,
)
btn_tick_off.pack(side=tk.LEFT, padx=(0, 10))

btn_clear = make_button(
    table_actions,
    "DỌN BẢNG",
    clear_results,
    APP_THEME["panel_alt"],
    "#334155",
    width=14,
)
btn_clear.pack(side=tk.LEFT, padx=(0, 10))

btn_export = make_button(
    table_actions,
    "XUẤT EXCEL",
    export_to_excel,
    APP_THEME["info"],
    "#0284C7",
    width=14,
)
btn_export.pack(side=tk.LEFT, padx=(0, 10))

btn_open_maps_quick = make_button(
    table_actions,
    "MỞ TUYẾN MAPS",
    open_route_on_google_maps,
    APP_THEME["accent"],
    APP_THEME["accent_hover"],
    width=14,
)
btn_open_maps_quick.pack(side=tk.LEFT)

route_card, route_body = make_card(
    right_col,
    "Sắp xếp theo tuyến cho sales",
    "Tối ưu thứ tự đi để hạn chế nhảy điểm, đi vòng và thuận tuyến thực tế hơn.",
    accent=APP_THEME["warning"],
)
route_card.grid(row=2, column=0, sticky="ew", pady=(0, 14))
route_body.grid_columnconfigure(0, weight=1)
route_body.grid_columnconfigure(1, weight=1)
route_body.grid_columnconfigure(2, weight=1)

field_route_start = tk.Frame(route_body, bg=APP_THEME["surface"])
field_route_start.grid(row=0, column=0, columnspan=2, sticky="ew", padx=(0, 10))
tk.Label(
    field_route_start,
    text="Điểm bắt đầu (tọa độ, link Maps hoặc địa chỉ)",
    font=(FONT_FAMILY, 9, "bold"),
    bg=APP_THEME["surface"],
    fg=APP_THEME["text"],
).pack(anchor="w")
ent_route_start = tk.Entry(field_route_start)
style_entry(ent_route_start, justify="left")
ent_route_start.pack(fill=tk.X, ipady=10, pady=(8, 0))
attach_entry_placeholder(ent_route_start, "Ví dụ: 10.8231,106.6297 hoặc link Google Maps")

field_route_pick = tk.Frame(route_body, bg=APP_THEME["surface"])
field_route_pick.grid(row=0, column=2, sticky="ew")
tk.Label(
    field_route_pick,
    text="Hoặc chọn từ danh sách",
    font=(FONT_FAMILY, 9, "bold"),
    bg=APP_THEME["surface"],
    fg=APP_THEME["text"],
).pack(anchor="w")
cmb_route_start_pick = ttk.Combobox(field_route_pick, state="readonly")
cmb_route_start_pick.pack(fill=tk.X, ipady=6, pady=(8, 0))
btn_refresh_route_points = make_button(
    field_route_pick,
    "LÀM MỚI ĐIỂM",
    refresh_route_source_options,
    APP_THEME["panel_alt"],
    "#334155",
    width=12,
)
btn_refresh_route_points.pack(fill=tk.X, pady=(8, 0))

field_route_sort = tk.Frame(route_body, bg=APP_THEME["surface"])
field_route_sort.grid(row=1, column=0, sticky="ew", pady=(12, 0), padx=(0, 10))
tk.Label(
    field_route_sort,
    text="Kiểu sắp xếp",
    font=(FONT_FAMILY, 9, "bold"),
    bg=APP_THEME["surface"],
    fg=APP_THEME["text"],
).pack(anchor="w")
cmb_route_sort_type = ttk.Combobox(field_route_sort, state="readonly", values=["Gần nhất trước", "Thuận tuyến", "Tối ưu thời gian đi"])
cmb_route_sort_type.pack(fill=tk.X, ipady=6, pady=(8, 0))
cmb_route_sort_type.set("Thuận tuyến")

field_route_optimize = tk.Frame(route_body, bg=APP_THEME["surface"])
field_route_optimize.grid(row=1, column=1, sticky="ew", pady=(12, 0), padx=5)
tk.Label(
    field_route_optimize,
    text="Chế độ tối ưu",
    font=(FONT_FAMILY, 9, "bold"),
    bg=APP_THEME["surface"],
    fg=APP_THEME["text"],
).pack(anchor="w")
cmb_route_optimize = ttk.Combobox(field_route_optimize, state="readonly", values=["Nhanh", "Cân bằng", "Tiết kiệm"])
cmb_route_optimize.pack(fill=tk.X, ipady=6, pady=(8, 0))
cmb_route_optimize.set("Cân bằng")

field_route_scope = tk.Frame(route_body, bg=APP_THEME["surface"])
field_route_scope.grid(row=1, column=2, sticky="ew", pady=(12, 0))
tk.Label(
    field_route_scope,
    text="Phạm vi áp dụng",
    font=(FONT_FAMILY, 9, "bold"),
    bg=APP_THEME["surface"],
    fg=APP_THEME["text"],
).pack(anchor="w")
cmb_route_scope = ttk.Combobox(field_route_scope, state="readonly", values=["Toàn bộ kết quả", "Chỉ các dòng đã chọn"])
cmb_route_scope.pack(fill=tk.X, ipady=6, pady=(8, 0))
cmb_route_scope.set("Toàn bộ kết quả")

actions_route = tk.Frame(route_body, bg=APP_THEME["surface"])
actions_route.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(14, 0))
actions_route.grid_columnconfigure(0, weight=1)
actions_route.grid_columnconfigure(1, weight=1)

btn_route_sort = make_button(
    actions_route,
    "SẮP XẾP TUYẾN",
    sort_route_for_sales,
    APP_THEME["warning"],
    "#D97706",
    width=13,
)
btn_route_sort.grid(row=0, column=0, sticky="ew", padx=(0, 6), pady=(0, 6))

btn_route_preview = make_button(
    actions_route,
    "XEM TRƯỚC TUYẾN",
    preview_route_plan,
    APP_THEME["panel_alt"],
    "#334155",
    width=13,
)
btn_route_preview.grid(row=0, column=1, sticky="ew", padx=(6, 0), pady=(0, 6))

btn_route_export = make_button(
    actions_route,
    "XUẤT THEO TUYẾN",
    export_route_sorted_list,
    APP_THEME["info"],
    "#0284C7",
    width=13,
)
btn_route_export.grid(row=1, column=0, sticky="ew", padx=(0, 6), pady=(6, 0))

btn_route_open_maps = make_button(
    actions_route,
    "MỞ TUYẾN MAPS",
    open_route_on_google_maps,
    APP_THEME["accent"],
    APP_THEME["accent_hover"],
    width=13,
)
btn_route_open_maps.grid(row=1, column=1, sticky="ew", padx=(6, 0), pady=(6, 0))

var_route_group_cluster = tk.BooleanVar(value=False)
chk_route_group_cluster = ttk.Checkbutton(
    route_body,
    text="Nhóm theo cụm tuyến khi xuất file",
    variable=var_route_group_cluster,
    style="Modern.TCheckbutton",
)
chk_route_group_cluster.grid(row=3, column=0, columnspan=3, sticky="w", pady=(12, 0))

route_summary = tk.Frame(
    route_body,
    bg=APP_THEME["panel"],
    highlightbackground=APP_THEME["border"],
    highlightthickness=1,
    bd=0,
)
route_summary.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(12, 0))
route_summary.grid_columnconfigure(1, weight=1)

tk.Label(
    route_summary,
    text="Điểm bắt đầu:",
    font=(FONT_FAMILY, 9, "bold"),
    bg=APP_THEME["panel"],
    fg=APP_THEME["muted"],
).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 4))
lbl_route_start_value = tk.Label(
    route_summary,
    text="Chưa chọn",
    font=(FONT_FAMILY, 9),
    bg=APP_THEME["panel"],
    fg=APP_THEME["text"],
)
lbl_route_start_value.grid(row=0, column=1, sticky="w", padx=8, pady=(10, 4))

tk.Label(
    route_summary,
    text="Thứ tự nên đi:",
    font=(FONT_FAMILY, 9, "bold"),
    bg=APP_THEME["panel"],
    fg=APP_THEME["muted"],
).grid(row=1, column=0, sticky="w", padx=12, pady=4)
lbl_route_order_value = tk.Label(
    route_summary,
    text="0",
    font=(FONT_FAMILY, 9),
    bg=APP_THEME["panel"],
    fg=APP_THEME["text"],
)
lbl_route_order_value.grid(row=1, column=1, sticky="w", padx=8, pady=4)

tk.Label(
    route_summary,
    text="Tổng số điểm:",
    font=(FONT_FAMILY, 9, "bold"),
    bg=APP_THEME["panel"],
    fg=APP_THEME["muted"],
).grid(row=2, column=0, sticky="w", padx=12, pady=4)
lbl_route_total_points_value = tk.Label(
    route_summary,
    text="0",
    font=(FONT_FAMILY, 9),
    bg=APP_THEME["panel"],
    fg=APP_THEME["text"],
)
lbl_route_total_points_value.grid(row=2, column=1, sticky="w", padx=8, pady=4)

tk.Label(
    route_summary,
    text="Tổng quãng đường ước tính:",
    font=(FONT_FAMILY, 9, "bold"),
    bg=APP_THEME["panel"],
    fg=APP_THEME["muted"],
).grid(row=3, column=0, sticky="w", padx=12, pady=(4, 10))
lbl_route_total_distance_value = tk.Label(
    route_summary,
    text="0.00 km",
    font=(FONT_FAMILY, 9),
    bg=APP_THEME["panel"],
    fg=APP_THEME["text"],
)
lbl_route_total_distance_value.grid(row=3, column=1, sticky="w", padx=8, pady=(4, 10))

runtime_card, runtime_body = make_card(
    right_col,
    "Cấu hình vận hành",
    "Thiết lập số luồng, kích thước cửa sổ và chế độ chạy.",
    accent=APP_THEME["warning"],
)
runtime_card.grid(row=0, column=0, sticky="ew", pady=(0, 14))
for col in range(2):
    runtime_body.grid_columnconfigure(col, weight=1)

field_threads = tk.Frame(runtime_body, bg=APP_THEME["surface"])
field_threads.grid(row=0, column=0, sticky="ew", padx=(0, 8))
tk.Label(
    field_threads,
    text="Số luồng",
    font=(FONT_FAMILY, 9, "bold"),
    bg=APP_THEME["surface"],
    fg=APP_THEME["text"],
).pack(anchor="w")
threads_var = tk.IntVar(value=1)
ent_threads = tk.Spinbox(
    field_threads,
    from_=1,
    to=50,
    increment=1,
    wrap=True,
    textvariable=threads_var,
    command=update_runtime_badges,
)
style_spinbox(ent_threads)
ent_threads.pack(fill=tk.X, ipady=10, pady=(8, 0))

tk.Label(
    field_threads,
    text="Chọn nhanh số luồng bằng nút tăng giảm hoặc nhập trực tiếp.",
    font=(FONT_FAMILY, 8),
    bg=APP_THEME["surface"],
    fg=APP_THEME["muted"],
).pack(anchor="w", pady=(6, 0))

field_size = tk.Frame(runtime_body, bg=APP_THEME["surface"])
field_size.grid(row=0, column=1, sticky="ew", padx=(8, 0))
tk.Label(
    field_size,
    text="Kích thước cửa sổ",
    font=(FONT_FAMILY, 9, "bold"),
    bg=APP_THEME["surface"],
    fg=APP_THEME["text"],
).pack(anchor="w")

size_inputs = tk.Frame(field_size, bg=APP_THEME["surface"])
size_inputs.pack(fill=tk.X, pady=(8, 0))
size_inputs.grid_columnconfigure(0, weight=1)
size_inputs.grid_columnconfigure(2, weight=1)

ent_win_w = tk.Entry(size_inputs)
style_entry(ent_win_w, justify="center")
ent_win_w.insert(0, "900")
ent_win_w.grid(row=0, column=0, sticky="ew")

tk.Label(
    size_inputs,
    text="x",
    font=(FONT_FAMILY, 11, "bold"),
    bg=APP_THEME["surface"],
    fg=APP_THEME["muted"],
).grid(row=0, column=1, padx=8)

ent_win_h = tk.Entry(size_inputs)
style_entry(ent_win_h, justify="center")
ent_win_h.insert(0, "500")
ent_win_h.grid(row=0, column=2, sticky="ew")

headless_wrap = tk.Frame(runtime_body, bg=APP_THEME["surface"])
headless_wrap.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(14, 0))
var_headless = tk.BooleanVar(value=False)
chk_headless = ttk.Checkbutton(
    headless_wrap,
    text="Chạy ẩn (headless)",
    variable=var_headless,
    style="Modern.TCheckbutton",
)
chk_headless.pack(anchor="w")

stats_frame = tk.Frame(runtime_body, bg=APP_THEME["surface"])
stats_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(16, 0))
for col in range(2):
    stats_frame.grid_columnconfigure(col, weight=1)

tile_threads, lbl_threads_value = make_stat_tile(stats_frame, "Luồng", "1", accent=APP_THEME["warning"])
tile_threads.grid(row=0, column=0, sticky="ew", padx=(0, 8), pady=(0, 10))

tile_target, lbl_target_value = make_stat_tile(stats_frame, "Mục tiêu", "100", accent=APP_THEME["info"])
tile_target.grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=(0, 10))

tile_proxy, lbl_proxy_value = make_stat_tile(stats_frame, "Proxy", "0", accent=APP_THEME["violet"])
tile_proxy.grid(row=1, column=0, sticky="ew", padx=(0, 8))

tile_mode, lbl_mode_value = make_stat_tile(stats_frame, "Chế độ", "Hiện", accent=APP_THEME["accent"])
tile_mode.grid(row=1, column=1, sticky="ew", padx=(8, 0))

lbl_window_note = tk.Label(
    runtime_body,
    text="Kích thước trình duyệt: 900 x 500 px",
    font=(FONT_FAMILY, 9),
    bg=APP_THEME["surface"],
    fg=APP_THEME["muted"],
)
lbl_window_note.grid(row=3, column=0, columnspan=2, sticky="w", pady=(12, 0))

proxy_card, proxy_body = make_card(
    right_col,
    "Danh sách proxy",
    "Mỗi dòng một proxy. Để trống nếu bạn muốn chạy bằng mạng hiện tại.",
    accent=APP_THEME["violet"],
)
proxy_card.grid(row=1, column=0, sticky="nsew", pady=(0, 14))
proxy_body.grid_rowconfigure(1, weight=1)
proxy_body.grid_columnconfigure(0, weight=1)

proxy_toolbar = tk.Frame(proxy_body, bg=APP_THEME["surface"])
proxy_toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 10))
proxy_toolbar.grid_columnconfigure(0, weight=1)

tk.Label(
    proxy_toolbar,
    text="Ô nhập proxy",
    font=(FONT_FAMILY, 9, "bold"),
    bg=APP_THEME["surface"],
    fg=APP_THEME["text"],
).grid(row=0, column=0, sticky="w")

proxy_actions = tk.Frame(proxy_toolbar, bg=APP_THEME["surface"])
proxy_actions.grid(row=0, column=1, sticky="e")

btn_proxy_paste = make_button(
    proxy_actions,
    "DÁN",
    paste_proxies_from_clipboard,
    APP_THEME["panel_alt"],
    "#334155",
    width=8,
)
btn_proxy_paste.pack(side=tk.LEFT, padx=(0, 8))

btn_proxy_file = make_button(
    proxy_actions,
    "NẠP FILE",
    import_proxy_file,
    APP_THEME["violet"],
    "#7C3AED",
    width=10,
)
btn_proxy_file.pack(side=tk.LEFT, padx=(0, 8))

btn_proxy_check = make_button(
    proxy_actions,
    "KIỂM TRA IP",
    check_proxy_ip,
    APP_THEME["info"],
    "#0284C7",
    width=12,
)
btn_proxy_check.pack(side=tk.LEFT, padx=(0, 8))

btn_proxy_clear = make_button(
    proxy_actions,
    "XÓA",
    clear_proxy_box,
    APP_THEME["danger"],
    APP_THEME["danger_hover"],
    width=8,
)
btn_proxy_clear.pack(side=tk.LEFT)

btn_reset_profile = make_button(
    proxy_actions,
    "RESET PROFILE",
    reset_profiles,
    APP_THEME["panel_alt"],
    "#334155",
    width=14,
)
btn_reset_profile.pack(side=tk.LEFT, padx=(8, 0))

proxy_frame = tk.Frame(proxy_body, bg=APP_THEME["surface"])
proxy_frame.grid(row=1, column=0, sticky="nsew")
proxy_frame.grid_rowconfigure(0, weight=1)
proxy_frame.grid_columnconfigure(0, weight=1)

txt_px = tk.Text(proxy_frame, height=12)
style_text_widget(txt_px)
txt_px.configure(wrap=tk.NONE)
txt_px.grid(row=0, column=0, sticky="nsew")

tk.Label(
    proxy_body,
    text="Nhập mỗi proxy trên một dòng, ví dụ: http://127.0.0.1:8080",
    font=(FONT_FAMILY, 8),
    bg=APP_THEME["surface"],
    fg=APP_THEME["muted"],
).grid(row=2, column=0, sticky="w", pady=(8, 0))

proxy_scroll = ttk.Scrollbar(proxy_frame, orient="vertical", command=txt_px.yview, style="Vertical.TScrollbar")
proxy_scroll.grid(row=0, column=1, sticky="ns")

proxy_scroll_x = ttk.Scrollbar(proxy_frame, orient="horizontal", command=txt_px.xview, style="Horizontal.TScrollbar")
proxy_scroll_x.grid(row=1, column=0, sticky="ew", pady=(8, 0))

txt_px.configure(yscrollcommand=proxy_scroll.set, xscrollcommand=proxy_scroll_x.set)

lbl_proxy_check_result = tk.Label(
    proxy_body,
    text="Chưa kiểm tra IP direct/proxy.",
    font=(FONT_FAMILY, 8),
    bg=APP_THEME["surface"],
    fg=APP_THEME["muted"],
    justify="left",
    wraplength=360,
)
lbl_proxy_check_result.grid(row=3, column=0, sticky="w", pady=(10, 0))

action_card, action_body = make_card(
    right_col,
    "Điều khiển",
    "Bắt đầu, dừng và theo dõi trạng thái phiên quét hiện tại.",
    accent=APP_THEME["accent"],
)
action_card.grid(row=3, column=0, sticky="ew")

action_buttons = tk.Frame(action_body, bg=APP_THEME["surface"])
action_buttons.pack(fill=tk.X)
action_buttons.grid_columnconfigure(0, weight=1)
action_buttons.grid_columnconfigure(1, weight=1)

btn_run = make_button(
    action_buttons,
    "BẮT ĐẦU QUÉT",
    start_app,
    APP_THEME["accent"],
    APP_THEME["accent_hover"],
    width=15,
)
btn_run.configure(pady=10)
btn_run.grid(row=0, column=0, sticky="ew", padx=(0, 8))

btn_stop = make_button(
    action_buttons,
    "DỪNG NGAY",
    stop_app,
    APP_THEME["danger"],
    APP_THEME["danger_hover"],
    width=15,
)
btn_stop.configure(pady=10)
btn_stop.grid(row=0, column=1, sticky="ew", padx=(8, 0))
btn_stop.config(state=tk.DISABLED)

status_panel = tk.Frame(
    action_body,
    bg=APP_THEME["panel"],
    highlightbackground=APP_THEME["border"],
    highlightthickness=1,
    bd=0,
)
status_panel.pack(fill=tk.X, pady=(14, 10))

tk.Label(
    status_panel,
    text="Trạng thái hiện tại",
    font=(FONT_FAMILY, 9, "bold"),
    bg=APP_THEME["panel"],
    fg=APP_THEME["muted"],
).pack(anchor="w", padx=14, pady=(12, 4))

lbl_stt = tk.Label(
    status_panel,
    text="Sẵn sàng để quét dữ liệu mới.",
    font=(FONT_FAMILY, 10),
    bg=APP_THEME["panel"],
    fg=APP_THEME["muted"],
    justify="left",
    wraplength=320,
)
lbl_stt.pack(anchor="w", padx=14, pady=(0, 12))

tk.Label(
    action_body,
    text="Dữ liệu sẽ được cập nhật trực tiếp vào bảng bên trái và có thể xuất ra Excel ngay sau khi hoàn tất.",
    font=(FONT_FAMILY, 9),
    bg=APP_THEME["surface"],
    fg=APP_THEME["muted"],
    justify="left",
    wraplength=340,
).pack(anchor="w")

for widget in (ent_threads, ent_lim, ent_win_w, ent_win_h, ent_lat, ent_lng, ent_zoom, ent_route_start):
    widget.bind("<KeyRelease>", update_runtime_badges)

attach_entry_placeholder(ent_lat, "10.8231")
attach_entry_placeholder(ent_lng, "106.6297")
for coordinate_entry in (ent_lat, ent_lng):
    coordinate_entry.bind("<Control-v>", handle_coordinate_paste, add="+")
    coordinate_entry.bind("<<Paste>>", handle_coordinate_paste, add="+")

tree.bind("<Button-1>", handle_tree_click_toggle, add="+")
txt_px.bind("<KeyRelease>", update_runtime_badges)
txt_px.bind("<<Paste>>", lambda _event: root.after(10, update_runtime_badges))
txt_px.bind("<<Cut>>", lambda _event: root.after(10, update_runtime_badges))
var_headless.trace_add("write", lambda *_args: update_runtime_badges())
threads_var.trace_add("write", lambda *_args: update_runtime_badges())
var_route_group_cluster.trace_add("write", lambda *_args: update_runtime_badges())
cmb_route_start_pick.bind("<<ComboboxSelected>>", lambda _event: update_runtime_badges())
cmb_route_sort_type.bind("<<ComboboxSelected>>", lambda _event: update_runtime_badges())
cmb_route_optimize.bind("<<ComboboxSelected>>", lambda _event: update_runtime_badges())
cmb_route_scope.bind("<<ComboboxSelected>>", lambda _event: update_runtime_badges())

build_tax_lookup_tab(tax_tab)
refresh_route_source_options()
apply_last_config(load_last_config())
root.after_idle(lambda: (_bind_right_panel_mousewheel(right_col), _sync_right_panel_scroll_region()))
update_runtime_badges()
set_runtime_status("Sẵn sàng để quét dữ liệu mới.", "success", "SẴN SÀNG")
ent_loc.focus_set()
root.protocol("WM_DELETE_WINDOW", handle_main_close)

lbl_product_credit = tk.Label(
    root,
    text="Product by Khương Bình",
    font=(FONT_FAMILY, 8),
    bg=APP_THEME["bg"],
    fg=APP_THEME["muted"],
)
lbl_product_credit.place(relx=1.0, rely=1.0, x=-12, y=-8, anchor="se")

root.mainloop()


