"""Sanity check: package imports cleanly and exposes a version string."""

import dng_preflight


def test_package_exposes_version():
    assert isinstance(dng_preflight.__version__, str)
    assert dng_preflight.__version__
