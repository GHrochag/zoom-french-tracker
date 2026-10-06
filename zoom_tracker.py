#!/usr/bin/env python3
"""
Zoom French Tracker — Menu bar app for macOS.
Detects Zoom meetings via CptHost process, deducts from hour balance.
Calendar: native WebKit window with dark theme.
"""

import subprocess, sys, os, json, calendar
from datetime import datetime
from pathlib import Path
import signal

import rumps
import objc
from Foundation import (
    NSBundle, NSURL, NSURLRequest,
)
from AppKit import (
    NSWindow, NSBackingStoreBuffered, NSFloatingWindowLevel, NSColor,
)
from WebKit import (
    WKWebView, WKWebViewConfiguration,
    WKUserContentController, WKScriptMessage,
)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db
from session_tracker import compute_duration, format_balance


# ═══════════════════════════════════════════════════
#  SINGLE INSTANCE LOCK
# ═══════════════════════════════════════════════════

LOCK_FILE = Path.home() / ".zoom_french_tracker" / ".app.lock"

def acquire_lock():
    """Return True if this is the first instance, False if another is running."""
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    if LOCK_FILE.exists():
        try:
            pid = int(LOCK_FILE.read_text().strip())
            os.kill(pid, 0)
            return False
        except (OSError, ValueError):
            pass
    LOCK_FILE.write_text(str(os.getpid()))
    return True

def release_lock():
    try: LOCK_FILE.unlink(missing_ok=True)
    except: pass


# ═══════════════════════════════════════════════════
#  MEETING DETECTION
# ═══════════════════════════════════════════════════

def is_in_meeting():
    try:
        r = subprocess.run(["pgrep","-x","CptHost"], capture_output=True, text=True, timeout=3)
        if r.returncode == 0: return True
    except: pass
    try:
        r = subprocess.run(["ps","-eo","comm"], capture_output=True, text=True, timeout=3)
        for line in r.stdout.splitlines():
            if line.strip() == "CptHost": return True
    except: pass
    return False


# ═══════════════════════════════════════════════════
#  HTML CALENDAR
# ═══════════════════════════════════════════════════

MESES = ["","Enero","Febrero","Marzo","Abril","Mayo","Junio",
         "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]
DIAS_SEMANA = ["Lu","Ma","Mi","Ju","Vi","Sá","Do"]

CSS = r"""
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,Helvetica,sans-serif;background:#1e1e2e;color:#cdd6f4;padding:16px;-webkit-user-select:none}
.balance-row{display:flex;gap:10px;margin-bottom:16px}
.balance-row .card{flex:1;background:#313244;border-radius:10px;padding:14px 12px;text-align:center}
.balance-row .card .lbl{font-size:11px;color:#a6adc8;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px}
.balance-row .card .val{font-size:26px;font-weight:700}
.month-nav{display:flex;align-items:center;justify-content:center;gap:16px;margin-bottom:16px}
.month-nav .title{font-size:18px;font-weight:700;min-width:160px;text-align:center}
.month-nav button{background:#45475a;border:none;color:#89b4fa;font-size:15px;padding:6px 16px;border-radius:8px;cursor:pointer}
.month-nav button:hover{background:#585b70}
.cal-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:3px;text-align:center;margin-bottom:16px}
.cal-grid .dh{font-size:11px;color:#89b4fa;padding:6px 0;font-weight:600}
.cal-grid .day{aspect-ratio:1;display:flex;flex-direction:column;align-items:center;justify-content:center;border-radius:10px;font-size:14px;font-weight:600;cursor:pointer;min-height:44px}
.cal-grid .day.off{background:transparent;cursor:default}
.cal-grid .day.normal{color:#cdd6f4;background:#252536}
.cal-grid .day.normal:hover{background:#353550}
.cal-grid .day.today{outline:2px solid #f9e2af;outline-offset:-2px}
.cal-grid .day.lv1{background:#1a3a2a;color:#a6e3a1}
.cal-grid .day.lv2{background:#1a3a3a;color:#94e2d5}
.cal-grid .day.lv3{background:#1a2a4a;color:#89dceb}
.cal-grid .day.lv4{background:#2a1a4a;color:#b4befe}
.cal-grid .day .hrs{font-size:9px;line-height:1;opacity:.85}
.usage-line{text-align:center;font-size:11px;color:#a6adc8;margin-bottom:16px}
.sec-title{font-size:14px;font-weight:700;color:#89b4fa;margin-bottom:8px}
.hist-table{width:100%;border-collapse:collapse;font-size:12px;margin-bottom:12px}
.hist-table th{color:#a6adc8;text-align:left;padding:5px 8px;font-weight:500;border-bottom:1px solid #313244}
.hist-table td{padding:5px 8px}
.hist-table tr:nth-child(even){background:#1a1a2e}
.day-detail{margin-top:12px;padding:12px;background:#252536;border-radius:10px;display:none}
.day-detail.show{display:block}
.day-detail .dd-title{font-size:13px;font-weight:700;color:#89b4fa;margin-bottom:8px}
.day-detail .dd-row{font-size:12px;padding:3px 0;color:#cdd6f4}
.empty-msg{text-align:center;color:#585b70;font-size:11px;padding:12px}
"""


def _day_level(hours):
    if hours >= 2.0: return 4
    if hours >= 1.5: return 3
    if hours >= 1.0: return 2
    if hours >= 0.5: return 1
    return 0


def build_html(year, month):
    balance = db.get_balance()
    purchased = db.get_total_credits()
    consumed = db.get_total_consumed()
    daily = db.get_daily_hours(year, month)
    sessions = db.get_month_sessions(year, month)
    month_used = sum(daily.values())

    bal_clr = "#a6e3a1" if balance > 5 else ("#f9e2af" if balance > 1 else "#f38ba8")

    cal = calendar.Calendar(firstweekday=0)
    weeks = cal.monthdayscalendar(year, month)
    today = datetime.now()
    is_cur = (today.year == year and today.month == month)
    today_day = today.day if is_cur else None

    cells = ""
    for d in DIAS_SEMANA:
        cells += f'<div class="dh">{d}</div>'
    for week in weeks:
        for day in week:
            if day == 0:
                cells += '<div class="day off"></div>'
            else:
                h = daily.get(day, 0)
                lvl = _day_level(h)
                cls = f"lv{lvl}" if lvl > 0 else "normal"
                if day == today_day:
                    cls += " today"
                hrs_html = f'<div class="hrs">{format_balance(h)}</div>' if h > 0 else ""
                cells += f'<div class="day {cls}" onclick="pickDay({year},{month},{day})">{day}{hrs_html}</div>'

    sessions_json = []
    for s in sessions:
        sd = datetime.strptime(s["start_time"], "%Y-%m-%d %H:%M:%S")
        ed = datetime.strptime(s["end_time"], "%Y-%m-%d %H:%M:%S") if s["end_time"] else None
        sessions_json.append({
            "day": sd.day,
            "start": sd.strftime("%H:%M"),
            "end": ed.strftime("%H:%M") if ed else "--",
            "hours": format_balance(s["rounded_hours"]),
        })

    hist_rows = ""
    if sessions:
        for s in sessions:
            sd = datetime.strptime(s["start_time"], "%Y-%m-%d %H:%M:%S")
            ed = datetime.strptime(s["end_time"], "%Y-%m-%d %H:%M:%S") if s["end_time"] else None
            hist_rows += f'<tr><td>{sd.day:02d} {MESES[sd.month][:3]}</td><td>{sd:%H:%M}</td><td>{ed:%H:%M if ed else "--"}</td><td>{format_balance(s["rounded_hours"])}</td></tr>'
    else:
        hist_rows = '<tr><td colspan="4" class="empty-msg">Sin sesiones este mes</td></tr>'

    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>{CSS}</style></head><body>

<div class="balance-row">
  <div class="card"><div class="lbl">Saldo</div><div class="val" style="color:{bal_clr}">{format_balance(balance)}</div></div>
  <div class="card"><div class="lbl">Comprado</div><div class="val" style="color:#89b4fa">{format_balance(purchased)}</div></div>
  <div class="card"><div class="lbl">Usado</div><div class="val" style="color:#fab387">{format_balance(consumed)}</div></div>
</div>

<div class="month-nav">
  <button onclick="goMonth({year},{month-1 if month>1 else 12},{year if month>1 else year-1})">◀</button>
  <div class="title">{MESES[month]} {year}</div>
  <button onclick="goMonth({year},{month+1 if month<12 else 1},{year if month<12 else year+1})">▶</button>
</div>

<div class="cal-grid">{cells}</div>
<div class="usage-line">Este mes: {format_balance(month_used)}</div>

<div class="day-detail" id="dayDetail">
  <div class="dd-title" id="ddTitle"></div>
  <div id="ddContent"></div>
</div>

<div class="sec-title">📋 Historial</div>
<table class="hist-table"><thead><tr><th>Fecha</th><th>Inicio</th><th>Fin</th><th>Horas</th></tr></thead><tbody>{hist_rows}</tbody></table>

<script>
var SESSIONS={json.dumps(sessions_json)};
var M={json.dumps(MESES)};
function goMonth(y,m,_y){{window.webkit.messageHandlers.nav.postMessage({{y:y,m:m}})}}
function pickDay(y,m,d){{
 var el=document.getElementById("dayDetail");
 var ti=document.getElementById("ddTitle");
 var co=document.getElementById("ddContent");
 ti.textContent=d+" de "+M[m]+" "+y;
 var ss=SESSIONS.filter(function(s){{return s.day===d}});
 if(!ss.length){{co.innerHTML='<div class="empty-msg">Sin sesiones este día</div>'}}
 else{{co.innerHTML=ss.map(function(s){{return '<div class="dd-row">🕐 '+s.start+" → "+s.end+" &nbsp;&nbsp; "+s.hours+'</div>'}}).join("")}}
 el.classList.add("show")
}}
</script>
</body></html>"""


# ═══════════════════════════════════════════════════
#  CALENDAR WINDOW
# ═══════════════════════════════════════════════════

class CalendarWindow:
    def __init__(self, app):
        self._app = app

        # Message handler
        NavHandler = type('NavHandler', (objc.lookUpClass('NSObject'),), {})

        def init_self(inner_self):
            inner_self = objc.super(NavHandler, inner_self).init()
            inner_self._app = app
            return inner_self
        NavHandler.init = init_self

        @objc.signature(b'v@:@@')
        def handle_msg(inner_self, controller, message):
            try:
                body = message.body()
                app._load_html(int(body.get("y",0)), int(body.get("m",0)))
            except: pass
        NavHandler.userContentController_didReceiveScriptMessage_ = handle_msg

        handler = NavHandler.alloc().init()

        config = WKWebViewConfiguration.alloc().init()
        ctrl = WKUserContentController.alloc().init()
        ctrl.addScriptMessageHandler_name_(handler, "nav")
        config.setUserContentController_(ctrl)

        mask = 1 | 2 | 8  # titled | closable | resizable
        self.win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            ((0,0),(440,620)), mask, NSBackingStoreBuffered, False
        )
        self.win.setTitle_("🇫🇷  Calendario")
        self.win.setLevel_(NSFloatingWindowLevel)
        self.win.setBackgroundColor_(NSColor.colorWithRed_green_blue_alpha_(0.118,0.118,0.180,1.0))
        self.win.setOpaque_(True)
        self.win.setReleasedWhenClosed_(False)
        self.win.center()

        rect = self.win.contentView().bounds()
        self._webview = WKWebView.alloc().initWithFrame_configuration_(rect, config)
        self._webview.setValue_forKey_(False, "drawsBackground")
        self._webview.setAutoresizingMask_(18)
        self.win.contentView().addSubview_(self._webview)

        self._load_html(datetime.now().year, datetime.now().month)

    def _load_html(self, year, month):
        try:
            html = build_html(year, month)
            self._webview.loadHTMLString_baseURL_(html, None)
        except: pass


# ═══════════════════════════════════════════════════
#  MAIN APP
# ═══════════════════════════════════════════════════

class ZoomFrenchTracker(rumps.App):
    def __init__(self):
        super().__init__(name="ZoomFrenchTracker", title="🇫🇷 --h")
        self.in_meeting = False
        self.active_session_id = None
        self._alert_2h = False
        self._alert_1h = False
        self.cal_win = None

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
            rumps.MenuItem("📅 Calendario", callback=self._show_cal),
            None,
            rumps.MenuItem("❌ Salir", callback=self._quit),
        ])

    def _tick(self, _):
        try:
            m = is_in_meeting()
            if m and not self.in_meeting:
                self._started()
            elif not m and self.in_meeting:
                self._stopped()
            self.in_meeting = m
            self._update_display()
        except: pass

    def _started(self):
        a = db.get_active_session()
        if a: db.cancel_session(a["id"])
        self.active_session_id = db.start_session(datetime.now())

    def _stopped(self):
        if not self.active_session_id: return
        a = db.get_active_session()
        if not a or a["id"] != self.active_session_id:
            self.active_session_id = None; return
        end = datetime.now()
        start = datetime.strptime(a["start_time"], "%Y-%m-%d %H:%M:%S")
        mins, rounded = compute_duration(start, end)
        if rounded == 0:
            db.cancel_session(a["id"])
        else:
            db.end_session(a["id"], end, mins, rounded)
            self._check_alerts()
        self.active_session_id = None
        self._update_display()
        self._refresh_cal()

    def _update_display(self):
        b = db.get_balance()
        pre = "🟢 " if self.in_meeting else "🇫🇷 "
        self.title = f"⚠️ {format_balance(b)}" if b <= 1 else f"{pre}{format_balance(b)}"

    def _check_alerts(self):
        b = db.get_balance()
        if b <= 1.0 and not self._alert_1h:
            rumps.notification("⚠️ Queda 1 hora", "", "Compra más horas.")
            self._alert_1h = self._alert_2h = True
        elif b <= 2.0 and not self._alert_2h:
            rumps.notification("⚠️ Quedan 2 horas", "", "Compra más horas.")
            self._alert_2h = True

    def _add_hours(self, _):
        r = rumps.Window(
            title="Agregar horas",
            message="¿Cuántas horas compraste?",
            ok="Agregar", cancel="Cancelar", dimensions=(200,40),
        ).run()
        if r.clicked and r.text:
            try:
                amt = float(r.text.strip())
                if amt <= 0 or amt > 200:
                    rumps.alert("Error", "Cantidad inválida."); return
                db.add_credits(amt, note="Compra")
                self._update_display()
                self._alert_2h = self._alert_1h = False
                self._refresh_cal()
            except ValueError:
                rumps.alert("Error", "Número inválido.")

    def _show_cal(self, _):
        try:
            if self.cal_win:
                self.cal_win.win.close()
                self.cal_win = None
        except: pass
        try:
            self.cal_win = CalendarWindow(self)
            self.cal_win.win.makeKeyAndOrderFront_(None)
        except Exception as e:
            self.cal_win = None
            rumps.alert("Error", str(e))

    def _load_html(self, year, month):
        if self.cal_win:
            try: self.cal_win._load_html(year, month)
            except: pass

    def _refresh_cal(self):
        if self.cal_win:
            try:
                now = datetime.now()
                self._load_html(now.year, now.month)
            except: pass

    def _quit(self, _):
        try:
            if self.cal_win: self.cal_win.win.close()
        except: pass
        release_lock()
        rumps.quit_application()


if __name__ == "__main__":
    if not acquire_lock():
        rumps.notification("Zoom French Tracker", "", "Ya está corriendo en la barra de menú.")
        sys.exit(0)
    try:
        ZoomFrenchTracker().run()
    finally:
        release_lock()
