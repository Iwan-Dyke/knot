"""Compatibility module for :mod:`knot.curating.rules`."""

import sys

from knot.curating import rules as _implementation

sys.modules[__name__] = _implementation
