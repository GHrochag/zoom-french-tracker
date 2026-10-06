#!/usr/bin/env python3
"""
Zoom French Tracker — Menu bar app for macOS.
Automatically tracks Zoom sessions and deducts from a purchased-hours balance.

Requires: Python 3.9+, rumps
"""

import subprocess
import sys
import os
import json
import calendar
from datetime import datetime
from pathlib import Path

try:
    import rumps
    import objc
    from AppKit import (
        NSWindow, NSWindowStyleMaskTitled, NSWindowStyleMaskClosable,
        NSWindowStyleMaskResizable, NSBackingStoreBuffered,
        NSFloatingWindowLevel, NSWindowCollectionBehaviorCanJoinAllSpaces,
        NSWindowCollectionBehaviorStationary,
        NSScreen, NSApp, NSApplicationActivationPolicyAccessory,
    )
    from WebKit import WKWebView, WKWebViewConfiguration, WKUserContentController
    from Foundation import NSURLRequest, NSURL
    WEBKIT_AVAILABLE = True
except ImportError as e:
    WEBKIT_AVAILABLE = False

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db
from session_tracker import compute_duration, format_balance


# ═══════════════════════════════════════════════════════════════
#  ZOOM DETECTION
# ═══════════════════════════════════════════════════════════════

def is_zoom_running() -> bool:
    try:
        result = subprocess.run(
            ["pgrep", "-ix", "zoom.us"],
            capture_output=True, text=True, timeout=3,
        )
        if result.returncode == 0:
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    try:
        result = subprocess.run(
            ["ps", "-eo", "comm"],
            capture_output=True, text=True, timeout=3,
        )
        for line in result.stdout.splitlines():
            if "zoom.us" in line.lower():
                return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return False


# ═══════════════════════════════════════════════════════════════
#  HTML CALENDAR (embedded in WebKit popup)
# ═══════════════════════════════════════════════════════════════

MESES = [
    "", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]
DIAS_SEMANA = ["Lu", "Ma", "Mi", "Ju", "Vi", "Sá", "Do"]

CSS = """
* { margin:0; padding:0; box-sizing:border-box; }
body {
    font-family: -apple-system, "Helvetica Neue", sans-serif;
    background: #1e1e2e; color: #cdd6f4; padding: 14px;
    -webkit-user-select: none; user-select: none;
    max-width: 420px; margin: 0 auto;
}
.balance-row {
    display: flex; gap: 10px; margin-bottom: 12px;
}
.b-card {
    background: #313244; border-radius: 8px; padding: 10px 14px;
    flex: 1; text-align: center;
}
.b-card .label { font-size: 10px; color: #a6adc8; text-transform: uppercase; }
.b-card .value { font-size: 22px; font-weight: 700; margin-top: 2px; }
.b-card .value.g { color: #a6e3a1; }
.b-card .value.y { color: #f9e2af; }
.b-card .value.r { color: #f38ba8; }
.nav {
    display: flex; align-items: center; gap: 10px;
    margin-bottom: 10px; font-size: 16px; font-weight: 700;
}
.nav button {
    background: #313244; border: none; color: #89b4fa;
    font-size: 15px; padding: 6px 12px; border-radius: 6px; cursor: pointer;
}
.nav button:hover { background: #45475a; }
.nav span { flex: 1; text-align: center; }
.cal { display: grid; grid-template-columns: repeat(7, 1fr); gap: 1px; margin-bottom: 10px; }
.cal .dh { text-align: center; font-size: 10px; font-weight: 600; color: #89b4fa; padding: 4px 0; }
.cal .day {
    aspect-ratio: 1; display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    border-radius: 5px; font-size: 13px; font-weight: 500;
    background: #181825; color: #585b70; min-height: 36px;
}
.cal .day.cm { color: #cdd6f4; }
.cal .day.td { outline: 2px solid #f9e2af; outline-offset: -2px; }
.cal .day.hh { font-weight: 700; }
.cal .day.l0 { }  /* no hours */
.cal .day.l1 { background: #1a3a2a; color: #a6e3a1; }
.cal .day.l2 { background: #1a3a3a; color: #94e2d5; }
.cal .day.l3 { background: #1a2a4a; color: #74c7ec; }
.cal .day.l4 { background: #2a1a4a; color: #89b4fa; }
.cal .day .hrs { font-size: 9px; margin-top: 1px; }
.legend { display: flex; gap: 12px; justify-content: center; margin-bottom: 10px; font-size: 10px; flex-wrap: wrap; }
.legend i { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 2px; vertical-align: middle; }
.section-title { font-size: 13px; font-weight: 700; margin-bottom: 6px; color: #89b4fa; }
.hist-table { width: 100%; border-collapse: collapse; font-size: 11px; }
.hist-table th { text-align: left; color: #a6adc8; padding: 4px 8px; font-size: 9px; text-transform: uppercase; }
.hist-table td { padding: 5px 8px; border-top: 1px solid #1e1e2e; }
.hist-table tr:nth-child(even) td { background: #181825; }
.empty { text-align: center; color: #585b70; padding: 16px; font-size: 12px; }
.month-total { text-align: center; background: #313244; padding: 8px; border-radius: 6px; margin-bottom: 10px; }
.month-total .lbl { font-size: 10px; color: #a6adc8; }
.month-total .val { font-size: 18px; font-weight: 700; color: #89b4fa; }
"""


def _day_level(hours: float) -> int:
    if hours >= 2.0: return 4
    if hours >= 1.5: return 3
    if hours >= 1.0: return 2
    if hours >= 0.5: return 1
    return 0


def _bal_color(balance: float) -> str:
    if balance > 5: return "g"
    if balance > 1: return "y"
    return "r"


def build_html(year: int, month: int) -> str:
    daily = db.get_daily_hours(year, month)
    sessions = db.get_month_sessions(year, month)
    balance = db.get_balance()
    total_purchased = db.get_total_credits()
    total_consumed = db.get_total_consumed()
    month_consumed = sum(daily.values())

    today = datetime.now()
    is_current = (today.year == year and today.month == month)
    today_day = today.day if is_current else None

    cal_obj = calendar.Calendar(firstweekday=0)
    weeks = cal_obj.monthdayscalendar(year, month)

    cal_cells = ""
    for d in DIAS_SEMANA:
        cal_cells += f'<div class="dh">{d}</div>'
    for week in weeks:
        for day in week:
            if day == 0:
                cal_cells += '<div class="day"></div>'
            else:
                h = daily.get(day, 0)
                lvl = _day_level(h)
                cls = f"day cm l{lvl}"
                if day == today_day:
                    cls += " td"
                if h > 0:
                    cls += " hh"
                inner = f"<span>{day}</span>"
                if h > 0:
                    inner += f'<span class="hrs">{format_balance(h)}</span>'
                cal_cells += f'<div class="{cls}">{inner}</div>'

    legend = ""
    for lvl, label, color in [
        (1, "0.5h", "#a6e3a1"), (2, "1.0h", "#94e2d5"),
        (3, "1.5h", "#74c7ec"), (4, "2.0h", "#89b4fa"),
    ]:
        legend += f'<span><i style="background:{color}"></i>{label}</span>'

    hist = ""
    if sessions:
        hist = '<table class="hist-table"><thead><tr><th>Fecha</th><th>Ini</th><th>Fin</th><th>Hrs</th></tr></thead><tbody>'
        for s in sessions:
            sd = datetime.strptime(s["start_time"], "%Y-%m-%d %H:%M:%S")
            ed = datetime.strptime(s["end_time"], "%Y-%m-%d %H:%M:%S") if s["end_time"] else None
            hist += (
                f'<tr><td>{sd.strftime("%d %b")}</td>'
                f'<td>{sd.strftime("%H:%M")}</td>'
                f'<td>{ed.strftime("%H:%M") if ed else "--"}</td>'
                f'<td><strong>{format_balance(s["rounded_hours"])}</strong></td></tr>'
            )
        hist += "</tbody></table>"
    else:
        hist = '<div class="empty">Sin sesiones este mes</div>'

    prev_m = month - 1 if month > 1 else 12
    prev_y = year if month > 1 else year - 1
    next_m = month + 1 if month < 12 else 1
    next_y = year if month < 12 else year + 1

    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>{CSS}</style></head><body>

<div class="balance-row">
    <div class="b-card"><div class="label">Saldo</div>
        <div class="value {_bal_color(balance)}">{format_balance(balance)}</div></div>
    <div class="b-card"><div class="label">Comprado</div>
        <div class="value" style="color:#89b4fa">{format_balance(total_purchased)}</div></div>
    <div class="b-card"><div class="label">Usado</div>
        <div class="value" style="color:#fab387">{format_balance(total_consumed)}</div></div>
</div>

<div class="nav">
    <button onclick="nav({prev_y},{prev_m},event)">◀</button>
    <span>{MESES[month]} {year}</span>
    <button onclick="nav({next_y},{next_m},event)">▶</button>
</div>

<div class="month-total"><div class="lbl">Este mes</div>
    <div class="val">{format_balance(month_consumed)}</div></div>

<div class="cal">{cal_cells}</div>

<div class="legend">{legend}</div>

<div class="section-title">📋 Historial</div>
{hist}

<script>
function nav(y,m,e) {{
    e.preventDefault(); e.stopPropagation();
    window.webkit.messageHandlers.navigate.postMessage({{year:y,month:m}});
}}
</script>
</body></html>"""


# ═══════════════════════════════════════════════════════════════
#  NATIVE POPUP (NSWindow + WKWebView)
# ═══════════════════════════════════════════════════════════════

if WEBKIT_AVAILABLE:

    class NavHandler(objc.lookUpClass("NSObject")):
        """Handle navigation messages from the web view."""

        def initWithApp_(self, app):
            self = objc.super(NavHandler, self).init()
            if self is None:
                return None
            self._app = app
            return self

        @objc.signature(b"v@:@@")
        def userContentController_didReceiveScriptMessage_(
            self, controller, message
        ):
            body = message.body()
            if isinstance(body, dict) and "year" in body:
                objc.performSelectorOnMainThread_withObject_waitUntilDone_(
                    self, "_navigate:", body, False
                )

        def _navigate_(self, info):
            year = int(info["year"])
            month = int(info["month"])
            self._app._reload_webview(year, month)

    def _create_popup(app):
        """Create a floating NSWindow with WKWebView."""
        # Window config
        mask = NSWindowStyleMaskTitled | NSWindowStyleMaskClosable | NSWindowStyleMaskResizable
        window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            ((0, 0), (460, 540)), mask, NSBackingStoreBuffered, False
        )
        window.setTitle_("🇫🇷 Zoom French Tracker")
        window.setLevel_(NSFloatingWindowLevel)
        window.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces | NSWindowCollectionBehaviorStationary
        )
        window.center()

        # WebView
        config = WKWebViewConfiguration.alloc().init()
        controller = WKUserContentController.alloc().init()
        handler = NavHandler.alloc().initWithApp_(app)
        controller.addScriptMessageHandler_name_(handler, "navigate")
        config.setUserContentController_(controller)

        webview = WKWebView.alloc().initWithFrame_configuration_(
            ((0, 0), (460, 500)), config
        )
        window.contentView().addSubview_(webview)

        return window, webview


# ═══════════════════════════════════════════════════════════════
#  MAIN APP
# ═══════════════════════════════════════════════════════════════

class ZoomFrenchTracker(rumps.App):
    def __init__(self):
        super().__init__(name="ZoomFrenchTracker", title="🇫🇷 --h")
        self.zoom_running = False
        self.active_session_id = None
        self._alert_2h_fired = False
        self._alert_1h_fired = False
        self._popup_window = None
        self._webview = None
        self._nav_handler = None

        db.init_db()
        self._update_display()
        self._build_menu()

        self.timer = rumps.Timer(self._tick, 5)
        self.timer.start()

        active = db.get_active_session()
        if active:
            db.cancel_session(active["id"])

    def _build_menu(self):
        self.menu.clear()
        self.menu.update([
            rumps.MenuItem("➕ Agregar horas…", callback=self._add_hours),
            rumps.MenuItem("📅 Calendario", callback=self._show_popup),
            None,
            rumps.MenuItem("❌ Salir", callback=self._quit),
        ])

    def _tick(self, _):
        try:
            zoom_now = is_zoom_running()
            if zoom_now and not self.zoom_running:
                self._on_zoom_started()
            elif not zoom_now and self.zoom_running:
                self._on_zoom_stopped()
            self.zoom_running = zoom_now
            self._update_display()
        except Exception:
            pass

    def _on_zoom_started(self):
        active = db.get_active_session()
        if active:
            db.cancel_session(active["id"])
        self.active_session_id = db.start_session(datetime.now())

    def _on_zoom_stopped(self):
        if self.active_session_id is None:
            return
        active = db.get_active_session()
        if active is None or active["id"] != self.active_session_id:
            self.active_session_id = None
            return
        end_time = datetime.now()
        start_time = datetime.strptime(active["start_time"], "%Y-%m-%d %H:%M:%S")
        minutes, rounded = compute_duration(start_time, end_time)
        if rounded == 0:
            db.cancel_session(active["id"])
        else:
            db.end_session(active["id"], end_time, minutes, rounded)
            self._check_alerts()
        self.active_session_id = None
        self._update_display()
        # Refresh popup if open
        if self._popup_window and self._popup_window.isVisible():
            now = datetime.now()
            self._load_html(now.year, now.month)

    def _update_display(self):
        balance = db.get_balance()
        self.title = f"⚠️ {format_balance(balance)}" if balance <= 1 else f"🇫🇷 {format_balance(balance)}"

    def _check_alerts(self):
        balance = db.get_balance()
        if balance <= 1.0 and not self._alert_1h_fired:
            rumps.notification(
                title="⚠️ Zoom French Tracker",
                subtitle="¡Hora de comprar!",
                message="Solo te queda 1 hora. Compra más horas.",
            )
            self._alert_1h_fired = True
            self._alert_2h_fired = True
        elif balance <= 2.0 and not self._alert_2h_fired:
            rumps.notification(
                title="⚠️ Zoom French Tracker",
                subtitle="Horas bajas",
                message="Te quedan 2 horas. Compra más pronto.",
            )
            self._alert_2h_fired = True

    def _add_hours(self, _):
        response = rumps.Window(
            title="Agregar horas compradas",
            message="¿Cuántas horas compraste?",
            default_text="",
            ok="Agregar",
            cancel="Cancelar",
            dimensions=(200, 40),
        ).run()

        if response.clicked and response.text:
            try:
                amount = float(response.text.strip())
                if amount <= 0:
                    rumps.alert("Error", "La cantidad debe ser mayor a 0.")
                    return
                if amount > 200:
                    rumps.alert("Error", "¿200+ horas? Verifica la cantidad.")
                    return
                db.add_credits(amount, note="Compra manual")
                self._update_display()
                self._alert_2h_fired = False
                self._alert_1h_fired = False
                # Refresh popup
                if self._popup_window and self._popup_window.isVisible():
                    now = datetime.now()
                    self._load_html(now.year, now.month)
                rumps.notification(
                    title="✅ Horas agregadas",
                    subtitle="",
                    message=f"Se agregaron {format_balance(amount)}. "
                    f"Saldo: {format_balance(db.get_balance())}",
                )
            except ValueError:
                rumps.alert("Error", "Ingresa un número válido (ej: 38).")

    def _show_popup(self, _):
        """Open the native calendar popup."""
        if not WEBKIT_AVAILABLE:
            rumps.alert("Error", "WebKit no disponible.")
            return

        if self._popup_window and self._popup_window.isVisible():
            self._popup_window.makeKeyAndOrderFront_(None)
            NSApp.activateIgnoringOtherApps_(True)
            return

        self._popup_window, self._webview = _create_popup(self)
        now = datetime.now()
        self._load_html(now.year, now.month)
        self._popup_window.makeKeyAndOrderFront_(None)
        NSApp.activateIgnoringOtherApps_(True)

    def _load_html(self, year, month):
        """Load calendar HTML into the web view."""
        if self._webview is None:
            return
        html = build_html(year, month)
        self._webview.loadHTMLString_baseURL_(html, None)

    def _reload_webview(self, year, month):
        """Called from JavaScript when user navigates months."""
        self._load_html(year, month)

    def _quit(self, _):
        if self._popup_window:
            self._popup_window.close()
        rumps.quit_application()


if __name__ == "__main__":
    ZoomFrenchTracker().run()
