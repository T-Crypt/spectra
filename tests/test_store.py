import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from adascope.cli import main
from adascope.model import HardwareProfile, Run, Workload, to_dict
from adascope.store import list_runs, load_run, save_run


def make_run(run_id="store-test-1"):
    hw = HardwareProfile(name="NVIDIA RTX 4090", arch="sm_89", compute_capability="8.9",
                         vram_total_bytes=24564 * 1024 * 1024)
    wl = Workload(adapter_id="lmcompat", engine_id="ninfer", model_id="test-model")
    return Run(id=run_id, started_at="2026-10-13T00:00:00Z", ended_at="2026-10-13T00:00:30Z",
               hardware=hw, workload=wl)


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def test_save_then_load_equals_original(self):
        run = make_run()
        path = save_run(run, self.dir)
        self.assertTrue(path.exists())
        loaded = load_run(path)
        self.assertEqual(loaded, run)

    def test_save_twice_one_file_identical_bytes(self):
        run = make_run()
        p1 = save_run(run, self.dir)
        p2 = save_run(run, self.dir)
        self.assertEqual(p1, p2)
        runs = list_runs(self.dir)
        self.assertEqual(len(runs), 1)
        self.assertEqual(p1.read_bytes(), p2.read_bytes())

    def test_list_runs_ignores_tmp(self):
        run = make_run()
        save_run(run, self.dir)
        (Path(self.dir) / "junk.json.tmp").write_text("partial")
        runs = list_runs(self.dir)
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0].name, f"{run.id}.json")


class StoreReadPathTest(unittest.TestCase):
    """The store's read path rejects a wrong field shape as a domain error.

    Each payload below used to escape the reader as a generated ``TypeError``
    or ``AttributeError`` and end the report command with a Python traceback.
    The contract asserted here is the one C3.5 states: one line naming the
    offending field on stderr, and exit 2.
    """

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.base = to_dict(make_run())

    def _report(self, payload) -> tuple[int, str]:
        path = self.dir / "bad.json"
        path.write_text(json.dumps(payload))
        error = io.StringIO()
        with contextlib.redirect_stderr(error):
            rc = main(["report", str(path)])
        return rc, error.getvalue()

    def test_wrong_shapes_exit_two_with_a_domain_error(self):
        good_series = {"metric": "power_draw_w", "unit": "W", "source": "nvml",
                       "quality": "measured", "samples": [[0.0, 320.5], [0.5, 335.0]]}
        cases = {
            "samples-not-pairs": {"series": [dict(good_series, samples=[1.0, 2.0])]},
            "hardware-null": {"hardware": None},
            "hardware-list": {"hardware": [self.base["hardware"]]},
            "series-dict": {"series": {"a": 1}},
        }
        for name, patch in cases.items():
            with self.subTest(case=name):
                payload = dict(self.base)
                payload.update(patch)
                rc, stderr = self._report(payload)
                self.assertEqual(rc, 2, stderr)
                self.assertIn("report: ", stderr)
                self.assertNotIn("Traceback", stderr)
                self.assertTrue(
                    any(field in stderr for field in ("samples", "hardware", "series")), stderr
                )

    def test_a_stored_object_is_required(self):
        path = self.dir / "list.json"
        path.write_text("[1, 2]")
        error = io.StringIO()
        with contextlib.redirect_stderr(error):
            rc = main(["report", str(path)])
        self.assertEqual(rc, 2)
        self.assertIn("expects a JSON object", error.getvalue())


if __name__ == "__main__":
    unittest.main()
