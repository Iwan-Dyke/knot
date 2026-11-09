import importlib.util
import unittest
from unittest.mock import patch


@unittest.skipUnless(importlib.util.find_spec('mcp'), 'MCP SDK is not installed')
class MCPEnvironmentTests(unittest.TestCase):
    def test_blocked_wakeup_socket_reports_actionable_error(self):
        from knot.mcp_server import check_asyncio_support

        with patch('socket.socketpair', side_effect=PermissionError('Denied')):
            with self.assertRaisesRegex(RuntimeError, 'outside the restrictive sandbox'):
                check_asyncio_support()
