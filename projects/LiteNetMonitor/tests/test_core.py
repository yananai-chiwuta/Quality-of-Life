import json
import os
import tempfile
import unittest
from collections import namedtuple
from unittest.mock import patch

import netmonitor_core as core


Counter = namedtuple("Counter", "bytes_recv bytes_sent")


class FormattingTests(unittest.TestCase):
    def test_byte_and_bit_rates_use_their_defined_bases(self):
        self.assertEqual(core.format_rate(1024), "1.0 KiB/s")
        self.assertEqual(core.format_rate(125), "125.0 B/s")
        self.assertEqual(core.format_rate(125, use_bits=True), "1.0 kb/s")
        self.assertEqual(core.format_rate(125000, use_bits=True), "1.0 Mb/s")

    def test_format_bytes(self):
        self.assertEqual(core.format_bytes(512), "512 B")
        self.assertEqual(core.format_bytes(1024), "1.0 KiB")


class SamplerTests(unittest.TestCase):
    def test_rates_session_and_all_aggregation(self):
        samples = [
            {"eth0": Counter(100, 200), "eth1": Counter(50, 70)},
            {"eth0": Counter(160, 240), "eth1": Counter(70, 90)},
        ]
        with patch.object(core.psutil, "net_io_counters", side_effect=samples):
            sampler = core.TrafficSampler()
            first = sampler.sample(10)
            second = sampler.sample(12)
        self.assertEqual((first["down"], first["up"], first["total"]), (0, 0, 420))
        self.assertEqual((second["down"], second["up"]), (40, 30))
        self.assertEqual((second["received"], second["sent"], second["total"]), (80, 60, 560))

    def test_all_adapter_changes_do_not_create_rate_or_session_spikes(self):
        samples = [
            {"eth0": Counter(100, 100)},
            {"eth0": Counter(110, 115), "new-vpn": Counter(9_000_000, 8_000_000)},
            {"eth0": Counter(120, 130)},
        ]
        with patch.object(core.psutil, "net_io_counters", side_effect=samples):
            sampler = core.TrafficSampler()
            sampler.sample(1)
            added = sampler.sample(2)
            removed = sampler.sample(3)
        self.assertEqual((added["down"], added["up"], added["received"], added["sent"]),
                         (10, 15, 10, 15))
        self.assertEqual((removed["down"], removed["up"], removed["received"], removed["sent"]),
                         (10, 15, 20, 30))
        self.assertGreater(added["total"], removed["total"])

    def test_missing_adapter_does_not_fall_back_and_reconnect_has_no_spike(self):
        samples = [{"other": Counter(90, 90)}, {"wifi": Counter(1000, 1200)},
                   {"wifi": Counter(1010, 1220)}]
        with patch.object(core.psutil, "net_io_counters", side_effect=samples):
            sampler = core.TrafficSampler("wifi")
            missing = sampler.sample(1)
            reconnected = sampler.sample(2)
            later = sampler.sample(3)
        self.assertFalse(missing["available"])
        self.assertTrue(reconnected["available"])
        self.assertEqual((reconnected["down"], reconnected["up"]), (0, 0))
        self.assertEqual((later["down"], later["up"], later["received"], later["sent"]),
                         (10, 20, 10, 20))

    def test_counter_rollback_and_reset(self):
        samples = [{"eth0": Counter(100, 100)}, {"eth0": Counter(5, 6)},
                   {"eth0": Counter(15, 16)}, {"eth0": Counter(50, 50)}]
        with patch.object(core.psutil, "net_io_counters", side_effect=samples):
            sampler = core.TrafficSampler("eth0")
            sampler.sample(1)
            rolled_back = sampler.sample(2)
            self.assertEqual((rolled_back["down"], rolled_back["received"]), (0, 0))
            later = sampler.sample(3)
            self.assertEqual((later["down"], later["received"]), (10, 10))
            sampler.reset()
            after_reset = sampler.sample(4)
        self.assertEqual((after_reset["down"], after_reset["received"]), (0, 0))


class SettingsTests(unittest.TestCase):
    def test_defaults_validation_and_atomic_roundtrip(self):
        self.assertEqual(core.default_settings(), {
            "theme": "midnight", "use_bits": False, "nic": "All",
            "always_on_top": True, "interval": 1, "position": None,
        })
        bad = {"theme": 4, "use_bits": "yes", "nic": None, "interval": 1000,
               "always_on_top": False, "position": [1, "bad"]}
        validated = core._validated_settings(bad)
        self.assertEqual(validated["theme"], "midnight")
        self.assertFalse(validated["use_bits"])
        self.assertEqual(validated["interval"], 60)
        self.assertIsNone(validated["position"])
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "nested", "settings.json")
            core.save_settings({"nic": "wifi", "position": [20, -3]}, path)
            loaded = core.load_settings(path)
            self.assertEqual(loaded["nic"], "wifi")
            self.assertEqual(loaded["position"], [20, -3])
            with open(path, encoding="utf-8") as stream:
                self.assertEqual(json.load(stream)["nic"], "wifi")

    def test_bad_json_returns_defaults(self):
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as stream:
            stream.write("{")
            path = stream.name
        try:
            self.assertEqual(core.load_settings(path), core.default_settings())
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
