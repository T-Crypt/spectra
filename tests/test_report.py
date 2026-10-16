"""Report contract: pure, label-complete, and pinned by a golden file.

Regenerating the golden file needs the committed fixture run, so the two move
together:

    python -c "from tests.fixtures.recorded_run import recorded_run; \
from adascope.store import save_run; print(save_run(recorded_run(), 'tests/fixtures'))"
    python -m adascope report tests/fixtures/fixture-recorded.json > tests/fixtures/report.golden.txt

A wording change needs the golden update in the same commit; test_golden_file
also asserts that the committed JSON still equals the Python fixture.
"""

import contextlib
import io
import re
import unittest
from dataclasses import replace
from pathlib import Path

from adascope.cli import main
from adascope.engine import default_rules_path, load_rules
from adascope.reference import load_profile
from adascope.report import render
from adascope.store import load_run
from tests.fixtures import recorded_run as fixtures

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE_RUN = FIXTURES / "fixture-recorded.json"
GOLDEN = FIXTURES / "report.golden.txt"
LABEL = re.compile(r"\((measured|derived|hypothesis|unavailable)\)\s*$")


def rules():
    return load_rules(default_rules_path())


def profile():
    return load_profile()


def unlabeled_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.strip() and not LABEL.search(line)]


class ReportTest(unittest.TestCase):
    def test_render_is_byte_identical(self):
        run = fixtures.treatment_run()
        first = render(run, profile(), rules())
        self.assertEqual(first, render(run, profile(), rules()))
        self.assertEqual(first, render(fixtures.treatment_run(), profile(), rules()))

    def test_render_carries_ceiling_hypotheses_and_alternatives(self):
        text = render(fixtures.treatment_run(), profile(), rules())
        self.assertIn("reference ceiling", text)
        self.assertIn("55.4 tok/s", text)
        self.assertIn("sm89.power-cap-limit", text)
        self.assertIn("(measured)", text)
        self.assertIn("(derived)", text)
        self.assertIn("Basis: power_draw_mean_w 441.0 W (measured)", text)
        self.assertIn("Alternatives: sm89.thermal-throttle (hypothesis)", text)

    def test_no_number_is_printed_without_a_label(self):
        for run in (fixtures.recorded_run(), fixtures.treatment_run(), fixtures.inconsistent_run()):
            text = render(run, profile(), rules())
            self.assertEqual(unlabeled_lines(text), [], text)

        # A7: what the run lacks is reported unavailable, never estimated.
        run = fixtures.recorded_run()
        hardware_only = replace(
            run,
            series=[s for s in run.series if s.source == "nvml"],
            sources=["nvml"],
            workload=replace(run.workload, artifact_bytes=None),
        )
        text = render(hardware_only, profile(), rules())
        self.assertIn("Unavailable:", text)
        self.assertNotIn("tok/s", text)
        self.assertEqual(unlabeled_lines(text), [], text)

    def test_roof_hypothesis_prints_a_basis_line(self):
        """A fired hypothesis always shows the evidence it claims."""
        text = render(fixtures.roof_run(), profile(), rules())
        self.assertIn("sm89.decode-near-bandwidth-roof", text)
        self.assertIn("Basis: decode_rate_tok_s 52.6 tok/s (derived)", text)
        self.assertEqual(unlabeled_lines(text), [], text)

    def test_one_sample_counters_print_no_rate(self):
        """A3: a counter series with no delta is unavailable, never 0.0.

        The rate and the ratio that needs it both disappear from the Derived
        block; the run cannot support either number.
        """
        text = render(fixtures.one_sample_run(), profile(), rules())
        self.assertIn("Unavailable: decode_rate_tok_s", text)
        self.assertIn("Unavailable: objective_ratio", text)
        self.assertNotIn(" 0.0 tok/s", text)
        self.assertEqual(unlabeled_lines(text), [], text)

    def test_a_rule_with_an_unresolvable_evidence_id_says_so(self):
        """A one-character typo in the rule data must not render as silence.

        The analyser keeps only the evidence ids that resolve, so before this
        the hypothesis printed with no Basis line and no hint of why. The report
        now names the rule and the id that resolves to nothing.
        """
        mutated = [dict(rule) for rule in rules()]
        for rule in mutated:
            if rule["id"] == "sm89.decode-near-bandwidth-roof":
                rule["evidence_observations"] = ["decode_rate_tok_s_typo"]
        text = render(fixtures.roof_run(), profile(), mutated)
        self.assertIn("sm89.decode-near-bandwidth-roof", text)
        self.assertIn("Warn: sm89.decode-near-bandwidth-roof declares evidence "
                      "'decode_rate_tok_s_typo'", text)
        self.assertNotIn("Basis: decode_rate_tok_s", text)
        self.assertEqual(unlabeled_lines(text), [], text)

    def test_golden_file_matches(self):
        self.assertEqual(load_run(FIXTURE_RUN), fixtures.recorded_run())
        self.assertEqual(render(load_run(FIXTURE_RUN), profile(), rules()), GOLDEN.read_text(encoding="utf-8"))


class ReportCliTest(unittest.TestCase):
    """Acceptance A1 through the documented command, not just ``render``.

    Every other report test calls ``render`` directly, so the ``report``
    subcommand itself -- argument parsing, default profile and rule paths, the
    print, the exit status -- had no success-path coverage. The README's second
    quick-start line and acceptance test 1 are both about this command.
    """

    def _report(self, path: Path) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = main(["report", str(path)])
        return rc, out.getvalue()

    def test_report_command_is_reproducible_from_the_stored_file(self):
        first_rc, first = self._report(FIXTURE_RUN)
        self.assertEqual(first_rc, 0)
        second_rc, second = self._report(FIXTURE_RUN)
        self.assertEqual(second_rc, 0)
        self.assertEqual(first, second)
        self.assertEqual(first, GOLDEN.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
