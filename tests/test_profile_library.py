import tempfile
import unittest

from adascope.model import Finding, FindingVerdict
from adascope.profile_library import best_profile, load_profiles, save_profile


class ProfileLibraryTest(unittest.TestCase):
    def test_save_and_load_profile(self):
        with tempfile.TemporaryDirectory() as d:
            f = Finding(id="f1", hypothesis_id="h1", verdict=FindingVerdict.CONFIRMED,
                        arch="sm_89", engine_id="ninfer", workload_class="dense-decode",
                        variable="power_limit_w", direction="maximize",
                        delta={"relative": 0.1})
            save_profile(f, d)
            profiles = load_profiles(d)
            self.assertEqual(len(profiles), 1)
            best = best_profile(d, "sm_89", "ninfer", "dense-decode",
                                "power_limit_w", "maximize")
            self.assertIsNotNone(best)
