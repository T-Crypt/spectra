"""The load driver, kept where the eval imports it from.

The implementation moved into the package, ``adascope/bench.py``, when it
became a first-party feature (``spectra bench``). This module re-exports the
two functions the eval and the live fidelity check call, so there is one
producer of the drive loop instead of two.

The driver cannot switch thinking off: the live launch sets
``--default-thinking-budget 4096``, so a "short" completion may still run for
a while. Callers must therefore check that the counters moved inside the
window rather than assume the load materialised, and record inconclusive
when they did not.
"""

from adascope.bench import drive_decode, stream_completion  # noqa: F401
