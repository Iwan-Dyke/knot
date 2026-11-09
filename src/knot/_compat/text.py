"""Compatibility module for :mod:`knot.shared.text`."""

import sys

from knot.shared import text as _implementation

sys.modules[__name__] = _implementation
