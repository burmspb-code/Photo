"""Единые настройки вырезки: ядро, CLI и предустановки."""
from __future__ import annotations

import unittest
from unittest.mock import patch

import numpy as np

from src.core.cut_params import CUT_DEFAULTS
from src.core.cutout import make_cutout
from src.photo_pipeline import cut_params
from src.ui.defaults import APP_DEFAULTS


class TestCutParams(unittest.TestCase):
    @staticmethod
    def _patches():
        orig = np.zeros((60, 60, 3), np.uint8)
        alpha = np.zeros((60, 60), np.float32)
        alpha[10:50, 10:50] = 1.0
        return (
            patch("src.core.cutout._read", return_value=orig),
            patch("src.core.cutout.tiled_alpha", return_value=alpha),
            patch("src.core.cutout.global_shape_alpha", return_value=alpha),
            patch("src.core.cutout.refine_alpha", return_value=alpha),
            patch("src.core.cutout.merge_global_shape", return_value=alpha),
            patch("src.core.cutout.stabilize_alpha", return_value=alpha),
            patch("src.core.cutout.remove_isolated", return_value=alpha),
            patch("src.core.cutout.fill_holes", return_value=alpha),
            patch("src.core.cutout.refine_hair", return_value=alpha),
            patch("src.core.cutout.estimate_foreground_ml",
                  return_value=np.zeros((60, 60, 3), np.float64)),
            patch("src.core.cutout.clean_color_gaps",
                  side_effect=lambda _orig, cut, **_kw: cut),
        )

    def test_all_defaults_have_preset_keys(self) -> None:
        for key in CUT_DEFAULTS:
            self.assertIn(f"cut/{key}", APP_DEFAULTS)
            self.assertEqual(APP_DEFAULTS[f"cut/{key}"], CUT_DEFAULTS[key])

    def test_disabled_stages_are_skipped_and_tunables_reach_core(self) -> None:
        patches = self._patches()
        with patches[0], patches[1] as tiled, patches[2] as whole, patches[3] as refine, \
             patches[4] as merge, patches[5] as stab, patches[6] as isolated, patches[7] as holes, \
             patches[8] as hair, patches[9], patches[10] as gaps:
            out = make_cutout(
                "in.jpg",
                params={"tile": 512, "overlap": 0.7, "sigma": 2.2,
                        "global_shape": False, "stabilize": False, "isolated": False,
                        "fill_holes": False, "hair_refine": False, "color_gaps": False},
            )

        self.assertEqual(out.shape, (60, 60, 4))
        self.assertEqual(tiled.call_args.kwargs["tile"], 512)
        self.assertEqual(tiled.call_args.kwargs["overlap"], 0.7)
        self.assertEqual(refine.call_args.kwargs["sigma"], 2.2)
        whole.assert_not_called()
        merge.assert_not_called()
        stab.assert_not_called()
        isolated.assert_not_called()
        holes.assert_not_called()
        hair.assert_not_called()
        gaps.assert_not_called()

    def test_cleanup_stages_are_enabled_by_default(self) -> None:
        patches = self._patches()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], \
             patches[6] as isolated, patches[7] as holes, patches[8] as hair, patches[9], \
             patches[10] as gaps:
            make_cutout("in.jpg")

        self.assertTrue(isolated.called)
        self.assertEqual(isolated.call_args.kwargs,
                         {"min_ratio": 0.15, "min_gap": 24, "halo": 32})
        self.assertTrue(holes.called)
        self.assertEqual(holes.call_args.kwargs,
                         {"max_area": 60000, "top_fraction": 0.5, "min_area": 250})
        self.assertTrue(hair.called)
        self.assertEqual(hair.call_args.kwargs,
                         {"top_fraction": 0.3, "min_mid": 25000, "gain": 3.0})
        self.assertTrue(gaps.called)
        self.assertEqual(gaps.call_args.kwargs,
                         {"lo": 45.0, "hi": 100.0, "top_fraction": 0.35, "min_blue": 25.0})

    def test_cli_flags_override_defaults(self) -> None:
        params = cut_params({
            "no-portrait": "true",
            "tile": "512",
            "isolated-ratio": "0.1",
            "isolated-gap": "40",
            "isolated-halo": "48",
            "no-isolated": "true",
            "no-fill-holes": "true",
            "hole-min-area": "300",
            "hole-max-area": "80000",
            "hole-top-fraction": "0.25",
            "no-hair-refine": "true",
            "hair-top-fraction": "0.3",
            "hair-min-mid": "30000",
            "hair-gain": "2.4",
            "no-color-gaps": "true",
            "color-gap-lo": "30",
            "color-gap-hi": "90",
            "color-gap-top-fraction": "0.4",
            "color-gap-min-blue": "20",
            "stabilize-min-comps": "10",
            "global-feather": "1.5",
        })

        self.assertIs(params["portrait"], False)
        self.assertEqual(params["tile"], 512)
        self.assertEqual(params["isolated_ratio"], 0.1)
        self.assertEqual(params["isolated_gap"], 40)
        self.assertEqual(params["isolated_halo"], 48)
        self.assertIs(params["isolated"], False)
        self.assertIs(params["fill_holes"], False)
        self.assertEqual(params["hole_min_area"], 300)
        self.assertEqual(params["hole_max_area"], 80000)
        self.assertEqual(params["hole_top_fraction"], 0.25)
        self.assertIs(params["hair_refine"], False)
        self.assertEqual(params["hair_top_fraction"], 0.3)
        self.assertEqual(params["hair_min_mid"], 30000)
        self.assertEqual(params["hair_gain"], 2.4)
        self.assertIs(params["color_gaps"], False)
        self.assertEqual(params["color_gap_lo"], 30.0)
        self.assertEqual(params["color_gap_hi"], 90.0)
        self.assertEqual(params["color_gap_top_fraction"], 0.4)
        self.assertEqual(params["color_gap_min_blue"], 20.0)
        self.assertEqual(params["stabilize_min_comps"], 10)
        self.assertEqual(params["global_feather"], 1.5)
        self.assertEqual(params["overlap"], CUT_DEFAULTS["overlap"])


if __name__ == "__main__":
    unittest.main()
