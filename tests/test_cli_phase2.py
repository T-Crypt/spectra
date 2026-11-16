import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from adascope.cli import build_parser, main
from tests.fixtures import recorded_run as fixtures


class Phase2CliTest(unittest.TestCase):
    def test_parser_has_new_commands(self):
        for cmd in ("runs", "findings"):
            args = build_parser().parse_args([cmd])
            self.assertEqual(args.command, cmd)
        args = build_parser().parse_args(["compare", "a.json", "b.json"])
        self.assertEqual(args.command, "compare")
        args = build_parser().parse_args(["experiment", "show", "x"])
        self.assertEqual(args.command, "experiment")

    def test_runs_lists(self):
        with tempfile.TemporaryDirectory() as tmp:
            from adascope.store import save_run
            save_run(fixtures.recorded_run(), tmp)
            rc = main(["runs", "--root", tmp])
            self.assertEqual(rc, 0)

    def test_compare_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            from adascope.store import save_run
            p1 = save_run(fixtures.recorded_run(), tmp)
            p2 = save_run(fixtures.recorded_run(), tmp + "/b")
            Path(tmp + "/b").mkdir(exist_ok=True)
            p2 = save_run(fixtures.recorded_run(), tmp + "/b")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = main(["compare", str(p1), str(p2)])
            self.assertEqual(rc, 0)
            data = json.loads(buf.getvalue())
            self.assertIn("verdict", data)

    def test_experiment_plan_show(self):
        with tempfile.TemporaryDirectory() as tmp:
            from adascope.store import save_run
            baseline = fixtures.recorded_run()
            baseline.workload.config = {"power_limit_w": 450}
            p = save_run(baseline, tmp)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = main(["experiment", "plan", "--baseline", str(p),
                           "--hypothesis", "h-x", "--variable", "power_limit_w",
                           "--treatment", "250", "--out", tmp + "/exp"])
            self.assertEqual(rc, 0)
            # show
            exp_id = list(Path(tmp + "/exp").glob("*.experiment.json"))[0].stem
            rc2 = main(["experiment", "show", exp_id, "--root", tmp + "/exp"])
            self.assertEqual(rc2, 0)
