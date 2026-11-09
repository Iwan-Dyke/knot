"""Compatibility module for :mod:`knot.interfaces.mcp_server`."""

import sys

from knot.interfaces import mcp_server as _implementation

if __name__ == '__main__':
    _implementation.main()
else:
    sys.modules[__name__] = _implementation
