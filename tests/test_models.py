"""Tests for per-model button tables (no device needed)."""

import unittest

from nagasynapse import layout
from nagasynapse.actions import Action
from nagasynapse.layout import (BUTTON_IDS, BUTTONS, BUTTONS_BY_ID, default_action,
                                find_button)
from nagasynapse.transport import SUPPORTED_DEVICES


class ModelTest(unittest.TestCase):
    def tearDown(self):
        layout.use_model("naga-v2-pro")

    def test_every_supported_pid_has_a_model(self):
        for pid in SUPPORTED_DEVICES:
            self.assertIn(layout.MODEL_BY_PID[pid], layout.MODELS)
        self.assertEqual(layout.model_for_pid(0x00A8).key, "naga-v2-pro")
        self.assertEqual(layout.model_for_pid(0x0090).key, "naga-pro")

    def test_v2_pro_is_the_default(self):
        self.assertEqual(layout.MODEL.key, "naga-v2-pro")
        self.assertIn(0x6D, BUTTONS_BY_ID)
        self.assertEqual(find_button("dpi"), 0x60)
        self.assertEqual(layout.dpi_max(), 30000)

    def test_naga_pro_buttons(self):
        layout.use_model("naga-pro")
        ids = set(BUTTON_IDS)
        self.assertEqual(len(ids), 30)
        self.assertNotIn(0x6D, ids)  # no scroll-mode button
        self.assertNotIn(0x60, ids)
        self.assertTrue({0x0B, 0x0C} <= ids)  # DPI up / down
        self.assertEqual(find_button("dpi"), 0x0B)
        self.assertEqual(find_button("dpi-"), 0x0C)
        self.assertEqual(layout.dpi_max(), 20000)
        # factory tilt repeats wheel up / down on this model
        self.assertTrue(default_action(0x34).same_as(
            Action.decode(bytes.fromhex("0e010900140000"))))

    def test_side_plates_are_shared(self):
        v2 = {b.id: b.default for b in layout.MODELS["naga-v2-pro"].buttons
              if b.group.startswith("side")}
        pro = {b.id: b.default for b in layout.MODELS["naga-pro"].buttons
               if b.group.startswith("side")}
        self.assertEqual(v2, pro)

    def test_use_model_updates_imported_tables_in_place(self):
        before = (id(BUTTONS), id(BUTTONS_BY_ID), id(BUTTON_IDS))
        layout.use_model("naga-pro")
        self.assertEqual(before, (id(BUTTONS), id(BUTTONS_BY_ID), id(BUTTON_IDS)))
        self.assertIn(0x0B, BUTTONS_BY_ID)
        layout.use_model("naga-v2-pro")
        self.assertNotIn(0x0B, BUTTONS_BY_ID)


if __name__ == "__main__":
    unittest.main()
