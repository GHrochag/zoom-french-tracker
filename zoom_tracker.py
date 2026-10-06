#!/usr/bin/env python3
"""
Zoom French Tracker — Menu bar app for macOS.
Tracks Zoom meetings via CptHost process detection.
Calendar: native NSTextView with NSAttributedString — no WebKit, no CSS.
"""

import subprocess, sys, os, calendar
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


# ═══════════════════════════════════════════════════════════════
#  CALENDAR WINDOW (Pure AppKit — NSTextView + NSAttributedString)
# ═══════════════════════════════════════════════════════════════

from Foundation import (
    NSAttributedString, NSMutableAttributedString,
    NSFontAttributeName, NSForegroundColorAttributeName,
    NSMakeRange,
)
from AppKit import (
    NSWindow, NSBackingStoreBuffered, NSFloatingWindowLevel,
    NSScrollView, NSTextView, NSFont, NSColor,
)

MESES = ["","Enero","Febrero","Marzo","Abril","Mayo","Junio",
         "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]
DIAS = ["Lu","Ma","Mi","Ju","Vi","Sá","Do"]

# Colors
CLR_BG    = NSColor.colorWithRed_green_blue_alpha_(0.118,0.118,0.180,1.0)
CLR_TEXT  = NSColor.colorWithRed_green_blue_alpha_(0.804,0.835,0.957,1.0)  # #cdd6f4
CLR_BLUE  = NSColor.colorWithRed_green_blue_alpha_(0.537,0.706,0.980,1.0)  # #89b4fa
CLR_GREEN = NSColor.colorWithRed_green_blue_alpha_(0.651,0.890,0.631,1.0)  # #a6e3a1
CLR_YELLOW= NSColor.colorWithRed_green_blue_alpha_(0.976,0.886,0.686,1.0)  # #f9e2af
CLR_DIM   = NSColor.colorWithRed_green_blue_alpha_(0.651,0.678,0.784,1.0)  # #a6adc8
CLR_RED   = NSColor.colorWithRed_green_blue_alpha_(0.953,0.545,0.659,1.0)  # #f38ba8


def make_attr(text, color=CLR_TEXT, bold=False, size=13, mono=False):
    fnt = NSFont.monospacedSystemFontOfSize_weight_(size, 0.0) if mono else \
          NSFont.systemFontOfSize_weight_(size, 0.6 if bold else 0.0)
    return NSAttributedString.alloc().initWithString_attributes_(text, {
        NSFontAttributeName: fnt,
        NSForegroundColorAttributeName: color,
    })


def build_calendar_text(year, month):
    """Build NSAttributedString for the calendar view."""
    result = NSMutableAttributedString.alloc().init()

    def add(text, color=CLR_TEXT, bold=False, size=13, mono=False):
        result.appendAttributedString_(make_attr(text, color, bold, size, mono))

    balance = db.get_balance()
    purchased = db.get_total_credits()
    consumed = db.get_total_consumed()
    daily = db.get_daily_hours(year, month)
    sessions = db.get_month_sessions(year, month)
    month_used = sum(daily.values())

    # ── Balance cards ──
    bal_clr = CLR_GREEN if balance > 5 else (CLR_YELLOW if balance > 1 else CLR_RED)
    add(f"Saldo: {format_balance(balance)}    ", bal_clr, True, 14)
    add(f"Comprado: {format_balance(purchased)}    ", CLR_BLUE, False, 12)
    add(f"Usado: {format_balance(consumed)}\n\n", CLR_DIM, False, 12)

    # ── Month header ──
    cal_months = calendar.TextCalendar(firstweekday=0)
    add(f"◀  {MESES[month]} {year}  ▶\n\n", CLR_BLUE, True, 16)

    # ── Day headers ──
    header_line = "  ".join(f"{d:>3}" for d in DIAS) + "\n"
    add(header_line, CLR_BLUE, True, 11, mono=True)

    # ── Calendar grid ──
    weeks = cal_months.monthdayscalendar(year, month)
    today = datetime.now()
    today_day = today.day if (today.year == year and today.month == month) else None

    for week in weeks:
        cells = []
        for day in week:
            if day == 0:
                cells.append("  · ")
            else:
                s = f"{day:3d}"
                cells.append(s)

        line = "  ".join(cells) + "\n"
        add(line, CLR_TEXT, False, 11, mono=True)

        # Day annotations (hours)
        anno_parts = []
        for day in week:
            if day == 0:
                anno_parts.append("    ")
            else:
                h = daily.get(day, 0)
                if h > 0:
                    s = f"{format_balance(h):>3}"
                elif day == today_day:
                    s = "  · "
                else:
                    s = "    "
                anno_parts.append(s)

        if any("h" in p for p in anno_parts) or today_day in week:
            anno = "  ".join(anno_parts) + "\n"
            add(anno, CLR_GREEN, False, 9, mono=True)

    add(f"\nEste mes: {format_balance(month_used)}\n\n", CLR_DIM, False, 10)

    # ── History ──
    add("▸ Historial\n\n", CLR_BLUE, True, 13)

    if sessions:
        for s in sessions:
            sd = datetime.strptime(s["start_time"], "%Y-%m-%d %H:%M:%S")
            ed_str = s["end_time"]
            ed = datetime.strptime(ed_str, "%Y-%m-%d %H:%M:%S") if ed_str else None
            line = f"  {sd.day:02d}/{sd.month:02d}  {sd:%H:%M}-{ed:%H:%M if ed else '--'}  {format_balance(s['rounded_hours']):>5}\n"
            add(line, CLR_TEXT, False, 11, mono=True)
    else:
        add("  Sin sesiones este mes\n", CLR_DIM, False, 11)

    return result


class CalendarWindow:
    def __init__(self, app):
        self._app = app
        self._year = datetime.now().year
        self._month = datetime.now().month

        mask = 1 | 2 | 8
        self.win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            ((0,0),(440,560)), mask, NSBackingStoreBuffered, False
        )
        self.win.setTitle_("🇫🇷 Zoom French Tracker")
        self.win.setLevel_(NSFloatingWindowLevel)
        self.win.setBackgroundColor_(CLR_BG)
        self.win.setReleasedWhenClosed_(False)
        self.win.center()

        cv = self.win.contentView()

        # ScrollView + TextView
        scr = NSScrollView.alloc().initWithFrame_(cv.bounds())
        scr.setHasVerticalScroller_(True)
        scr.setAutohidesScrollers_(True)
        scr.setBorderType_(0)
        scr.setDrawsBackground_(False)
        scr.setBackgroundColor_(CLR_BG)
        scr.setAutoresizingMask_(18)

        self.tv = NSTextView.alloc().initWithFrame_(scr.contentView().bounds())
        self.tv.setEditable_(False)
        self.tv.setSelectable_(True)
        self.tv.setBackgroundColor_(CLR_BG)
        self.tv.setMinSize_((400, 200))
        self.tv.setMaxSize_((1000, 10000))
        self.tv.setVerticallyResizable_(True)
        self.tv.setHorizontallyResizable_(False)

        scr.setDocumentView_(self.tv)
        cv.addSubview_(scr)

        self._load()

    def _load(self):
        self.tv.textStorage().setAttributedString_(
            build_calendar_text(self._year, self._month)
        )

    def go_prev(self):
        m, y = self._month - 1, self._year
        if m < 1:
            m, y = 12, y - 1
        if y >= 2020:
            self._month, self._year = m, y
            self._load()

    def go_next(self):
        m, y = self._month + 1, self._year
        if m > 12:
            m, y = 1, y + 1
        self._month, self._year = m, y
        self._load()


# ═══════════════════════════════════════════════════════════════
#  MAIN APP
# ═══════════════════════════════════════════════════════════════

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
            rumps.MenuItem("◀ Mes anterior", callback=self._prev),
            rumps.MenuItem("▶ Mes siguiente", callback=self._next),
            None,
            rumps.MenuItem("❌ Salir", callback=self._quit),
        ])

    def _tick(self, _):
        try:
            zoom_now = is_in_meeting()
            if zoom_now and not self.in_meeting:
                self._started()
            elif not zoom_now and self.in_meeting:
                self._stopped()
            self.in_meeting = zoom_now
            self._update_display()
        except: pass

    def _started(self):
        active = db.get_active_session()
        if active: db.cancel_session(active["id"])
        self.active_session_id = db.start_session(datetime.now())

    def _stopped(self):
        if not self.active_session_id: return
        active = db.get_active_session()
        if not active or active["id"] != self.active_session_id:
            self.active_session_id = None; return
        end = datetime.now()
        start = datetime.strptime(active["start_time"], "%Y-%m-%d %H:%M:%S")
        mins, rounded = compute_duration(start, end)
        if rounded == 0:
            db.cancel_session(active["id"])
        else:
            db.end_session(active["id"], end, mins, rounded)
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
            rumps.notification("⚠️ Quedan 2 horas", "", "Compra más horas pronto.")
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

    def _prev(self, _):
        if self.cal_win:
            self.cal_win.go_prev()

    def _next(self, _):
        if self.cal_win:
            self.cal_win.go_next()

    def _refresh_cal(self):
        if self.cal_win:
            self.cal_win._load()

    def _quit(self, _):
        try:
            if self.cal_win:
                self.cal_win.win.close()
        except: pass
        rumps.quit_application()


if __name__ == "__main__":
    ZoomFrenchTracker().run()
