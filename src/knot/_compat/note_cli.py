"""Compatibility module for :mod:`knot.interfaces.note_cli`."""

import sys

from knot.interfaces import note_cli as _implementation

if __name__ == '__main__':
    _implementation.main()
else:
    sys.modules[__name__] = _implementation
