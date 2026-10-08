#!/usr/bin/env python3
"""
Zoom French Tracker — macOS menu bar app.
Detects Zoom meetings via CptHost process, deducts from hour balance.
Calendar: WKWebView with Catppuccin Mocha dark theme.
"""

import subprocess, sys, os, json, calendar, signal
from datetime import datetime
from pathlib import Path

import rumps
import objc
from Foundation import NSBundle, NSURL, NSURLRequest
from AppKit import (
    NSWindow, NSBackingStoreBuffered, NSFloatingWindowLevel,
)
from WebKit import (
    WKWebView, WKWebViewConfiguration,
    WKUserContentController, WKUserScript,
)

import db
from session_tracker import round_session, compute_duration

# ── Paths ──────────────────────────────────────────────
DB_DIR = Path.home() / ".zoom_french_tracker"
DB_DIR.mkdir(parents=True, exist_ok=True)
os.chdir(DB_DIR)

# ── CSS ────────────────────────────────────────────────
CSS = """
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,sans-serif;background:#1e1e2e;color:#cdd6f4;padding:14px;-webkit-user-select:none;user-select:none}
.balance-row{display:flex;gap:10px;margin-bottom:16px}
.balance-row .card{flex:1;background:#313244;border-radius:10px;padding:12px 14px;text-align:center}
.balance-row .card .label{font-size:11px;color:#a6adc8;text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px}
.balance-row .card .value{font-size:22px;font-weight:700}
.balance-row .card .value.bal{color:#a6e3a1}
.balance-row .card .value.buy{color:#89b4fa}
.balance-row .card .value.used{color:#f38ba8}
.cal-wrap{text-align:center;margin-bottom:14px}
.cal-wrap .nav-row{display:flex;align-items:center;justify-content:center;gap:16px;margin-bottom:12px}
.cal-wrap .nav-row .month{font-size:15px;font-weight:600;color:#cdd6f4}
.cal-wrap .nav-row button{background:#45475a;color:#cdd6f4;border:none;border-radius:6px;padding:4px 12px;font-size:15px;cursor:pointer}
.cal-wrap .nav-row button:hover{background:#585b70}
.cal{display:grid;grid-template-columns:repeat(7,1fr);gap:4px;max-width:340px;margin:0 auto}
.cal .dh{font-size:11px;color:#6c7086;text-transform:uppercase;padding:4px 0}
.cal .day{aspect-ratio:1;display:flex;flex-direction:column;align-items:center;justify-content:center;border-radius:8px;font-size:13px;font-weight:600;cursor:pointer;background:#181825;color:#cdd6f4;position:relative}
.cal .day .hrs{font-size:10px;color:#a6e3a1;margin-top:1px}
.cal .day.cm{color:#cdd6f4}
.cal .day.cm:hover{filter:brightness(1.3)}
.cal .day.td{outline:2px solid #f9e2af;outline-offset:-2px}
.cal .day.selected{outline:2px solid #89b4fa;outline-offset:-2px}
.cal .day .dots{position:absolute;bottom:3px;left:0;right:0;display:flex;justify-content:center;gap:2px}
.day-detail{background:#313244;border-radius:10px;padding:12px;margin-top:12px;display:none}
.day-detail h3{font-size:14px;margin-bottom:8px;color:#cdd6f4}
.day-detail .sess{font-size:12px;color:#bac2de;padding:4px 0;border-bottom:1px solid #45475a}
.day-detail .sess:last-child{border:none}
.hist-title{font-size:14px;font-weight:600;color:#cdd6f4;margin:16px 0 8px}
.hist-table{width:100%;border-collapse:collapse;font-size:12px}
.hist-table th{text-align:left;color:#6c7086;padding:4px 8px;font-weight:500;border-bottom:1px solid #45475a}
.hist-table td{color:#bac2de;padding:5px 8px;border-bottom:1px solid #313244}
.hist-table .h-hrs{text-align:right;color:#a6e3a1;font-weight:600}
.empty{text-align:center;color:#585b70;padding:20px;font-size:13px}
"""

# ── Detection ──────────────────────────────────────────
def is_in_meeting():
    """Checks if CptHost process is running (Zoom meeting active)."""
    try:
        result = subprocess.run(
            ["pgrep", "-x", "CptHost"],
            capture_output=True, text=True, timeout=3,
        )
        return result.returncode == 0
    except Exception:
        return False

# ── Formatting ─────────────────────────────────────────
def format_balance(hours):
    h = int(hours)
    m = int((hours - h) * 60)
    if m == 0:
        return f"{h}h"
    return f"{h}h{m}m"

# ── Lock ───────────────────────────────────────────────
LOCK_FILE = DB_DIR / ".app.lock"

def acquire_lock():
    if LOCK_FILE.exists():
        try:
            old_pid = int(LOCK_FILE.read_text().strip())
            os.kill(old_pid, 0)
            return False
        except (OSError, ValueError):
            pass
    LOCK_FILE.write_text(str(os.getpid()))
    return True

def release_lock():
    try:
        LOCK_FILE.unlink(missing_ok=True)
    except Exception:
        pass

# ── Calendar Window ────────────────────────────────────
class CalendarWindow:
    def __init__(self, app):
        self.app = app
        mask = 1 | 2 | 8  # titled | closable | resizable

        self.win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            ((0, 0), (400, 560)), mask, NSBackingStoreBuffered, False
        )
        self.win.setTitle_("Calendario")
        self.win.setLevel_(NSFloatingWindowLevel)
        self.win.setCollectionBehavior_(1 | 4)  # canJoinAllSpaces | stationary
        self.win.setReleasedWhenClosed_(False)
        self.win.setBackgroundColor_(objc.lookUpClass('NSColor').colorWithRed_green_blue_alpha_(0.12, 0.12, 0.18, 1.0))
        self.win.center()

        # Config
        config = WKWebViewConfiguration.alloc().init()
        ctrl = WKUserContentController.alloc().init()
        config.setUserContentController_(ctrl)

        # JavaScript message handler
        class NavHandler(objc.lookUpClass("NSObject")):
            @objc.signature(b"v@:@@")
            def userContentController_didReceiveScriptMessage_(self, controller, msg):
                try:
                    body = msg.body()
                    y, m = int(body["year"]), int(body["month"])
                    # Defer via NSTimer to avoid re-entrancy
                    from Foundation import NSTimer, NSDictionary
                    info = NSDictionary.dictionaryWithDictionary_({"year": y, "month": m})
                    NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                        0.0, self._app, b'_deferredLoad:', info, False
                    )
                except Exception:
                    pass

        handler = NavHandler.alloc().init()
        handler._app = app
        ctrl.addScriptMessageHandler_name_(handler, "navigate")

        # WebView
        self.webview = WKWebView.alloc().initWithFrame_configuration_(
            self.win.contentView().bounds(), config
        )
        self.webview.setAutoresizingMask_(2 | 16)  # widthSizable | heightSizable
        self.win.contentView().addSubview_(self.webview)

    def load_html(self, year, month):
        html = build_html(year, month, self.in_meeting, self.meeting_start_ts)
        self.webview.loadHTMLString_baseURL_(html, None)

    def close(self):
        self.win.close()

# ── HTML Builder ───────────────────────────────────────
DIAS_SEMANA_ES = ["Lu", "Ma", "Mi", "Ju", "Vi", "Sá", "Do"]
MESES_ES = [
    "", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
]

def build_html(year, month, in_meeting=False, meeting_start_ts=None):
    balance = db.get_balance()
    bought = db.get_total_credits()
    used = bought - balance

    daily = db.get_daily_hours(year, month)
    sessions = db.get_month_sessions(year, month)

    # Calendar grid
    cal = calendar.Calendar(firstweekday=0)  # Monday first
    weeks = cal.monthdayscalendar(year, month)
    today = datetime.now()
    today_day = today.day if today.year == year and today.month == month else 0

    cal_cells = ""
    for d in DIAS_SEMANA_ES:
        cal_cells += f'<div class="dh">{d}</div>'
    for week in weeks:
        for day in week:
            if day == 0:
                cal_cells += '<div class="day"></div>'
            else:
                cls = "cm"  # current month day
                if day == today_day:
                    cls += " td"
                hours = daily.get(day, 0)
                hrs_html = f'<span class="hrs">{hours:.1f}h</span>' if hours > 0 else ""
                cal_cells += (
                    f'<div class="day {cls}" '
                    f'onclick="showDay({year},{month},{day},event)" '
                    f'data-day="{day}" data-hrs="{hours:.1f}">'
                    f'{day}{hrs_html}'
                    f'</div>'
                )

    # Sessions JSON for JS
    sess_data = []
    for s in sessions:
        sd = datetime.strptime(str(s["start_time"]), "%Y-%m-%d %H:%M:%S")
        ed = datetime.strptime(str(s["end_time"]), "%Y-%m-%d %H:%M:%S")
        sess_data.append({
            "day": sd.day,
            "start": sd.strftime("%H:%M"),
            "end": ed.strftime("%H:%M"),
            "hours": s["rounded_hours"],
        })

    # History table
    hist_rows = ""
    if sessions:
        for s in sessions:
            sd = datetime.strptime(str(s["start_time"]), "%Y-%m-%d %H:%M:%S")
            ed = datetime.strptime(str(s["end_time"]), "%Y-%m-%d %H:%M:%S")
            hist_rows += (
                f'<tr>'
                f'<td>{sd.day:02d} {MESES_ES[sd.month][:3]} {sd.strftime("%H")}:{sd.strftime("%M")}</td>'
                f'<td>{ed.strftime("%H:%M")}</td>'
                f'<td class="h-hrs">{s["rounded_hours"]:.1f}h</td>'
                f'</tr>'
            )

    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>{CSS}</style></head><body>

<div class="balance-row">
  <div class="card"><div class="label">Saldo</div><div class="value bal">{format_balance(balance)}</div></div>
  <div class="card"><div class="label">Comprado</div><div class="value buy">{format_balance(bought)}</div></div>
  <div class="card"><div class="label">Usado</div><div class="value used">{format_balance(used)}</div></div>
</div>

<div class="cal-wrap">
  <div class="nav-row">
    <button onclick="nav({year},{month-1},event)">◀</button>
    <span class="month">{MESES_ES[month]} {year}</span>
    <button onclick="nav({year},{month+1},event)">▶</button>
  </div>
  <div class="cal">{cal_cells}</div>
</div>

<div class="day-detail" id="dayDetail">
  <h3 id="dayTitle"></h3>
  <div id="daySessions"></div>
</div>

<div class="hist-title">📋 Historial</div>
{'' if sessions else '<div class="empty">Sin sesiones este mes</div>'}
<table class="hist-table"><tbody>{hist_rows}</tbody></table>

<script>
var SESSIONS = {json.dumps(sess_data)};
var IN_MEETING = {json.dumps(in_meeting)};
var MEETING_START = {json.dumps(meeting_start_ts)};

function nav(y,m,e){{
    e.preventDefault();
    e.stopPropagation();
    window.webkit.messageHandlers.navigate.postMessage({{year:y,month:m}});
}}

function showDay(y,m,d,e){{
    e.stopPropagation();
    document.querySelectorAll('.day.selected').forEach(function(el){{el.classList.remove('selected')}});
    e.currentTarget.classList.add('selected');
    var detail=document.getElementById('dayDetail');
    var title=document.getElementById('dayTitle');
    var list=document.getElementById('daySessions');
    title.textContent='{MESES_ES[month]} ' + d + ', {year}';
    var daySess=SESSIONS.filter(function(s){{return s.day==d}});
    list.innerHTML=daySess.length
        ?daySess.map(function(s){{return '<div class="sess">'+s.start+' – '+s.end+' · <b>'+s.hours+'h</b></div>'}}).join('')
        :'<div class="sess" style="color:#6c7086">Sin sesiones este día</div>';
    detail.style.display='block';
}}
</script>
</body></html>"""

# ── App ─────────────────────────────────────────────────
class ZoomFrenchTracker(rumps.App):
    def __init__(self):
        super().__init__("🇫🇷 Zoom French Tracker", quit_button=None)
        db.init_db()

        self.in_meeting = False
        self.meeting_start_ts = None
        self.active_session_id = None
        self.cal_win = None

        self._update_display()
        self._build_menu()

        # Timer: check every 5 seconds
        rumps.Timer(self._tick, 5).start()

    def _build_menu(self):
        self.menu.clear()
        self.menu.add(rumps.MenuItem("📅 Calendario", callback=self._show_cal))
        self.menu.add(rumps.MenuItem("◀  Mes anterior", callback=self._prev_month))
        self.menu.add(rumps.MenuItem("▶  Mes siguiente", callback=self._next_month))
        self.menu.add(rumps.separator)
        self.menu.add(rumps.MenuItem("➕ Recargar horas", callback=self._add_credits))
        self.menu.add(rumps.separator)
        self.menu.add(rumps.MenuItem("Salir", callback=self._quit))

    def _tick(self, _):
        meeting_now = is_in_meeting()
        if meeting_now != self.in_meeting:
            self.in_meeting = meeting_now
            if meeting_now:
                self._on_meeting_started()
            else:
                self._on_meeting_ended()
        self._update_display()

    def _on_meeting_started(self):
        self.meeting_start_ts = datetime.now().isoformat()
        self.active_session_id = db.start_session(datetime.now())

    def _on_meeting_ended(self):
        if self.active_session_id:
            now = datetime.now()
            duration_min = compute_duration(
                datetime.strptime(db.get_session_start(self.active_session_id), "%Y-%m-%d %H:%M:%S"),
                now
            )
            if duration_min >= 3:
                rounded = round_session(duration_min)
                db.end_session(self.active_session_id, now, duration_min, rounded)
                balance = db.get_balance()
                if 0 < balance <= 2:
                    try:
                        rumps.notification(
                            "⚠️ Saldo bajo",
                            f"Quedan {format_balance(balance)}",
                            "Recarga para continuar"
                        )
                    except Exception:
                        pass
            else:
                db.cancel_session(self.active_session_id)
            self.active_session_id = None
        self.meeting_start_ts = None

    def _update_display(self):
        balance = db.get_balance()
        prefix = "🟢 " if self.in_meeting else "🇫🇷 "
        if balance <= 1:
            self.title = f"⚠️ {format_balance(balance)}"
        else:
            self.title = f"{prefix}{format_balance(balance)}"

    def _deferredLoad_(self, timer):
        info = timer.userInfo()
        self._load_calendar(int(info["year"]), int(info["month"]))

    def _load_calendar(self, year, month):
        if self.cal_win:
            self.cal_win.load_html(year, month)

    def _show_cal(self, _):
        now = datetime.now()
        self._open_calendar(now.year, now.month)

    def _open_calendar(self, year, month):
        if self.cal_win is None:
            self.cal_win = CalendarWindow(self)
        self.cal_win.load_html(year, month)
        self.cal_win.win.makeKeyAndOrderFront_(None)

    def _prev_month(self, _):
        if self.cal_win is None:
            now = datetime.now()
            self._open_calendar(now.year, now.month - 1 if now.month > 1 else now.year - 1, 12)
        self.cal_win.load_html(*self._prev_month_date())

    def _next_month(self, _):
        if self.cal_win is None:
            now = datetime.now()
            self._open_calendar(now.year, now.month + 1 if now.month < 12 else now.year + 1, 1)
        self.cal_win.load_html(*self._next_month_date())

    def _prev_month_date(self):
        now = datetime.now()
        if now.month == 1:
            return (now.year - 1, 12)
        return (now.year, now.month - 1)

    def _next_month_date(self):
        now = datetime.now()
        if now.month == 12:
            return (now.year + 1, 1)
        return (now.year, now.month + 1)

    def _add_credits(self, _):
        try:
            window = rumps.Window(
                title="Recargar horas",
                message="¿Cuántas horas compraste?",
                ok="Agregar",
                cancel="Cancelar",
                dimensions=(200, 40)
            )
            response = window.run()
            if response.clicked and response.text:
                hours = float(response.text)
                if hours > 0:
                    db.add_credits(hours)
                    self._update_display()
                    rumps.notification("✅ Recarga", f"+{format_balance(hours)}", "")
                    if self.cal_win:
                        now = datetime.now()
                        self._load_calendar(now.year, now.month)
        except (ValueError, AttributeError):
            pass

    def _quit(self, _):
        try:
            if self.cal_win:
                self.cal_win.close()
        except Exception:
            pass
        release_lock()
        rumps.quit_application()

# ── Main ───────────────────────────────────────────────
if __name__ == "__main__":
    if not acquire_lock():
        rumps.notification("Zoom French Tracker", "", "Ya está corriendo en la barra de menú.")
        sys.exit(0)
    try:
        ZoomFrenchTracker().run()
    finally:
        release_lock()