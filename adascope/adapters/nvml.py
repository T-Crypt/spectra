"""NVML hardware and telemetry adapter.

This module is one of the two places that touch foreign formats. It parses
NVML values into domain units (watts, MHz, bytes, named throttle booleans)
here. Everything downstream trusts the types.
"""

from __future__ import annotations

import ctypes
from ctypes import byref, c_int, c_uint, c_ulonglong, create_string_buffer

from ..model import HardwareProfile

NVML_CLOCK_SM = 1
NVML_CLOCK_MEM = 2
NVML_TEMP_GPU = 0

THROTTLE_REASONS = {
    0x1: "gpu_idle",
    0x2: "applications_clocks_setting",
    0x4: "sw_power_cap",
    0x8: "hw_slowdown",
    0x10: "sync_boost",
    0x20: "sw_thermal_slowdown",
    0x40: "hw_thermal_slowdown",
    0x80: "hw_power_brake_slowdown",
    0x100: "display_clock_setting",
}


class _Utilization(ctypes.Structure):
    _fields_ = [("gpu", c_uint), ("memory", c_uint)]


class _Memory(ctypes.Structure):
    _fields_ = [("total", c_ulonglong), ("free", c_ulonglong), ("used", c_ulonglong)]


def _check(rc: int, call: str) -> None:
    if rc != 0:
        raise RuntimeError(f"NVML call {call} failed with code {rc}")


_lib = None


def _load():
    """Load the library and call nvmlInit_v2 once per process.

    A sampling loop ticks at 1 to 10 Hz; re-initialising NVML per tick is
    wasted work. Callers that want to release the library call
    ``Nvml.shutdown()``.
    """
    global _lib
    if _lib is None:
        lib = ctypes.CDLL("libnvidia-ml.so.1")
        _check(lib.nvmlInit_v2(), "nvmlInit_v2")
        _lib = lib
    return _lib


def _handle(lib, device_index: int):
    handle = ctypes.c_void_p()
    _check(lib.nvmlDeviceGetHandleByIndex_v2(device_index, byref(handle)), "nvmlDeviceGetHandleByIndex_v2")
    return handle


def _decode_throttle(reasons: int) -> dict[str, bool]:
    return {f"throttle.{name}": bool(reasons & bit) for bit, name in THROTTLE_REASONS.items()}


class Nvml:
    """Hardware discovery and telemetry sampling through NVML."""

    @staticmethod
    def discover(device_index: int = 0) -> HardwareProfile:
        lib = _load()
        dev = _handle(lib, device_index)
        name_buf = create_string_buffer(96)
        _check(lib.nvmlDeviceGetName(dev, name_buf, 96), "nvmlDeviceGetName")
        name = name_buf.value.decode()

        mem = _Memory()
        _check(lib.nvmlDeviceGetMemoryInfo(dev, byref(mem)), "nvmlDeviceGetMemoryInfo")

        limit, default, low, high = c_uint(), c_uint(), c_uint(), c_uint()
        lib.nvmlDeviceGetPowerManagementLimit.restype = c_int
        lib.nvmlDeviceGetPowerManagementDefaultLimit.restype = c_int
        lib.nvmlDeviceGetPowerManagementLimitConstraints.restype = c_int
        _check(lib.nvmlDeviceGetPowerManagementLimit(dev, byref(limit)), "nvmlDeviceGetPowerManagementLimit")
        _check(lib.nvmlDeviceGetPowerManagementDefaultLimit(dev, byref(default)), "nvmlDeviceGetPowerManagementDefaultLimit")
        _check(
            lib.nvmlDeviceGetPowerManagementLimitConstraints(dev, byref(low), byref(high)),
            "nvmlDeviceGetPowerManagementLimitConstraints",
        )

        sm_max, mem_max = c_uint(), c_uint()
        lib.nvmlDeviceGetMaxClockInfo.restype = c_int
        _check(lib.nvmlDeviceGetMaxClockInfo(dev, NVML_CLOCK_SM, byref(sm_max)), "nvmlDeviceGetMaxClockInfo(SM)")
        _check(lib.nvmlDeviceGetMaxClockInfo(dev, NVML_CLOCK_MEM, byref(mem_max)), "nvmlDeviceGetMaxClockInfo(MEM)")

        major, minor = c_int(), c_int()
        _check(lib.nvmlDeviceGetCudaComputeCapability(dev, byref(major), byref(minor)), "nvmlDeviceGetCudaComputeCapability")

        drv_buf = create_string_buffer(80)
        _check(lib.nvmlSystemGetDriverVersion(drv_buf, 80), "nvmlSystemGetDriverVersion")
        cuda_v = c_int()
        lib.nvmlSystemGetCudaDriverVersion.restype = c_int
        _check(lib.nvmlSystemGetCudaDriverVersion(byref(cuda_v)), "nvmlSystemGetCudaDriverVersion")
        return HardwareProfile(
            name=name,
            arch=f"sm_{major.value}{minor.value}",
            compute_capability=f"{major.value}.{minor.value}",
            vram_total_bytes=mem.total,
            power_limit_w=limit.value / 1000.0,
            power_default_w=default.value / 1000.0,
            power_max_w=high.value / 1000.0,
            clock_sm_max_mhz=sm_max.value,
            clock_mem_max_mhz=mem_max.value,
            driver_version=drv_buf.value.decode(),
            cuda_driver_version=f"{cuda_v.value // 1000}.{(cuda_v.value % 1000) // 10}",
            mem_bandwidth_measured_gbps=None,
        )

    @staticmethod
    def sample(device_index: int = 0) -> dict[str, float | int | bool]:
        lib = _load()
        dev = _handle(lib, device_index)
        power, limit, temp = c_uint(), c_uint(), c_uint()
        lib.nvmlDeviceGetPowerUsage.restype = c_int
        _check(lib.nvmlDeviceGetPowerUsage(dev, byref(power)), "nvmlDeviceGetPowerUsage")
        lib.nvmlDeviceGetPowerManagementLimit.restype = c_int
        _check(lib.nvmlDeviceGetPowerManagementLimit(dev, byref(limit)), "nvmlDeviceGetPowerManagementLimit")
        _check(lib.nvmlDeviceGetTemperature(dev, NVML_TEMP_GPU, byref(temp)), "nvmlDeviceGetTemperature")

        util = _Utilization()
        lib.nvmlDeviceGetUtilizationRates.restype = c_int
        _check(lib.nvmlDeviceGetUtilizationRates(dev, byref(util)), "nvmlDeviceGetUtilizationRates")

        sm_clk, mem_clk = c_uint(), c_uint()
        lib.nvmlDeviceGetClockInfo.restype = c_int
        _check(lib.nvmlDeviceGetClockInfo(dev, NVML_CLOCK_SM, byref(sm_clk)), "nvmlDeviceGetClockInfo(SM)")
        _check(lib.nvmlDeviceGetClockInfo(dev, NVML_CLOCK_MEM, byref(mem_clk)), "nvmlDeviceGetClockInfo(MEM)")

        mem = _Memory()
        _check(lib.nvmlDeviceGetMemoryInfo(dev, byref(mem)), "nvmlDeviceGetMemoryInfo")

        reasons = c_ulonglong()
        lib.nvmlDeviceGetCurrentClocksThrottleReasons.restype = c_int
        _check(lib.nvmlDeviceGetCurrentClocksThrottleReasons(dev, byref(reasons)), "nvmlDeviceGetCurrentClocksThrottleReasons")

        out: dict[str, float | int | bool] = {
            "power_draw_w": power.value / 1000.0,
            "power_limit_w": limit.value / 1000.0,
            "temp_c": temp.value,
            "util_gpu_pct": util.gpu,
            "util_mem_pct": util.memory,
            "clock_sm_mhz": sm_clk.value,
            "clock_mem_mhz": mem_clk.value,
            "mem_used_bytes": mem.used,
            "mem_free_bytes": mem.free,
            "mem_total_bytes": mem.total,
            "throttle_reasons": reasons.value,
        }
        out.update(_decode_throttle(reasons.value))
        return out

    @staticmethod
    def shutdown() -> None:
        """Release NVML for this process. The next call re-initialises it."""
        global _lib
        if _lib is not None:
            _lib.nvmlShutdown()
            _lib = None
