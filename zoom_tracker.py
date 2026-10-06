#!/usr/bin/env python3
"""
Zoom French Tracker — Menu bar app for macOS.
Tracks Zoom meetings via CptHost process detection.
Pure WebKit calendar — the one that looked good.
"""

import subprocess
import sys
import os
import json
import calendar
from datetime import datetime
from pathlib import Path

import rumps

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db
from session_tracker import compute_duration, format_balance


# ═══════════════════════════════════════════════════════════════
#  ZOOM MEETING DETECTION
# ═══════════════════════════════════════════════════════════════

def is_in_meeting():
    """Check if a Zoom meeting is active via CptHost process."""
    try:
        result = subprocess.run(
            ["pgrep", "-x", "CptHost"],
            capture_output=True, text=True, timeout=3,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    try:
        result = subprocess.run(
            ["ps", "-eo", "comm"],
            capture_output=True, text=True, timeout=3,
        )
        for line in result.stdout.splitlines():
            if line.strip() == "CptHost":
                return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return False


# ═══════════════════════════════════════════════════════════════
#  WEBKIT CALENDAR WINDOW
# ═══════════════════════════════════════════════════════════════

MESES = [
    "", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]
DIAS_SEMANA = ["Lu", "Ma", "Mi", "Ju", "Vi", "Sá", "Do"]

CSS = """
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,Helvetica,sans-serif;background:#1e1e2e;color:#cdd6f4;padding:16px;-webkit-user-select:none;user-select:none}
.balance-row{display:flex;gap:10px;margin-bottom:14px}
.balance-row .card{flex:1;background:#313244;border-radius:10px;padding:12px 10px;text-align:center}
.balance-row .card .lbl{font-size:10px;color:#a6adc8;text-transform:uppercase;letter-spacing:.5px}
.balance-row .card .val{font-size:22px;font-weight:700;margin-top:2px}
.month-head{display:flex;align-items:center;justify-content:center;gap:14px;margin-bottom:14px}
.month-head .ttl{font-size:16px;font-weight:700;min-width:140px;text-align:center}
.month-head button{background:#45475a;border:none;color:#89b4fa;font-size:14px;padding:5px 14px;border-radius:6px;cursor:pointer}
.month-head button:hover{background:#585b70}
.cal{display:grid;grid-template-columns:repeat(7,1fr);gap:2px;text-align:center;margin-bottom:14px}
.cal .dh{font-size:10px;color:#89b4fa;padding:4px 0;font-weight:600}
.cal .day{aspect-ratio:1;display:flex;flex-direction:column;align-items:center;justify-content:center;border-radius:8px;font-size:13px;font-weight:600}
.cal .day.off{background:transparent}
.cal .day.cm{color:#cdd6f4;cursor:pointer;background:#181825}
.cal .day.cm:hover{filter:brightness(1.3)}
.cal .day.td{outline:2px solid #f9e2af;outline-offset:-2px}
.cal .day.lv1{background:#1a3a2a;color:#a6e3a1}
.cal .day.lv2{background:#1a3a3a;color:#94e2d5}
.cal .day.lv3{background:#1a2a4a;color:#89dceb}
.cal .day.lv4{background:#2a1a4a;color:#b4befe}
.cal .day .sm{font-size:8px;margin-top:-2px;opacity:.8}
.hist-title{font-size:13px;font-weight:700;color:#89b4fa;margin-bottom:6px}
.hist-table{width:100%;border-collapse:collapse;font-size:11px}
.hist-table th{color:#a6adc8;text-align:left;padding:4px 6px;font-weight:500;border-bottom:1px solid #313244}
.hist-table td{padding:4px 6px}
.hist-table tr:nth-child(even){background:#181825}
.day-detail{margin-top:12px;padding:10px;background:#313244;border-radius:8px;display:none}
.day-detail.visible{display:block}
.day-detail .dd-title{font-size:12px;font-weight:700;color:#89b4fa;margin-bottom:6px}
.day-detail .dd-row{font-size:11px;padding:2px 0;color:#cdd6f4}
.empty{text-align:center;color:#585b70;font-size:10px;padding:10px}
.month-usage{text-align:center;font-size:10px;color:#a6adc8;margin-top:10px}
"""


def _day_level(hours):
    if hours >= 2.0: return 4
    if hours >= 1.5: return 3
    if hours >= 1.0: return 2
    if hours >= 0.5: return 1
    return 0


def build_html(year, month):
    """Generate the dark-themed HTML calendar."""
    balance = db.get_balance()
    purchased = db.get_total_credits()
    consumed = db.get_total_consumed()
    daily = db.get_daily_hours(year, month)
    sessions = db.get_month_sessions(year, month)
    month_consumed = sum(daily.values())

    # Card colors
    bal_clr = "#a6e3a1" if balance > 5 else ("#f9e2af" if balance > 1 else "#f38ba8")

    # Calendar grid
    cal = calendar.Calendar(firstweekday=0)
    weeks = cal.monthdayscalendar(year, month)
    today = datetime.now()
    is_current = (today.year == year and today.month == month)
    today_day = today.day if is_current else None

    cal_cells = ""
    for d in DIAS_SEMANA:
        cal_cells += f'<div class="dh">{d}</div>'
    for week in weeks:
        for day in week:
            if day == 0:
                cal_cells += '<div class="day off"></div>'
            else:
                h = daily.get(day, 0)
                lvl = _day_level(h)
                cls = f"cm lv{lvl}" if lvl > 0 else "cm"
                if day == today_day:
                    cls += " td"
                sub = f'<div class="sm">{format_balance(h)}</div>' if h > 0 else ""
                cal_cells += f'<div class="day {cls}" onclick="showDay({year},{month},{day})">{day}{sub}</div>'

    # Sessions JSON for JS
    sessions_json = []
    for s in sessions:
        sd = datetime.strptime(s["start_time"], "%Y-%m-%d %H:%M:%S")
        ed = datetime.strptime(s["end_time"], "%Y-%m-%d %H:%M:%S") if s["end_time"] else None
        sessions_json.append({
            "day": sd.day,
            "start": sd.strftime("%H:%M"),
            "end": ed.strftime("%H:%M") if ed else "--",
            "hours": format_balance(s["rounded_hours"]),
            "raw": s["rounded_hours"],
        })

    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>{CSS}</style></head><body>

<div class="balance-row">
  <div class="card"><div class="lbl">Saldo</div><div class="val" style="color:{bal_clr}">{format_balance(balance)}</div></div>
  <div class="card"><div class="lbl">Comprado</div><div class="val" style="color:#89b4fa">{format_balance(purchased)}</div></div>
  <div class="card"><div class="lbl">Usado</div><div class="val" style="color:#fab387">{format_balance(consumed)}</div></div>
</div>

<div class="month-head">
  <button onclick="nav({year},{month-1 if month>1 else 12},{year if month>1 else year-1})">◀</button>
  <div class="ttl">{MESES[month]} {year}</div>
  <button onclick="nav({year},{month+1 if month<12 else 1},{year if month<12 else year+1})">▶</button>
</div>

<div class="cal">{cal_cells}</div>

<div class="month-usage">Este mes: {format_balance(month_consumed)}</div>

<div class="day-detail" id="dayDetail">
  <div class="dd-title" id="ddTitle"></div>
  <div id="ddContent"></div>
</div>

<div class="hist-title">📋 Historial</div>
<table class="hist-table"><thead><tr><th>Fecha</th><th>Ini</th><th>Fin</th><th>Hrs</th></tr></thead><tbody>
{"".join(
    f'<tr><td>{sd.strftime("%d %b")}</td><td>{sd.strftime("%H:%M")}</td><td>{ed.strftime("%H:%M") if ed else "--"}</td><td>{format_balance(s["rounded_hours"])}</td></tr>'
    for s in sessions
    for sd in [datetime.strptime(s["start_time"], "%Y-%m-%d %H:%M:%S")]
    for ed in [datetime.strptime(s["end_time"], "%Y-%m-%d %H:%M:%S") if s["end_time"] else None]
) if sessions else '<tr><td colspan="4" class="empty">Sin sesiones este mes</td></tr>'}
</tbody></table>

<script>
var SESSIONS = {json.dumps(sessions_json)};
var MESES = {json.dumps(MESES)};
function nav(y,m){window.webkit.messageHandlers.calNav.postMessage({{year:y,month:m}})}
function showDay(y,m,d){{
  var dd=document.getElementById("dayDetail");
  var dt=document.getElementById("ddTitle");
  var dc=document.getElementById("ddContent");
  var ms=MESES[m];
  dt.textContent=d+" "+ms+" "+y;
  var ss=SESSIONS.filter(function(s){{return s.day==d}});
  if(ss.length==0){{dc.innerHTML='<div class="empty">Sin sesiones este día</div>'}}
  else{{dc.innerHTML=ss.map(function(s){{return '<div class="dd-row">'+s.start+' → '+s.end+' &nbsp;&nbsp;'+s.hours+'</div>'}}).join("")}}
  dd.classList.add("visible")
}}
</script>
</body></html>"""


class CalendarWindow:
    """Native window with WKWebView showing the calendar."""

    def __init__(self, app):
        self._app = app

        import objc
        from Foundation import NSURL, NSURLRequest
        from AppKit import (
            NSWindow, NSBackingStoreBuffered, NSFloatingWindowLevel,
        )

        try:
            from WebKit import WKWebView, WKWebViewConfiguration, WKUserContentController, WKScriptMessage
        except ImportError:
            # Fallback: load WebKit framework manually
            from Foundation import NSBundle
            bundle = NSBundle.bundleWithPath_('/System/Library/Frameworks/WebKit.framework')
            if not bundle or not bundle.load():
                raise RuntimeError("Cannot load WebKit.framework")
            WKWebView = objc.lookUpClass('WKWebView')
            WKWebViewConfiguration = objc.lookUpClass('WKWebViewConfiguration')
            WKUserContentController = objc.lookUpClass('WKUserContentController')
            WKScriptMessage = objc.lookUpClass('WKScriptMessage')

        # Create NavHandler
        handler_cls = type('NavHandler', (objc.lookUpClass('NSObject'),), {})
        objc.classAddMethods(handler_cls, [
            objc.selector(
                lambda self, cmd, controller, message: self._handle_msg(message),
                signature=b'v@:@@',
                selector=b'userContentController:didReceiveScriptMessage:',
            ),
        ])

        def init_handler(inner_self):
            inner_self = objc.super(handler_cls, inner_self).init()
            inner_self._app = app
            return inner_self
        handler_cls.init = init_handler

        def handle_msg(inner_self, message):
            try:
                body = message.body()
                app._load_html(int(body["year"]), int(body["month"]))
            except Exception:
                pass
        handler_cls._handle_msg = handle_msg

        self._handler = handler_cls.alloc().init()

        config = WKWebViewConfiguration.alloc().init()
        controller = WKUserContentController.alloc().init()
        controller.addScriptMessageHandler_name_(self._handler, "calNav")
        config.setUserContentController_(controller)

        mask = 1 | 2 | 8
        self.win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            ((0, 0), (420, 600)), mask, NSBackingStoreBuffered, False
        )
        self.win.setTitle_("🇫🇷 Zoom French Tracker")
        self.win.setLevel_(NSFloatingWindowLevel)
        self.win.setReleasedWhenClosed_(False)
        self.win.center()

        rect = self.win.contentView().bounds()
        self._webview = WKWebView.alloc().initWithFrame_configuration_(rect, config)
        self.win.contentView().addSubview_(self._webview)
        self._webview.setAutoresizingMask_(18)  # width|height sizable

        self._load_html(datetime.now().year, datetime.now().month)

    def _load_html(self, year, month):
        try:
            html = build_html(year, month)
            self._webview.loadHTMLString_baseURL_(html, None)
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════
#  MAIN APP
# ═══════════════════════════════════════════════════════════════

class ZoomFrenchTracker(rumps.App):
    def __init__(self):
        super().__init__(name="ZoomFrenchTracker", title="🇫🇷 --h")
        self.in_meeting = False
        self.active_session_id = None
        self._alert_2h_fired = False
        self._alert_1h_fired = False
        self.calendar_window = None

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
            rumps.MenuItem("📅 Calendario", callback=self._show_calendar),
            None,
            rumps.MenuItem("❌ Salir", callback=self._quit),
        ])

    def _tick(self, _):
        try:
            meeting_now = is_in_meeting()
            if meeting_now and not self.in_meeting:
                self._on_meeting_started()
            elif not meeting_now and self.in_meeting:
                self._on_meeting_stopped()
            self.in_meeting = meeting_now
            self._update_display()
        except Exception:
            pass

    def _on_meeting_started(self):
        active = db.get_active_session()
        if active:
            db.cancel_session(active["id"])
        self.active_session_id = db.start_session(datetime.now())

    def _on_meeting_stopped(self):
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
        self._refresh_calendar()

    def _update_display(self):
        balance = db.get_balance()
        prefix = "🟢 " if self.in_meeting else "🇫🇷 "
        self.title = f"⚠️ {format_balance(balance)}" if balance <= 1 else f"{prefix}{format_balance(balance)}"

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
                self._refresh_calendar()
                rumps.notification(
                    title="✅ Horas agregadas",
                    subtitle="",
                    message=f"Se agregaron {format_balance(amount)}. Saldo: {format_balance(db.get_balance())}",
                )
            except ValueError:
                rumps.alert("Error", "Ingresa un número válido (ej: 38).")

    def _show_calendar(self, _):
        if self.calendar_window is not None:
            try:
                self.calendar_window.win.close()
            except Exception:
                pass
            self.calendar_window = None

        try:
            self.calendar_window = CalendarWindow(self)
            self.calendar_window.win.makeKeyAndOrderFront_(None)
        except Exception as e:
            self.calendar_window = None
            rumps.alert("Error", f"No se pudo abrir el calendario:\n{e}")

    def _load_html(self, year, month):
        if self.calendar_window:
            try:
                self.calendar_window._load_html(year, month)
            except Exception:
                pass

    def _refresh_calendar(self):
        if self.calendar_window:
            try:
                now = datetime.now()
                self._load_html(now.year, now.month)
            except Exception:
                pass

    def _quit(self, _):
        if self.calendar_window:
            try:
                self.calendar_window.win.close()
            except Exception:
                pass
        rumps.quit_application()


if __name__ == "__main__":
    ZoomFrenchTracker().run()
