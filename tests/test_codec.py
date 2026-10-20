"""Tests for the byte-level encodings (no device needed)."""

import unittest

from nagasynapse.actions import Action, DpiOp, Kind, MouseFn, ProfileOp, parse_action
from nagasynapse.hid_usage import parse_combo, text_to_keys
from nagasynapse.layout import BUTTONS, default_action, find_button
from nagasynapse.macros import Macro, MacroEvent, delay, key, parse_steps
from nagasynapse.transport import build_report, crc


class TransportTest(unittest.TestCase):
    def test_report_layout_and_crc(self):
        r = build_report(0x1F, 0x02, 0x8C, bytes([1, 0x40, 0]), 10)
        self.assertEqual(len(r), 90)
        self.assertEqual(r[1], 0x1F)
        self.assertEqual(r[5], 10)
        self.assertEqual((r[6], r[7]), (0x02, 0x8C))
        self.assertEqual(bytes(r[8:11]), bytes([1, 0x40, 0]))
        self.assertEqual(r[88], crc(r))
        expected = 0
        for b in r[2:88]:
            expected ^= b
        self.assertEqual(r[88], expected)


class ActionTest(unittest.TestCase):
    def test_factory_defaults_decode(self):
        # Factory bindings have length byte 1 even with longer payloads.
        a = Action.decode(bytes.fromhex("0e016800140000"))
        self.assertEqual(a.kind, Kind.MOUSE_TURBO)
        self.assertEqual(a.data, bytes([0x68, 0x00, 0x14]))
        self.assertEqual(a.turbo_ms, 20)
        k = Action.decode(bytes.fromhex("0201001e000000"))
        self.assertEqual(k, Action.keyboard(0x1E))
        self.assertEqual(k.describe(), "1")

    def test_encode_uses_real_length(self):
        self.assertEqual(Action.keyboard(0x06, 0x01).encode(),
                         bytes.fromhex("02020106000000"))
        self.assertEqual(Action.macro(0x1234, Kind.MACRO_TIMES, 3).encode(),
                         bytes.fromhex("03031234030000"))
        self.assertEqual(Action.dpi(DpiOp.CLUTCH, dpi_x=400).encode(),
                         bytes.fromhex("06050501900190"))

    def test_roundtrip_all_constructors(self):
        actions = [
            Action.disabled(), Action.mouse(MouseFn.LEFT),
            Action.mouse(MouseFn.RIGHT, double_click=True),
            Action.mouse(MouseFn.WHEEL_UP, turbo_ms=50),
            Action.keyboard(0x04, 0x03), Action.keyboard(0x2C, turbo_ms=100),
            Action.macro(7), Action.macro(7, Kind.MACRO_HOLD),
            Action.macro(7, Kind.MACRO_TOGGLE), Action.macro(7, Kind.MACRO_SEQUENCE),
            Action.dpi(DpiOp.CYCLE_UP), Action.dpi(DpiOp.STAGE, stage=3),
            Action.dpi(DpiOp.CLUTCH, dpi_x=800, dpi_y=600),
            Action.profile(ProfileOp.CYCLE_UP), Action.profile(ProfileOp.SET, 4),
            Action.consumer(0xE9), Action.system(2), Action.hypershift(),
            Action.scroll_mode(),
        ]
        for a in actions:
            b = Action.decode(a.encode())
            self.assertTrue(a.same_as(b), (a, b))
            self.assertFalse(a.describe().startswith("Unknown"), a)

    def test_parse_action(self):
        self.assertEqual(parse_action("key:ctrl+c"), Action.keyboard(0x06, 0x01))
        self.assertEqual(parse_action("mouse:left:double"),
                         Action.mouse(MouseFn.LEFT, double_click=True))
        self.assertEqual(parse_action("macro:5:hold"), Action.macro(5, Kind.MACRO_HOLD))
        self.assertEqual(parse_action("macro:5:times=4"), Action.macro(5, Kind.MACRO_TIMES, 4))
        self.assertEqual(parse_action("dpi:stage=2"), Action.dpi(DpiOp.STAGE, stage=2))
        self.assertEqual(parse_action("profile:3"), Action.profile(ProfileOp.SET, 3))
        self.assertEqual(parse_action("media:volup"), Action.consumer(0xE9))
        self.assertEqual(parse_action("hypershift"), Action.hypershift())

    def test_defaults_cover_every_button(self):
        self.assertEqual(len(BUTTONS), 30)
        for b in BUTTONS:
            self.assertFalse(default_action(b.id).describe().startswith("Unknown"))

    def test_find_button(self):
        self.assertEqual(find_button("12:1"), 0x40)
        self.assertEqual(find_button("12:12"), 0x4B)
        self.assertEqual(find_button("6:6"), 0x55)
        self.assertEqual(find_button("dpi"), 0x60)


class KeyTest(unittest.TestCase):
    def test_combo(self):
        self.assertEqual(parse_combo("ctrl+shift+a"), (0x03, 0x04))
        self.assertEqual(parse_combo("f5"), (0, 0x3E))
        self.assertEqual(parse_combo("shift"), (0, 0xE1))

    def test_text(self):
        self.assertEqual(text_to_keys("aB!"), [(0x04, False), (0x05, True), (0x1E, True)])


class MacroTest(unittest.TestCase):
    def test_encoding_matches_device_format(self):
        m = Macro(events=[key(0x04, True), delay(10), key(0x04, False)])
        self.assertEqual(m.encode(), bytes.fromhex("0104110a0204"))
        m = Macro(events=[delay(1000)])
        self.assertEqual(m.encode(), bytes.fromhex("1203e8"))

    def test_mouse_buttons_are_state_bitmasks(self):
        m = Macro(events=[MacroEvent("mouse", "left", True), MacroEvent("mouse", "right", True),
                          MacroEvent("mouse", "left", False), MacroEvent("mouse", "right", False)])
        self.assertEqual(m.encode(), bytes.fromhex("0801080308020800"))
        back = Macro.decode(m.encode())
        self.assertEqual([e.to_json() for e in back.events], [e.to_json() for e in m.events])

    def test_stuck_mouse_button_released(self):
        m = Macro(events=[MacroEvent("mouse", "left", True)])
        self.assertEqual(m.encode(), bytes.fromhex("08010800"))

    def test_roundtrip(self):
        events = parse_steps("ctrl+c, 50ms, text:Hi!, click:right, wheel:-2, media:mute, "
                             "delay:70000, +shift, a, -shift")
        m = Macro(name="x", events=events)
        back = Macro.decode(m.encode())
        # the 70 s delay is split into 65535 + 4465
        self.assertEqual(back.duration_ms(), m.duration_ms())
        self.assertEqual(Macro.decode(back.encode()).encode(), m.encode())
        self.assertEqual(m.stuck_keys(), [])

    def test_stuck_keys(self):
        m = Macro(events=parse_steps("+shift, a"))
        self.assertEqual(m.stuck_keys(), ["Left Shift"])


if __name__ == "__main__":
    unittest.main()
