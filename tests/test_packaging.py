"""The installed package must be able to find its own data files.

``pip install .`` ships only what setuptools puts in the wheel, and the
installed ``spectra report`` loads both the architecture profile
(``reference.default_profile_path``) and the rule set
(``engine.default_rules_path``) at run time. If either is left out of the
wheel, the README quick start dies on a FileNotFoundError the moment the
code stops running from a checkout, so this test rebuilds the wheel and
checks both paths are in its file list.

The build runs against a copy of the checkout in a temp dir, so a stale
in-tree ``build/`` directory (setuptools does not clean it) cannot leak
old files into the wheel under test.
"""

import importlib.util
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# The two data files the installed package loads at run time.
REQUIRED_DATA_FILES = (
    "adascope/profiles/sm89.json",
    "adascope/rules/sm89.json",
)

# Things that must not be copied into the build sandbox.
_BUILD_ARTIFACTS = ("build", "*.egg-info", "__pycache__", ".git", ".venv", "runs")


def _wheel_file_list() -> list[str]:
    """Build the wheel from a clean copy of the checkout; return its file list."""
    with tempfile.TemporaryDirectory(prefix="spectra-wheel-") as tmp:
        source = Path(tmp) / "source"
        outdir = Path(tmp) / "dist"
        shutil.copytree(
            REPO_ROOT,
            source,
            ignore=shutil.ignore_patterns(*_BUILD_ARTIFACTS),
        )
        command = [
            sys.executable,
            "-m", "build",
            "--wheel", "--no-isolation",
            "--outdir", str(outdir),
            str(source),
        ]
        result = subprocess.run(command, cwd=source, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            raise AssertionError(
                "wheel build failed:\n" + result.stdout[-2000:] + result.stderr[-2000:]
            )
        wheels = sorted(outdir.glob("*.whl"))
        if len(wheels) != 1:
            raise AssertionError(f"expected exactly one wheel in {outdir!s}, found {wheels}")
        with zipfile.ZipFile(wheels[0]) as wheel:
            return wheel.namelist()


class WheelDataFilesTest(unittest.TestCase):
    def test_wheel_ships_profile_and_rules(self):
        # `python -m build --no-isolation` needs the frontend and the
        # backend both importable in this interpreter.
        for tool in ("build", "setuptools"):
            if importlib.util.find_spec(tool) is None:
                self.skipTest(f"{tool} is not installed; cannot build the wheel")
        names = _wheel_file_list()
        missing = [path for path in REQUIRED_DATA_FILES if path not in names]
        self.assertEqual(
            missing,
            [],
            "wheel is missing data files the installed package loads: "
            f"{missing}; full file list: {sorted(names)}",
        )


if __name__ == "__main__":
    unittest.main()
