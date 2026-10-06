#!/usr/bin/env python3
"""
Zoom French Tracker — macOS menu bar app.
Tracks Zoom meetings via CptHost, deducts from hour balance.
Calendar: clean text with monospaced grid.
"""

import subprocess, sys, os, json, calendar, signal
from datetime import datetime
from pathlib import Path

import rumps
from Foundation import (
    NSAttributedString, NSMutableAttributedString,
    NSMakeRange, NSMakeRect,
)
from AppKit import (
    NSWindow, NSBackingStoreBuffered, NSFloatingWindowLevel,
    NSScrollView, NSTextView, NSFont, NSColor, NSFontWeightBold,
)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db
from session_tracker import compute_duration, format_balance


# ═══════════════════════════════════════════════════
#  SINGLE INSTANCE
# ═══════════════════════════════════════════════════

LOCK = Path.home() / ".zoom_french_tracker" / ".app.lock"

def lock():
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    if LOCK.exists():
        try:
            os.kill(int(LOCK.read_text().strip()), 0)
            return False
        except: pass
    LOCK.write_text(str(os.getpid()))
    return True

def unlock():
    try: LOCK.unlink(missing_ok=True)
    except: pass


# ═══════════════════════════════════════════════════
#  MEETING DETECTION
# ═══════════════════════════════════════════════════

def in_meeting():
    try:
        r = subprocess.run(["pgrep","-x","CptHost"], capture_output=True, text=True, timeout=3)
        return r.returncode == 0
    except: pass
    try:
        r = subprocess.run(["ps","-eo","comm"], capture_output=True, text=True, timeout=3)
        for l in r.stdout.splitlines():
            if l.strip() == "CptHost": return True
    except: pass
    return False


# ═══════════════════════════════════════════════════
#  CALENDAR TEXT BUILDER
# ═══════════════════════════════════════════════════

MESES = ["","Enero","Febrero","Marzo","Abril","Mayo","Junio",
         "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]

WHITE  = NSColor.whiteColor()
GREEN  = NSColor.colorWithRed_green_blue_alpha_(0.65,0.89,0.63,1.0)
BLUE   = NSColor.colorWithRed_green_blue_alpha_(0.54,0.71,0.98,1.0)
YELLOW = NSColor.colorWithRed_green_blue_alpha_(0.98,0.89,0.69,1.0)
GRAY   = NSColor.colorWithRed_green_blue_alpha_(0.65,0.68,0.78,1.0)
RED    = NSColor.colorWithRed_green_blue_alpha_(0.95,0.55,0.66,1.0)

def mono(size): return NSFont.monospacedSystemFontOfSize_weight_(size, 0.0)
def bold(size): return NSFont.systemFontOfSize_weight_(size, NSFontWeightBold)


def build_calendar(year, month):
    """Return NSAttributedString calendar."""
    out = NSMutableAttributedString.alloc().init()

    def add(text, color=WHITE, font=None):
        f = font or mono(12)
        a = NSAttributedString.alloc().initWithString_attributes_(text,
            {"NSFont": f, "NSColor": color})
        out.appendAttributedString_(a)

    # ── Header ──
    bal = db.get_balance()
    pur = db.get_total_credits()
    con = db.get_total_consumed()
    daily = db.get_daily_hours(year, month)
    sessions = db.get_month_sessions(year, month)
    month_h = sum(daily.values())

    bc = GREEN if bal > 5 else (YELLOW if bal > 1 else RED)
    add(f"Saldo: {format_balance(bal)}    ", bc, bold(15))
    add(f"Comprado: {format_balance(pur)}    ", BLUE, bold(12))
    add(f"Usado: {format_balance(con)}\n", GRAY, bold(12))
    add(f"\n   {MESES[month]} {year}\n\n", BLUE, bold(18))

    # ── Grid ──
    today = datetime.now()
    td = today.day if (today.year, today.month) == (year, month) else None
    cal = calendar.Calendar(firstweekday=0)
    weeks = cal.monthdayscalendar(year, month)

    # Headers
    add("   Lu  Ma  Mi  Ju  Vi  Sa  Do\n", BLUE, mono(11))

    for w in weeks:
        line = ""
        for d in w:
            if d == 0: line += "    "
            else: line += f"{d:4d}"
        line += "\n"
        add(line, WHITE, mono(13))

        # Hour annotations
        ann = ""
        has = False
        for d in w:
            if d == 0: ann += "    "
            else:
                h = daily.get(d, 0)
                if h > 0:
                    ann += f"{format_balance(h):>4}"
                    has = True
                elif d == td:
                    ann += "  · "
                else:
                    ann += "    "
        if has or td in w:
            ann += "\n"
            add(ann, GREEN, mono(9))

    add(f"\nEste mes: {format_balance(month_h)}\n", GRAY, mono(10))

    # ── History ──
    add(f"\n── Historial ──\n", BLUE, bold(14))

    if sessions:
        for s in reversed(sessions):
            sd = datetime.strptime(s["start_time"], "%Y-%m-%d %H:%M:%S")
            ed = datetime.strptime(s["end_time"], "%Y-%m-%d %H:%M:%S") if s["end_time"] else None
            et = ed.strftime("%H:%M") if ed else "--:--"
            add(f"  {sd:%a} {sd.day:02d}  {sd:%H:%M}→{et}  {format_balance(s['rounded_hours'])}\n",
                WHITE, mono(11))
    else:
        add("  Sin sesiones\n", GRAY, mono(11))

    return out


# ═══════════════════════════════════════════════════
#  CALENDAR WINDOW
# ═══════════════════════════════════════════════════

class CalendarWindow:
    def __init__(self, app):
        self._app = app
        self._year = datetime.now().year
        self._month = datetime.now().month

        self.win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            ((0, 0), (420, 580)),
            1 | 2 | 8,  # titled | closable | resizable
            NSBackingStoreBuffered, False
        )
        self.win.setTitle_("📅  Calendario")
        self.win.setLevel_(NSFloatingWindowLevel)
        self.win.setBackgroundColor_(
            NSColor.colorWithRed_green_blue_alpha_(0.118,0.118,0.180,1.0)
        )
        self.win.setReleasedWhenClosed_(False)
        self.win.center()

        scr = NSScrollView.alloc().initWithFrame_(self.win.contentView().bounds())
        scr.setHasVerticalScroller_(True)
        scr.setAutohidesScrollers_(True)
        scr.setBorderType_(0)
        scr.setDrawsBackground_(False)
        scr.setAutoresizingMask_(18)  # width | height

        self.tv = NSTextView.alloc().initWithFrame_(scr.contentView().bounds())
        self.tv.setEditable_(False)
        self.tv.setSelectable_(True)
        self.tv.setBackgroundColor_(
            NSColor.colorWithRed_green_blue_alpha_(0.118,0.118,0.180,1.0)
        )
        self.tv.setMinSize_((380, 400))
        self.tv.setMaxSize_((1000, 100000))
        self.tv.setVerticallyResizable_(True)
        self.tv.setHorizontallyResizable_(False)
        scr.setDocumentView_(self.tv)
        self.win.contentView().addSubview_(scr)

        self._load()

    def _load(self):
        self.tv.textStorage().setAttributedString_(
            build_calendar(self._year, self._month)
        )

    def prev(self):
        m, y = self._month - 1, self._year
        if m < 1: m, y = 12, y - 1
        if y >= 2020:
            self._month, self._year = m, y
            self._load()

    def next(self):
        m, y = self._month + 1, self._year
        if m > 12: m, y = 1, y + 1
        self._month, self._year = m, y
        self._load()


# ═══════════════════════════════════════════════════
#  MAIN APP
# ═══════════════════════════════════════════════════

NSFontWeightBold = 0.6


class ZoomFrenchTracker(rumps.App):
    def __init__(self):
        super().__init__(name="ZoomFrenchTracker", title="🇫🇷 --h")
        self._meeting = False
        self._sid = None
        self._alert2 = False
        self._alert1 = False
        self.cal = None

        db.init_db()
        self._update_display()
        self._build_menu()

        self.timer = rumps.Timer(self._tick, 5)
        self.timer.start()

        a = db.get_active_session()
        if a: db.cancel_session(a["id"])

    def _build_menu(self):
        self.menu.clear()
        self.menu.update([
            rumps.MenuItem("➕ Agregar horas…", callback=self._add_hours),
            rumps.MenuItem("📅 Calendario", callback=self._show_cal),
            rumps.MenuItem("◀  Mes anterior", callback=self._prev),
            rumps.MenuItem("▶  Mes siguiente", callback=self._next),
            None,
            rumps.MenuItem("❌  Salir", callback=self._quit),
        ])

    def _tick(self, _):
        try:
            m = in_meeting()
            if m and not self._meeting: self._start()
            elif not m and self._meeting: self._stop()
            self._meeting = m
            self._update_display()
        except: pass

    def _start(self):
        a = db.get_active_session()
        if a: db.cancel_session(a["id"])
        self._sid = db.start_session(datetime.now())

    def _stop(self):
        if not self._sid: return
        a = db.get_active_session()
        if not a or a["id"] != self._sid:
            self._sid = None; return
        end = datetime.now()
        start = datetime.strptime(a["start_time"], "%Y-%m-%d %H:%M:%S")
        mins, rnd = compute_duration(start, end)
        if rnd == 0: db.cancel_session(a["id"])
        else:
            db.end_session(a["id"], end, mins, rnd)
            self._check_alerts()
        self._sid = None
        self._update_display()
        if self.cal: self.cal._load()

    def _update_display(self):
        b = db.get_balance()
        p = "🟢 " if self._meeting else "🇫🇷 "
        self.title = f"⚠️ {format_balance(b)}" if b <= 1 else f"{p}{format_balance(b)}"

    def _check_alerts(self):
        b = db.get_balance()
        if b <= 1.0 and not self._alert1:
            rumps.notification("⚠️  Queda 1 hora", "", "Compra más horas.")
            self._alert1 = self._alert2 = True
        elif b <= 2.0 and not self._alert2:
            rumps.notification("⚠️  Quedan 2 horas", "", "Compra más horas.")
            self._alert2 = True

    def _add_hours(self, _):
        r = rumps.Window(
            title="Agregar horas",
            message="¿Cuántas horas compraste?",
            ok="Agregar", cancel="Cancelar", dimensions=(200,40),
        ).run()
        if r.clicked and r.text:
            try:
                v = float(r.text.strip())
                if v <= 0 or v > 200:
                    rumps.alert("Error", "Cantidad inválida."); return
                db.add_credits(v, note="Compra")
                self._update_display()
                self._alert2 = self._alert1 = False
                if self.cal: self.cal._load()
            except ValueError:
                rumps.alert("Error", "Número inválido.")

    def _show_cal(self, _):
        try:
            if self.cal: self.cal.win.close(); self.cal = None
        except: pass
        try:
            self.cal = CalendarWindow(self)
            self.cal.win.makeKeyAndOrderFront_(None)
        except Exception as e:
            self.cal = None
            rumps.alert("Error", str(e))

    def _prev(self, _):
        if self.cal: self.cal.prev()

    def _next(self, _):
        if self.cal: self.cal.next()

    def _quit(self, _):
        try:
            if self.cal: self.cal.win.close()
        except: pass
        unlock()
        rumps.quit_application()


if __name__ == "__main__":
    if not lock():
        rumps.notification("Zoom French Tracker", "",
                           "Ya está en la barra de menú.")
        sys.exit(0)
    try:
        ZoomFrenchTracker().run()
    finally:
        unlock()
