"""Desktop integration checks; skipped when no graphical display is available."""
import csv
from pathlib import Path
import runpy
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch

import netmonitor_core as core

UI = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'LiteNetMonitor.pyw'))


class DesktopTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        self.addCleanup(self.cleanup_window)
        self.prefs = patch.dict(UI['LiteNetworkMonitor'].__init__.__globals__,
                                load_settings=core.default_settings, save_settings=lambda data: None)
        self.prefs.start()
        self.addCleanup(self.prefs.stop)
        self.app = UI['LiteNetworkMonitor'](self.root)
        self.root.update()

    def cleanup_window(self):
        for callback in self.root.tk.call('after', 'info'):
            self.root.after_cancel(callback)
        self.root.destroy()

    def test_window_controls_fit_and_menu_survives_posting(self):
        self.assertLess(self.app.pause_btn.winfo_rooty() + self.app.pause_btn.winfo_height(),
                        self.root.winfo_rooty() + self.root.winfo_height())
        # Native popup menus can wait for human input on unattended CI desktops.
        with patch.object(tk.Menu, 'tk_popup'):
            self.app.popup_menu()
        self.root.update_idletasks()
        self.assertTrue(self.app.menu.winfo_exists())
        self.app.menu.unpost()
        for index in range(self.app.menu.index('end') + 1):
            if self.app.menu.type(index) == 'command' and self.app.menu.entrycget(index, 'label').startswith('Switch light'):
                self.app.menu.invoke(index)
                break
        self.assertEqual(self.app.settings['theme'], 'paper')
        self.app.menu.destroy()
        del self.app.menu

    def test_pause_keeps_sampling_and_resume_uses_current_totals(self):
        self.app.toggle_pause()
        initial = dict(self.app.reading)
        current = dict(initial, received=4096, sent=1024, down=2048, up=512)
        with patch.object(self.app.sampler, 'sample', return_value=current) as sample:
            self.app.update_stats()
            sample.assert_called_once()
            self.assertEqual(self.app.reading, initial)
            self.app.toggle_pause()
            self.app.update_stats()
            self.assertEqual(self.app.reading['received'], 4096)

    def test_csv_is_raw_bytes_and_neutralizes_formula_adapter_names(self):
        self.app.settings['nic'] = '=1+1'
        self.app.reading.update(received=4096, sent=1024, down=125000, up=500)
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / 'session.csv')
            with patch.object(UI['filedialog'], 'asksaveasfilename', return_value=path):
                self.app.export_csv()
            with open(path, newline='', encoding='utf-8') as stream:
                row = next(csv.DictReader(stream))
        self.assertEqual(row['adapter'], "'=1+1")
        self.assertEqual(row['session_received_bytes'], '4096')
        self.assertEqual(float(row['download_bytes_per_second']), 125000)


if __name__ == '__main__':
    unittest.main()
