import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('build_release', Path(__file__).resolve().parents[1] / 'tools' / 'build_release.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class ReleaseTests(unittest.TestCase):
    def test_tag_must_match_application_version(self):
        self.assertEqual(release.checked_version('v' + release.APP_VERSION), release.APP_VERSION)
        with self.assertRaises(ValueError):
            release.checked_version('v0.0.0')

    def test_rejects_non_semantic_version(self):
        with patch.object(release, 'APP_VERSION', '1.1'):
            with self.assertRaises(ValueError):
                release.checked_version()
