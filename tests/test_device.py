"""Hardware test. Runs only with NAGA_DEVICE_TESTS=1 and a connected mouse.

Uses profile slot 5 as a scratch area (it must be empty) and removes
everything it creates. The active profile is never modified.
"""

import os
import unittest

from nagasynapse.actions import Action, DpiOp, Kind, MouseFn, ProfileOp
from nagasynapse.device import NagaDevice
from nagasynapse.macros import Macro, parse_steps

SLOT = 5


@unittest.skipUnless(os.environ.get("NAGA_DEVICE_TESTS") == "1", "needs the mouse")
class DeviceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dev = NagaDevice.open()
        if SLOT in cls.dev.profiles():
            raise unittest.SkipTest(f"profile slot {SLOT} is in use")
        cls.active = cls.dev.active_profile()
        cls.snapshot = cls.dev.read_profile(cls.active)
        cls.macros_before = cls.dev.macro_ids()
        cls.dev.create_profile(SLOT)
        cls.dev.init_profile(SLOT)

    @classmethod
    def tearDownClass(cls):
        dev = cls.dev
        for mid in dev.macro_ids():
            if mid not in cls.macros_before:
                dev.delete_macro(mid)
        if SLOT in dev.profiles():
            dev.delete_profile(SLOT)
        dev.compact_flash()
        after = dev.read_profile(cls.active)
        assert dev.active_profile() == cls.active
        for key, action in cls.snapshot.bindings.items():
            assert after.bindings[key].same_as(action), key
        assert after.dpi_stages == cls.snapshot.dpi_stages
        dev.close()

    def test_bindings_roundtrip(self):
        actions = [
            Action.keyboard(0x06, 0x01), Action.keyboard(0x2C, turbo_ms=50),
            Action.mouse(MouseFn.MIDDLE), Action.mouse(MouseFn.LEFT, double_click=True),
            Action.mouse(MouseFn.WHEEL_DOWN, turbo_ms=40), Action.consumer(0xE9),
            Action.dpi(DpiOp.STAGE, stage=2), Action.dpi(DpiOp.CLUTCH, dpi_x=400),
            Action.profile(ProfileOp.SET, 1), Action.profile(ProfileOp.CYCLE_DOWN),
            Action.system(2), Action.hypershift(), Action.scroll_mode(), Action.disabled(),
        ]
        for layer in (0, 1):
            for i, action in enumerate(actions):
                button = [0x40, 0x41, 0x42, 0x43, 0x44, 0x45, 0x46, 0x47, 0x48, 0x49,
                          0x4A, 0x4B, 0x50, 0x51][i]
                self.dev.set_binding(SLOT, button, layer, action)
                back = self.dev.get_binding(SLOT, button, layer)
                self.assertTrue(back.same_as(action), (layer, hex(button), action, back))

    def test_macro_lifecycle(self):
        macro = Macro(name="Integration ✓", events=parse_steps(
            "ctrl+a, 30ms, text:Hello\\, world, click:left, wheel:2, delay:300"))
        mid = self.dev.write_macro(macro)
        self.assertIn(mid, self.dev.macro_ids())
        stored = self.dev.read_macro(mid)
        self.assertEqual(stored.name, "Integration ✓")
        self.assertEqual(stored.encode(), macro.encode())
        for mode in (Kind.MACRO_TIMES, Kind.MACRO_HOLD, Kind.MACRO_TOGGLE, Kind.MACRO_SEQUENCE):
            action = Action.macro(mid, mode, 3)
            self.dev.set_binding(SLOT, 0x52, 0, action)
            self.assertTrue(self.dev.get_binding(SLOT, 0x52, 0).same_as(action))
        # edit in place keeps the id
        macro.events = parse_steps("b")
        macro.name = "Edited"
        self.assertEqual(self.dev.write_macro(macro), mid)
        self.assertEqual(self.dev.read_macro(mid).encode(), macro.encode())
        self.assertEqual(self.dev.read_macro(mid).name, "Edited")
        # compaction keeps macros and profile names
        self.dev.set_profile_name(SLOT, "Scratch")
        self.dev.compact_flash()
        # at most the stale page of each rewritten profile name is recycled
        self.assertLessEqual(self.dev.flash_usage().recycled, 256 * len(self.dev.profiles()))
        self.assertEqual(self.dev.read_macro(mid).encode(), macro.encode())
        self.assertEqual(self.dev.profile_name(SLOT), "Scratch")
        self.dev.delete_macro(mid)
        self.assertNotIn(mid, self.dev.macro_ids())

    def test_performance(self):
        self.dev.set_dpi_stages(SLOT, [(400, 400), (800, 600), (1600, 1600)], 2)
        stages, active = self.dev.get_dpi_stages(SLOT)
        self.assertEqual(stages, [(400, 400), (800, 600), (1600, 1600)])
        self.assertEqual(active, 2)
        self.dev.set_polling_interval(SLOT, 2)
        self.assertEqual(self.dev.get_polling_interval(SLOT), 2)
        self.dev.set_polling_interval(SLOT, 1)

    def test_profile_export_import_shape(self):
        data = self.dev.read_profile(SLOT)
        self.assertEqual(len(data.bindings), 60)
        from nagasynapse.device import ProfileData
        clone = ProfileData.from_json(data.to_json(), SLOT)
        for key, action in data.bindings.items():
            self.assertTrue(clone.bindings[key].same_as(action))


if __name__ == "__main__":
    unittest.main()
