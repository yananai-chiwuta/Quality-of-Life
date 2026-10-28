"""Platform-independent sampling and settings for LiteNetMonitor."""

import json
import math
import os
import sys
import tempfile
import time

import psutil


APP_VERSION = "1.1.0"


def format_rate(value, use_bits=False):
    """Format bytes per second using IEC byte or SI bit units."""
    value = max(0.0, float(value))
    if use_bits:
        value *= 8
        units, base = ("b/s", "kb/s", "Mb/s", "Gb/s", "Tb/s"), 1000.0
    else:
        units, base = ("B/s", "KiB/s", "MiB/s", "GiB/s", "TiB/s"), 1024.0
    idx = 0
    while value >= base and idx < len(units) - 1:
        value /= base
        idx += 1
    return f"{value:.1f} {units[idx]}"


def format_bytes(value):
    value = max(0.0, float(value))
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    idx = 0
    while value >= 1024 and idx < len(units) - 1:
        value /= 1024.0
        idx += 1
    return f"{value:.1f} {units[idx]}" if idx else f"{int(value)} B"


class TrafficSampler:
    """Sample interface counters and maintain rates plus session totals."""

    def __init__(self, nic="All"):
        self.nic = nic
        self._previous = None
        self._previous_time = None
        self._session_recv = 0
        self._session_sent = 0
        self._down = 0.0
        self._up = 0.0

    @staticmethod
    def _read(nic):
        counters = psutil.net_io_counters(pernic=True)
        if nic == "All":
            if not counters:
                return None
            return {name: (max(0, c.bytes_recv), max(0, c.bytes_sent))
                    for name, c in counters.items()}
        counter = counters.get(nic)
        return {nic: (max(0, counter.bytes_recv), max(0, counter.bytes_sent))} if counter is not None else None

    def sample(self, now=None):
        now = time.monotonic() if now is None else float(now)
        current = self._read(self.nic)
        available = current is not None
        total = sum(recv + sent for recv, sent in current.values()) if available else 0
        if available:
            if self._previous is None:
                # First sample and reconnect establish a baseline without spikes.
                self._previous, self._previous_time = current, now
                self._down = self._up = 0.0
            else:
                elapsed = now - self._previous_time
                recv_delta = sent_delta = 0
                if elapsed > 0:
                    # Match counters by interface. New interfaces establish a baseline
                    # here, avoiding a spike when All gains an adapter.
                    for name in current.keys() & self._previous.keys():
                        old_recv, old_sent = self._previous[name]
                        new_recv, new_sent = current[name]
                        if new_recv >= old_recv and new_sent >= old_sent:
                            recv_delta += new_recv - old_recv
                            sent_delta += new_sent - old_sent
                if elapsed <= 0:
                    self._down = self._up = 0.0
                else:
                    self._session_recv += recv_delta
                    self._session_sent += sent_delta
                    self._down = recv_delta / elapsed
                    self._up = sent_delta / elapsed
                self._previous, self._previous_time = current, now
        else:
            # Keep visible readings and session totals during a disconnect.
            self._previous = self._previous_time = None
        return {
            "down": self._down, "up": self._up,
            "received": self._session_recv, "sent": self._session_sent,
            "total": total, "available": available,
        }

    def reset(self):
        self._previous = self._previous_time = None
        self._session_recv = self._session_sent = 0
        self._down = self._up = 0.0


def default_settings():
    return {"theme": "midnight", "use_bits": False, "nic": "All",
            "always_on_top": True, "interval": 1, "position": None}


def settings_path():
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base, "LiteNetMonitor", "settings.json")
    if sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~"), "Library", "Application Support",
                            "LiteNetMonitor", "settings.json")
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "litenetmonitor", "settings.json")


def _validated_settings(data):
    result = default_settings()
    if not isinstance(data, dict):
        return result
    theme = data.get("theme")
    if isinstance(theme, str) and 0 < len(theme) <= 40:
        result["theme"] = theme
    for key in ("use_bits", "always_on_top"):
        if isinstance(data.get(key), bool):
            result[key] = data[key]
    nic = data.get("nic")
    if isinstance(nic, str) and 0 < len(nic) <= 256:
        result["nic"] = nic
    interval = data.get("interval")
    if isinstance(interval, (int, float)) and not isinstance(interval, bool) and math.isfinite(interval):
        result["interval"] = min(60, max(0.2, interval))
    pos = data.get("position")
    if (isinstance(pos, (list, tuple)) and len(pos) == 2 and
            all(isinstance(v, int) and not isinstance(v, bool) and -100000 <= v <= 100000 for v in pos)):
        result["position"] = list(pos)
    return result


def load_settings(path=None):
    try:
        with open(path or settings_path(), "r", encoding="utf-8") as stream:
            return _validated_settings(json.load(stream))
    except (OSError, ValueError, TypeError):
        return default_settings()


def save_settings(settings, path=None):
    target = path or settings_path()
    directory = os.path.dirname(os.path.abspath(target))
    os.makedirs(directory, exist_ok=True)
    normalized = _validated_settings(settings)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=directory,
                                         prefix=".settings-", suffix=".tmp", delete=False) as stream:
            temp_path = stream.name
            json.dump(normalized, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, target)
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)
