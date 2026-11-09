"""Compatibility module for :mod:`knot.curating.entity_labels`."""

import sys

from knot.curating import entity_labels as _implementation

sys.modules[__name__] = _implementation
