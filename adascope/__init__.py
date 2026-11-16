"""Spectra: architecture-aware GPU performance diagnosis."""

try:
    from importlib.metadata import version as _version

    __version__ = _version("spectra")
except Exception:  # pragma: no cover - package not installed
    __version__ = "0.1.0"
