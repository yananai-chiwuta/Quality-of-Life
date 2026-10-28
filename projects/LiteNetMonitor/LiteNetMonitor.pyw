"""A small, local-first desktop traffic monitor."""
from collections import deque
import csv
from datetime import datetime, timezone
from pathlib import Path
import queue
import re
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox

import psutil
from netmonitor_core import APP_VERSION, TrafficSampler, format_bytes, format_rate, load_settings, save_settings

THEMES = {
    'midnight': dict(bg='#10151f', surface='#192231', fg='#f0f4fa', muted='#9aaac0', line='#2b384b', down='#65dfc1', up='#a7b8ff'),
    'paper': dict(bg='#f4f6fa', surface='#ffffff', fg='#192436', muted='#59697f', line='#d8e0ea', down='#087d69', up='#5b50c6'),
}


class LiteNetworkMonitor:
    def __init__(self, root):
        self.root = root
        self.settings = load_settings()
        if self.settings['interval'] not in (1, 2, 5):
            self.settings['interval'] = 1
        if self.settings['theme'] not in THEMES:
            self.settings['theme'] = 'midnight'
        self.sampler = TrafficSampler(self.settings['nic'])
        self.reading = dict(down=0, up=0, received=0, sent=0, total=0, available=True)
        self.history = deque(maxlen=60)
        self.events = queue.Queue()
        self.closed = self.paused = self.tray_pending = self.ping_pending = False
        self.icon = self.after_id = self.drag_origin = None
        self.notice_until = 0
        self.root.title(f'LiteNetMonitor {APP_VERSION}')
        self.root.resizable(False, False)
        self.root.geometry('380x374')
        self.root.attributes('-topmost', self.settings['always_on_top'])
        if sys.platform == 'win32':
            self.root.overrideredirect(True)
            self.root.bind('<Map>', self._restore_borderless)
        position = self.settings['position']
        if position:
            x = max(0, min(position[0], self.root.winfo_screenwidth() - 380))
            y = max(0, min(position[1], self.root.winfo_screenheight() - 374))
            self.root.geometry(f'+{x}+{y}')
        self.root.protocol('WM_DELETE_WINDOW', self.exit_app)
        self.family = 'Segoe UI' if sys.platform == 'win32' else 'Helvetica' if sys.platform == 'darwin' else 'DejaVu Sans'
        self.widgets = []
        self._build_ui()
        self.apply_theme()
        self.root.bind('<Button-3>', self.popup_menu)
        if sys.platform == 'darwin':
            self.root.bind('<Button-2>', self.popup_menu)
            self.root.bind('<Control-Button-1>', self.popup_menu)
        self.root.bind('<Command-c>' if sys.platform == 'darwin' else '<Control-c>', self.copy_speed)
        self.root.bind('<space>', lambda e: self.toggle_pause())
        self.root.bind('<t>', lambda e: self.cycle_theme())
        self.root.bind('<Escape>', lambda e: self.minimize())
        self.update_stats()
        self.root.after(100, self.drain_events)

    def label(self, parent, text, role='fg', bg='bg', size=10, bold=False):
        widget = tk.Label(parent, text=text, font=(self.family, size, 'bold' if bold else 'normal'), anchor='w')
        self.widgets.append((widget, role, bg))
        return widget

    def button(self, parent, text, command):
        widget = tk.Button(parent, text=text, command=command, relief='flat', bd=0, cursor='hand2',
                           font=(self.family, 9), padx=8, pady=4, takefocus=True)
        self.widgets.append((widget, 'muted', 'bg'))
        return widget

    def _build_ui(self):
        self.frames = []
        self.header = tk.Frame(self.root)
        self.frames.append(self.header)
        self.header.pack(fill='x', padx=18, pady=(12, 8))
        self.title = self.label(self.header, '●  LITE / NET', 'down', bold=True)
        self.title.pack(side='left')
        self.button(self.header, '×', self.exit_app).pack(side='right')
        self.button(self.header, '−', self.minimize).pack(side='right')
        self.menu_btn = self.button(self.header, '•••', self.popup_menu)
        self.menu_btn.pack(side='right')
        for widget in (self.header, self.title):
            widget.bind('<Button-1>', self.start_move)
            widget.bind('<B1-Motion>', self.move_window)
        self.adapter = self.label(self.root, '', 'muted', size=9)
        self.adapter.pack(fill='x', padx=22, pady=(0, 10))
        row = tk.Frame(self.root)
        self.frames.append(row)
        row.pack(fill='x', padx=18)
        row.columnconfigure((0, 1), weight=1, uniform='rate')
        self.cards, self.rates, self.units = [], [], []
        for index, (title, role) in enumerate((('↓ DOWNLOAD', 'down'), ('↑ UPLOAD', 'up'))):
            card = tk.Frame(row, padx=12, pady=10)
            self.cards.append(card)
            card.grid(row=0, column=index, sticky='nsew', padx=(0, 5) if index == 0 else (5, 0))
            self.label(card, title, role, 'surface', 8, True).pack(anchor='w')
            rate = self.label(card, '0.0', bg='surface', size=22, bold=True)
            rate.pack(anchor='w', pady=(4, 0))
            unit = self.label(card, 'B/s', 'muted', 'surface', 9)
            unit.pack(anchor='w')
            self.rates.append(rate)
            self.units.append(unit)
            for child in (card, *card.winfo_children()):
                child.bind('<Double-Button-1>', self.copy_speed)
        graph_header = tk.Frame(self.root)
        self.frames.append(graph_header)
        graph_header.pack(fill='x', padx=22, pady=(14, 0))
        self.label(graph_header, 'LAST 60 SECONDS', 'muted', size=8, bold=True).pack(side='left')
        self.scale_label = self.label(graph_header, '', 'muted', size=9)
        self.scale_label.pack(side='right')
        self.graph = tk.Canvas(self.root, height=56, highlightthickness=0)
        self.graph.pack(fill='x', padx=22, pady=(4, 10))
        self.graph.bind('<Configure>', lambda e: self.draw_graph())
        self.divider = tk.Frame(self.root, height=1)
        self.divider.pack(fill='x', padx=22)
        self.totals = self.label(self.root, '', 'muted', size=9)
        self.totals.pack(fill='x', padx=22, pady=(10, 4))
        footer = tk.Frame(self.root)
        self.frames.append(footer)
        footer.pack(fill='x', padx=18)
        self.status = self.label(footer, '● Live · local only', 'down', size=9)
        self.status.pack(side='left')
        self.pause_btn = self.button(footer, 'Pause', self.toggle_pause)
        self.pause_btn.pack(side='right')

    def apply_theme(self):
        theme = THEMES[self.settings['theme']]
        self.root.config(bg=theme['bg'])
        for frame in self.frames:
            frame.config(bg=theme['bg'])
        for card in self.cards:
            card.config(bg=theme['surface'])
        for widget, role, bg in self.widgets:
            widget.config(bg=theme[bg], fg=theme[role])
            if isinstance(widget, tk.Button):
                widget.config(activebackground=theme['surface'], activeforeground=theme['fg'],
                              highlightbackground=theme['line'], highlightcolor=theme['down'])
        self.graph.config(bg=theme['bg'])
        self.divider.config(bg=theme['line'])
        self.draw_graph()

    def popup_menu(self, event=None):
        if hasattr(self, 'menu'):
            self.menu.destroy()
        menu = tk.Menu(self.root, tearoff=False)
        self.menu = menu
        menu.add_command(label='Copy current speeds     Ctrl/Cmd+C', command=self.copy_speed)
        menu.add_command(label='Export session snapshot…', command=self.export_csv)
        menu.add_command(label='Reset session', command=self.reset_session)
        menu.add_separator()
        self.nic_var = tk.StringVar(value=self.settings['nic'])
        adapters = tk.Menu(menu, tearoff=False)
        adapters.add_radiobutton(label='All adapters', variable=self.nic_var, value='All', command=self.set_nic)
        for nic in sorted(psutil.net_io_counters(pernic=True)):
            adapters.add_radiobutton(label=nic, variable=self.nic_var, value=nic, command=self.set_nic)
        menu.add_cascade(label='Network adapter', menu=adapters)
        self.bits_var = tk.BooleanVar(value=self.settings['use_bits'])
        menu.add_checkbutton(label='Show bits per second', variable=self.bits_var, command=self.toggle_units)
        self.top_var = tk.BooleanVar(value=self.settings['always_on_top'])
        menu.add_checkbutton(label='Always on top', variable=self.top_var, command=self.toggle_topmost)
        menu.add_command(label='Switch light / dark theme     T', command=self.cycle_theme)
        self.interval_var = tk.IntVar(value=int(self.settings['interval']))
        intervals = tk.Menu(menu, tearoff=False)
        for seconds in (1, 2, 5):
            intervals.add_radiobutton(label=f'Every {seconds}s', variable=self.interval_var, value=seconds, command=self.set_interval)
        menu.add_cascade(label='Refresh interval', menu=intervals)
        menu.add_separator()
        menu.add_command(label='Check latency (1.1.1.1)…', command=self.check_latency)
        menu.add_command(label='Local network details…', command=self.show_ip)
        if sys.platform == 'win32':
            self.autostart_var = tk.BooleanVar(value=self.autostart_enabled())
            menu.add_checkbutton(label='Start with Windows', variable=self.autostart_var, command=self.toggle_autostart)
        if sys.platform != 'darwin':
            menu.add_command(label='Hide in system tray (optional)', command=self.minimize_to_tray)
        menu.add_command(label='About / keyboard shortcuts…', command=self.show_about)
        menu.add_separator()
        menu.add_command(label='Quit LiteNetMonitor', command=self.exit_app)
        x = event.x_root if event else self.menu_btn.winfo_rootx()
        y = event.y_root if event else self.menu_btn.winfo_rooty() + self.menu_btn.winfo_height()
        try:
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def persist(self):
        try:
            save_settings(self.settings)
        except OSError:
            self.notify('Preferences could not be saved')

    def set_nic(self):
        self.settings['nic'] = self.nic_var.get()
        self.sampler = TrafficSampler(self.settings['nic'])
        self.reset_session()
        self.persist()

    def reset_session(self):
        self.sampler.reset()
        self.history.clear()
        self.reading = self.sampler.sample()
        self.render_reading()
        self.draw_graph()
        self.notify('Session reset')

    def toggle_pause(self):
        self.paused = not self.paused
        self.pause_btn.config(text='Resume' if self.paused else 'Pause')
        self.notice_until = 0
        self.update_status()

    def cycle_theme(self):
        self.settings['theme'] = 'paper' if self.settings['theme'] == 'midnight' else 'midnight'
        self.apply_theme()
        self.persist()

    def toggle_units(self):
        self.settings['use_bits'] = self.bits_var.get()
        self.render_reading()
        self.draw_graph()
        self.persist()

    def toggle_topmost(self):
        self.settings['always_on_top'] = self.top_var.get()
        self.root.attributes('-topmost', self.settings['always_on_top'])
        self.persist()

    def set_interval(self):
        self.settings['interval'] = self.interval_var.get()
        self.persist()
        if self.after_id:
            self.root.after_cancel(self.after_id)
        self.update_stats()

    def render_reading(self):
        available = self.reading['available']
        for index, key in enumerate(('down', 'up')):
            value, unit = format_rate(self.reading[key], self.settings['use_bits']).split()
            self.rates[index].config(text=value if available else '—')
            self.units[index].config(text=unit if available else 'unavailable')
        nic = self.settings['nic']
        self.adapter.config(text='All adapters' if nic == 'All' else nic)
        self.totals.config(text=f"SESSION   ↓ {format_bytes(self.reading['received'])}    ↑ {format_bytes(self.reading['sent'])}")

    def update_stats(self):
        if self.closed:
            return
        try:
            current = self.sampler.sample()
        except (OSError, RuntimeError):
            current = dict(self.reading, available=False)
        if not self.paused:
            self.reading = current
            self.history.append((time.monotonic(), current['down'] if current['available'] else 0, current['up'] if current['available'] else 0))
            self.render_reading()
            self.draw_graph()
        self.update_status()
        self.after_id = self.root.after(int(self.settings['interval'] * 1000), self.update_stats)

    def draw_graph(self):
        theme = THEMES[self.settings['theme']]
        self.graph.delete('all')
        width, height = max(20, self.graph.winfo_width()), 54
        end = self.history[-1][0] if self.history else time.monotonic()
        points = [item for item in self.history if item[0] >= end - 60]
        peak = max((max(p[1], p[2]) for p in points), default=0)
        self.scale_label.config(text=format_rate(peak, self.settings['use_bits']) + ' peak')
        for y in (2, 27, 53):
            self.graph.create_line(0, y, width, y, fill=theme['line'], dash=(2, 5))
        for index, role in ((1, 'down'), (2, 'up')):
            coords = []
            for point in points:
                coords.extend(((point[0] - end + 60) / 60 * width, height - 2 - point[index] / max(peak, 1) * (height - 6)))
            if len(coords) >= 4:
                self.graph.create_line(*coords, fill=theme[role], width=2)

    def update_status(self):
        if time.monotonic() < self.notice_until:
            return
        text = 'Ⅱ Display paused · still counting' if self.paused else '● Live · local only' if self.reading['available'] else '● Adapter unavailable'
        self.status.config(text=text)

    def notify(self, text):
        self.notice_until = time.monotonic() + 3
        self.status.config(text=text)

    def copy_speed(self, event=None):
        if not self.reading['available']:
            self.notify('Select an available adapter')
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(f"Download: {format_rate(self.reading['down'], self.settings['use_bits'])} | Upload: {format_rate(self.reading['up'], self.settings['use_bits'])}")
        self.notify('Speeds copied')

    def export_csv(self):
        path = filedialog.asksaveasfilename(parent=self.root, title='Export session snapshot', defaultextension='.csv',
                                          initialfile='litenetmonitor-session.csv', filetypes=[('CSV', '*.csv')])
        if not path:
            return
        try:
            with open(path, 'w', newline='', encoding='utf-8') as stream:
                writer = csv.writer(stream)
                writer.writerow(('timestamp_utc', 'adapter', 'available', 'download_bytes_per_second', 'upload_bytes_per_second', 'session_received_bytes', 'session_sent_bytes'))
                nic = self.settings['nic']
                if nic.startswith(('=', '+', '-', '@', '\t', '\r', '\n')):
                    nic = "'" + nic
                writer.writerow((datetime.now(timezone.utc).isoformat(), nic, self.reading['available'],
                                 round(self.reading['down'], 2), round(self.reading['up'], 2), self.reading['received'], self.reading['sent']))
            self.notify('Session snapshot exported')
        except OSError as exc:
            messagebox.showerror('Export failed', str(exc), parent=self.root)

    def show_ip(self):
        lines = [f'Hostname: {socket.gethostname()}']
        for nic, addresses in psutil.net_if_addrs().items():
            if self.settings['nic'] != 'All' and nic != self.settings['nic']:
                continue
            for address in addresses:
                if address.family in (socket.AF_INET, socket.AF_INET6):
                    lines.append(f'{nic}: {address.address}')
        messagebox.showinfo('Local network details', '\n'.join(lines), parent=self.root)

    def check_latency(self):
        if self.ping_pending:
            return
        self.ping_pending = True
        self.notify('Checking latency…')
        threading.Thread(target=self._run_ping, daemon=True).start()

    def _run_ping(self):
        command = ['ping', '-n', '1', '-w', '1500', '1.1.1.1'] if sys.platform == 'win32' else ['ping', '-c', '1', '1.1.1.1']
        try:
            options = {'creationflags': subprocess.CREATE_NO_WINDOW} if sys.platform == 'win32' else {}
            result = subprocess.run(command, capture_output=True, text=True, errors='replace', timeout=4, **options)
            match = re.search(r'(?:time|temps|zeit|tempo)[=<]\s*([\d.,]+)\s*ms', result.stdout, re.I)
            text = f'Round trip to 1.1.1.1: {match.group(1)} ms' if result.returncode == 0 and match else 'Reply received from 1.1.1.1.' if result.returncode == 0 else 'No ICMP reply. This does not necessarily mean you are offline.'
        except (OSError, subprocess.TimeoutExpired):
            text = 'Ping is unavailable or timed out.'
        self.events.put(('ping', text))

    def drain_events(self):
        if self.closed:
            return
        try:
            while True:
                event, value = self.events.get_nowait()
                if event == 'show':
                    self.restore_from_tray()
                elif event == 'quit':
                    self.exit_app()
                    return
                elif event == 'tray_ready' and self.icon is value:
                    self.tray_pending = False
                    try:
                        value.visible = True
                        self.root.withdraw()
                    except Exception:
                        self.restore_from_tray()
                        self.notify('Tray unavailable · window restored')
                elif event == 'tray_error':
                    self.tray_pending = False
                    self.restore_from_tray()
                    self.notify('Tray unavailable · window restored')
                elif event == 'ping':
                    self.ping_pending = False
                    messagebox.showinfo('Latency check', value, parent=self.root)
        except queue.Empty:
            pass
        self.root.after(100, self.drain_events)

    def minimize_to_tray(self):
        if self.icon or self.tray_pending:
            return
        if getattr(sys, 'frozen', False):
            messagebox.showinfo('Tray support', 'The compact build uses regular minimize.\nRun from source with tray extras for a system tray icon.', parent=self.root)
            return
        try:
            import pystray
            from PIL import Image, ImageDraw
        except Exception:
            messagebox.showinfo('Optional tray support', 'Install tray extras with:\npython -m pip install -r requirements-tray.txt\n\nYou can also use the regular minimize button.', parent=self.root)
            return
        image = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
        pen = ImageDraw.Draw(image)
        pen.rounded_rectangle((2, 2, 62, 62), radius=14, fill='#192231')
        pen.line((17, 16, 17, 45, 10, 37, 17, 45, 24, 37), fill='#65dfc1', width=4)
        pen.line((45, 48, 45, 19, 38, 27, 45, 19, 52, 27), fill='#a7b8ff', width=4)
        menu = pystray.Menu(pystray.MenuItem('Show LiteNetMonitor', lambda *a: self.events.put(('show', None)), default=True),
                            pystray.MenuItem('Quit', lambda *a: self.events.put(('quit', None))))
        self.icon = pystray.Icon('LiteNetMonitor', image, 'LiteNetMonitor', menu)
        self.tray_pending = True
        icon = self.icon
        def run():
            try:
                icon.run(setup=lambda ready: self.events.put(('tray_ready', ready)))
            except Exception:
                self.events.put(('tray_error', None))
        threading.Thread(target=run, daemon=True).start()

    def restore_from_tray(self):
        if self.icon:
            icon, self.icon = self.icon, None
            icon.stop()
        self.root.deiconify()
        self.root.lift()

    def minimize(self):
        if sys.platform == 'win32':
            self.root.overrideredirect(False)
        self.root.iconify()

    def _restore_borderless(self, event):
        if event.widget is self.root and self.root.state() == 'normal':
            self.root.after_idle(lambda: self.root.overrideredirect(True) if not self.closed else None)

    def start_move(self, event):
        self.drag_origin = (event.x_root - self.root.winfo_x(), event.y_root - self.root.winfo_y())

    def move_window(self, event):
        if self.drag_origin:
            self.root.geometry(f'+{max(0, event.x_root - self.drag_origin[0])}+{max(0, event.y_root - self.drag_origin[1])}')

    @staticmethod
    def autostart_enabled():
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Run') as key:
                winreg.QueryValueEx(key, 'LiteNetMonitor')
            return True
        except OSError:
            return False

    def toggle_autostart(self):
        import winreg
        try:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Run') as key:
                if self.autostart_var.get():
                    executable = Path(sys.executable)
                    if not getattr(sys, 'frozen', False) and executable.with_name('pythonw.exe').exists():
                        executable = executable.with_name('pythonw.exe')
                    args = [str(executable)] if getattr(sys, 'frozen', False) else [str(executable), str(Path(__file__).resolve())]
                    winreg.SetValueEx(key, 'LiteNetMonitor', 0, winreg.REG_SZ, subprocess.list2cmdline(args))
                else:
                    try:
                        winreg.DeleteValue(key, 'LiteNetMonitor')
                    except FileNotFoundError:
                        pass
        except OSError as exc:
            messagebox.showerror('Startup setting failed', str(exc), parent=self.root)

    def show_about(self):
        messagebox.showinfo('About LiteNetMonitor', f'LiteNetMonitor {APP_VERSION}\nA little window into your network.\n\nSpace · pause display (traffic still counted)\nCtrl/Cmd+C · copy speeds\nT · switch theme\nEscape · minimize\nDrag the header · move\nRight-click or ••• · settings and tools\n\nAll adapters may include VPN/virtual traffic twice.\nAdapter changes start a fresh session.\nSessions end on reset, adapter change, or quit.\n\nMIT License · © 2026 Yananai Chiwuta', parent=self.root)

    def exit_app(self):
        if self.closed:
            return
        self.settings['position'] = [self.root.winfo_x(), self.root.winfo_y()]
        self.persist()
        self.closed = True
        if self.icon:
            self.icon.stop()
        self.root.destroy()


if __name__ == '__main__':
    root = tk.Tk()
    app = LiteNetworkMonitor(root)
    if '--smoke-test' in sys.argv:
        root.update()
        if not app.status.winfo_ismapped():
            raise RuntimeError('The application controls did not render')
        root.destroy()
    else:
        root.mainloop()
