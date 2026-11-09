"""Compatibility module for :mod:`knot.interfaces.access`."""

import sys

from knot.interfaces import access as _implementation

sys.modules[__name__] = _implementation
