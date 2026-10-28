# LiteNetMonitor

[![CI](https://github.com/yananai-chiwuta/Quality-of-Life/actions/workflows/ci.yml/badge.svg)](https://github.com/yananai-chiwuta/Quality-of-Life/actions/workflows/ci.yml) [![Latest release](https://img.shields.io/github/v/release/yananai-chiwuta/Quality-of-Life)](https://github.com/yananai-chiwuta/Quality-of-Life/releases/latest) [![MIT license](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

A quiet, compact desktop view of your network traffic. LiteNetMonitor shows live download and upload rates, a one-minute graph, and session totals in a small Tkinter window. **Current release: v1.1.0.**

## Download v1.1.0

Choose the archive for your system, extract it, and launch the app inside. No Python installation is needed for these builds.

| Platform | Download |
| --- | --- |
| Windows 10/11, x64 | [LiteNetMonitor-1.1.0-windows-x64.zip](https://github.com/yananai-chiwuta/Quality-of-Life/releases/download/v1.1.0/LiteNetMonitor-1.1.0-windows-x64.zip) |
| Linux, x64 (glibc 2.35+) | [LiteNetMonitor-1.1.0-linux-x64.tar.gz](https://github.com/yananai-chiwuta/Quality-of-Life/releases/download/v1.1.0/LiteNetMonitor-1.1.0-linux-x64.tar.gz) |
| macOS 14+, Apple silicon (arm64) | [LiteNetMonitor-1.1.0-macos-arm64.zip](https://github.com/yananai-chiwuta/Quality-of-Life/releases/download/v1.1.0/LiteNetMonitor-1.1.0-macos-arm64.zip) |
| macOS 15+, Intel (x64) | [LiteNetMonitor-1.1.0-macos-x64.zip](https://github.com/yananai-chiwuta/Quality-of-Life/releases/download/v1.1.0/LiteNetMonitor-1.1.0-macos-x64.zip) |

[See the release and notes](https://github.com/yananai-chiwuta/Quality-of-Life/releases/tag/v1.1.0). Linux desktop libraries such as Tk and X11 may need to be installed on your system. CI downloads are unsigned and the macOS apps are not notarized.

## Features

- Midnight and paper themes; refresh every 1, 2, or 5 seconds.
- Download and upload rates in KiB/s or decimal bits/s, plus a scrolling graph covering the last 60 seconds.
- Session received/sent totals, with reset and CSV snapshot export.
- Select a network adapter or view all adapters. Missing adapters are shown as unavailable.
- Pause the display while counting continues; keep the widget on top; save preferences and window position.
- Copy current speeds, view local interface addresses, and explicitly ping `1.1.1.1`.
- Native decorated window on macOS and Linux; compact borderless window on Windows. Optional source-run tray support on Windows and Linux; startup toggle on Windows.

**Shortcuts:** `Space` pauses/resumes the display · `Ctrl+C` / `Cmd+C` copies speeds · `T` switches theme · `Escape` minimizes · drag the header to move the window · right-click or **•••** opens settings.

Session totals start when the app opens and reset when you quit, reset the session, or change adapters. They are not a monthly usage meter. Viewing all adapters can count VPN or virtual interface traffic more than once, so select a physical adapter for a clearer total.

## Run from source

Python 3.11 or newer is required. Tkinter is included with most Python installers; Linux users may need their distribution's Tk package, often `python3-tk`.

```sh
git clone https://github.com/yananai-chiwuta/Quality-of-Life.git
cd Quality-of-Life/projects/LiteNetMonitor
```

Install and launch with the environment's Python:

```powershell
# Windows PowerShell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe LiteNetMonitor.pyw
```

```sh
# macOS / Linux
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python LiteNetMonitor.pyw
```

For optional tray support when running from source on Windows or Linux, install `requirements-tray.txt` using your environment's Python. Packaged builds use regular minimize.

## Privacy and preferences

Monitoring reads local interface counters. There is no account, analytics, telemetry, or background network request. Only the explicit latency check sends a ping to `1.1.1.1`. CSV files are saved only where you choose, and local IP information stays in the app.

Preferences are saved as `settings.json` in:

| System | Folder |
| --- | --- |
| Windows | `%LOCALAPPDATA%\LiteNetMonitor` |
| macOS | `~/Library/Application Support/LiteNetMonitor` |
| Linux | `$XDG_CONFIG_HOME/litenetmonitor`, or `~/.config/litenetmonitor` |

## Troubleshooting

- **No Tkinter module:** install the Tk package for your Python version (`python3-tk` on Ubuntu/Debian), then restart.
- **Adapter unavailable:** select another adapter from **••• → Network adapter**. Adapter selection starts a fresh session.
- **Tray icon missing:** desktop support varies; regular minimize works without tray libraries.
- **Ping gets no reply:** ICMP may be blocked even when your connection works.

## Development and license

Run checks with `python -m unittest discover -s tests -v`. Source and desktop integration checks run on Windows, macOS, and Linux with Python 3.11 and 3.13. Each release build also starts the packaged app before publishing.

Versions follow `major.minor.patch`. `APP_VERSION` in [netmonitor_core.py](netmonitor_core.py) drives the app title, About dialog, executable metadata, archive names, and `VERSION.txt`. Release tags must match it, for example `v1.1.0`. Downloads include [SHA-256 checksums](https://github.com/yananai-chiwuta/Quality-of-Life/releases/download/v1.1.0/SHA256SUMS.txt).

See [contributing notes](CONTRIBUTING.md), the [changelog](CHANGELOG.md), and the [release build workflow](../../.github/workflows/build.yml). LiteNetMonitor is licensed under [MIT](LICENSE); dependencies retain their own licenses.
