"""NagaDevice against a fake transport (no device needed)."""

import struct
import unittest

from nagasynapse import layout
from nagasynapse.actions import Action
from nagasynapse.device import NagaDevice, ProfileData
from nagasynapse.transport import HidrawInfo, RazerError, Response

NAGA_PRO_IDS = [b.id for b in layout.MODELS["naga-pro"].buttons]


class FakeTransport:
    """Answers the commands write_profile needs and records what was sent."""

    def __init__(self, button_ids, slots=(1,)):
        self.button_ids = list(button_ids)
        self.slots = list(slots)
        self.lift = {}
        self.sent = []

    def command(self, cls, cid, args=b"", data_size=None, *, timeout=2.0, check=True):
        args = bytes(args)
        self.sent.append((cls, cid, args))
        out, status = bytearray(80), 2
        if (cls, cid) == (0x02, 0x84):
            out[0] = len(self.button_ids)
            out[1:1 + len(self.button_ids)] = bytes(self.button_ids)
        elif (cls, cid) == (0x05, 0x80):
            out[0] = len(self.slots)
        elif (cls, cid) == (0x05, 0x81):
            out[0] = 5
            out[1:1 + len(self.slots)] = bytes(self.slots)
        elif (cls, cid) == (0x0B, 0x0B):
            self.lift[args[0]] = (args[2] << 8) | args[3]
        elif (cls, cid) == (0x0B, 0x8B):
            value = self.lift.get(args[0], 0)
            out[:4] = bytes([args[0], 0x04, value >> 8, value & 0xFF])
        elif (cls, cid) == (0x05, 0x88):
            status = 3  # no profile metadata
        if check and status != 2:
            raise RazerError("fail", status)
        return Response(status, 0x1F, data_size or len(args), cls, cid, bytes(out), b"")

    def close(self):
        pass

    def bindings_sent(self):
        return {(a[1], a[2]) for c, i, a in self.sent if (c, i) == (0x02, 0x0C)}


def naga_pro():
    fake = FakeTransport(NAGA_PRO_IDS)
    return NagaDevice(fake, HidrawInfo("/dev/null", 0x1532, 0x0090, 0, "Naga Pro")), fake


class DeviceModelTest(unittest.TestCase):
    def tearDown(self):
        layout.use_model("naga-v2-pro")

    def test_opening_a_device_does_not_switch_the_shared_tables(self):
        dev, _ = naga_pro()
        self.assertEqual(dev.model.key, "naga-pro")
        self.assertEqual(layout.MODEL.key, "naga-v2-pro")
        self.assertIn(0x6D, layout.BUTTONS_BY_ID)

    def test_default_action_for_a_given_model(self):
        pro = layout.MODELS["naga-pro"]
        self.assertFalse(layout.default_action(0x34).same_as(layout.default_action(0x34, pro)))
        self.assertTrue(layout.default_action(0x0B, pro).same_as(
            Action.decode(bytes.fromhex("06010100000000"))))


class WriteProfileTest(unittest.TestCase):
    def test_skips_buttons_the_mouse_does_not_have(self):
        dev, fake = naga_pro()
        data = ProfileData(slot=1, bindings={
            (0x6D, 0): Action.scroll_mode(),     # V2 Pro only
            (0x60, 1): Action.disabled(),        # V2 Pro only
            (0x50, 0): Action.keyboard(0x04),
        })
        skipped = dev.write_profile(1, data)
        self.assertEqual(sorted(skipped), [(0x60, 1), (0x6D, 0)])
        self.assertEqual(fake.bindings_sent(), {(0x50, 0)})

    def test_dpi_stages_are_clamped_to_the_model(self):
        dev, fake = naga_pro()
        dev.write_profile(1, ProfileData(slot=1, dpi_stages=[(400, 400), (26000, 30000)],
                                         dpi_active=1))
        args = next(a for c, i, a in fake.sent if (c, i) == (0x04, 0x06))
        self.assertEqual(struct.unpack(">BHH", args[3 + 7:3 + 7 + 5])[1:], (20000, 20000))

    def test_lift_off_outside_the_known_values_is_restored(self):
        dev, fake = naga_pro()
        dev.write_profile(1, ProfileData(slot=1, lift_off=0x0300))  # pad calibration
        self.assertEqual(fake.lift[1], 0x0300)


if __name__ == "__main__":
    unittest.main()
