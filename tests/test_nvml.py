import subprocess
import unittest
from unittest import mock

from adascope.adapters.nvml import Nvml
from tests import support
from tests.support import NO_GPU_REASON, gpu_available


def nvidia_smi(field: str) -> float:
    out = subprocess.run(
        ["nvidia-smi", f"--query-gpu={field}", "--format=csv,noheader,nounits"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip().splitlines()
    return float(out[0])


class GpuProbeTest(unittest.TestCase):
    """The guard itself, on no hardware.

    A probe that answers "no GPU" for every exception turns a broken adapter
    into three skipped tests, so the adapter's own coverage disappears without
    a word. Only a missing library or an NVML refusal may do that.
    """

    def setUp(self):
        saved = support._gpu
        support._gpu = None
        self.addCleanup(setattr, support, "_gpu", saved)

    def test_a_missing_library_is_no_gpu(self):
        with mock.patch.object(Nvml, "sample", side_effect=OSError("no libnvidia-ml.so.1")):
            self.assertFalse(gpu_available())

    def test_an_nvml_refusal_is_no_gpu(self):
        with mock.patch.object(Nvml, "sample", side_effect=RuntimeError("NVML call failed")):
            self.assertFalse(gpu_available())

    def test_a_broken_adapter_is_not_reported_as_no_gpu(self):
        with mock.patch.object(Nvml, "sample", side_effect=AttributeError("broken binding")):
            with self.assertRaises(AttributeError):
                gpu_available()


@unittest.skipUnless(gpu_available(), NO_GPU_REASON)
class NvmlTest(unittest.TestCase):
    def test_discover_matches_this_card(self):
        hw = Nvml.discover()
        self.assertIn("4090", hw.name)
        vram_mib = nvidia_smi("memory.total")
        self.assertAlmostEqual(hw.vram_total_bytes, vram_mib * 1024 * 1024, delta=0.01 * vram_mib * 1024 * 1024)
        self.assertEqual(hw.clock_sm_max_mhz, nvidia_smi("clocks.max.sm"))
        self.assertEqual(hw.arch, "sm_89")
        self.assertEqual(hw.compute_capability, "8.9")

    def test_sample_returns_expected_keys(self):
        s = Nvml.sample()
        for key in (
            "power_draw_w",
            "temp_c",
            "util_gpu_pct",
            "clock_sm_mhz",
            "throttle.sw_power_cap",
            "throttle.sw_thermal_slowdown",
            "throttle.hw_thermal_slowdown",
        ):
            self.assertIn(key, s)
        self.assertIsInstance(s["throttle.sw_power_cap"], bool)

    def test_power_limit_cross_checked_against_nvidia_smi(self):
        s = Nvml.sample()
        self.assertAlmostEqual(float(s["power_limit_w"]), nvidia_smi("power.limit"), delta=1.0)

    def test_processes_reports_pid_memory_and_name(self):
        procs = Nvml.processes()
        self.assertIsInstance(procs, list)
        for proc in procs:
            self.assertGreater(proc["pid"], 0)
            self.assertGreaterEqual(proc["used_gpu_memory_bytes"], 0)
            self.assertIsInstance(proc["process_name"], str)
        # The enumerator and nvidia-smi must name the same processes, the
        # same cross-check the adapter already applies to power.
        smi_pids = subprocess.run(
            ["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader"],
            capture_output=True, text=True, check=True,
        ).stdout.split()
        self.assertEqual({str(p["pid"]) for p in procs}, set(smi_pids))
        # The enumerator and the CLI must name the same processes, and the
        # run must say which one produced the list.
        self.assertIn(Nvml.processes_method(), ("nvml", "nvidia-smi"))


if __name__ == "__main__":
    unittest.main()
