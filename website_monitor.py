r"""
Website Monitor
===============

Checks whether a website is responding, on a repeating interval, and tells you
the moment it comes back online (sound + pop-up + window jumps to the front).

Run it by double-clicking the "Website Monitor" shortcut or
"Run Website Monitor.bat" (uses ArcGIS Pro's Python -- nothing to install).

"Up"   = the server sent back a real response (any HTTP status below 500).
"Down" = no response within 30 s, connection refused/DNS failure, or a 5xx
         server error (502/503/504 are what you usually get while a site is down).

Your last website, interval and light/dark choice are saved in
website_monitor_settings.json next to this script.
"""

import json
import os
import threading
import time
import tkinter as tk
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from tkinter import messagebox, ttk

try:
    import winsound
except ImportError:
    winsound = None

HERE = os.path.dirname(os.path.abspath(__file__))
ICON_FILE = os.path.join(HERE, "website_monitor.ico")
SETTINGS_FILE = os.path.join(HERE, "website_monitor_settings.json")

INTERVALS = {
    "30 seconds": 30,
    "1 minute": 60,
    "2 minutes": 120,
    "5 minutes": 300,
    "10 minutes": 600,
    "15 minutes": 900,
    "30 minutes": 1800,
    "60 minutes": 3600,
}
TIMEOUT = 30
MAX_POINTS = 60  # checks shown on the graph

THEMES = {
    "light": {
        "bg": "#f3f3f3", "fg": "#1e1e1e", "muted": "#666666",
        "field": "#ffffff", "border": "#c8c8c8", "button": "#e4e4e4", "button_active": "#d4d4d4",
        "select": "#0078d4",
        "graph_bg": "#ffffff", "grid": "#e6e6e6", "line": "#0078d4",
        "up_bg": "#78d282", "down_bg": "#f07878", "idle_bg": "#d3d3d3", "status_fg": "#1e1e1e",
        "up_dot": "#2e9d3e", "down_dot": "#d63c3c", "down_band": "#fbe1e1", "progress": "#0078d4",
    },
    "dark": {
        "bg": "#1f1f1f", "fg": "#e6e6e6", "muted": "#9a9a9a",
        "field": "#2b2b2b", "border": "#3c3c3c", "button": "#333333", "button_active": "#444444",
        "select": "#2f6fb0",
        "graph_bg": "#252526", "grid": "#353535", "line": "#4fa3ff",
        "up_bg": "#2f7d3a", "down_bg": "#a33a3a", "idle_bg": "#3a3a3a", "status_fg": "#ffffff",
        "up_dot": "#5fd16f", "down_dot": "#ff6b6b", "down_band": "#3d2626", "progress": "#4fa3ff",
    },
}


def probe(url):
    """Return (is_up, detail_text, response_ms or None)."""
    start = time.time()
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) WebsiteMonitor"}
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            ms = int((time.time() - start) * 1000)
            return True, f"{resp.status} {resp.reason} ({ms} ms)", ms
    except urllib.error.HTTPError as e:
        ms = int((time.time() - start) * 1000)
        up = e.code < 500
        return up, f"{e.code} {e.reason}", ms if up else None
    except urllib.error.URLError as e:
        reason = e.reason
        if isinstance(reason, TimeoutError) or "timed out" in str(reason):
            return False, f"Timed out (no response in {TIMEOUT} s)", None
        return False, f"Can't connect: {reason}", None
    except TimeoutError:
        return False, f"Timed out (no response in {TIMEOUT} s)", None
    except Exception as e:
        return False, f"Error: {e}", None


def load_settings():
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_settings(data):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


class App:
    def __init__(self, root):
        self.root = root
        self.running = False
        self.checking = False
        self.check_started = None
        self.last_up = None
        self.next_check = None
        self.timer_id = None
        self.history = []  # list of (datetime, is_up, ms or None)

        settings = load_settings()
        self.theme_name = "dark" if settings.get("dark", False) else "light"

        root.title("Website Monitor")
        scale = max(1.0, root.winfo_fpixels("1i") / 96)  # Windows display scaling (125%, 150%...)
        height = min(int(640 * scale), int(root.winfo_screenheight() * 0.85))
        root.geometry(settings.get("geometry", f"{int(640 * scale)}x{height}"))
        root.minsize(int(500 * scale), min(int(520 * scale), height))
        if os.path.exists(ICON_FILE):
            try:
                root.iconbitmap(default=ICON_FILE)
            except tk.TclError:
                pass
            self.set_sharp_icon()

        self.style = ttk.Style(root)
        self.style.theme_use("clam")

        frm = ttk.Frame(root, padding=12)
        frm.pack(fill="both", expand=True)
        frm.columnconfigure(1, weight=1)

        ttk.Label(frm, text="Website:").grid(row=0, column=0, sticky="w")
        self.url_var = tk.StringVar(value=settings.get("url", "https://"))
        self.url_entry = ttk.Entry(frm, textvariable=self.url_var)
        self.url_entry.grid(row=0, column=1, columnspan=4, sticky="ew", pady=(0, 8))
        self.url_entry.bind("<Return>", lambda e: self.toggle())

        ttk.Label(frm, text="Check every:").grid(row=1, column=0, sticky="w")
        controls = ttk.Frame(frm)
        controls.grid(row=1, column=1, columnspan=4, sticky="ew")
        interval = settings.get("interval", "1 minute")
        self.interval_var = tk.StringVar(value=interval if interval in INTERVALS else "1 minute")
        self.interval_cb = ttk.Combobox(controls, textvariable=self.interval_var, values=list(INTERVALS),
                                        state="readonly", width=11)
        self.interval_cb.pack(side="left")
        self.interval_cb.bind("<<ComboboxSelected>>",
                              lambda e: self.running and not self.checking and self.schedule_next())

        self.start_btn = ttk.Button(controls, text="Start", width=6, command=self.toggle)
        self.start_btn.pack(side="left", padx=(8, 0))
        self.check_btn = ttk.Button(controls, text="Check now", width=10, command=self.check_now)
        self.check_btn.pack(side="left", padx=(6, 0))
        self.theme_btn = ttk.Button(controls, width=10, command=self.toggle_theme)
        self.theme_btn.pack(side="right")

        self.popup_var = tk.BooleanVar(value=settings.get("popup", True))
        ttk.Checkbutton(frm, text="Pop up when it's back online", variable=self.popup_var).grid(
            row=2, column=0, columnspan=5, sticky="w", pady=6)

        self.status = tk.Label(frm, text="Not started", font=("Segoe UI", 18, "bold"), height=2)
        self.status.grid(row=3, column=0, columnspan=5, sticky="ew")
        self.status_state = "idle"

        self.next_var = tk.StringVar()
        ttk.Label(frm, textvariable=self.next_var, style="Muted.TLabel").grid(
            row=4, column=0, columnspan=3, sticky="w", pady=4)
        self.stats_var = tk.StringVar()
        ttk.Label(frm, textvariable=self.stats_var, style="Muted.TLabel").grid(
            row=4, column=3, columnspan=2, sticky="e", pady=4)

        self.graph = tk.Canvas(frm, height=190, highlightthickness=1, bd=0)
        self.graph.grid(row=5, column=0, columnspan=5, sticky="nsew", pady=(0, 8))
        self.graph.bind("<Configure>", lambda e: self.draw_graph())
        frm.rowconfigure(5, weight=3)

        log_frame = ttk.Frame(frm)
        log_frame.grid(row=6, column=0, columnspan=5, sticky="nsew")
        frm.rowconfigure(6, weight=2)
        self.log = tk.Listbox(log_frame, font=("Consolas", 9), height=6, bd=0, highlightthickness=1,
                              activestyle="none")
        sb = ttk.Scrollbar(log_frame, command=self.log.yview)
        self.log.config(yscrollcommand=sb.set)
        self.log.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        self.apply_theme()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.url_entry.focus_set()
        self.url_entry.icursor("end")
        self.tick()

    # ---- theme -----------------------------------------------------------
    def toggle_theme(self):
        self.theme_name = "light" if self.theme_name == "dark" else "dark"
        self.apply_theme()

    def apply_theme(self):
        c = THEMES[self.theme_name]
        s = self.style
        self.root.configure(bg=c["bg"])
        s.configure(".", background=c["bg"], foreground=c["fg"], fieldbackground=c["field"],
                    bordercolor=c["border"], lightcolor=c["border"], darkcolor=c["border"],
                    troughcolor=c["bg"], selectbackground=c["select"], selectforeground="#ffffff",
                    insertcolor=c["fg"], font=("Segoe UI", 10))
        s.configure("TFrame", background=c["bg"])
        s.configure("TLabel", background=c["bg"], foreground=c["fg"])
        s.configure("Muted.TLabel", background=c["bg"], foreground=c["muted"])
        s.configure("TButton", background=c["button"], foreground=c["fg"], padding=(10, 4))
        s.map("TButton",
              background=[("disabled", c["bg"]), ("pressed", c["button_active"]), ("active", c["button_active"])],
              foreground=[("disabled", c["muted"])])
        s.configure("TCheckbutton", background=c["bg"], foreground=c["fg"], indicatorbackground=c["field"],
                    indicatorforeground=c["fg"])
        s.map("TCheckbutton", background=[("active", c["bg"])],
              indicatorbackground=[("pressed", c["button_active"]), ("active", c["field"])])
        s.configure("TEntry", fieldbackground=c["field"], foreground=c["fg"], padding=4)
        s.map("TEntry", fieldbackground=[("disabled", c["bg"])], foreground=[("disabled", c["muted"])])
        s.configure("TCombobox", fieldbackground=c["field"], background=c["button"], foreground=c["fg"],
                    arrowcolor=c["fg"], padding=3)
        s.map("TCombobox", fieldbackground=[("readonly", c["field"])], foreground=[("readonly", c["fg"])],
              selectbackground=[("readonly", c["field"])], selectforeground=[("readonly", c["fg"])],
              background=[("active", c["button_active"])])
        s.configure("Vertical.TScrollbar", background=c["button"], arrowcolor=c["fg"], troughcolor=c["bg"])
        s.map("Vertical.TScrollbar", background=[("active", c["button_active"])])

        # The combobox drop-down list is a plain Tk listbox; colour it directly.
        try:
            popdown = self.root.tk.eval(f"ttk::combobox::PopdownWindow {self.interval_cb}")
            self.root.tk.call(f"{popdown}.f.l", "configure", "-background", c["field"],
                              "-foreground", c["fg"], "-selectbackground", c["select"],
                              "-selectforeground", "#ffffff")
        except tk.TclError:
            pass

        self.log.configure(bg=c["field"], fg=c["fg"], selectbackground=c["select"],
                           highlightbackground=c["border"], highlightcolor=c["border"])
        self.graph.configure(bg=c["graph_bg"], highlightbackground=c["border"])
        self.theme_btn.configure(text="Light mode" if self.theme_name == "dark" else "Dark mode")
        self.set_status(self.status_state, self.status.cget("text"))
        self.set_title_bar_dark(self.theme_name == "dark")
        self.draw_graph()

    def set_title_bar_dark(self, dark):
        """Windows 10/11: make the window's title bar match the theme."""
        try:
            from ctypes import byref, c_int, sizeof, windll
            self.root.update_idletasks()
            hwnd = windll.user32.GetParent(self.root.winfo_id())
            value = c_int(1 if dark else 0)
            for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (new id, old id)
                if windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, byref(value), sizeof(value)) == 0:
                    break
            # Nudge the window so Windows repaints the title bar right away.
            w, h = self.root.winfo_width(), self.root.winfo_height()
            if w > 1:
                self.root.geometry(f"{w + 1}x{h}")
                self.root.geometry(f"{w}x{h}")
        except Exception:
            pass

    def set_sharp_icon(self):
        """Tk only hands Windows the 16px icon, which looks blurry when stretched on the
        taskbar. Load the right sizes from the .ico ourselves and give them to Windows."""
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            user32.GetParent.restype = wintypes.HWND
            user32.LoadImageW.restype = wintypes.HANDLE
            user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
                                          ctypes.c_int, ctypes.c_int, wintypes.UINT]
            user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
            self.root.update_idletasks()
            hwnd = user32.GetParent(self.root.winfo_id())
            IMAGE_ICON, LR_LOADFROMFILE, WM_SETICON = 1, 0x10, 0x80
            # (ICON_BIG, SM_CXICON, SM_CYICON) for taskbar/Alt-Tab, (ICON_SMALL, SM_CXSMICON, SM_CYSMICON) for title bar
            for which, metric_x, metric_y in ((1, 11, 12), (0, 49, 50)):
                hicon = user32.LoadImageW(None, ICON_FILE, IMAGE_ICON, user32.GetSystemMetrics(metric_x),
                                          user32.GetSystemMetrics(metric_y), LR_LOADFROMFILE)
                if hicon:
                    user32.SendMessageW(hwnd, WM_SETICON, which, hicon)
        except Exception:
            pass

    def set_status(self, state, text):
        c = THEMES[self.theme_name]
        self.status_state = state
        self.status.configure(text=text, bg=c[state + "_bg"], fg=c["status_fg"])

    # ---- helpers ---------------------------------------------------------
    def get_url(self):
        url = self.url_var.get().strip()
        if url in ("", "http://", "https://"):
            return None
        if not url.lower().startswith(("http://", "https://")):
            url = "https://" + url
            self.url_var.set(url)
        return url

    def add_log(self, msg):
        self.log.insert(0, f"{datetime.now():%H:%M:%S}  {msg}")
        if self.log.size() > 500:
            self.log.delete(500, "end")

    def bring_to_front(self):
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.focus_force()

    def on_close(self):
        save_settings({
            "url": self.url_var.get().strip(),
            "interval": self.interval_var.get(),
            "dark": self.theme_name == "dark",
            "popup": self.popup_var.get(),
            "geometry": f"{self.root.winfo_width()}x{self.root.winfo_height()}",
        })
        self.root.destroy()

    # ---- start / stop / schedule ----------------------------------------
    def toggle(self):
        if self.running:
            self.running = False
            if self.timer_id:
                self.root.after_cancel(self.timer_id)
                self.timer_id = None
            self.start_btn.config(text="Start")
            self.url_entry.config(state="normal")
            self.next_var.set("Stopped.")
            self.add_log("Monitoring stopped.")
            self.draw_progress()
            return
        url = self.get_url()
        if not url:
            messagebox.showwarning("Website Monitor", "Please enter a website address.")
            return
        self.running = True
        self.last_up = None
        self.history.clear()
        self.start_btn.config(text="Stop")
        self.url_entry.config(state="disabled")
        self.add_log(f"Monitoring started: {url}")
        self.draw_graph()
        self.check_now()

    def schedule_next(self):
        if self.timer_id:
            self.root.after_cancel(self.timer_id)
        secs = INTERVALS[self.interval_var.get()]
        self.next_check = datetime.now() + timedelta(seconds=secs)
        self.timer_id = self.root.after(secs * 1000, self.check_now)

    def tick(self):
        if self.running and not self.checking and self.next_check:
            left = max(0, int((self.next_check - datetime.now()).total_seconds()))
            self.next_var.set(f"Next check in {left // 60}m {left % 60:02d}s")
        self.draw_progress()
        self.root.after(100, self.tick)

    # ---- checking --------------------------------------------------------
    def check_now(self):
        if self.checking:
            return
        url = self.get_url()
        if not url:
            messagebox.showwarning("Website Monitor", "Please enter a website address.")
            return
        self.checking = True
        self.check_started = time.time()
        if self.timer_id:
            self.root.after_cancel(self.timer_id)
            self.timer_id = None
        self.check_btn.config(state="disabled")
        self.next_var.set(f"Checking {url} ...")

        def work():
            up, detail, ms = probe(url)
            self.root.after(0, lambda: self.show_result(url, up, detail, ms))

        threading.Thread(target=work, daemon=True).start()

    def show_result(self, url, up, detail, ms):
        self.checking = False
        self.check_btn.config(state="normal")
        self.set_status("up" if up else "down", "ONLINE" if up else "DOWN")
        self.add_log(("UP    - " if up else "DOWN  - ") + detail)

        self.history.append((datetime.now(), up, ms))
        del self.history[:-MAX_POINTS]
        self.update_stats()
        self.draw_graph()

        came_back = up and self.last_up is False  # only alert on a real down -> up change
        self.last_up = up

        if self.running:
            self.schedule_next()
        else:
            self.next_var.set("Checked once. Press Start to keep monitoring.")

        if came_back and self.running:
            if winsound:
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            else:
                self.root.bell()
            if self.popup_var.get():
                self.bring_to_front()
                messagebox.showinfo("Website is back online!",
                                    f"{url}\n\nis responding again:\n{detail}", parent=self.root)
                self.root.attributes("-topmost", False)

    def update_stats(self):
        n = len(self.history)
        ups = [h for h in self.history if h[1]]
        times = [h[2] for h in ups if h[2] is not None]
        text = f"Checks: {n}   Up: {100 * len(ups) // n}%"
        if times:
            text += f"   Avg: {sum(times) // len(times)} ms"
        self.stats_var.set(text)

    # ---- graph -----------------------------------------------------------
    PAD_L, PAD_R, PAD_T, PAD_B = 58, 14, 46, 26

    def plot_area(self):
        w = self.graph.winfo_width()
        h = self.graph.winfo_height()
        return self.PAD_L, self.PAD_T, w - self.PAD_R, h - self.PAD_B

    def draw_progress(self):
        """Thin bar across the top of the graph: fills up until the next check,
        and shows a sliding pulse while a check is in progress."""
        g = self.graph
        g.delete("progress")
        c = THEMES[self.theme_name]
        _, _, x1, _ = self.plot_area()
        x0 = self.PAD_R
        if x1 <= x0:
            return
        y = 10
        g.create_line(x0, y, x1, y, fill=c["grid"], width=4, tags="progress")
        if self.checking:
            span = (x1 - x0) * 0.25
            phase = ((time.time() - self.check_started) % 1.2) / 1.2
            start = x0 - span + phase * (x1 - x0 + span)
            g.create_line(max(x0, start), y, min(x1, start + span), y,
                          fill=c["progress"], width=4, tags="progress")
        elif self.running and self.next_check:
            total = INTERVALS[self.interval_var.get()]
            left = max(0.0, (self.next_check - datetime.now()).total_seconds())
            frac = 1 - min(1.0, left / total)
            g.create_line(x0, y, x0 + frac * (x1 - x0), y, fill=c["progress"], width=4, tags="progress")

    def draw_graph(self):
        g = self.graph
        g.delete("all")
        c = THEMES[self.theme_name]
        x0, y0, x1, y1 = self.plot_area()
        if x1 - x0 < 20 or y1 - y0 < 20:
            return

        g.create_text(x0, y0 - 4, text="Response time (ms)", anchor="sw",
                      fill=c["muted"], font=("Segoe UI", 8), tags="axis")

        times = [h[2] for h in self.history if h[2] is not None]
        top = max(times) * 1.2 if times else 1000
        step = self.nice_step(top / 4)
        top = step * 4

        for i in range(5):
            y = y1 - (y1 - y0) * i / 4
            g.create_line(x0, y, x1, y, fill=c["grid"])
            g.create_text(x0 - 6, y, text=f"{int(step * i)}", anchor="e",
                          fill=c["muted"], font=("Segoe UI", 8))

        if not self.history:
            g.create_text((x0 + x1) / 2, (y0 + y1) / 2,
                          text="Results will appear here after the first check",
                          fill=c["muted"], font=("Segoe UI", 9))
            self.draw_progress()
            return

        n = len(self.history)
        slot = (x1 - x0) / max(MAX_POINTS - 1, 1)

        def xpos(i):
            # Newest point sits at the right edge; history scrolls left.
            return x1 - (n - 1 - i) * slot

        # Red bands behind checks where the site was down.
        for i, (_, up, _) in enumerate(self.history):
            if not up:
                x = xpos(i)
                g.create_rectangle(max(x0, x - slot / 2), y0, min(x1, x + slot / 2), y1,
                                   fill=c["down_band"], outline="")
        for i in range(5):  # redraw grid over the bands
            y = y1 - (y1 - y0) * i / 4
            g.create_line(x0, y, x1, y, fill=c["grid"])

        # Line through consecutive successful checks.
        prev = None
        for i, (_, up, ms) in enumerate(self.history):
            if up and ms is not None:
                pt = (xpos(i), y1 - (y1 - y0) * min(ms, top) / top)
                if prev:
                    g.create_line(*prev, *pt, fill=c["line"], width=2, smooth=True)
                prev = pt
            else:
                prev = None

        r = 3.5
        for i, (_, up, ms) in enumerate(self.history):
            x = xpos(i)
            if up and ms is not None:
                y = y1 - (y1 - y0) * min(ms, top) / top
                g.create_oval(x - r, y - r, x + r, y + r, fill=c["up_dot"], outline=c["graph_bg"])
            else:
                y = y1 - 6
                g.create_line(x - r, y - r, x + r, y + r, fill=c["down_dot"], width=2)
                g.create_line(x - r, y + r, x + r, y - r, fill=c["down_dot"], width=2)

        if n == 1 or xpos(0) < x1 - 110:
            g.create_text(xpos(0), y1 + 6, text=f"{self.history[0][0]:%H:%M:%S}",
                          anchor="ne" if n == 1 else "n", fill=c["muted"], font=("Segoe UI", 8))
        if n > 1:
            g.create_text(x1, y1 + 6, text=f"{self.history[-1][0]:%H:%M:%S}", anchor="ne",
                          fill=c["muted"], font=("Segoe UI", 8))
        self.draw_progress()

    @staticmethod
    def nice_step(raw):
        for s in (25, 50, 100, 200, 250, 500, 1000, 2000, 2500, 5000, 10000):
            if raw <= s:
                return s
        return 10000


if __name__ == "__main__":
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)  # crisp text on high-DPI screens
        # Own taskbar identity, so the taskbar shows our icon instead of Python's.
        windll.shell32.SetCurrentProcessExplicitAppUserModelID("WebsiteMonitor.App")
    except Exception:
        pass
    root = tk.Tk()
    App(root)
    root.mainloop()
