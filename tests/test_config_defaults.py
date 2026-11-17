import json
from pathlib import Path
import tempfile
import unittest

from config import ConfigManager, DC_CONFIG_DEFAULTS


class ConfigDefaultsTests(unittest.TestCase):
    def test_missing_config_and_directory_created_with_defaults(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "configs/dc_config.json"
            config = ConfigManager(str(path), defaults=DC_CONFIG_DEFAULTS)
            self.assertEqual(json.loads(path.read_text()), DC_CONFIG_DEFAULTS)
            self.assertEqual(config.get("admin_user_ids"), [])
            self.assertIs(config.get("admin_setup_completed"), False)

    def test_existing_assignments_and_completion_flag_preserved(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "dc_config.json"
            existing = {"channel_ids": [123], "admin_user_ids": [456], "admin_setup_completed": True}
            path.write_text(json.dumps(existing))
            before = path.read_bytes()
            config = ConfigManager(str(path), defaults=DC_CONFIG_DEFAULTS)
            self.assertEqual(config.data, existing)
            self.assertEqual(path.read_bytes(), before)
            config.set("admin_user_ids", [])
            self.assertIs(ConfigManager(str(path), defaults=DC_CONFIG_DEFAULTS).get("admin_setup_completed"), True)

    def test_defaults_are_not_shared_between_managers(self):
        with tempfile.TemporaryDirectory() as root:
            a = ConfigManager(str(Path(root) / "a.json"), defaults=DC_CONFIG_DEFAULTS)
            b = ConfigManager(str(Path(root) / "b.json"), defaults=DC_CONFIG_DEFAULTS)
            a.get("admin_user_ids").append(123)
            self.assertEqual(b.get("admin_user_ids"), [])
            self.assertEqual(DC_CONFIG_DEFAULTS["admin_user_ids"], [])


if __name__ == "__main__":
    unittest.main()
