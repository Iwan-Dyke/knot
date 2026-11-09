"""Compatibility module for :mod:`knot.writing.sync`."""

import sys

from knot.writing import sync as _implementation

sys.modules[__name__] = _implementation
