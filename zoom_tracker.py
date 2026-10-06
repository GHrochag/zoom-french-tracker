#!/usr/bin/env python3
"""
Zoom French Tracker — Menu bar app for macOS.
Tracks Zoom meetings automatically — detects CptHost (meeting process).
Deducts from purchased-hours balance with 0.5h rounding and 2.0h cap.

Pure AppKit calendar — no WebKit, no tkinter, no browser.
"""

import subprocess
import sys
import os
import json
import calendar
from datetime import datetime
from pathlib import Path

import rumps
import objc
from Foundation import (
    NSBundle, NSURLRequest, NSURL, NSTimer, NSDictionary,
    NSMutableParagraphStyle, NSAttributedString, NSMakeRect,
)

# NSAttributedString keys as raw strings (avoids PyObjC version issues)
NS_FONT = 'NSFont'
NS_FG_COLOR = 'NSForegroundColor'
NS_PARA = 'NSParagraphStyle'
from AppKit import (
    NSWindow, NSBackingStoreBuffered,
    NSFloatingWindowLevel, NSView, NSScrollView,
    NSFont, NSColor, NSBezierPath,
    NSScreen, NSApp,
)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db
from session_tracker import compute_duration, format_balance


# ═══════════════════════════════════════════════════════════════
#  ZOOM MEETING DETECTION
# ═══════════════════════════════════════════════════════════════

def is_in_meeting() -> bool:
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
#  NATIVE CALENDAR VIEW (pure AppKit — no WebKit needed)
# ═══════════════════════════════════════════════════════════════

MESES = [
    "", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]
DIAS = ["Lu", "Ma", "Mi", "Ju", "Vi", "Sá", "Do"]

# Catppuccin Mocha palette
CLR_BG = (30/255, 30/255, 46/255, 1.0)         # #1e1e2e
CLR_SURFACE = (24/255, 24/255, 37/255, 1.0)     # #181825
CLR_OVERLAY = (49/255, 50/255, 68/255, 1.0)     # #313244
CLR_TEXT = (205/255, 214/255, 244/255, 1.0)     # #cdd6f4
CLR_SUBTEXT = (166/255, 173/255, 200/255, 1.0)   # #a6adc8
CLR_BLUE = (137/255, 180/255, 250/255, 1.0)     # #89b4fa
CLR_GREEN = (166/255, 227/255, 161/255, 1.0)    # #a6e3a1
CLR_YELLOW = (249/255, 226/255, 175/255, 1.0)   # #f9e2af
CLR_RED = (243/255, 139/255, 168/255, 1.0)      # #f38ba8
CLR_PEACH = (250/255, 179/255, 135/255, 1.0)    # #fab387
CLR_DIM = (88/255, 91/255, 112/255, 1.0)         # #585b70

LEVEL_COLORS = [
    None,                              # 0 — no hours
    (26/255, 58/255, 42/255, 1.0),    # 1 — dark green
    (26/255, 58/255, 58/255, 1.0),    # 2 — dark teal
    (26/255, 42/255, 74/255, 1.0),    # 3 — dark blue
    (42/255, 26/255, 74/255, 1.0),    # 4 — dark purple
]

LEVEL_TXT = [
    (88/255, 91/255, 112/255, 1.0),   # dim
    (166/255, 227/255, 161/255, 1.0), # green
    (148/255, 226/255, 213/255, 1.0), # teal
    (116/255, 199/255, 236/255, 1.0), # blue
    (137/255, 180/255, 250/255, 1.0), # lavender
]

BUTTON_CLR = (69/255, 71/255, 90/255, 1.0)  # #45475a for buttons


def _day_level(hours: float) -> int:
    if hours >= 2.0: return 4
    if hours >= 1.5: return 3
    if hours >= 1.0: return 2
    if hours >= 0.5: return 1
    return 0


class CalendarView(NSView):
    """A scrollable calendar view drawn with Core Graphics."""

    CELL_W = 52
    CELL_H = 42
    HEADER_H = 20
    HEADER_CARD_H = 60
    TOP_PAD = 8
    PADDING_X = 14
    GAP = 2
    MONTH_NAV_H = 30

    def initWithApp_(self, app):
        self = objc.super(CalendarView, self).init()
        if self is None:
            return None
        self._app = app
        self._year = datetime.now().year
        self._month = datetime.now().month
        self._daily = {}
        self._sessions = []
        return self

    def reload_data(self):
        """Reload data and redraw."""
        self._daily = db.get_daily_hours(self._year, self._month)
        self._sessions = db.get_month_sessions(self._year, self._month)
        self.setNeedsDisplay_(True)

    def go_month(self, year, month):
        self._year = year
        self._month = month
        self.reload_data()

    def mouseDown_(self, event):
        """Handle clicks — navigation buttons or day cells."""
        pt = self.convertPoint_fromView_(event.locationInWindow(), None)
        x, y = pt.x, pt.y
        total_h = self._total_height()
        cy = total_h - y  # flip y

        # Nav row: top of view
        nav_y_top = total_h - self.TOP_PAD
        nav_y_bot = nav_y_top - self.MONTH_NAV_H

        if nav_y_bot <= cy <= nav_y_top:
            # Prev button
            btn_w = 32
            if self.PADDING_X <= x <= self.PADDING_X + btn_w:
                self._go_prev()
                return
            # Next button
            title_width = 140
            next_x = self.PADDING_X + title_width + 20
            if next_x <= x <= next_x + btn_w:
                self._go_next()
                return
            return

        # Calendar grid
        grid_top = nav_y_bot - self.HEADER_H - self.GAP - self.HEADER_CARD_H - 12
        grid_bot = grid_top - (6 * (self.CELL_H + self.GAP)) - self.HEADER_H - 8

        if grid_bot <= cy <= grid_top:
            # Figure out which cell
            cal = calendar.Calendar(firstweekday=0)
            weeks = cal.monthdayscalendar(self._year, self._month)
            row_h = self.CELL_H + self.GAP

            for wi, week in enumerate(weeks):
                row_top = grid_top - self.HEADER_H - 4 - wi * row_h
                row_bot = row_top - self.CELL_H
                if row_bot <= cy <= row_top:
                    for di, day in enumerate(week):
                        if day == 0:
                            continue
                        cx = self.PADDING_X + di * (self.CELL_W + self.GAP)
                        if cx <= x <= cx + self.CELL_W:
                            self._app._show_day_popup(day, self._year, self._month)
                            return
                    return

    def _go_prev(self):
        m = self._month - 1 if self._month > 1 else 12
        y = self._year if self._month > 1 else self._year - 1
        self.go_month(y, m)

    def _go_next(self):
        m = self._month + 1 if self._month < 12 else 1
        y = self._year if self._month < 12 else self._year + 1
        self.go_month(y, m)

    def _total_height(self):
        rows = len(calendar.Calendar(firstweekday=0).monthdayscalendar(self._year, self._month))
        grid_h = self.HEADER_H + rows * (self.CELL_H + self.GAP)
        return (
            self.TOP_PAD + self.MONTH_NAV_H + self.HEADER_CARD_H + 12
            + grid_h + self.HEADER_CARD_H + 100
        )

    def drawRect_(self, rect):
        """Draw the entire calendar."""
        w = self.bounds().size.width
        total_h = self._total_height()
        y = total_h - self.TOP_PAD

        # ── Background ──
        self._fill_rect(0, 0, w, total_h, CLR_BG)

        # ── Navigation ──
        y = self._draw_nav(y, w)
        y = self._draw_header_cards(y, w)
        y = self._draw_grid(y, w)
        self._draw_history(y, w)

    def _fill_rect(self, x, y, w, h, color, radius=0):
        """Fill a rectangle with optional rounded corners."""
        NSColor.colorWithRed_green_blue_alpha_(*color).setFill()
        if radius > 0:
            NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                ((x, y), (w, h)), radius, radius
            ).fill()
        else:
            NSBezierPath.fillRect_(((x, y), (w, h)))

    def _draw_text(self, x, y, text, font_size, color, bold=False, align='left', max_w=None):
        font = NSFont.boldSystemFontOfSize_(font_size) if bold else NSFont.systemFontOfSize_(font_size)
        para = NSMutableParagraphStyle.alloc().init()
        if align == 'center':
            para.setAlignment_(2)  # NSCenterTextAlignment
        elif align == 'right':
            para.setAlignment_(1)
        attrs = {
            NS_FONT: font,
            NS_FG_COLOR: NSColor.colorWithRed_green_blue_alpha_(*color),
            NS_PARA: para,
        }
        attr_str = NSAttributedString.alloc().initWithString_attributes_(text, attrs)
        size = attr_str.size()
        actual_w = max_w if max_w else size.width
        attr_str.drawInRect_(((x, y - size.height), (actual_w, size.height)))

    def _stroke_rect(self, x, y, w, h, color, line_width=2):
        NSColor.colorWithRed_green_blue_alpha_(*color).setStroke()
        NSBezierPath.setDefaultLineWidth_(line_width)
        NSBezierPath.strokeRect_(((x, y), (w, h)))

    def _draw_nav(self, y, w):
        y -= self.MONTH_NAV_H
        title = f"{MESES[self._month]} {self._year}"
        font = NSFont.boldSystemFontOfSize_(15)
        attrs = {
            NS_FONT: font,
            NS_FG_COLOR: NSColor.colorWithRed_green_blue_alpha_(*CLR_TEXT),
        }
        t = NSAttributedString.alloc().initWithString_attributes_(title, attrs)
        ts = t.size()
        tx = self.PADDING_X + 38  # space for prev button
        self._draw_text(tx, y + self.MONTH_NAV_H - ts.height - 4,
                       title, 15, CLR_TEXT, bold=True, align='left')

        # Prev button
        self._fill_rect(self.PADDING_X, y + 4, 30, 22, BUTTON_CLR, radius=5)
        self._draw_text(self.PADDING_X + 8, y + 8, "◀", 12, CLR_BLUE, bold=True)

        # Next button
        self._fill_rect(self.PADDING_X + 170, y + 4, 30, 22, BUTTON_CLR, radius=5)
        self._draw_text(self.PADDING_X + 178, y + 8, "▶", 12, CLR_BLUE, bold=True)

        return y

    def _draw_header_cards(self, y, w):
        y -= 8
        card_w = (w - 2 * self.PADDING_X - 16) / 3
        card_h = 52

        balance = db.get_balance()
        purchased = db.get_total_credits()
        consumed = db.get_total_consumed()

        cards = [
            ("Saldo", format_balance(balance),
             CLR_GREEN if balance > 5 else (CLR_YELLOW if balance > 1 else CLR_RED)),
            ("Comprado", format_balance(purchased), CLR_BLUE),
            ("Usado", format_balance(consumed), CLR_PEACH),
        ]

        for i, (label, value, vclr) in enumerate(cards):
            cx = self.PADDING_X + i * (card_w + 8)
            self._fill_rect(cx, y, card_w, card_h, CLR_OVERLAY, radius=8)
            self._draw_text(cx + card_w/2, y + card_h - 12,
                          label, 9, CLR_SUBTEXT, align='center')
            self._draw_text(cx + card_w/2, y + 24,
                          value, 20, vclr, bold=True, align='center')

        return y - card_h

    def _draw_grid(self, y, w):
        month_consumed = sum(self._daily.values())
        card_w = w - 2 * self.PADDING_X
        y -= 12

        self._draw_text(self.PADDING_X + card_w/2, y,
                      f"Este mes: {format_balance(month_consumed)}",
                      10, CLR_SUBTEXT, align='center')
        y -= 20

        # Day headers
        for di, d in enumerate(DIAS):
            cx = self.PADDING_X + di * (self.CELL_W + self.GAP)
            self._draw_text(cx + self.CELL_W/2, y,
                          d, 9, CLR_BLUE, bold=True, align='center')
        y -= self.HEADER_H

        # Day cells
        cal = calendar.Calendar(firstweekday=0)
        weeks = cal.monthdayscalendar(self._year, self._month)
        today = datetime.now()
        is_current = (today.year == self._year and today.month == self._month)
        today_day = today.day if is_current else None

        for week in weeks:
            for di, day in enumerate(week):
                cx = self.PADDING_X + di * (self.CELL_W + self.GAP)
                if day == 0:
                    self._fill_rect(cx, y, self.CELL_W, self.CELL_H, CLR_SURFACE, radius=5)
                else:
                    h = self._daily.get(day, 0)
                    lvl = _day_level(h)
                    bg = LEVEL_COLORS[lvl] if lvl > 0 else CLR_SURFACE
                    txt_c = LEVEL_TXT[lvl]
                    self._fill_rect(cx, y, self.CELL_W, self.CELL_H, bg, radius=5)
                    # Today outline
                    if day == today_day:
                        self._stroke_rect(cx, y, self.CELL_W, self.CELL_H, CLR_YELLOW)
                    # Day number
                    self._draw_text(cx + self.CELL_W/2, y + 12,
                                  str(day), 13, txt_c, bold=True, align='center')
                    if h > 0:
                        self._draw_text(cx + self.CELL_W/2, y + 28,
                                      format_balance(h), 8, txt_c, align='center')
            y -= (self.CELL_H + self.GAP)

        return y

    def _draw_history(self, y, w):
        y -= 12
        card_w = w - 2 * self.PADDING_X
        self._draw_text(self.PADDING_X, y, "📋 Historial", 12, CLR_BLUE, bold=True)
        y -= 18

        if not self._sessions:
            self._draw_text(self.PADDING_X + card_w/2, y,
                          "Sin sesiones este mes", 10, CLR_DIM, align='center')
            return y - 20

        # Draw sessions as rows
        row_h = 22
        headers = ["Fecha", "Inicio", "Fin", "Horas"]
        col_x = [self.PADDING_X, self.PADDING_X + 60, self.PADDING_X + 120, self.PADDING_X + 180]

        for hdr, cx in zip(headers, col_x):
            self._draw_text(cx, y, hdr, 8, CLR_SUBTEXT)
        y -= 16

        for s in self._sessions:
            sd = datetime.strptime(s["start_time"], "%Y-%m-%d %H:%M:%S")
            ed = datetime.strptime(s["end_time"], "%Y-%m-%d %H:%M:%S") if s["end_time"] else None

            if row_h * len(self._sessions) > 200:
                # Alternating row bg
                row_bg = CLR_SURFACE if self._sessions.index(s) % 2 == 0 else CLR_BG
                self._fill_rect(self.PADDING_X, y - 2, card_w, row_h - 2, row_bg, radius=3)

            vals = [
                sd.strftime("%d %b"),
                sd.strftime("%H:%M"),
                ed.strftime("%H:%M") if ed else "--",
                format_balance(s["rounded_hours"]),
            ]
            for val, cx in zip(vals, col_x):
                self._draw_text(cx, y, val, 10, CLR_TEXT)
            y -= row_h

        return y


class CalendarWindow:
    """Wrapper around an NSWindow containing CalendarView."""

    def __init__(self, app):
        self._app = app

        mask = 1 | 2 | 8  # titled | closable | resizable
        self.win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            ((0, 0), (420, 580)), mask, NSBackingStoreBuffered, False
        )
        self.win.setTitle_("🇫🇷 Zoom French Tracker")
        self.win.setLevel_(NSFloatingWindowLevel)
        self.win.setCollectionBehavior_(1 | 4)  # canJoinAllSpaces | stationary
        self.win.setReleasedWhenClosed_(False)
        self.win.setBackgroundColor_(NSColor.colorWithRed_green_blue_alpha_(*CLR_BG))
        self.win.center()

        # Scroll view for the calendar
        self.scroll = NSScrollView.alloc().initWithFrame_(
            self.win.contentView().bounds()
        )
        self.scroll.setHasVerticalScroller_(True)
        self.scroll.setAutohidesScrollers_(True)
        self.scroll.setBorderType_(0)  # NSNoBorder
        self.scroll.setDrawsBackground_(False)
        self.scroll.setBackgroundColor_(NSColor.colorWithRed_green_blue_alpha_(*CLR_BG))

        self.view = CalendarView.alloc().initWithApp_(app)
        self.view.reload_data()
        total_h = self.view._total_height()
        self.view.setFrame_(NSMakeRect(0, 0, 420, max(total_h, 580)))
        self.scroll.setDocumentView_(self.view)
        self.win.contentView().addSubview_(self.scroll)


# ═══════════════════════════════════════════════════════════════
#  DAY DETAIL POPUP (small window showing sessions for a day)
# ═══════════════════════════════════════════════════════════════

class DayDetailView(NSView):
    def initWithSessions_day_month_year_app_(self, sessions, day, month, year, app):
        self = objc.super(DayDetailView, self).init()
        if self is None:
            return None
        self._sessions = sessions
        self._day = day
        self._month = month
        self._year = year
        self._app = app
        return self

    def drawRect_(self, rect):
        w = self.bounds().size.width
        h = self.bounds().size.height
        self._fill_rect(0, 0, w, h, CLR_BG)

        title = f"{self._day} {MESES[self._month]} {self._year}"
        self._draw_text(14, h - 20, title, 13, CLR_BLUE, bold=True)

        if not self._sessions:
            self._draw_text(14, h - 44, "Sin sesiones", 11, CLR_DIM)
        else:
            y = h - 44
            for s in self._sessions:
                sd = datetime.strptime(s["start_time"], "%Y-%m-%d %H:%M:%S")
                ed = datetime.strptime(s["end_time"], "%Y-%m-%d %H:%M:%S") if s["end_time"] else None
                line = f"{sd.strftime('%H:%M')} → {ed.strftime('%H:%M') if ed else '--'}   {format_balance(s['rounded_hours'])}"
                self._draw_text(14, y, line, 12, CLR_TEXT)
                y -= 22

    def _fill_rect(self, x, y, w, h, color, radius=0):
        NSColor.colorWithRed_green_blue_alpha_(*color).setFill()
        if radius > 0:
            NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                ((x, y), (w, h)), radius, radius
            ).fill()
        else:
            NSBezierPath.fillRect_(((x, y), (w, h)))

    def _draw_text(self, x, y, text, font_size, color, bold=False, align='left'):
        font = NSFont.boldSystemFontOfSize_(font_size) if bold else NSFont.systemFontOfSize_(font_size)
        para = NSMutableParagraphStyle.alloc().init()
        if align == 'center':
            para.setAlignment_(2)
        attrs = {
            NS_FONT: font,
            NS_FG_COLOR: NSColor.colorWithRed_green_blue_alpha_(*color),
            NS_PARA: para,
        }
        attr_str = NSAttributedString.alloc().initWithString_attributes_(text, attrs)
        size = attr_str.size()
        attr_str.drawInRect_(((x, y - size.height), (size.width, size.height)))


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
        self._day_popup = None

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
            self.calendar_window.view.reload_data()
            self.calendar_window.win.makeKeyAndOrderFront_(None)
        except Exception as e:
            self.calendar_window = None
            rumps.alert("Error", f"No se pudo abrir el calendario:\n{e}")

    def _refresh_calendar(self):
        if self.calendar_window is not None:
            try:
                self.calendar_window.view.reload_data()
            except Exception:
                pass

    def _show_day_popup(self, day, year, month):
        """Show a small floating window with sessions for a specific day."""
        sessions = [s for s in db.get_month_sessions(year, month)
                    if datetime.strptime(s["start_time"], "%Y-%m-%d %H:%M:%S").day == day]

        if self._day_popup is not None:
            try:
                self._day_popup.close()
            except Exception:
                pass
            self._day_popup = None

        mask = 1 | 2  # titled | closable
        self._day_popup = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            ((0, 0), (280, max(120, 60 + len(sessions) * 22))), mask,
            NSBackingStoreBuffered, False
        )
        self._day_popup.setTitle_(f"{day} {MESES[month]} {year}")
        self._day_popup.setLevel_(NSFloatingWindowLevel)
        self._day_popup.setReleasedWhenClosed_(False)

        view = DayDetailView.alloc().initWithSessions_day_month_year_app_(
            sessions, day, month, year, self
        )
        view.setFrame_(((0, 0), (280, max(120, 60 + len(sessions) * 22))))
        self._day_popup.contentView().addSubview_(view)
        self._day_popup.center()
        self._day_popup.makeKeyAndOrderFront_(None)

    def _quit(self, _):
        if self.calendar_window:
            try:
                self.calendar_window.win.close()
            except Exception:
                pass
        if self._day_popup:
            try:
                self._day_popup.close()
            except Exception:
                pass
        rumps.quit_application()


if __name__ == "__main__":
    ZoomFrenchTracker().run()
