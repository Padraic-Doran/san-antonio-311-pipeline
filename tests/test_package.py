"""Basic package-level smoke tests."""

from san_antonio_311 import __version__


def test_package_version() -> None:
    # A successful import confirms the src-layout package is installed correctly.
    assert __version__ == "0.1.0"
