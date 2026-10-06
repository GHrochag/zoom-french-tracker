#!/usr/bin/env python3
"""
Zoom French Tracker — Menu bar app for macOS.
Automatically tracks Zoom sessions and deducts from a purchased-hours balance.

Requires: Python 3.11+, rumps, matplotlib, and tkinter (python-tk on Homebrew).
"""

import subprocess
import sys
import os
from datetime import datetime, timedelta
import calendar
import locale
import math
from pathlib import Path

# ── macOS-specific imports (fail gracefully if not on macOS) ──
try:
    import rumps
except ImportError:
    print("Error: rumps is required. Install with: pip install rumps")
    sys.exit(1)

# ── Local imports ──
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db
from session_tracker import compute_duration, format_balance, round_session

# ── Tkinter (optional, for calendar/chart windows) ──
try:
    import tkinter as tk
    from tkinter import ttk, messagebox

    TK_AVAILABLE = True
except ImportError:
    TK_AVAILABLE = False


# ═══════════════════════════════════════════════════════════════
#  ZOOM DETECTION
# ═══════════════════════════════════════════════════════════════


def is_zoom_running() -> bool:
    """Detect if Zoom is currently running."""
    try:
        result = subprocess.run(
            ["pgrep", "-ix", "zoom.us"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode == 0:
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Fallback: scan process list
    try:
        result = subprocess.run(
            ["ps", "-eo", "comm"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        for line in result.stdout.splitlines():
            if "zoom.us" in line.lower() or "zoom" in line.lower():
                return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return False


# ═══════════════════════════════════════════════════════════════
#  TKINTER UI WINDOWS
# ═══════════════════════════════════════════════════════════════

if TK_AVAILABLE:

    # ── Color palette ──
    BG_COLOR = "#1e1e2e"
    FG_COLOR = "#cdd6f4"
    ACCENT = "#89b4fa"
    ACCENT_DARK = "#45475a"
    GREEN = "#a6e3a1"
    YELLOW = "#f9e2af"
    RED = "#f38ba8"
    SURFACE = "#313244"
    CALENDAR_BG = "#181825"
    DAY_HIGH = "#89b4fa"  # 2.0h
    DAY_MED = "#74c7ec"  # 1.5h
    DAY_LOW = "#94e2d5"  # 1.0h
    DAY_MIN = "#a6e3a1"  # 0.5h

    # ── Month names in Spanish ──
    MESES = [
        "", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
        "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
    ]
    DIAS_SEMANA = ["Lu", "Ma", "Mi", "Ju", "Vi", "Sá", "Do"]

    def _init_tk_root():
        """Lazy-init the hidden tkinter root."""
        if not hasattr(_init_tk_root, "root"):
            root = tk.Tk()
            root.withdraw()  # Hidden — only show Toplevels
            root.option_add("*Font", "Helvetica 12")
            _init_tk_root.root = root
        return _init_tk_root.root

    def _day_color(hours: float) -> str:
        """Return a background color based on hours consumed that day."""
        if hours >= 2.0:
            return DAY_HIGH
        elif hours >= 1.5:
            return DAY_MED
        elif hours >= 1.0:
            return DAY_LOW
        elif hours >= 0.5:
            return DAY_MIN
        return ""

    # ─────────────────────────────────────────────────────────
    #  CALENDAR + HISTORY WINDOW
    # ─────────────────────────────────────────────────────────

    class CalendarWindow:
        """Shows a monthly calendar with daily hours + session history."""

        def __init__(self, app_ref):
            self.app = app_ref
            self.year = datetime.now().year
            self.month = datetime.now().month
            self._build()

        def _build(self):
            self.win = tk.Toplevel(_init_tk_root())
            self.win.title("🇫🇷 Zoom French Tracker — Calendario")
            self.win.geometry("720x640")
            self.win.configure(bg=BG_COLOR)
            self.win.minsize(600, 500)

            # ── Header with month navigation ──
            header = tk.Frame(self.win, bg=BG_COLOR)
            header.pack(pady=(15, 5), fill=tk.X, padx=20)

            self.prev_btn = tk.Button(
                header, text="◀", command=self._prev_month,
                bg=SURFACE, fg=ACCENT, font=("Helvetica", 16, "bold"),
                relief=tk.FLAT, cursor="hand2", padx=10,
            )
            self.prev_btn.pack(side=tk.LEFT)

            self.month_label = tk.Label(
                header,
                text=f"{MESES[self.month]} {self.year}",
                font=("Helvetica", 18, "bold"),
                bg=BG_COLOR, fg=FG_COLOR,
            )
            self.month_label.pack(side=tk.LEFT, expand=True)

            self.next_btn = tk.Button(
                header, text="▶", command=self._next_month,
                bg=SURFACE, fg=ACCENT, font=("Helvetica", 16, "bold"),
                relief=tk.FLAT, cursor="hand2", padx=10,
            )
            self.next_btn.pack(side=tk.RIGHT)

            # ── Balance summary ──
            summary_frame = tk.Frame(self.win, bg=BG_COLOR)
            summary_frame.pack(pady=(0, 10), fill=tk.X, padx=20)

            balance = db.get_balance()
            consumed_this_month = sum(
                db.get_daily_hours(self.year, self.month).values()
            )

            tk.Label(
                summary_frame, text=f"💳 Saldo: {format_balance(balance)}",
                font=("Helvetica", 14, "bold"),
                bg=BG_COLOR, fg=GREEN if balance > 5 else YELLOW if balance > 1 else RED,
            ).pack(side=tk.LEFT, padx=(0, 20))

            tk.Label(
                summary_frame,
                text=f"📅 Este mes: {format_balance(consumed_this_month)}",
                font=("Helvetica", 12),
                bg=BG_COLOR, fg=ACCENT,
            ).pack(side=tk.LEFT)

            # ── Calendar grid ──
            cal_frame = tk.Frame(self.win, bg=CALENDAR_BG)
            cal_frame.pack(pady=(0, 10), padx=20, fill=tk.X)

            self._draw_calendar(cal_frame)

            # ── Action buttons ──
            btn_frame = tk.Frame(self.win, bg=BG_COLOR)
            btn_frame.pack(pady=(0, 10), fill=tk.X, padx=20)

            tk.Button(
                btn_frame, text="➕ Agregar horas", command=self._add_hours,
                bg=GREEN, fg="#1e1e2e", font=("Helvetica", 12, "bold"),
                relief=tk.FLAT, cursor="hand2", padx=20, pady=8,
            ).pack(side=tk.LEFT, padx=(0, 10))

            tk.Button(
                btn_frame, text="📊 Ver gráfico", command=self._show_chart,
                bg=SURFACE, fg=ACCENT, font=("Helvetica", 12),
                relief=tk.FLAT, cursor="hand2", padx=20, pady=8,
            ).pack(side=tk.LEFT)

            # ── History table ──
            hist_label = tk.Label(
                self.win, text="📋 Historial de sesiones",
                font=("Helvetica", 14, "bold"), bg=BG_COLOR, fg=FG_COLOR,
            )
            hist_label.pack(anchor=tk.W, padx=20, pady=(5, 5))

            self._draw_history()

        def _draw_calendar(self, parent):
            """Draw the month calendar grid."""
            # Day-of-week headers
            for i, day_name in enumerate(DIAS_SEMANA):
                tk.Label(
                    parent, text=day_name,
                    font=("Helvetica", 11, "bold"),
                    bg=CALENDAR_BG, fg=ACCENT,
                    width=6, pady=5,
                ).grid(row=0, column=i, sticky="nsew")

            # Get daily hours
            daily = db.get_daily_hours(self.year, self.month)

            # Build calendar
            cal = calendar.Calendar(firstweekday=0)  # Monday first
            weeks = cal.monthdayscalendar(self.year, self.month)

            today = datetime.now().day if (
                datetime.now().year == self.year
                and datetime.now().month == self.month
            ) else None

            for r, week in enumerate(weeks, start=1):
                for c, day in enumerate(week):
                    if day == 0:
                        lbl = tk.Label(
                            parent, text="",
                            bg=CALENDAR_BG, width=6, height=3,
                        )
                    else:
                        hours = daily.get(day, 0)
                        bg = _day_color(hours)
                        if bg == "":
                            bg = CALENDAR_BG

                        text = f"{day}"
                        fg = FG_COLOR

                        # Highlight today
                        if day == today:
                            fg = YELLOW
                            if bg == CALENDAR_BG:
                                bg = SURFACE

                        if hours > 0:
                            text = f"{day}\n{format_balance(hours)}"

                        lbl = tk.Label(
                            parent, text=text,
                            font=("Helvetica", 10, "bold" if day == today else "normal"),
                            bg=bg, fg=fg,
                            width=8, height=3,
                            relief=tk.FLAT,
                            borderwidth=1,
                        )
                    lbl.grid(row=r, column=c, sticky="nsew", padx=1, pady=1)

            # Legend
            legend_frame = tk.Frame(parent, bg=CALENDAR_BG)
            legend_frame.grid(
                row=len(weeks) + 1, column=0, columnspan=7, pady=(10, 5)
            )

            legend_items = [
                (DAY_MIN, "0.5h"), (DAY_LOW, "1.0h"),
                (DAY_MED, "1.5h"), (DAY_HIGH, "2.0h"),
            ]
            for i, (color, label) in enumerate(legend_items):
                tk.Frame(legend_frame, bg=color, width=16, height=16).pack(
                    side=tk.LEFT, padx=(15 if i == 0 else 8, 4)
                )
                tk.Label(
                    legend_frame, text=label,
                    font=("Helvetica", 10), bg=CALENDAR_BG, fg=FG_COLOR,
                ).pack(side=tk.LEFT)

        def _draw_history(self):
            """Draw the session history table for the current month."""
            sessions = db.get_month_sessions(self.year, self.month)

            if not sessions:
                tk.Label(
                    self.win,
                    text="   No hay sesiones este mes.",
                    font=("Helvetica", 11),
                    bg=BG_COLOR, fg=ACCENT_DARK,
                ).pack(anchor=tk.W, padx=20)
                return

            # Table container
            table_frame = tk.Frame(self.win, bg=SURFACE)
            table_frame.pack(padx=20, pady=(0, 15), fill=tk.BOTH, expand=True)

            # Header
            headers = [
                ("Fecha", 12), ("Inicio", 8), ("Fin", 8),
                ("Minutos", 8), ("Horas", 6),
            ]
            for c, (text, w) in enumerate(headers):
                tk.Label(
                    table_frame, text=text,
                    font=("Helvetica", 10, "bold"),
                    bg=SURFACE, fg=ACCENT, width=w, anchor=tk.W, padx=6, pady=4,
                ).grid(row=0, column=c, sticky="ew")

            # Rows
            for r, s in enumerate(sessions, start=1):
                start_dt = datetime.strptime(s["start_time"], "%Y-%m-%d %H:%M:%S")
                end_dt = (
                    datetime.strptime(s["end_time"], "%Y-%m-%d %H:%M:%S")
                    if s["end_time"]
                    else None
                )

                fecha = start_dt.strftime("%d %b %Y")
                inicio = start_dt.strftime("%H:%M")
                fin = end_dt.strftime("%H:%M") if end_dt else "--"
                minutos = f"{s['duration_minutes']:.0f}" if s["duration_minutes"] else "--"
                horas = format_balance(s["rounded_hours"])

                row_color = BG_COLOR if r % 2 == 0 else SURFACE

                values = [fecha, inicio, fin, minutos, horas]
                for c, val in enumerate(values):
                    tk.Label(
                        table_frame, text=val,
                        font=("Helvetica", 10),
                        bg=row_color, fg=FG_COLOR,
                        width=headers[c][1], anchor=tk.W, padx=6, pady=3,
                    ).grid(row=r, column=c, sticky="ew")

        def _prev_month(self):
            if self.month == 1:
                self.month = 12
                self.year -= 1
            else:
                self.month -= 1
            self._refresh()

        def _next_month(self):
            if self.month == 12:
                self.month = 1
                self.year += 1
            else:
                self.month += 1
            self._refresh()

        def _refresh(self):
            self.win.destroy()
            self._build()

        def _add_hours(self):
            self.app._add_hours_callback(None)

        def _show_chart(self):
            self.app._show_chart_callback(None)


    # ─────────────────────────────────────────────────────────
    #  CHART WINDOW
    # ─────────────────────────────────────────────────────────

    def show_chart_window():
        """Show a bar chart of monthly consumption using matplotlib."""
        try:
            import matplotlib
            matplotlib.use("TkAgg")
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            from matplotlib.figure import Figure
        except ImportError:
            messagebox.showerror(
                "Error", "matplotlib no está instalado.\nEjecuta: pip install matplotlib"
            )
            return

        breakdown = db.get_monthly_hours_breakdown()

        if not breakdown:
            messagebox.showinfo("Sin datos", "No hay sesiones registradas aún.")
            return

        win = tk.Toplevel(_init_tk_root())
        win.title("📊 Consumo mensual")
        win.geometry("700x420")
        win.configure(bg=BG_COLOR)

        tk.Label(
            win, text="Horas consumidas por mes",
            font=("Helvetica", 16, "bold"), bg=BG_COLOR, fg=FG_COLOR,
        ).pack(pady=(15, 5))

        # Build chart
        labels = [f"{r['month']}/{r['year']}" for r in breakdown]
        values = [r["hours"] for r in breakdown]

        fig = Figure(figsize=(4, 2.5), dpi=100, facecolor=BG_COLOR)
        ax = fig.add_subplot(111)
        ax.set_facecolor(BG_COLOR)

        bars = ax.bar(range(len(labels)), values, color=ACCENT, width=0.6, edgecolor=BG_COLOR)
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, color=FG_COLOR, fontsize=9)
        ax.set_ylabel("Horas", color=FG_COLOR, fontsize=10)
        ax.tick_params(colors=FG_COLOR, which="both")
        ax.spines["bottom"].set_color(ACCENT_DARK)
        ax.spines["left"].set_color(ACCENT_DARK)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.yaxis.grid(True, color=ACCENT_DARK, linestyle="--", alpha=0.5)

        # Value labels on bars
        for bar, val in zip(bars, values):
            ax.text(
                bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.1,
                format_balance(val),
                ha="center", va="bottom", color=FG_COLOR, fontsize=10, fontweight="bold",
            )

        fig.tight_layout(pad=2)

        canvas = FigureCanvasTkAgg(fig, master=win)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

        tk.Button(
            win, text="Cerrar", command=win.destroy,
            bg=SURFACE, fg=ACCENT, font=("Helvetica", 12),
            relief=tk.FLAT, cursor="hand2", padx=25, pady=8,
        ).pack(pady=(0, 15))

else:
    # Tkinter not available — dummy classes that show rumps alerts
    class CalendarWindow:
        def __init__(self, app_ref):
            rumps.alert(
                "Tkinter no disponible",
                "Instala python-tk para ver el calendario.\n\n"
                "Con Homebrew: brew install python-tk\n"
                "O usa Python de python.org",
            )

    def show_chart_window():
        rumps.alert(
            "Tkinter no disponible",
            "Instala python-tk para ver gráficos.\n\n"
            "Con Homebrew: brew install python-tk",
        )


# ═══════════════════════════════════════════════════════════════
#  MAIN MENU BAR APP
# ═══════════════════════════════════════════════════════════════


class ZoomFrenchTracker(rumps.App):
    def __init__(self):
        super().__init__(
            name="ZoomFrenchTracker",
            title="🇫🇷 --h",
        )
        self.zoom_running = False
        self.active_session_id: int | None = None
        self.calendar_window: CalendarWindow | None = None

        # Alert deduplication flags (reset when credits are added)
        self._alert_2h_fired = False
        self._alert_1h_fired = False

        db.init_db()
        self._update_display()
        self._build_menu()

        # Poll Zoom status every 5 seconds
        self.timer = rumps.Timer(self._tick, 5)
        self.timer.start()

        # Restore any orphaned active session
        active = db.get_active_session()
        if active:
            db.cancel_session(active["id"])

    # ── Menu ──────────────────────────────────────────────────

    def _build_menu(self):
        self.menu.clear()
        self.menu.update(
            [
                rumps.MenuItem("➕ Agregar horas…", callback=self._add_hours_callback),
                rumps.MenuItem("📅 Ver calendario", callback=self._show_calendar),
                rumps.MenuItem("📊 Ver gráfico", callback=self._show_chart_callback),
                None,  # separator
                rumps.MenuItem("❌ Salir", callback=self._quit),
            ]
        )

    # ── Tick (polling loop) ───────────────────────────────────

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
            pass  # Never crash the timer

    # ── Zoom lifecycle ────────────────────────────────────────

    def _on_zoom_started(self):
        """Zoom launched — start tracking."""
        # Cancel any orphaned active session
        active = db.get_active_session()
        if active:
            db.cancel_session(active["id"])

        now = datetime.now()
        self.active_session_id = db.start_session(now)
        print(f"[Tracker] Session started at {now.strftime('%H:%M:%S')}")

    def _on_zoom_stopped(self):
        """Zoom quit — finalize the session."""
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
            # Under 3 minutes — ignore
            db.cancel_session(active["id"])
            status = "cancelled (<3 min)"
        else:
            db.end_session(active["id"], end_time, minutes, rounded)
            status = f"completed ({format_balance(rounded)})"
            self._check_alerts()

        print(
            f"[Tracker] Session {status}: "
            f"{start_time.strftime('%H:%M')} → {end_time.strftime('%H:%M')} "
            f"({minutes:.0f} min reales)"
        )

        self.active_session_id = None
        self._update_display()

    # ── Display ───────────────────────────────────────────────

    def _update_display(self):
        balance = db.get_balance()
        self.title = f"🇫🇷 {format_balance(balance)}"
        if balance <= 1:
            self.title = f"⚠️ {format_balance(balance)}"

    # ── Alerts ────────────────────────────────────────────────

    def _check_alerts(self):
        balance = db.get_balance()

        if balance <= 1.0 and not self._alert_1h_fired:
            rumps.notification(
                title="⚠️ Zoom French Tracker",
                subtitle="¡Hora de comprar!",
                message="Solo te queda 1 hora de clase. Compra más horas.",
            )
            self._alert_1h_fired = True
            self._alert_2h_fired = True  # Don't also fire the 2h one later
        elif balance <= 2.0 and not self._alert_2h_fired:
            rumps.notification(
                title="⚠️ Zoom French Tracker",
                subtitle="Horas bajas",
                message="Te quedan 2 horas. Considera comprar más pronto.",
            )
            self._alert_2h_fired = True

    # ── Callbacks ─────────────────────────────────────────────

    def _add_hours_callback(self, _):
        """Prompt user to add purchased hours."""
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

                # Reset alert flags
                self._alert_2h_fired = False
                self._alert_1h_fired = False

                rumps.notification(
                    title="✅ Horas agregadas",
                    subtitle="",
                    message=f"Se agregaron {format_balance(amount)}. "
                    f"Saldo: {format_balance(db.get_balance())}",
                )
            except ValueError:
                rumps.alert("Error", "Ingresa un número válido (ej: 38).")

    def _show_calendar(self, _):
        """Open the calendar + history window."""
        if not TK_AVAILABLE:
            rumps.alert(
                "Tkinter no disponible",
                "Instala python-tk:\nbrew install python-tk",
            )
            return
        if self.calendar_window is not None:
            try:
                self.calendar_window.win.lift()
                self.calendar_window.win.focus_force()
                return
            except Exception:
                self.calendar_window = None
        self.calendar_window = CalendarWindow(self)

    def _show_chart_callback(self, _):
        """Open the chart window."""
        if not TK_AVAILABLE:
            rumps.alert(
                "Tkinter no disponible",
                "Instala python-tk:\nbrew install python-tk",
            )
            return
        show_chart_window()

    def _quit(self, _):
        """Clean up and quit."""
        rumps.quit_application()


# ═══════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    ZoomFrenchTracker().run()