"""Compatibility module for :mod:`knot.interfaces.mcp_authoring`."""

import sys

from knot.interfaces import mcp_authoring as _implementation

sys.modules[__name__] = _implementation
