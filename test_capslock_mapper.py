import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import caps_lock_blocker as app


@unittest.skipUnless(sys.platform == "win32", "Windows only")
class VKHelperTests(unittest.TestCase):
    def test_letter_and_digit_names(self):
        self.assertEqual(app.vk_display_name(0x41), "A")
        self.assertEqual(app.vk_display_name(0x5A), "Z")
        self.assertEqual(app.vk_display_name(0x30), "0")
        self.assertEqual(app.vk_display_name(0x39), "9")

    def test_common_key_names(self):
        self.assertEqual(app.vk_display_name(0x1B), "Esc")
        self.assertEqual(app.vk_display_name(0x70), "F1")
        self.assertEqual(app.vk_display_name(0x87), "F24")
        self.assertEqual(app.vk_display_name(0x25), "Left")

    def test_extended_flag(self):
        self.assertTrue(app.is_extended_vk(0x25))
        self.assertTrue(app.is_extended_vk(0x2D))
        self.assertTrue(app.is_extended_vk(0xA3))
        self.assertFalse(app.is_extended_vk(0x41))
        self.assertFalse(app.is_extended_vk(0x60))

    def test_mappable_vk(self):
        self.assertTrue(app.is_mappable_vk(0x41))
        self.assertTrue(app.is_mappable_vk(0x70))
        self.assertTrue(app.is_mappable_vk(0xA2))
        self.assertFalse(app.is_mappable_vk(app.VK_CAPITAL))
        self.assertFalse(app.is_mappable_vk(app.VK_LWIN))
        self.assertFalse(app.is_mappable_vk(0x01))
        self.assertFalse(app.is_mappable_vk(-1))
        self.assertFalse(app.is_mappable_vk(999))

    def test_normalize_config(self):
        cfg = app._normalize_cfg(None)
        self.assertEqual(cfg["target_vk"], 0x1B)
        self.assertEqual(cfg["target_name"], "Esc")

        cfg = app._normalize_cfg({"target_vk": 0x14})
        self.assertEqual(cfg["target_vk"], 0x1B)

        cfg = app._normalize_cfg({"target_vk": 0x70})
        self.assertEqual(cfg["target_vk"], 0x70)
        self.assertEqual(cfg["target_name"], "F1")

        cfg = app._normalize_cfg({"target_vk": "bad"})
        self.assertEqual(cfg["target_vk"], 0x1B)

        cfg = app._normalize_cfg({"target_vk": 0xA3})
        self.assertTrue(cfg["target_extended"])

    def test_mapping_mode_config(self):
        cfg = app._normalize_cfg(None)
        self.assertEqual(cfg["mapping_mode"], app.MAPPING_MODE_TOGGLE)

        cfg = app._normalize_cfg({"mapping_mode": app.MAPPING_MODE_HOLD})
        self.assertEqual(cfg["mapping_mode"], app.MAPPING_MODE_HOLD)

        cfg = app._normalize_cfg({"mapping_mode": "bad"})
        self.assertEqual(cfg["mapping_mode"], app.MAPPING_MODE_TOGGLE)


if __name__ == "__main__":
    unittest.main()
