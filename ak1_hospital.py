"""
AK1 Hospital - Hospital Management System
=========================================
Advanced Programming Practice - Project (2nd Year)
Developed by : Aneek Sen

A modern Tkinter desktop application for managing patients, doctors,
appointments and billing, backed by a local SQLite database
(ak1_hospital.db). Only the Python standard library is required.

Highlights
----------
* Modern UI drawn with Tkinter Canvas: rounded cards, buttons and inputs,
  gradient login & splash screens, animated charts and counters,
  slide-in toast notifications, and a Light / Dark theme switch.
* Responsive (no freezing): every database query runs on a dedicated
  background worker thread. Results are passed back to the Tk main thread
  through a queue polled with `after()`, because Tkinter widgets may only
  be touched from the main thread. Large tables are filled in chunks and
  the search box is debounced.
* Keyboard shortcuts: Ctrl+S save, Ctrl+F search, Esc clear form.

Default login ->  username: admin   password: admin123
Run:  python ak1_hospital.py
"""

import math
import queue
import sqlite3
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from datetime import date, datetime, timedelta
from tkinter import filedialog, messagebox, ttk

HOSPITAL_NAME = "AK1 Hospital"
DEVELOPER = "Aneek Sen"
DEVELOPER_ROLE = "Administrator"
DB_FILE = "ak1_hospital.db"

POLL_MS = 30           # how often the UI checks for finished DB jobs
CHUNK_SIZE = 200       # rows inserted into a table per UI step
SEARCH_DELAY_MS = 250  # wait this long after the last keystroke before filtering

# ================================================================ THEME ===
THEMES = {
    "light": {
        "bg": "#f1f5f9", "card": "#ffffff", "text": "#0f172a", "muted": "#64748b",
        "border": "#e2e8f0", "shadow": "#e3e8ef", "input": "#f8fafc",
        "input_border": "#cbd5e1", "head": "#f8fafc", "stripe": "#fafbfd",
        "hover": "#eef4ff",
        "primary": "#2563eb", "accent": "#0d9488", "success": "#16a34a",
        "warning": "#d97706", "danger": "#dc2626", "violet": "#7c3aed",
        "sidebar": "#0f172a", "sidebar_active": "#1e293b", "sidebar_text": "#94a3b8",
        "grad1": "#1d4ed8", "grad2": "#0d9488",
    },
    "dark": {
        "bg": "#0b1120", "card": "#111827", "text": "#e2e8f0", "muted": "#94a3b8",
        "border": "#1f2937", "shadow": "#060a14", "input": "#0f172a",
        "input_border": "#334155", "head": "#162032", "stripe": "#131c2e",
        "hover": "#1a2540",
        "primary": "#3b82f6", "accent": "#14b8a6", "success": "#22c55e",
        "warning": "#f59e0b", "danger": "#f87171", "violet": "#a78bfa",
        "sidebar": "#020617", "sidebar_active": "#111c33", "sidebar_text": "#94a3b8",
        "grad1": "#1e3a8a", "grad2": "#115e59",
    },
}
C = dict(THEMES["light"])   # the active palette; widgets read it when built

UI = "Segoe UI"
F_BODY = (UI, 10)
F_SMALL = (UI, 9)
F_LABEL = (UI, 9, "bold")
F_SEMI = ("Segoe UI Semibold", 10)
F_H1 = ("Segoe UI Semibold", 20)
F_H2 = ("Segoe UI Semibold", 13)
F_NUM = ("Segoe UI Semibold", 22)

# Icons: Windows "Segoe MDL2 Assets" glyphs, with plain-text fallbacks
ICONS = {
    "dashboard": ("", "⌂"), "patients": ("", "☺"),
    "doctors": ("", "⚕"), "appointments": ("", "◷"),
    "billing": ("", "₹"), "about": ("", "i"),
    "search": ("", "⌕"), "sun": ("", "☀"), "moon": ("", "☾"),
    "logout": ("", "⏻"), "add": ("", "+"), "edit": ("", "✎"),
    "delete": ("", "✕"), "clear": ("", "↺"), "print": ("", "⎙"),
    "save": ("", "✓"), "user": ("", "☺"), "lock": ("", "⚿"),
    "check": ("", "✓"), "error": ("", "!"), "info": ("", "i"),
    "clock": ("", "◷"), "heart": ("", "♥"),
}
_ICON_FAMILY = None


def init_icons(root):
    global _ICON_FAMILY
    families = set(tkfont.families(root))
    for fam in ("Segoe MDL2 Assets", "Segoe Fluent Icons"):
        if fam in families:
            _ICON_FAMILY = fam
            return


def icon(name):
    glyph, fallback = ICONS[name]
    return glyph if _ICON_FAMILY else fallback


def icon_font(size=12):
    return (_ICON_FAMILY or "Segoe UI Symbol", size)


# ---- colour helpers
def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def blend(c1, c2, t):
    """Mix two hex colours: t=0 gives c1, t=1 gives c2."""
    a, b = _rgb(c1), _rgb(c2)
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def tint(color, amount=0.86):
    """A soft background version of `color` for the current theme."""
    return blend(color, C["card"], amount)


def ease(t):
    return 1 - (1 - t) ** 3


def apply_theme(root, name):
    C.clear()
    C.update(THEMES[name])
    s = ttk.Style(root)
    s.theme_use("clam")
    s.configure("Modern.Treeview", background=C["card"], fieldbackground=C["card"],
                foreground=C["text"], rowheight=36, borderwidth=0, font=F_BODY)
    s.layout("Modern.Treeview", [("Modern.Treeview.treearea", {"sticky": "nswe"})])
    s.configure("Modern.Treeview.Heading", background=C["head"], foreground=C["muted"],
                font=F_LABEL, relief="flat", borderwidth=0, padding=(4, 9))
    s.map("Modern.Treeview.Heading", background=[("active", C["head"])])
    s.map("Modern.Treeview", background=[("selected", tint(C["primary"], 0.78))],
          foreground=[("selected", C["text"])])
    for orient in ("Vertical", "Horizontal"):
        s.configure(f"{orient}.TScrollbar", background=C["border"], troughcolor=C["card"],
                    bordercolor=C["card"], arrowcolor=C["muted"], lightcolor=C["border"],
                    darkcolor=C["border"], gripcount=0, arrowsize=11)
        s.map(f"{orient}.TScrollbar", background=[("active", C["input_border"])])
    s.configure("Field.TCombobox", fieldbackground=C["input"], background=C["input"],
                foreground=C["text"], arrowcolor=C["muted"], bordercolor=C["input"],
                lightcolor=C["input"], darkcolor=C["input"], padding=(4, 2), arrowsize=13)
    s.map("Field.TCombobox",
          fieldbackground=[("readonly", C["input"])],
          background=[("readonly", C["input"]), ("active", C["input"])],
          foreground=[("readonly", C["text"])],
          selectbackground=[("readonly", C["input"])],
          selectforeground=[("readonly", C["text"])],
          bordercolor=[("focus", C["input"])], lightcolor=[("focus", C["input"])],
          darkcolor=[("focus", C["input"])])
    root.option_add("*TCombobox*Listbox.background", C["card"])
    root.option_add("*TCombobox*Listbox.foreground", C["text"])
    root.option_add("*TCombobox*Listbox.selectBackground", C["primary"])
    root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
    root.option_add("*TCombobox*Listbox.font", F_BODY)
    root.configure(bg=C["bg"])


# ============================================================= DATABASE ===
class Database:
    """
    SQLite access on a background thread.

    The connection is created and used only inside the worker thread
    (SQLite connections are bound to the thread that created them).
    The UI calls `run(job, on_done, on_error)`; `job(db)` executes on the
    worker, and the callbacks are later invoked on the Tk main thread.
    """

    def __init__(self, root, path=DB_FILE):
        self.root = root
        self.conn = None
        self.on_busy = None          # optional callback(bool) for a busy indicator
        self._pending = 0
        self._jobs = queue.Queue()
        self._results = queue.Queue()
        self._init_error = None
        self._thread = threading.Thread(target=self._worker, args=(path,), daemon=True)
        self._thread.start()
        self._poll_id = self.root.after(POLL_MS, self._poll)

    # ---- worker thread side
    def _worker(self, path):
        try:
            self.conn = sqlite3.connect(path)
            self.conn.execute("PRAGMA foreign_keys = ON")
            self._create_tables()
            self._seed()
        except Exception as e:  # report on every job instead of dying silently
            self._init_error = e

        while True:
            item = self._jobs.get()
            if item is None:
                break
            job, on_done, on_error = item
            try:
                if self._init_error:
                    raise self._init_error
                result, error = job(self), None
            except Exception as e:
                result, error = None, e
            self._results.put((on_done, on_error, result, error))

        if self.conn:
            self.conn.close()

    def _create_tables(self):
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users(
                username TEXT PRIMARY KEY, password TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS settings(
                key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS patients(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL, age INTEGER, gender TEXT,
                phone TEXT, blood_group TEXT, address TEXT, disease TEXT,
                admitted_on TEXT);
            CREATE TABLE IF NOT EXISTS doctors(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL, specialization TEXT, phone TEXT,
                experience INTEGER, fee REAL);
            CREATE TABLE IF NOT EXISTS appointments(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id INTEGER REFERENCES patients(id) ON DELETE CASCADE,
                doctor_id INTEGER REFERENCES doctors(id) ON DELETE CASCADE,
                date TEXT, time TEXT, status TEXT);
            CREATE TABLE IF NOT EXISTS bills(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id INTEGER REFERENCES patients(id) ON DELETE CASCADE,
                consultation REAL, medicine REAL, room REAL, lab REAL,
                total REAL, date TEXT, paid TEXT);
            """
        )
        self.conn.commit()

    def _seed(self):
        """Insert sample data the first time the app runs."""
        if self.query("SELECT COUNT(*) FROM users")[0][0]:
            return
        today = date.today()
        day = lambda offset: (today + timedelta(days=offset)).isoformat()
        cur = self.conn.cursor()
        cur.execute("INSERT INTO users VALUES(?, ?)", ("admin", "admin123"))
        cur.executemany(
            "INSERT INTO doctors(name, specialization, phone, experience, fee) VALUES(?,?,?,?,?)",
            [("Dr. Riya Sharma", "Cardiologist", "9830011111", 12, 800),
             ("Dr. Arjun Mehta", "Neurologist", "9830022222", 9, 900),
             ("Dr. Sneha Das", "Pediatrician", "9830033333", 7, 600),
             ("Dr. Kunal Roy", "Orthopedic", "9830044444", 15, 750),
             ("Dr. Ananya Iyer", "Dermatologist", "9830055555", 6, 650),
             ("Dr. Vikram Bose", "General Physician", "9830066666", 20, 500)])
        cur.executemany(
            "INSERT INTO patients(name, age, gender, phone, blood_group, address, disease,"
            " admitted_on) VALUES(?,?,?,?,?,?,?,?)",
            [("Rahul Verma", 34, "Male", "9876500001", "B+", "Kolkata", "Hypertension", day(-6)),
             ("Priya Singh", 27, "Female", "9876500002", "O+", "Howrah", "Migraine", day(-5)),
             ("Amit Ghosh", 8, "Male", "9876500003", "A-", "Salt Lake", "Viral Fever", day(-4)),
             ("Neha Kapoor", 45, "Female", "9876500004", "AB+", "New Town", "Skin Allergy", day(-3)),
             ("Sourav Paul", 52, "Male", "9876500005", "O-", "Dum Dum", "Knee Pain", day(-2)),
             ("Ishita Roy", 31, "Female", "9876500006", "A+", "Behala", "Thyroid", day(-1)),
             ("Arnab Dutta", 63, "Male", "9876500007", "B-", "Garia", "Diabetes", day(0)),
             ("Meera Nair", 22, "Female", "9876500008", "O+", "Park Street", "Asthma", day(0))])
        cur.executemany(
            "INSERT INTO appointments(patient_id, doctor_id, date, time, status) VALUES(?,?,?,?,?)",
            [(p, d, day(o), t, s) for p, d, o, t, s in (
                (1, 1, -6, "10:00", "Completed"), (2, 2, -6, "11:30", "Completed"),
                (3, 3, -5, "09:30", "Completed"), (4, 5, -4, "12:00", "Cancelled"),
                (5, 4, -4, "15:00", "Completed"), (6, 6, -3, "10:30", "Completed"),
                (7, 1, -3, "16:00", "Completed"), (8, 6, -2, "11:00", "Completed"),
                (1, 1, -1, "09:00", "Completed"), (2, 2, -1, "13:30", "Completed"),
                (3, 3, -1, "17:00", "Cancelled"), (4, 5, 0, "10:30", "Scheduled"),
                (5, 4, 0, "12:15", "Scheduled"), (7, 6, 0, "16:45", "Scheduled"),
                (6, 1, 1, "11:00", "Scheduled"), (8, 2, 2, "10:00", "Scheduled"),
                (1, 4, 3, "14:30", "Scheduled"))])
        cur.executemany(
            "INSERT INTO bills(patient_id, consultation, medicine, room, lab, total, date, paid)"
            " VALUES(?,?,?,?,?,?,?,?)",
            [(p, c, m, r, l, c + m + r + l, day(o), s) for p, c, m, r, l, o, s in (
                (1, 800, 1200, 2500, 900, -5, "Paid"), (2, 900, 450, 0, 300, -5, "Paid"),
                (3, 600, 350, 0, 250, -4, "Paid"), (5, 750, 900, 3000, 1200, -3, "Unpaid"),
                (6, 500, 300, 0, 400, -2, "Paid"), (8, 500, 650, 1500, 0, -1, "Unpaid"))])
        self.conn.commit()

    # Only call these from inside a job (i.e. on the worker thread).
    def execute(self, sql, params=()):
        cur = self.conn.execute(sql, params)
        self.conn.commit()
        return cur

    def query(self, sql, params=()):
        return self.conn.execute(sql, params).fetchall()

    def get_setting(self, key, default=None):
        r = self.query("SELECT value FROM settings WHERE key=?", (key,))
        return r[0][0] if r else default

    def set_setting(self, key, value):
        self.execute("INSERT OR REPLACE INTO settings(key, value) VALUES(?, ?)", (key, value))

    # ---- main (Tk) thread side
    def run(self, job, on_done=None, on_error=None):
        """Queue `job(db)` on the worker thread. Call from the Tk thread only."""
        self._pending += 1
        if self._pending == 1 and self.on_busy:
            self.on_busy(True)
        self._jobs.put((job, on_done, on_error))

    def _poll(self):
        while True:
            try:
                on_done, on_error, result, error = self._results.get_nowait()
            except queue.Empty:
                break
            self._pending -= 1
            try:
                if error is None:
                    if on_done:
                        on_done(result)
                elif on_error:
                    on_error(error)
                else:
                    messagebox.showerror("Database error", str(error))
            except tk.TclError:
                # The widget that asked for this data was destroyed (e.g. logout)
                pass
            if self._pending == 0 and self.on_busy:
                try:
                    self.on_busy(False)
                except tk.TclError:
                    pass
        self._poll_id = self.root.after(POLL_MS, self._poll)

    def close(self):
        self.root.after_cancel(self._poll_id)
        self._jobs.put(None)
        self._thread.join(timeout=2)


# ===================================================== CUSTOM WIDGETS ===
def round_rect(cv, x1, y1, x2, y2, r, **kw):
    """Draw a rounded rectangle on a canvas (smoothed polygon)."""
    r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
           x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return cv.create_polygon(pts, smooth=True, **kw)


def initials(name):
    parts = [p for p in name.replace("Dr.", "").split() if p]
    return "".join(p[0] for p in parts[:2]).upper() or "?"


def avatar(master, text, size=36, color=None, fg="#ffffff"):
    cv = tk.Canvas(master, width=size, height=size, bg=master["bg"],
                   highlightthickness=0, bd=0)
    cv.create_oval(1, 1, size - 1, size - 1, fill=color or C["primary"], outline="")
    cv.create_text(size / 2, size / 2, text=text, fill=fg,
                   font=("Segoe UI Semibold", max(8, int(size * 0.33))))
    return cv


def animate_number(label, target, fmt="{:,.0f}", steps=28, delay=16):
    """Count a label up from 0 to `target`."""
    def step(i=1):
        if not label.winfo_exists():
            return
        label.config(text=fmt.format(target * ease(i / steps)))
        if i < steps:
            label.after(delay, step, i + 1)
    step()


class Card(tk.Canvas):
    """A rounded, softly shadowed panel. Put children inside `card.inner`."""

    def __init__(self, master, pad=20, radius=16, bg=None, shadow=True, **kw):
        super().__init__(master, bg=master["bg"], highlightthickness=0, bd=0, **kw)
        self.fill = bg or C["card"]
        self.pad, self.radius, self.shadow = pad, radius, shadow
        self.inner = tk.Frame(self, bg=self.fill)
        self._win = self.create_window(pad, pad, window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", self._fit, add="+")
        self.bind("<Configure>", self._redraw)
        self.after_idle(self._fit)

    def _fit(self, _event=None):
        if not self.winfo_exists():
            return
        w = self.inner.winfo_reqwidth() + 2 * self.pad
        h = self.inner.winfo_reqheight() + 2 * self.pad + 3
        if int(self["width"]) != w or int(self["height"]) != h:
            self.configure(width=w, height=h)

    def _redraw(self, event):
        w, h = event.width, event.height
        self.delete("bg")
        if self.shadow:
            round_rect(self, 1, 3, w - 1, h - 1, self.radius, fill=C["shadow"],
                       outline="", tags="bg")
        round_rect(self, 0, 0, w - 1, h - 4, self.radius, fill=self.fill,
                   outline=C["border"], tags="bg")
        self.tag_lower("bg")
        self.itemconfigure(self._win, width=max(1, w - 2 * self.pad),
                           height=max(1, h - 2 * self.pad - 3))


class RoundButton(tk.Canvas):
    """A rounded button with an optional icon and a hover effect."""

    def __init__(self, master, text="", command=None, color=None, fg="#ffffff",
                 icon_name=None, width=None, height=38, radius=10, font=F_SEMI,
                 outline=None):
        super().__init__(master, height=height, bg=master["bg"], highlightthickness=0,
                         bd=0, cursor="hand2")
        self.text, self.icon_name, self.command = text, icon_name, command
        self.color = color or C["primary"]
        self.fg, self.font, self.radius, self.h, self.outline = fg, font, radius, height, outline
        self.hover_color = blend(self.color, fg if color in (C["card"], C["input"]) or
                                 _is_light(self.color) else "#000000", 0.10)
        tw = tkfont.Font(font=font).measure(text) if text else 0
        iw = tkfont.Font(font=icon_font(11)).measure(icon(icon_name)) if icon_name else 0
        self.gap = 8 if text and icon_name else 0
        self.tw, self.iw = tw, iw
        self.configure(width=width or tw + iw + self.gap + 36)
        self.enabled, self.hovered = True, False
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<ButtonRelease-1>", self._click)
        self._draw()

    def _set_hover(self, on):
        self.hovered = on
        self._draw()

    def _draw(self):
        self.delete("all")
        w = self.winfo_width() if self.winfo_width() > 1 else int(self["width"])
        h = self.h
        if not self.enabled:
            fill, fg = blend(self.color, C["card"], 0.5), blend(self.fg, C["card"], 0.35)
        else:
            fill, fg = (self.hover_color if self.hovered else self.color), self.fg
        round_rect(self, 1, 1, w - 2, h - 2, self.radius, fill=fill,
                   outline=self.outline or fill)
        x = (w - (self.tw + self.iw + self.gap)) / 2
        if self.icon_name:
            self.create_text(x + self.iw / 2, h / 2 + 1, text=icon(self.icon_name),
                             font=icon_font(11), fill=fg)
            x += self.iw + self.gap
        if self.text:
            self.create_text(x, h / 2, text=self.text, font=self.font, fill=fg, anchor="w")

    def _click(self, event):
        inside = 0 <= event.x <= self.winfo_width() and 0 <= event.y <= self.winfo_height()
        if self.enabled and inside and self.command:
            self.command()

    def set_enabled(self, on):
        self.enabled = on
        self.configure(cursor="hand2" if on else "arrow")
        self._draw()


def _is_light(color):
    r, g, b = _rgb(color)
    return (0.299 * r + 0.587 * g + 0.114 * b) > 170


class Field(tk.Canvas):
    """A rounded input box wrapping a tk.Entry or ttk.Combobox (`.widget`)."""

    def __init__(self, master, kind="entry", values=(), width=240, height=38, show="",
                 icon_name=None, placeholder="", textvariable=None):
        super().__init__(master, width=width, height=height, bg=master["bg"],
                         highlightthickness=0, bd=0)
        self.h, self.focused = height, False
        self.x = 38 if icon_name else 12
        if icon_name:
            self.create_text(20, height / 2 + 1, text=icon(icon_name), font=icon_font(11),
                             fill=C["muted"], tags="icon")
        if kind == "combo":
            self.widget = ttk.Combobox(self, values=list(values), state="readonly",
                                       style="Field.TCombobox", font=F_BODY)
            self._win = self.create_window(self.x - 6, height / 2, window=self.widget,
                                           anchor="w", height=height - 8)
        else:
            self.widget = tk.Entry(self, relief="flat", bd=0, bg=C["input"], fg=C["text"],
                                   insertbackground=C["text"], font=F_BODY, show=show,
                                   textvariable=textvariable)
            self._win = self.create_window(self.x, height / 2, window=self.widget,
                                           anchor="w", height=height - 12)
        self.ph, self.var = None, textvariable
        if placeholder and textvariable is not None:
            ph = tk.Label(self, text=placeholder, bg=C["input"], fg=C["muted"], font=F_BODY,
                          anchor="w", cursor="xterm")
            ph.bind("<Button-1>", lambda e: self.widget.focus_set())
            self.ph = self.create_window(self.x, height / 2, window=ph, anchor="w")
            textvariable.trace_add("write", lambda *_: self._update_placeholder())
        self.widget.bind("<FocusIn>", lambda e: self._focus(True), add="+")
        self.widget.bind("<FocusOut>", lambda e: self._focus(False), add="+")
        self.bind("<Configure>", lambda e: self._draw())
        self._draw()

    def _focus(self, on):
        self.focused = on
        self._draw()
        self._update_placeholder()

    def _update_placeholder(self):
        if self.ph is not None:
            show = not self.var.get() and not self.focused
            self.itemconfigure(self.ph, state="normal" if show else "hidden")

    def _draw(self):
        w = self.winfo_width() if self.winfo_width() > 1 else int(self["width"])
        self.delete("border")
        round_rect(self, 1, 1, w - 2, self.h - 2, 10, fill=C["input"],
                   outline=C["primary"] if self.focused else C["input_border"],
                   width=2 if self.focused else 1, tags="border")
        self.tag_lower("border")
        self.itemconfigure(self._win, width=max(10, w - self.x - 8))


class Pill(tk.Canvas):
    """A small rounded badge, e.g. a status or a count."""

    def __init__(self, master, text, color, height=24, font=(UI, 9, "bold")):
        super().__init__(master, height=height, width=10, bg=master["bg"],
                         highlightthickness=0, bd=0)
        self.font, self.h = font, height
        self.set(text, color)

    def set(self, text, color):
        w = tkfont.Font(font=self.font).measure(text) + 22
        self.configure(width=w)
        self.delete("all")
        round_rect(self, 0, 0, w, self.h, self.h / 2, fill=tint(color, 0.82), outline="")
        self.create_text(w / 2, self.h / 2, text=text, fill=color, font=self.font)


class Gradient(tk.Canvas):
    """A vertical gradient. `overlay(canvas, w, h)` draws content on top."""

    def __init__(self, master, c1, c2, overlay=None, radius=0, **kw):
        super().__init__(master, highlightthickness=0, bd=0, bg=c1, **kw)
        self.c1, self.c2, self.overlay, self.radius = c1, c2, overlay, radius
        self.mask = master["bg"]
        self._job = None
        self.bind("<Configure>", self._schedule)

    def _schedule(self, _event):
        if self._job:
            self.after_cancel(self._job)
        self._job = self.after(10, self.redraw)

    def redraw(self):
        self._job = None
        w, h = self.winfo_width(), self.winfo_height()
        self.delete("all")
        for y in range(0, h, 2):
            self.create_line(0, y, w, y, width=2,
                             fill=blend(self.c1, self.c2, y / max(h - 1, 1)))
        if self.overlay:
            self.overlay(self, w, h)
        if self.radius:
            self._mask_corners(w, h, self.radius)

    def _mask_corners(self, w, h, r):
        for cx, cy, a0 in ((r, r, 90), (w - r, r, 0), (w - r, h - r, 270), (r, h - r, 180)):
            corner = (cx + (r if a0 in (0, 270) else -r), cy + (-r if a0 in (90, 0) else r))
            pts = [corner]
            for i in range(11):
                a = math.radians(a0 + 9 * i)
                pts.append((cx + r * math.cos(a), cy - r * math.sin(a)))
            self.create_polygon(pts, fill=self.mask, outline=self.mask)


class NavItem(tk.Canvas):
    """A sidebar menu entry with a rounded highlight."""

    def __init__(self, master, icon_name, text, command, width=218):
        super().__init__(master, width=width, height=42, bg=C["sidebar"],
                         highlightthickness=0, bd=0, cursor="hand2")
        self.icon_name, self.text, self.command = icon_name, text, command
        self.active = self.hovered = False
        self.bind("<Enter>", lambda e: self._hover(True))
        self.bind("<Leave>", lambda e: self._hover(False))
        self.bind("<ButtonRelease-1>", lambda e: self.command())
        self._draw()

    def _hover(self, on):
        self.hovered = on
        self._draw()

    def set_active(self, on):
        self.active = on
        self._draw()

    def _draw(self):
        self.delete("all")
        w, h = int(self["width"]), 42
        if self.active:
            round_rect(self, 0, 2, w, h - 2, 10, fill=C["primary"], outline="")
        elif self.hovered:
            round_rect(self, 0, 2, w, h - 2, 10, fill=C["sidebar_active"], outline="")
        fg = "#ffffff" if self.active or self.hovered else C["sidebar_text"]
        self.create_text(24, h / 2 + 1, text=icon(self.icon_name), font=icon_font(12), fill=fg)
        self.create_text(48, h / 2, text=self.text, anchor="w", fill=fg,
                         font=(UI, 10, "bold") if self.active else (UI, 10))


class Toast:
    """Slide-in notification in the bottom-right corner."""
    current = None

    @classmethod
    def show(cls, root, message, kind="success", ms=2600):
        if cls.current is not None and cls.current.winfo_exists():
            cls.current.destroy()
        color = {"success": C["success"], "error": C["danger"],
                 "info": C["primary"], "warning": C["warning"]}[kind]
        glyph = {"success": "check", "error": "error", "info": "info", "warning": "error"}[kind]
        card = tk.Frame(root, bg=C["card"], highlightthickness=1,
                        highlightbackground=C["border"])
        tk.Frame(card, bg=color, width=4).pack(side="left", fill="y")
        badge = tk.Canvas(card, width=30, height=30, bg=C["card"], highlightthickness=0)
        badge.create_oval(1, 1, 29, 29, fill=tint(color, 0.8), outline="")
        badge.create_text(15, 16, text=icon(glyph), font=icon_font(10), fill=color)
        badge.pack(side="left", padx=(12, 10), pady=12)
        tk.Label(card, text=message, bg=C["card"], fg=C["text"], font=F_SEMI,
                 wraplength=320, justify="left").pack(side="left", padx=(0, 20), pady=12)
        cls.current = card

        def slide(step, out=False):
            if not card.winfo_exists():
                return
            t = ease(step / 12)
            offset = t * 420 if out else (1 - t) * 420
            card.place(relx=1.0, rely=1.0, x=-28 + offset, y=-52, anchor="se")
            card.lift()
            if step < 12:
                root.after(16, slide, step + 1, out)
            elif out:
                card.destroy()
        slide(0)
        root.after(ms, lambda: slide(0, out=True))


# ========================================================== SPLASH/LOGIN ===
class LoginPage(tk.Frame):
    def __init__(self, master, app):
        super().__init__(master, bg=C["card"])
        self.app, self.db = app, app.db
        self.columnconfigure(0, weight=45, uniform="cols")
        self.columnconfigure(1, weight=55, uniform="cols")
        self.rowconfigure(0, weight=1)
        Gradient(self, C["grad1"], C["grad2"], overlay=self._art).grid(row=0, column=0,
                                                                        sticky="nsew")
        right = tk.Frame(self, bg=C["card"])
        right.grid(row=0, column=1, sticky="nsew")

        self.form = form = tk.Frame(right, bg=C["card"])
        form.place(relx=0.5, rely=0.47, anchor="center")
        Pill(form, "SECURE LOGIN", C["primary"]).pack(anchor="w")
        tk.Label(form, text="Welcome back", font=("Segoe UI Semibold", 24), bg=C["card"],
                 fg=C["text"]).pack(anchor="w", pady=(10, 0))
        tk.Label(form, text=f"Sign in to continue to {HOSPITAL_NAME}", font=(UI, 11),
                 bg=C["card"], fg=C["muted"]).pack(anchor="w", pady=(0, 26))

        tk.Label(form, text="Username", font=F_LABEL, bg=C["card"],
                 fg=C["text"]).pack(anchor="w", pady=(0, 6))
        self.user_f = Field(form, icon_name="user", width=340, height=44)
        self.user_f.pack()
        tk.Label(form, text="Password", font=F_LABEL, bg=C["card"],
                 fg=C["text"]).pack(anchor="w", pady=(16, 6))
        self.pwd_f = Field(form, icon_name="lock", width=340, height=44, show="•")
        self.pwd_f.pack()
        self.user, self.pwd = self.user_f.widget, self.pwd_f.widget

        row = tk.Frame(form, bg=C["card"])
        row.pack(fill="x", pady=(12, 0))
        self.show_var = tk.BooleanVar()
        tk.Checkbutton(row, text="Show password", variable=self.show_var,
                       command=lambda: self.pwd.config(show="" if self.show_var.get() else "•"),
                       bg=C["card"], fg=C["muted"], activebackground=C["card"],
                       activeforeground=C["text"], selectcolor=C["input"], font=F_SMALL,
                       bd=0, highlightthickness=0, cursor="hand2").pack(side="left")
        forgot = tk.Label(row, text="Forgot password?", bg=C["card"], fg=C["primary"],
                          font=(UI, 9, "bold"), cursor="hand2")
        forgot.pack(side="right")
        forgot.bind("<Button-1>", lambda e: Toast.show(
            self.app, "Please contact the system administrator.", "info"))

        self.error = tk.Label(form, text="", bg=C["card"], fg=C["danger"], font=F_SEMI)
        self.error.pack(anchor="w", pady=(10, 4))
        self.login_btn = RoundButton(form, "Sign In  →", self.login, width=340, height=46,
                                     font=("Segoe UI Semibold", 11))
        self.login_btn.pack()

        hint = tk.Frame(form, bg=C["card"])
        hint.pack(pady=(22, 0))
        tk.Label(hint, text=icon("info"), font=icon_font(10), bg=C["card"],
                 fg=C["muted"]).pack(side="left", padx=(0, 6))
        tk.Label(hint, text="Demo login:  admin  /  admin123", font=F_SMALL,
                 bg=C["card"], fg=C["muted"]).pack(side="left")

        tk.Label(right, text=f"© {date.today().year} {HOSPITAL_NAME}  ·  Developed by {DEVELOPER}",
                 font=F_SMALL, bg=C["card"], fg=C["muted"]).place(relx=0.5, rely=1.0, y=-22,
                                                                  anchor="center")

        self.user.focus_set()
        self.pwd.bind("<Return>", lambda e: self.login())
        self.user.bind("<Return>", lambda e: self.pwd.focus_set())

    def _art(self, cv, w, h):
        """Branding drawn on the gradient panel."""
        white = "#ffffff"
        soft = blend(C["grad1"], white, 0.10)
        cv.create_oval(-160, -160, 260, 260, fill=soft, outline="")
        cv.create_oval(w - 220, h - 240, w + 180, h + 160, fill=blend(C["grad2"], white, 0.10),
                       outline="")
        cv.create_oval(w - 150, 70, w - 70, 150, outline=blend(C["grad1"], white, 0.35), width=2)
        cv.create_oval(w - 110, 170, w - 92, 188, fill=blend(C["grad1"], white, 0.35), outline="")

        x, y = 64, max(90, h * 0.2)
        round_rect(cv, x, y, x + 64, y + 64, 18, fill=white, outline="")
        cv.create_text(x + 32, y + 32, text="✚", fill=C["primary"], font=(UI, 28, "bold"))
        cv.create_text(x, y + 104, text=HOSPITAL_NAME, anchor="w", fill=white,
                       font=("Segoe UI Semibold", 32))
        cv.create_text(x, y + 144, text="Hospital Management System", anchor="w",
                       fill=blend(white, C["grad1"], 0.18), font=(UI, 14))
        cv.create_text(x, y + 190, anchor="nw", width=max(200, w - 2 * x),
                       fill=blend(white, C["grad1"], 0.25), font=(UI, 11),
                       text="Smart, simple and secure management of patients, doctors, "
                            "appointments and billing, all in one place.")
        features = ["Patient & doctor records", "Appointment scheduling",
                    "Billing with printable receipts", "Fast, responsive & thread-safe"]
        for i, feat in enumerate(features):
            fy = y + 268 + i * 38
            cv.create_oval(x, fy - 12, x + 24, fy + 12, fill=blend(C["grad1"], white, 0.22),
                           outline="")
            cv.create_text(x + 12, fy + 1, text=icon("check"), font=icon_font(9), fill=white)
            cv.create_text(x + 38, fy, text=feat, anchor="w", fill=white, font=(UI, 11))
        cv.create_text(x, h - 36, anchor="w", fill=blend(white, C["grad2"], 0.3), font=F_SMALL,
                       text=f"Advanced Programming Practice  ·  Project by {DEVELOPER}")

    def login(self):
        if not self.login_btn.enabled:
            return  # a check is already running
        user, pwd = self.user.get().strip(), self.pwd.get()
        if not user or not pwd:
            self._fail("Please enter both username and password.")
            return
        self.error.config(text="")
        self.login_btn.text = "Signing in…"
        self.login_btn.set_enabled(False)
        self.db.run(
            lambda db: bool(db.query("SELECT 1 FROM users WHERE username=? AND password=?",
                                     (user, pwd))),
            lambda ok: self.app.build_main(user) if ok else self._fail(
                "Invalid username or password."),
            lambda err: self._fail(f"Database error: {err}"))

    def _fail(self, msg):
        self.login_btn.text = "Sign In  →"
        self.login_btn.set_enabled(True)
        self.error.config(text=msg)
        self.pwd.delete(0, tk.END)
        self.pwd.focus_set()
        self._shake()

    def _shake(self, i=0):
        offsets = [-14, 14, -10, 10, -6, 6, -2, 0]
        if i < len(offsets) and self.form.winfo_exists():
            self.form.place_configure(x=offsets[i])
            self.after(28, self._shake, i + 1)


# ========================================================= CRUD SECTION ===
class CrudPage(tk.Frame):
    """
    Generic page: a form card on the left and a searchable table card on the
    right. Subclasses define `fields`, `columns`, titles and the SQL helpers.
    `fields` is a list of (key, label, kind, options) where kind is 'entry'
    or 'combo'. For combos, `options` is a list or a function `options(db)`
    that runs on the DB thread.

    SQL helpers (fetch_rows, load_record, insert, modify, remove) receive
    `db` and run on the background thread, so they must NOT touch widgets.
    """
    form_title = table_title = noun = ""
    columns = []

    def __init__(self, master, app):
        super().__init__(master, bg=C["bg"])
        self.app = app
        self.db = app.db
        self.selected_id = None
        self.widgets = {}
        self.action_buttons = []
        self.rows = []              # last rows loaded from the DB
        self._fill_token = 0        # cancels an older chunked table fill
        self._search_after = None
        self._hover_item = None
        self._build()

    # ---- layout
    def _build(self):
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        form_card = Card(self, pad=22)
        form_card.grid(row=0, column=0, sticky="ns", padx=(0, 20), pady=(0, 6))
        f = self.form = form_card.inner
        head = tk.Frame(f, bg=C["card"])
        head.pack(fill="x")
        tk.Label(head, text=self.form_title, font=F_H2, bg=C["card"],
                 fg=C["text"]).pack(side="left")
        self.mode_pill = Pill(head, "NEW", C["success"])
        self.mode_pill.pack(side="right")
        tk.Label(f, text="Fill in the details and press Save.", font=F_SMALL, bg=C["card"],
                 fg=C["muted"]).pack(anchor="w", pady=(2, 14))

        grid = tk.Frame(f, bg=C["card"])
        grid.pack(fill="x")
        for i, (key, label, kind, options) in enumerate(self.fields):
            tk.Label(grid, text=label, font=F_LABEL, bg=C["card"], fg=C["muted"]).grid(
                row=i, column=0, sticky="w", pady=4, padx=(0, 12))
            fld = Field(grid, kind, values=[] if callable(options) else options,
                        width=214, height=34)
            fld.grid(row=i, column=1, pady=4)
            self.widgets[key] = fld.widget

        self.extra = tk.Frame(f, bg=C["card"])
        self.extra.pack(fill="x")

        self.btns = btns = tk.Frame(f, bg=C["card"])
        btns.pack(fill="x", pady=(16, 0))
        for i, (text, cmd, color, ic) in enumerate((
                ("Save", self.add_record, C["primary"], "add"),
                ("Update", self.update_record, C["warning"], "edit"),
                ("Delete", self.delete_record, C["danger"], "delete"))):
            b = RoundButton(btns, text, cmd, color=color, icon_name=ic, width=104)
            b.grid(row=0, column=i, padx=(0 if i == 0 else 8, 0))
            self.action_buttons.append(b)
        clear = RoundButton(btns, "Clear form", self.clear, color=C["input"], fg=C["text"],
                            icon_name="clear", outline=C["border"])
        clear.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        self.clear_btn = clear
        self.action_buttons.append(clear)

        table_card = Card(self, pad=20)
        table_card.grid(row=0, column=1, sticky="nsew", pady=(0, 6))
        t = table_card.inner
        head = tk.Frame(t, bg=C["card"])
        head.pack(fill="x")
        tk.Label(head, text=self.table_title, font=F_H2, bg=C["card"],
                 fg=C["text"]).pack(side="left")
        self.count_pill = Pill(head, "Loading…", C["primary"])
        self.count_pill.pack(side="left", padx=10)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self._on_search)
        self.search = Field(head, icon_name="search", width=270, height=38,
                            placeholder=f"Search {self.noun}…", textvariable=self.search_var)
        self.search.pack(side="right")

        table_frame = tk.Frame(t, bg=C["card"])
        table_frame.pack(fill="both", expand=True, pady=(16, 0))
        self.tree = ttk.Treeview(table_frame, columns=[c[0] for c in self.columns],
                                 show="headings", selectmode="browse", style="Modern.Treeview")
        for col, heading, width in self.columns:
            self.tree.heading(col, text=heading.upper())
            self.tree.column(col, width=width, minwidth=40, anchor="center")
        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        self.tree.tag_configure("odd", background=C["stripe"])
        self.tree.tag_configure("hover", background=C["hover"])
        self.tree.tag_configure("muted", foreground=C["muted"])
        self.tree.tag_configure("blue", foreground=C["primary"])
        self.tree.tag_configure("red", foreground=C["danger"])
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.tree.bind("<Motion>", self._on_hover)
        self.tree.bind("<Leave>", lambda e: self._set_hover(None))
        self.empty = tk.Label(table_frame, text="No records found", font=(UI, 11),
                              bg=C["card"], fg=C["muted"])

    # ---- table hover highlight
    def _on_hover(self, event):
        self._set_hover(self.tree.identify_row(event.y) or None)

    def _set_hover(self, item):
        if item == self._hover_item:
            return
        for it, add in ((self._hover_item, False), (item, True)):
            if it and self.tree.exists(it):
                tags = [t for t in self.tree.item(it, "tags") if t != "hover"]
                self.tree.item(it, tags=(["hover"] + tags) if add else tags)
        self._hover_item = item

    # ---- form helpers
    def get_form(self):
        return {k: w.get().strip() for k, w in self.widgets.items()}

    def set_form(self, values):
        self.clear(keep_selection=True)
        for k, v in values.items():
            w = self.widgets[k]
            if isinstance(w, ttk.Combobox):
                w.set(v)
            else:
                w.insert(0, "" if v is None else str(v))
        self.mode_pill.set(f"EDITING #{self.selected_id}", C["warning"])

    def clear(self, keep_selection=False):
        for w in self.widgets.values():
            if isinstance(w, ttk.Combobox):
                w.set("")
            else:
                w.delete(0, tk.END)
        if not keep_selection:
            self.selected_id = None
            self.tree.selection_remove(self.tree.selection())
            self.mode_pill.set("NEW", C["success"])

    def set_busy(self, busy):
        for b in self.action_buttons:
            b.set_enabled(not busy)

    def focus_search(self):
        self.search.widget.focus_set()

    def save_shortcut(self):
        if self.selected_id is None:
            self.add_record()
        else:
            self.update_record()

    # ---- loading data (background thread -> UI)
    def reload_options(self):
        for key, _, kind, options in self.fields:
            if kind == "combo" and callable(options):
                widget = self.widgets[key]
                self.db.run(options, lambda vals, w=widget: w.configure(values=vals))

    def refresh(self):
        self.db.run(self.fetch_rows, self._rows_loaded)

    def _rows_loaded(self, rows):
        self.rows = rows
        self._show_rows()

    def _on_search(self, *_):
        # debounce: only filter once the user pauses typing
        if self._search_after:
            self.after_cancel(self._search_after)
        self._search_after = self.after(SEARCH_DELAY_MS, self._show_rows)

    def _show_rows(self):
        self._search_after = None
        self._fill_token += 1
        self._hover_item = None
        term = self.search_var.get().strip().lower()
        rows = [r for r in self.rows
                if not term or term in " ".join(str(x) for x in r).lower()]
        self.tree.delete(*self.tree.get_children())
        self.count_pill.set(f"{len(rows)} record{'' if len(rows) == 1 else 's'}", C["primary"])
        if rows:
            self.empty.place_forget()
        else:
            self.empty.config(text="No matching records" if term else "No records yet")
            self.empty.place(relx=0.5, rely=0.45, anchor="center")
        self._insert_chunk(rows, 0, self._fill_token)

    def _insert_chunk(self, rows, start, token):
        """Insert rows a chunk at a time so the window stays responsive."""
        if token != self._fill_token or not self.winfo_exists():
            return  # a newer refresh/search started, or the page is gone
        end = min(start + CHUNK_SIZE, len(rows))
        for i in range(start, end):
            tags = (("odd",) if i % 2 else ()) + tuple(self.row_tags(rows[i]))
            self.tree.insert("", "end", values=self.format_row(rows[i]), tags=tags)
        if end < len(rows):
            self.after(1, self._insert_chunk, rows, end, token)

    def on_select(self, _event):
        sel = self.tree.selection()
        if not sel:
            return
        rid = int(str(self.tree.item(sel[0], "values")[0]).lstrip("#"))
        self.selected_id = rid

        def loaded(values):
            if self.selected_id == rid and values:  # ignore stale results
                self.set_form(values)
        self.db.run(lambda db: self.load_record(db, rid), loaded)

    # ---- actions
    def _save(self, job, msg):
        self.set_busy(True)

        def done(_):
            self.set_busy(False)
            self.after_change(msg)

        def failed(err):
            self.set_busy(False)
            Toast.show(self.app, f"Database error: {err}", "error", ms=4000)
        self.db.run(job, done, failed)

    def add_record(self):
        try:
            data = self.validate(self.get_form())
        except ValueError as e:
            Toast.show(self.app, str(e), "error")
            return
        self._save(lambda db: self.insert(db, data), f"{self.noun.title()[:-1]} added successfully")

    def update_record(self):
        if self.selected_id is None:
            Toast.show(self.app, "Select a record from the table first.", "info")
            return
        try:
            data = self.validate(self.get_form())
        except ValueError as e:
            Toast.show(self.app, str(e), "error")
            return
        rid = self.selected_id
        self._save(lambda db: self.modify(db, rid, data), f"Record #{rid} updated")

    def delete_record(self):
        if self.selected_id is None:
            Toast.show(self.app, "Select a record from the table first.", "info")
            return
        if messagebox.askyesno("Confirm delete",
                               f"Delete record #{self.selected_id}? This cannot be undone."):
            rid = self.selected_id
            self._save(lambda db: self.remove(db, rid), f"Record #{rid} deleted")

    def after_change(self, msg):
        self.clear()
        self.reload_options()
        self.refresh()
        self.app.set_status(msg)
        Toast.show(self.app, msg, "success")

    # ---- to be implemented by subclasses
    def format_row(self, row): return row   # UI thread: how a row is displayed
    def row_tags(self, row): return ()      # UI thread: extra colour tags
    def validate(self, data): return data   # UI thread
    def fetch_rows(self, db): return []     # the rest run on the DB thread
    def load_record(self, db, rid): return {}
    def insert(self, db, data): pass
    def modify(self, db, rid, data): pass
    def remove(self, db, rid): pass


# ================================================================ PAGES ===
def patient_choices(db):
    return [f"{r[0]} - {r[1]}" for r in db.query("SELECT id, name FROM patients ORDER BY id")]


def doctor_choices(db):
    return [f"{r[0]} - {r[1]} ({r[2]})"
            for r in db.query("SELECT id, name, specialization FROM doctors ORDER BY id")]


def choice_for(db, table, rid):
    """Build the combobox text for one patient/doctor id."""
    if table == "patients":
        r = db.query("SELECT id, name FROM patients WHERE id=?", (rid,))
        return f"{r[0][0]} - {r[0][1]}" if r else ""
    r = db.query("SELECT id, name, specialization FROM doctors WHERE id=?", (rid,))
    return f"{r[0][0]} - {r[0][1]} ({r[0][2]})" if r else ""


def id_from_choice(choice, what):
    if not choice:
        raise ValueError(f"Please select a {what}.")
    return int(choice.split(" - ")[0])


def to_float(value, field):
    try:
        return float(value or 0)
    except ValueError:
        raise ValueError(f"{field} must be a number")


def num(v):
    """Show 500.0 as 500 in the form."""
    return int(v) if isinstance(v, float) and v.is_integer() else v


def money(v):
    return f"₹ {v:,.0f}" if float(v).is_integer() else f"₹ {v:,.2f}"


class PatientsPage(CrudPage):
    form_title, table_title, noun = "Patient Details", "All Patients", "patients"
    columns = [("id", "ID", 40), ("name", "Name", 135), ("age", "Age", 52),
               ("gender", "Gender", 78), ("blood", "Blood", 66),
               ("disease", "Condition", 120), ("admitted", "Admitted", 108)]

    def __init__(self, master, app):
        self.fields = [
            ("name", "Full Name", "entry", None),
            ("age", "Age", "entry", None),
            ("gender", "Gender", "combo", ["Male", "Female", "Other"]),
            ("phone", "Phone", "entry", None),
            ("blood_group", "Blood Group", "combo",
             ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]),
            ("address", "Address", "entry", None),
            ("disease", "Condition", "entry", None),
            ("admitted_on", "Admitted On", "entry", None),
        ]
        super().__init__(master, app)
        self.widgets["admitted_on"].insert(0, date.today().isoformat())

    def clear(self, keep_selection=False):
        super().clear(keep_selection)
        if not keep_selection:
            self.widgets["admitted_on"].insert(0, date.today().isoformat())

    def format_row(self, r):
        dd = datetime.strptime(r[7], "%Y-%m-%d").date() if r[7] else None
        return (r[0], r[1], r[2], r[3], r[5], r[6], dd.strftime("%d %b %Y") if dd else "")

    def fetch_rows(self, db):
        return db.query("SELECT id, name, age, gender, phone, blood_group, disease,"
                        " admitted_on FROM patients ORDER BY id")

    def load_record(self, db, rid):
        r = db.query("SELECT name, age, gender, phone, blood_group, address, disease,"
                     " admitted_on FROM patients WHERE id=?", (rid,))
        return dict(zip([f[0] for f in self.fields], r[0])) if r else {}

    def validate(self, d):
        if not d["name"]:
            raise ValueError("Patient name is required.")
        if not d["age"].isdigit() or not 0 <= int(d["age"]) <= 120:
            raise ValueError("Age must be a number between 0 and 120.")
        if d["phone"] and (not d["phone"].isdigit() or len(d["phone"]) != 10):
            raise ValueError("Phone must be a 10-digit number.")
        try:
            datetime.strptime(d["admitted_on"], "%Y-%m-%d")
        except ValueError:
            raise ValueError("Admitted On must be in YYYY-MM-DD format.")
        return d

    def insert(self, db, d):
        db.execute("INSERT INTO patients(name, age, gender, phone, blood_group, address,"
                   " disease, admitted_on) VALUES(?,?,?,?,?,?,?,?)",
                   tuple(d[f[0]] for f in self.fields))

    def modify(self, db, rid, d):
        db.execute("UPDATE patients SET name=?, age=?, gender=?, phone=?, blood_group=?,"
                   " address=?, disease=?, admitted_on=? WHERE id=?",
                   (*[d[f[0]] for f in self.fields], rid))

    def remove(self, db, rid):
        db.execute("DELETE FROM patients WHERE id=?", (rid,))


class DoctorsPage(CrudPage):
    form_title, table_title, noun = "Doctor Details", "Medical Staff", "doctors"
    columns = [("id", "ID", 40), ("name", "Name", 150), ("spec", "Department", 135),
               ("phone", "Phone", 105), ("exp", "Experience", 90),
               ("fee", "Fee", 75)]

    def __init__(self, master, app):
        self.fields = [
            ("name", "Doctor Name", "entry", None),
            ("specialization", "Department", "combo",
             ["Cardiologist", "Neurologist", "Pediatrician", "Orthopedic",
              "Dermatologist", "General Physician", "Gynecologist", "ENT Specialist"]),
            ("phone", "Phone", "entry", None),
            ("experience", "Experience (yrs)", "entry", None),
            ("fee", "Fee (₹)", "entry", None),
        ]
        super().__init__(master, app)

    def format_row(self, r):
        return (r[0], r[1], r[2], r[3], f"{r[4]} yrs", money(r[5] or 0))

    def fetch_rows(self, db):
        return db.query("SELECT id, name, specialization, phone, experience, fee"
                        " FROM doctors ORDER BY id")

    def load_record(self, db, rid):
        r = db.query("SELECT name, specialization, phone, experience, fee"
                     " FROM doctors WHERE id=?", (rid,))
        return dict(zip([f[0] for f in self.fields], map(num, r[0]))) if r else {}

    def validate(self, d):
        if not d["name"]:
            raise ValueError("Doctor name is required.")
        if not d["specialization"]:
            raise ValueError("Please choose a department.")
        if d["phone"] and (not d["phone"].isdigit() or len(d["phone"]) != 10):
            raise ValueError("Phone must be a 10-digit number.")
        if not d["experience"].isdigit():
            raise ValueError("Experience must be a whole number.")
        d["fee"] = to_float(d["fee"], "Fee")
        return d

    def insert(self, db, d):
        db.execute("INSERT INTO doctors(name, specialization, phone, experience, fee)"
                   " VALUES(?,?,?,?,?)", tuple(d[f[0]] for f in self.fields))

    def modify(self, db, rid, d):
        db.execute("UPDATE doctors SET name=?, specialization=?, phone=?, experience=?,"
                   " fee=? WHERE id=?", (*[d[f[0]] for f in self.fields], rid))

    def remove(self, db, rid):
        db.execute("DELETE FROM doctors WHERE id=?", (rid,))


class AppointmentsPage(CrudPage):
    form_title, table_title, noun = "Book Appointment", "Appointments", "appointments"
    columns = [("id", "ID", 40), ("patient", "Patient", 120), ("doctor", "Doctor", 135),
               ("date", "Date", 120), ("time", "Time", 60), ("status", "Status", 95)]

    def __init__(self, master, app):
        self.fields = [
            ("patient", "Patient", "combo", patient_choices),
            ("doctor", "Doctor", "combo", doctor_choices),
            ("date", "Date", "entry", None),
            ("time", "Time (HH:MM)", "entry", None),
            ("status", "Status", "combo", ["Scheduled", "Completed", "Cancelled"]),
        ]
        super().__init__(master, app)
        self.widgets["date"].insert(0, date.today().isoformat())

    def clear(self, keep_selection=False):
        super().clear(keep_selection)
        if not keep_selection:
            self.widgets["date"].insert(0, date.today().isoformat())

    def format_row(self, r):
        dd = datetime.strptime(r[3], "%Y-%m-%d").date()
        return (r[0], r[1], r[2], dd.strftime("%d %b %Y"), r[4], r[5])

    def row_tags(self, r):
        return {"Cancelled": ("muted",), "Scheduled": ("blue",)}.get(r[5], ())

    def fetch_rows(self, db):
        return db.query(
            "SELECT a.id, p.name, d.name, a.date, a.time, a.status"
            " FROM appointments a JOIN patients p ON p.id=a.patient_id"
            " JOIN doctors d ON d.id=a.doctor_id ORDER BY a.date DESC, a.time")

    def load_record(self, db, rid):
        r = db.query("SELECT patient_id, doctor_id, date, time, status"
                     " FROM appointments WHERE id=?", (rid,))
        if not r:
            return {}
        pid, did, dt, tm, st = r[0]
        return {"patient": choice_for(db, "patients", pid),
                "doctor": choice_for(db, "doctors", did),
                "date": dt, "time": tm, "status": st}

    def validate(self, d):
        d["patient_id"] = id_from_choice(d["patient"], "patient")
        d["doctor_id"] = id_from_choice(d["doctor"], "doctor")
        try:
            datetime.strptime(d["date"], "%Y-%m-%d")
            datetime.strptime(d["time"], "%H:%M")
        except ValueError:
            raise ValueError("Use date as YYYY-MM-DD and time as HH:MM.")
        d["status"] = d["status"] or "Scheduled"
        return d

    def insert(self, db, d):
        db.execute("INSERT INTO appointments(patient_id, doctor_id, date, time, status)"
                   " VALUES(?,?,?,?,?)",
                   (d["patient_id"], d["doctor_id"], d["date"], d["time"], d["status"]))

    def modify(self, db, rid, d):
        db.execute("UPDATE appointments SET patient_id=?, doctor_id=?, date=?, time=?,"
                   " status=? WHERE id=?",
                   (d["patient_id"], d["doctor_id"], d["date"], d["time"], d["status"], rid))

    def remove(self, db, rid):
        db.execute("DELETE FROM appointments WHERE id=?", (rid,))


class BillingPage(CrudPage):
    form_title, table_title, noun = "Create Bill", "Invoices", "bills"
    columns = [("id", "Bill #", 70), ("patient", "Patient", 150), ("date", "Date", 120),
               ("items", "Charges", 95), ("total", "Total", 105), ("paid", "Status", 90)]
    AMOUNTS = ("consultation", "medicine", "room", "lab")

    def __init__(self, master, app):
        self.fields = [
            ("patient", "Patient", "combo", patient_choices),
            ("consultation", "Consultation (₹)", "entry", None),
            ("medicine", "Medicine (₹)", "entry", None),
            ("room", "Room Charges (₹)", "entry", None),
            ("lab", "Lab Tests (₹)", "entry", None),
            ("paid", "Payment", "combo", ["Paid", "Unpaid"]),
        ]
        super().__init__(master, app)
        box = Card(self.extra, pad=12, radius=12, bg=tint(C["primary"], 0.9), shadow=False)
        box.pack(fill="x", pady=(10, 0))
        tk.Label(box.inner, text="TOTAL AMOUNT", font=(UI, 8, "bold"), bg=box.fill,
                 fg=C["muted"]).pack(anchor="w")
        self.total_lbl = tk.Label(box.inner, text="₹ 0", font=("Segoe UI Semibold", 18),
                                  bg=box.fill, fg=C["primary"])
        self.total_lbl.pack(anchor="w")
        for key in self.AMOUNTS:
            self.widgets[key].bind("<KeyRelease>", lambda e: self.show_total())
        receipt = RoundButton(self.btns, "Receipt", self.receipt, color=C["accent"],
                              icon_name="print", width=104)
        self.clear_btn.grid_configure(columnspan=2)
        receipt.grid(row=1, column=2, padx=(8, 0), pady=(8, 0))
        self.action_buttons.append(receipt)

    def show_total(self):
        try:
            total = sum(to_float(self.widgets[k].get(), k) for k in self.AMOUNTS)
            self.total_lbl.config(text=money(total), fg=C["primary"])
        except ValueError:
            self.total_lbl.config(text="Invalid amount", fg=C["danger"])

    def set_form(self, values):
        super().set_form(values)
        self.show_total()

    def clear(self, keep_selection=False):
        super().clear(keep_selection)
        if hasattr(self, "total_lbl"):
            self.show_total()

    def format_row(self, r):
        dd = datetime.strptime(r[2], "%Y-%m-%d").date()
        items = sum(1 for v in r[3:7] if v)
        return (f"#{r[0]:05d}", r[1], dd.strftime("%d %b %Y"),
                f"{items} item{'s' if items != 1 else ''}", money(r[7]), r[8])

    def row_tags(self, r):
        return ("red",) if r[8] == "Unpaid" else ()

    def fetch_rows(self, db):
        return db.query(
            "SELECT b.id, p.name, b.date, b.consultation, b.medicine, b.room, b.lab,"
            " b.total, b.paid FROM bills b JOIN patients p ON p.id=b.patient_id"
            " ORDER BY b.id DESC")

    def load_record(self, db, rid):
        r = db.query("SELECT patient_id, consultation, medicine, room, lab, paid"
                     " FROM bills WHERE id=?", (rid,))
        if not r:
            return {}
        pid, c, m, rm, lab, paid = r[0]
        return {"patient": choice_for(db, "patients", pid), "consultation": num(c),
                "medicine": num(m), "room": num(rm), "lab": num(lab), "paid": paid}

    def validate(self, d):
        d["patient_id"] = id_from_choice(d["patient"], "patient")
        for key in self.AMOUNTS:
            d[key] = to_float(d[key], key.title())
            if d[key] < 0:
                raise ValueError("Amounts cannot be negative.")
        d["total"] = sum(d[k] for k in self.AMOUNTS)
        if d["total"] <= 0:
            raise ValueError("Enter at least one charge.")
        d["paid"] = d["paid"] or "Unpaid"
        return d

    def insert(self, db, d):
        db.execute("INSERT INTO bills(patient_id, consultation, medicine, room, lab, total,"
                   " date, paid) VALUES(?,?,?,?,?,?,?,?)",
                   (d["patient_id"], d["consultation"], d["medicine"], d["room"],
                    d["lab"], d["total"], date.today().isoformat(), d["paid"]))

    def modify(self, db, rid, d):
        db.execute("UPDATE bills SET patient_id=?, consultation=?, medicine=?, room=?,"
                   " lab=?, total=?, paid=? WHERE id=?",
                   (d["patient_id"], d["consultation"], d["medicine"], d["room"],
                    d["lab"], d["total"], d["paid"], rid))

    def remove(self, db, rid):
        db.execute("DELETE FROM bills WHERE id=?", (rid,))

    def receipt(self):
        if self.selected_id is None:
            Toast.show(self.app, "Select a bill from the table first.", "info")
            return
        rid = self.selected_id
        self.db.run(lambda db: db.query(
            "SELECT b.id, p.name, p.age, p.gender, b.consultation, b.medicine, b.room,"
            " b.lab, b.total, b.date, b.paid FROM bills b JOIN patients p"
            " ON p.id=b.patient_id WHERE b.id=?", (rid,)), self._show_receipt)

    def _show_receipt(self, rows):
        if not rows:
            Toast.show(self.app, "This bill no longer exists.", "error")
            return
        ReceiptWindow(self.app, rows[0])


class ReceiptWindow(tk.Toplevel):
    def __init__(self, app, bill):
        super().__init__(app)
        self.bill = bill
        bid, name, age, gender, cons, med, room, lab, total, bdate, status = bill
        self.title(f"Receipt #{bid:05d} - {HOSPITAL_NAME}")
        self.configure(bg=C["bg"])
        self.resizable(False, False)
        self.transient(app)

        def header(cv, w, h):
            cv.create_text(28, 38, text=f"✚  {HOSPITAL_NAME}", anchor="w", fill="#ffffff",
                           font=("Segoe UI Semibold", 18))
            cv.create_text(28, 70, text="Payment Receipt", anchor="w",
                           fill=blend("#ffffff", C["grad1"], 0.2), font=(UI, 11))
            cv.create_text(w - 28, 38, text=f"#{bid:05d}", anchor="e", fill="#ffffff",
                           font=("Segoe UI Semibold", 14))
            cv.create_text(w - 28, 70, text=bdate, anchor="e",
                           fill=blend("#ffffff", C["grad1"], 0.2), font=(UI, 10))
        Gradient(self, C["grad1"], C["grad2"], overlay=header, width=440,
                 height=104).pack(fill="x")

        card = Card(self, pad=24)
        card.pack(fill="both", padx=20, pady=20)
        b = card.inner
        bg = C["card"]

        def row(parent, left, right, lf=F_BODY, rf=F_SEMI, lc=None, rc=None, pady=3):
            fr = tk.Frame(parent, bg=bg)
            fr.pack(fill="x", pady=pady)
            tk.Label(fr, text=left, font=lf, bg=bg, fg=lc or C["muted"]).pack(side="left")
            tk.Label(fr, text=right, font=rf, bg=bg, fg=rc or C["text"]).pack(side="right")

        row(b, "Patient", name)
        row(b, "Age / Gender", f"{age} / {gender}")
        row(b, "Bill date", bdate)
        tk.Frame(b, bg=C["border"], height=1).pack(fill="x", pady=12)
        tk.Label(b, text="CHARGES", font=(UI, 8, "bold"), bg=bg,
                 fg=C["muted"]).pack(anchor="w", pady=(0, 4))
        for label, amount in (("Consultation", cons), ("Medicine", med),
                              ("Room charges", room), ("Lab tests", lab)):
            row(b, label, money(amount), lc=C["text"], rf=F_BODY)
        tk.Frame(b, bg=C["border"], height=1).pack(fill="x", pady=12)
        row(b, "Total", money(total), lf=F_H2, rf=("Segoe UI Semibold", 18),
            lc=C["text"], rc=C["primary"])
        st = tk.Frame(b, bg=bg)
        st.pack(fill="x", pady=(10, 0))
        tk.Label(st, text="Status", font=F_BODY, bg=bg, fg=C["muted"]).pack(side="left")
        Pill(st, status.upper(), C["success"] if status == "Paid" else C["danger"]).pack(
            side="right")
        tk.Label(b, text="Thank you for choosing AK1 Hospital. Get well soon!",
                 font=(UI, 9, "italic"), bg=bg, fg=C["muted"]).pack(pady=(18, 0))

        btns = tk.Frame(self, bg=C["bg"])
        btns.pack(fill="x", padx=20, pady=(0, 20))
        RoundButton(btns, "Close", self.destroy, width=120).pack(side="right")
        RoundButton(btns, "Save as Text", self.save_text, color=C["card"], fg=C["text"],
                    icon_name="save", outline=C["border"]).pack(side="right", padx=8)

    def as_text(self):
        bid, name, age, gender, cons, med, room, lab, total, bdate, status = self.bill
        line = "-" * 42
        return "\n".join([
            f"{HOSPITAL_NAME.upper():^42}", f"{'Payment Receipt':^42}", line,
            f"Bill No : #{bid:05d}        Date : {bdate}", f"Patient : {name}",
            f"Age/Sex : {age} / {gender}", line,
            *(f"{k:<26}{money(v):>16}" for k, v in (("Consultation", cons), ("Medicine", med),
                                                   ("Room charges", room), ("Lab tests", lab))),
            line, f"{'TOTAL':<26}{money(total):>16}", f"{'Status':<26}{status:>16}", line,
            f"{'Thank you. Get well soon!':^42}", ""])

    def save_text(self):
        path = filedialog.asksaveasfilename(
            parent=self, defaultextension=".txt", initialfile=f"AK1_Receipt_{self.bill[0]:05d}.txt",
            filetypes=[("Text file", "*.txt")])
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self.as_text())
            Toast.show(self.master, "Receipt saved", "success")


# ============================================================ DASHBOARD ===
class BarChart(tk.Canvas):
    """Animated bar chart. data = [(label, value, highlight), ...]"""

    def __init__(self, master, data, height=170):
        super().__init__(master, height=height, bg=master["bg"], highlightthickness=0, bd=0)
        self.data, self.p = data, 0.0
        self.bind("<Configure>", lambda e: self.draw())
        self._animate(0)

    def _animate(self, i):
        if not self.winfo_exists():
            return
        self.p = ease(i / 36)
        self.draw()
        if i < 36:
            self.after(16, self._animate, i + 1)

    def draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 50:
            return
        left, right, top, bottom = 34, 6, 20, 26
        base = h - bottom
        step = max(1, math.ceil(max([v for _, v, _ in self.data] + [1]) / 4))
        mx = step * 4
        for i in range(5):
            y = base - (base - top) * i / 4
            self.create_line(left, y, w - right, y, fill=C["border"], dash=(2, 4))
            if i % 2 == 0:
                self.create_text(left - 10, y, text=str(step * i), anchor="e", fill=C["muted"],
                                 font=(UI, 8))
        slot = (w - left - right) / len(self.data)
        bw = min(40, slot * 0.5)
        for i, (label, value, highlight) in enumerate(self.data):
            cx = left + slot * (i + 0.5)
            bh = (base - top) * value / mx * self.p
            color = C["primary"] if highlight else blend(C["primary"], C["card"], 0.55)
            if bh > 1:
                x1, x2 = cx - bw / 2, cx + bw / 2
                round_rect(self, x1, base - bh, x2, base, min(8, bh / 2), fill=color, outline="")
                self.create_rectangle(x1, base - min(bh, 6), x2, base, fill=color, outline="")
            self.create_text(cx, base - bh - 10, text=str(value), fill=C["text"],
                             font=(UI, 9, "bold"))
            self.create_text(cx, h - 12, text=label, font=(UI, 9, "bold") if highlight else (UI, 9),
                             fill=C["text"] if highlight else C["muted"])


class Donut(tk.Canvas):
    """Animated donut chart. parts = [(value, color), ...]"""

    def __init__(self, master, parts, title, size=170):
        super().__init__(master, width=size, height=size, bg=master["bg"],
                         highlightthickness=0, bd=0)
        self.parts, self.title, self.p = parts, title, 0.0
        self.bind("<Configure>", lambda e: self.draw())
        self._animate(0)

    def _animate(self, i):
        if not self.winfo_exists():
            return
        self.p = ease(i / 40)
        self.draw()
        if i < 40:
            self.after(16, self._animate, i + 1)

    def draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 50:
            return
        cx, cy, thick = w / 2, h / 2, 14
        r = min(w, h) / 2 - thick / 2 - 2
        box = (cx - r, cy - r, cx + r, cy + r)
        self.create_oval(*box, outline=C["border"], width=thick)
        total = sum(v for v, _ in self.parts)
        start = 90
        for value, color in self.parts:
            if total and value:
                extent = -min(359.9, 360 * value / total) * self.p
                self.create_arc(*box, start=start, extent=extent, style="arc",
                                outline=color, width=thick)
                start += extent
        self.create_text(cx, cy - 7, text=self.title, fill=C["text"], font=("Segoe UI Semibold", 15))
        self.create_text(cx, cy + 14, text="collected", fill=C["muted"], font=(UI, 8))


class DashboardPage(tk.Frame):
    def __init__(self, master, app):
        super().__init__(master, bg=C["bg"])
        self.app = app
        self.db = app.db
        tk.Label(self, text="Loading dashboard…", font=F_H2, bg=C["bg"],
                 fg=C["muted"]).pack(pady=60)

    def refresh(self):
        self.db.run(self._load_stats, self._render)

    @staticmethod
    def _load_stats(db):
        """Runs on the DB thread: gather everything the dashboard shows."""
        today = date.today()
        iso = today.isoformat()
        one = lambda sql, p=(): db.query(sql, p)[0][0] or 0
        counts = dict(db.query("SELECT date, COUNT(*) FROM appointments WHERE date BETWEEN ? AND ?"
                               " GROUP BY date", ((today - timedelta(days=6)).isoformat(), iso)))
        week = []
        for back in range(6, -1, -1):
            d = today - timedelta(days=back)
            week.append(("Today" if back == 0 else d.strftime("%a"),
                         counts.get(d.isoformat(), 0), back == 0))
        return {
            "patients": one("SELECT COUNT(*) FROM patients"),
            "new_patients": one("SELECT COUNT(*) FROM patients WHERE admitted_on=?", (iso,)),
            "doctors": one("SELECT COUNT(*) FROM doctors"),
            "departments": one("SELECT COUNT(DISTINCT specialization) FROM doctors"),
            "today": one("SELECT COUNT(*) FROM appointments WHERE date=?", (iso,)),
            "scheduled_today": one("SELECT COUNT(*) FROM appointments WHERE date=?"
                                   " AND status='Scheduled'", (iso,)),
            "paid": one("SELECT SUM(total) FROM bills WHERE paid='Paid'"),
            "unpaid": one("SELECT SUM(total) FROM bills WHERE paid='Unpaid'"),
            "unpaid_count": one("SELECT COUNT(*) FROM bills WHERE paid='Unpaid'"),
            "week": week,
            "upcoming": db.query(
                "SELECT p.name, d.name, d.specialization, a.date, a.time FROM appointments a"
                " JOIN patients p ON p.id=a.patient_id JOIN doctors d ON d.id=a.doctor_id"
                " WHERE a.status='Scheduled' AND a.date>=? ORDER BY a.date, a.time LIMIT 3",
                (iso,)),
        }

    def _render(self, s):
        for w in self.winfo_children():
            w.destroy()
        for c in range(4):
            self.columnconfigure(c, weight=1, uniform="dash")
        self.rowconfigure(1, weight=1)
        self.rowconfigure(2, weight=1)

        stats = [
            ("Total Patients", s["patients"], "{:,.0f}", f"+{s['new_patients']} admitted today",
             C["primary"], "patients"),
            ("Doctors", s["doctors"], "{:,.0f}", f"Across {s['departments']} departments",
             C["accent"], "doctors"),
            ("Today's Appointments", s["today"], "{:,.0f}",
             f"{s['scheduled_today']} still scheduled", C["warning"], "appointments"),
            ("Revenue Collected", s["paid"], "₹ {:,.0f}",
             f"₹ {s['unpaid']:,.0f} pending · {s['unpaid_count']} bills", C["violet"], "billing"),
        ]
        for i, (label, value, fmt, caption, color, ic) in enumerate(stats):
            card = Card(self, pad=16)
            card.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 8, 0 if i == 3 else 8),
                      pady=(0, 16))
            inner = card.inner
            badge = tk.Canvas(inner, width=48, height=48, bg=C["card"], highlightthickness=0)
            round_rect(badge, 0, 0, 48, 48, 14, fill=tint(color, 0.84), outline="")
            badge.create_text(24, 25, text=icon(ic), font=icon_font(17), fill=color)
            badge.pack(side="left", anchor="n")
            txt = tk.Frame(inner, bg=C["card"])
            txt.pack(side="left", padx=(14, 0), fill="x")
            tk.Label(txt, text=label, font=F_SMALL, bg=C["card"], fg=C["muted"]).pack(anchor="w")
            num = tk.Label(txt, text="0", font=F_NUM, bg=C["card"], fg=C["text"])
            num.pack(anchor="w")
            animate_number(num, value, fmt)
            tk.Label(txt, text=caption, font=(UI, 8), bg=C["card"], fg=color).pack(anchor="w")

        # appointments chart
        chart = Card(self, pad=20)
        chart.grid(row=1, column=0, columnspan=3, sticky="nsew", padx=(0, 8), pady=(0, 16))
        head = tk.Frame(chart.inner, bg=C["card"])
        head.pack(fill="x")
        tk.Label(head, text="Appointments", font=F_H2, bg=C["card"], fg=C["text"]).pack(side="left")
        tk.Label(head, text="  ·  last 7 days", font=F_SMALL, bg=C["card"],
                 fg=C["muted"]).pack(side="left", pady=(3, 0))
        Pill(head, f"{sum(v for _, v, _ in s['week'])} this week", C["primary"]).pack(side="right")
        BarChart(chart.inner, s["week"], height=120).pack(fill="both", expand=True, pady=(10, 0))

        # billing donut
        donut = Card(self, pad=20)
        donut.grid(row=1, column=3, sticky="nsew", padx=(8, 0), pady=(0, 16))
        tk.Label(donut.inner, text="Billing", font=F_H2, bg=C["card"], fg=C["text"]).pack(anchor="w")
        total = s["paid"] + s["unpaid"]
        pct = f"{100 * s['paid'] / total:.0f}%" if total else "0%"
        body = tk.Frame(donut.inner, bg=C["card"])
        body.pack(fill="both", expand=True, pady=(8, 0))
        Donut(body, [(s["paid"], C["success"]), (s["unpaid"], C["danger"])],
              pct, size=118).pack(side="left")
        legend = tk.Frame(body, bg=C["card"])
        legend.pack(side="left", padx=(12, 0))
        for label, value, color in (("Paid", s["paid"], C["success"]),
                                    ("Pending", s["unpaid"], C["danger"])):
            r = tk.Frame(legend, bg=C["card"])
            r.pack(anchor="w", pady=2)
            tk.Label(r, text="●  " + label, font=F_SMALL, bg=C["card"],
                     fg=color).pack(anchor="w")
            tk.Label(r, text=money(value), font=F_SEMI, bg=C["card"],
                     fg=C["text"]).pack(anchor="w")

        # upcoming appointments
        up = Card(self, pad=20)
        up.grid(row=2, column=0, columnspan=3, sticky="nsew", padx=(0, 8))
        head = tk.Frame(up.inner, bg=C["card"])
        head.pack(fill="x", pady=(0, 2))
        tk.Label(head, text="Upcoming Appointments", font=F_H2, bg=C["card"],
                 fg=C["text"]).pack(side="left")
        link = tk.Label(head, text="View all  →", font=(UI, 9, "bold"), bg=C["card"],
                        fg=C["primary"], cursor="hand2")
        link.pack(side="right")
        link.bind("<Button-1>", lambda e: self.app.show_page("Appointments"))
        if not s["upcoming"]:
            tk.Label(up.inner, text="No upcoming appointments", font=F_BODY, bg=C["card"],
                     fg=C["muted"]).pack(pady=20)
        palette = [C["primary"], C["accent"], C["violet"], C["warning"]]
        today = date.today()
        for i, (pname, dname, spec, d, t) in enumerate(s["upcoming"]):
            if i:
                tk.Frame(up.inner, bg=C["border"], height=1).pack(fill="x")
            r = tk.Frame(up.inner, bg=C["card"])
            r.pack(fill="x", pady=2)
            avatar(r, initials(pname), 32, tint(palette[i % 4], 0.8), palette[i % 4]).pack(side="left")
            txt = tk.Frame(r, bg=C["card"])
            txt.pack(side="left", padx=12)
            tk.Label(txt, text=pname, font=F_SEMI, bg=C["card"], fg=C["text"]).pack(anchor="w")
            tk.Label(txt, text=f"with {dname}  ·  {spec}", font=F_SMALL, bg=C["card"],
                     fg=C["muted"]).pack(anchor="w")
            dd = datetime.strptime(d, "%Y-%m-%d").date()
            when = ("Today" if dd == today else "Tomorrow" if dd == today + timedelta(days=1)
                    else dd.strftime("%a, %d %b"))
            Pill(r, f"{when}  ·  {t}", C["primary"] if dd == today else C["muted"]).pack(side="right")

        # quick actions
        qa = Card(self, pad=20)
        qa.grid(row=2, column=3, sticky="nsew", padx=(8, 0))
        tk.Label(qa.inner, text="Quick Actions", font=F_H2, bg=C["card"],
                 fg=C["text"]).pack(anchor="w", pady=(0, 6))
        for text, page, color, ic in (("Register Patient", "Patients", C["primary"], "patients"),
                                      ("Book Appointment", "Appointments", C["accent"], "appointments"),
                                      ("Create Bill", "Billing", C["violet"], "billing"),
                                      ("Add Doctor", "Doctors", C["warning"], "doctors")):
            RoundButton(qa.inner, text, lambda p=page: self.app.show_page(p),
                        color=tint(color, 0.85), fg=color, icon_name=ic,
                        height=34).pack(fill="x", pady=2)


# ================================================================ ABOUT ===
class AboutPage(tk.Frame):
    def __init__(self, master, app):
        super().__init__(master, bg=C["bg"])
        self.app = app

        def banner(cv, w, h):
            white = "#ffffff"
            cv.create_oval(w - 260, -120, w + 60, 200, fill=blend(C["grad2"], white, 0.1), outline="")
            cv.create_oval(w - 120, h - 60, w - 40, h + 20, outline=blend(C["grad1"], white, 0.3),
                           width=2)
            round_rect(cv, 32, h / 2 - 34, 100, h / 2 + 34, 18, fill=white, outline="")
            cv.create_text(66, h / 2, text="✚", fill=C["primary"], font=(UI, 28, "bold"))
            cv.create_text(124, h / 2 - 16, text=f"{HOSPITAL_NAME} Management System", anchor="w",
                           fill=white, font=("Segoe UI Semibold", 20))
            cv.create_text(124, h / 2 + 16, anchor="w", fill=blend(white, C["grad1"], 0.2),
                           font=(UI, 11), text="Advanced Programming Practice  ·  2nd Year Project")
        Gradient(self, C["grad1"], C["grad2"], overlay=banner, radius=16,
                 height=140).pack(fill="x", pady=(0, 18))

        grid = tk.Frame(self, bg=C["bg"])
        grid.pack(fill="both", expand=True)
        for c in range(3):
            grid.columnconfigure(c, weight=1, uniform="about")
        grid.rowconfigure(0, weight=1)

        dev = Card(grid, pad=24)
        dev.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        avatar(dev.inner, initials(DEVELOPER), 84, C["primary"]).pack(pady=(6, 12))
        tk.Label(dev.inner, text=DEVELOPER, font=("Segoe UI Semibold", 16), bg=C["card"],
                 fg=C["text"]).pack()
        tk.Label(dev.inner, text="Developer  ·  B.Tech, 2nd Year", font=F_BODY, bg=C["card"],
                 fg=C["muted"]).pack(pady=(2, 14))
        Pill(dev.inner, "Advanced Programming Practice", C["primary"]).pack()
        tk.Frame(dev.inner, bg=C["border"], height=1).pack(fill="x", pady=18)
        for k, v in (("Project", "Hospital Management"), ("Hospital", HOSPITAL_NAME),
                     ("Version", "2.0"), ("Year", str(date.today().year))):
            r = tk.Frame(dev.inner, bg=C["card"])
            r.pack(fill="x", pady=3)
            tk.Label(r, text=k, font=F_BODY, bg=C["card"], fg=C["muted"]).pack(side="left")
            tk.Label(r, text=v, font=F_SEMI, bg=C["card"], fg=C["text"]).pack(side="right")

        feats = Card(grid, pad=24)
        feats.grid(row=0, column=1, sticky="nsew", padx=10)
        tk.Label(feats.inner, text="Features", font=F_H2, bg=C["card"],
                 fg=C["text"]).pack(anchor="w", pady=(0, 10))
        for feat in ("Secure login screen", "Dashboard with live charts",
                     "Patient records", "Doctors & departments", "Appointment booking",
                     "Billing & printable receipts", "Instant search everywhere",
                     "Light & dark themes", "No freezing (DB thread)"):
            r = tk.Frame(feats.inner, bg=C["card"])
            r.pack(fill="x", pady=4)
            tk.Label(r, text=icon("check"), font=icon_font(9), bg=C["card"],
                     fg=C["success"]).pack(side="left")
            tk.Label(r, text=feat, font=F_BODY, bg=C["card"], fg=C["text"]).pack(side="left",
                                                                                 padx=8)

        tech = Card(grid, pad=24)
        tech.grid(row=0, column=2, sticky="nsew", padx=(10, 0))
        tk.Label(tech.inner, text="Built With", font=F_H2, bg=C["card"],
                 fg=C["text"]).pack(anchor="w", pady=(0, 10))
        palette = [C["primary"], C["accent"], C["violet"], C["warning"], C["success"]]
        rows = [("Python 3", "Tkinter"), ("SQLite", "Threading"), ("Canvas graphics", "OOP")]
        for i, pair in enumerate(rows):
            r = tk.Frame(tech.inner, bg=C["card"])
            r.pack(anchor="w", pady=3)
            for j, name in enumerate(pair):
                Pill(r, name, palette[(i * 2 + j) % 5], height=28).pack(side="left", padx=(0, 6))
        tk.Label(tech.inner, text="Keyboard Shortcuts", font=F_H2, bg=C["card"],
                 fg=C["text"]).pack(anchor="w", pady=(22, 8))
        for keys, what in (("Ctrl + S", "Save / update record"), ("Ctrl + F", "Search table"),
                           ("Esc", "Clear the form"), ("Enter", "Sign in (login)")):
            r = tk.Frame(tech.inner, bg=C["card"])
            r.pack(fill="x", pady=3)
            Pill(r, keys, C["muted"]).pack(side="left")
            tk.Label(r, text=what, font=F_BODY, bg=C["card"], fg=C["text"]).pack(side="left",
                                                                                 padx=10)


# ============================================================ MAIN APP ===
class HospitalApp(tk.Tk):
    PAGES = {
        "Dashboard": (DashboardPage, "dashboard", "Overview of hospital activity"),
        "Patients": (PatientsPage, "patients", "Register and manage patient records"),
        "Doctors": (DoctorsPage, "doctors", "Manage doctors and departments"),
        "Appointments": (AppointmentsPage, "appointments", "Schedule and track appointments"),
        "Billing": (BillingPage, "billing", "Create invoices and print receipts"),
        "About": (AboutPage, "about", "About this project"),
    }

    def __init__(self):
        super().__init__()
        self.title(f"{HOSPITAL_NAME} - Hospital Management System | {DEVELOPER}")
        self.geometry("1280x760")
        self.minsize(1120, 680)
        try:
            self.state("zoomed")
        except tk.TclError:
            pass
        init_icons(self)
        self.theme = "light"
        apply_theme(self, self.theme)
        self.db = Database(self)
        self.db.on_busy = self.show_busy
        self.pages, self.nav = {}, {}
        self.current = self.username = None
        self.status = self.busy_lbl = self.clock = None
        self._tick_id = None
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.bind("<Control-f>", lambda e: self._crud() and self._crud().focus_search())
        self.bind("<Control-s>", lambda e: self._crud() and self._crud().save_shortcut())
        self.bind("<Escape>", lambda e: self._crud() and self._crud().clear())
        self.show_splash()

    def _crud(self):
        page = self.pages.get(self.current)
        return page if isinstance(page, CrudPage) else None

    def _clear_window(self):
        for w in self.winfo_children():
            w.destroy()
        self.status = self.busy_lbl = self.clock = None

    def on_close(self):
        self.db.close()   # let the worker thread finish and close SQLite cleanly
        self.destroy()

    # ---- splash screen (waits for the DB thread to be ready)
    def show_splash(self):
        self._clear_window()
        self._splash_p, self._splash_start = 0.0, time.time()
        self._db_ready = False

        def art(cv, w, h):
            white = "#ffffff"
            cv.create_oval(-140, -140, 280, 280, fill=blend(C["grad1"], white, 0.08), outline="")
            cv.create_oval(w - 260, h - 260, w + 140, h + 140, fill=blend(C["grad2"], white, 0.08),
                           outline="")
            cx, cy = w / 2, h / 2 - 50
            round_rect(cv, cx - 44, cy - 44, cx + 44, cy + 44, 24, fill=white, outline="")
            cv.create_text(cx, cy, text="✚", fill=C["primary"], font=(UI, 38, "bold"))
            cv.create_text(cx, cy + 86, text=HOSPITAL_NAME, fill=white,
                           font=("Segoe UI Semibold", 30))
            cv.create_text(cx, cy + 122, text="Hospital Management System",
                           fill=blend(white, C["grad1"], 0.2), font=(UI, 12))
            cv.bar = (cx - 150, cy + 170, cx + 150, cy + 176)
            round_rect(cv, *cv.bar, 3, fill=blend(C["grad1"], white, 0.25), outline="")
            cv.create_text(cx, cy + 200, text="Starting…", tags="status",
                           fill=blend(white, C["grad1"], 0.2), font=F_SMALL)
            cv.create_text(cx, h - 30, text=f"Developed by {DEVELOPER}",
                           fill=blend(white, C["grad2"], 0.3), font=F_SMALL)
            self._draw_splash_bar(cv)

        self.splash = Gradient(self, C["grad1"], C["grad2"], overlay=art)
        self.splash.pack(fill="both", expand=True)
        self.db.run(lambda db: db.get_setting("theme", "light"), self._splash_ready,
                    lambda err: (messagebox.showerror("Database error", str(err)),
                                 self._splash_ready("light")))
        self._animate_splash()

    def _splash_ready(self, theme):
        self._db_ready, self._saved_theme = True, theme

    def _draw_splash_bar(self, cv):
        if not hasattr(cv, "bar"):
            return
        x1, y1, x2, y2 = cv.bar
        cv.delete("bar")
        if self._splash_p > 0.01:
            round_rect(cv, x1, y1, x1 + (x2 - x1) * self._splash_p, y2, 3, fill="#ffffff",
                       outline="", tags="bar")
        p = self._splash_p
        cv.itemconfigure("status", text="Connecting to database…" if p < 0.4 else
                         "Loading records…" if p < 0.85 else "Almost ready…")

    def _animate_splash(self):
        if not self.splash.winfo_exists():
            return
        target = 1.0 if self._db_ready else 0.85
        self._splash_p = min(target, self._splash_p + max(0.008, (target - self._splash_p) * 0.06))
        self._draw_splash_bar(self.splash)
        if self._splash_p >= 1.0 and time.time() - self._splash_start > 1.2:
            if self._saved_theme in THEMES and self._saved_theme != self.theme:
                self.theme = self._saved_theme
                apply_theme(self, self.theme)
            self.show_login()
            return
        self.after(16, self._animate_splash)

    # ---- login / logout
    def show_login(self):
        self._clear_window()
        self.pages.clear()
        self.nav.clear()
        self.current = None
        LoginPage(self, self).pack(fill="both", expand=True)

    def logout(self):
        if messagebox.askyesno("Sign out", "Do you want to sign out?"):
            self.show_login()

    # ---- theme
    def toggle_theme(self):
        self.theme = "dark" if self.theme == "light" else "light"
        apply_theme(self, self.theme)
        self.db.run(lambda db, t=self.theme: db.set_setting("theme", t))
        self.build_main(self.username, page=self.current)
        Toast.show(self, f"{self.theme.title()} mode enabled", "info")

    # ---- main layout
    def build_main(self, username, page="Dashboard"):
        self.username = username
        self._clear_window()
        self.pages.clear()
        self.nav.clear()
        self.current = None

        # sidebar
        sidebar = tk.Frame(self, bg=C["sidebar"], width=250)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        brand = tk.Frame(sidebar, bg=C["sidebar"])
        brand.pack(fill="x", padx=18, pady=(24, 26))
        logo = tk.Canvas(brand, width=42, height=42, bg=C["sidebar"], highlightthickness=0)
        round_rect(logo, 0, 0, 42, 42, 12, fill=C["primary"], outline="")
        logo.create_text(21, 21, text="✚", fill="#ffffff", font=(UI, 17, "bold"))
        logo.pack(side="left")
        names = tk.Frame(brand, bg=C["sidebar"])
        names.pack(side="left", padx=12)
        tk.Label(names, text=HOSPITAL_NAME, font=("Segoe UI Semibold", 14), bg=C["sidebar"],
                 fg="#ffffff").pack(anchor="w")
        tk.Label(names, text="Management System", font=F_SMALL, bg=C["sidebar"],
                 fg=C["sidebar_text"]).pack(anchor="w")

        def section(text):
            tk.Label(sidebar, text=text, font=(UI, 8, "bold"), bg=C["sidebar"],
                     fg=blend(C["sidebar_text"], C["sidebar"], 0.35)).pack(anchor="w", padx=24,
                                                                         pady=(10, 6))
        section("MAIN MENU")
        for name, (_, ic, _) in self.PAGES.items():
            if name == "About":
                section("SYSTEM")
            item = NavItem(sidebar, ic, name, lambda n=name: self.show_page(n))
            item.pack(padx=16, pady=1)
            self.nav[name] = item

        user = tk.Frame(sidebar, bg=C["sidebar_active"])
        user.pack(side="bottom", fill="x", padx=16, pady=18)
        avatar(user, initials(DEVELOPER), 38, C["accent"]).pack(side="left", padx=(12, 10), pady=12)
        who = tk.Frame(user, bg=C["sidebar_active"])
        who.pack(side="left")
        tk.Label(who, text=DEVELOPER, font=F_SEMI, bg=C["sidebar_active"],
                 fg="#ffffff").pack(anchor="w")
        tk.Label(who, text=f"{DEVELOPER_ROLE}  ·  {username}", font=(UI, 8),
                 bg=C["sidebar_active"], fg=C["sidebar_text"]).pack(anchor="w")
        out = tk.Label(user, text=icon("logout"), font=icon_font(13), bg=C["sidebar_active"],
                       fg=C["sidebar_text"], cursor="hand2")
        out.pack(side="right", padx=12)
        out.bind("<Button-1>", lambda e: self.logout())
        out.bind("<Enter>", lambda e: out.config(fg=C["danger"]))
        out.bind("<Leave>", lambda e: out.config(fg=C["sidebar_text"]))

        # main column
        main = tk.Frame(self, bg=C["bg"])
        main.pack(side="left", fill="both", expand=True)
        top = tk.Frame(main, bg=C["bg"])
        top.pack(fill="x", padx=28, pady=(18, 12))
        titles = tk.Frame(top, bg=C["bg"])
        titles.pack(side="left")
        self.page_title = tk.Label(titles, text="", font=F_H1, bg=C["bg"], fg=C["text"])
        self.page_title.pack(anchor="w")
        self.page_sub = tk.Label(titles, text="", font=F_BODY, bg=C["bg"], fg=C["muted"])
        self.page_sub.pack(anchor="w")

        RoundButton(top, "", self.toggle_theme, color=C["card"], fg=C["text"],
                    icon_name="moon" if self.theme == "light" else "sun", width=42, height=42,
                    radius=12, outline=C["border"]).pack(side="right", padx=(10, 0))
        chip = Card(top, pad=11, radius=12, shadow=False)
        chip.pack(side="right")
        tk.Label(chip.inner, text=icon("clock"), font=icon_font(10), bg=C["card"],
                 fg=C["primary"]).pack(side="left", padx=(2, 8))
        self.clock = tk.Label(chip.inner, text="", font=F_SEMI, bg=C["card"], fg=C["text"])
        self.clock.pack(side="left", padx=(0, 4))

        footer = tk.Frame(main, bg=C["bg"])
        footer.pack(side="bottom", fill="x", padx=28, pady=(0, 10))
        self.status = tk.Label(footer, text="Ready", font=F_SMALL, bg=C["bg"], fg=C["muted"])
        self.status.pack(side="left")
        self.busy_lbl = tk.Label(footer, text="", font=(UI, 9, "bold"), bg=C["bg"],
                                 fg=C["warning"])
        self.busy_lbl.pack(side="left", padx=12)
        tk.Label(footer, text=f"© {date.today().year} {HOSPITAL_NAME}  ·  Developed by {DEVELOPER}",
                 font=F_SMALL, bg=C["bg"], fg=C["muted"]).pack(side="right")

        self.container = tk.Frame(main, bg=C["bg"])
        self.container.pack(fill="both", expand=True, padx=28, pady=(0, 8))

        self._start_clock()
        self.show_page(page or "Dashboard")

    def show_page(self, name):
        if self.current in self.pages:
            self.pages[self.current].pack_forget()
        if name not in self.pages:
            self.pages[name] = self.PAGES[name][0](self.container, self)
        page = self.pages[name]
        # keep data fresh when switching pages (loaded in the background)
        if isinstance(page, CrudPage):
            page.reload_options()
            page.refresh()
        elif isinstance(page, DashboardPage):
            page.refresh()
        page.pack(fill="both", expand=True)
        for n, item in self.nav.items():
            item.set_active(n == name)
        self.current = name
        self.page_title.config(text=name)
        if name == "Dashboard":
            hour = datetime.now().hour
            greet = "Good morning" if hour < 12 else "Good afternoon" if hour < 17 else "Good evening"
            self.page_sub.config(text=f"{greet}, {DEVELOPER.split()[0]}! "
                                      "Here's what's happening at the hospital today.")
        else:
            self.page_sub.config(text=self.PAGES[name][2])
        self.set_status(f"Viewing {name}" + ("   ·   Ctrl+S save  ·  Esc clear  ·  Ctrl+F search"
                                             if isinstance(page, CrudPage) else ""))

    def set_status(self, msg):
        if self.status is not None and self.status.winfo_exists():
            self.status.config(text=msg)

    def show_busy(self, busy):
        if self.busy_lbl is not None and self.busy_lbl.winfo_exists():
            self.busy_lbl.config(text="●  Syncing…" if busy else "")

    def _start_clock(self):
        if self._tick_id:
            self.after_cancel(self._tick_id)
        self._tick()

    def _tick(self):
        if self.clock is not None and self.clock.winfo_exists():
            self.clock.config(text=datetime.now().strftime("%a, %d %b %Y  ·  %I:%M %p"))
            self._tick_id = self.after(1000, self._tick)


if __name__ == "__main__":
    HospitalApp().mainloop()
